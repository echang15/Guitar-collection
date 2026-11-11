import base64
import csv
import io
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from . import config, db, images

BASE_DIR = Path(__file__).parent

SORTS = {
    "brand": "g.brand COLLATE NOCASE, g.model COLLATE NOCASE",
    "year": "g.year IS NULL, g.year, g.brand COLLATE NOCASE",
    "year_desc": "g.year IS NULL, g.year DESC, g.brand COLLATE NOCASE",
    "newest": "g.created_at DESC, g.id DESC",
    "value": "g.estimated_value IS NULL, g.estimated_value DESC",
}
SEARCH_COLUMNS = ["brand", "model", "serial_number", "finish", "notes",
                  "country", "body_style", "pickups", "storage_location"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Guitar Collection", lifespan=lifespan)
config.ensure_dirs()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/photos", StaticFiles(directory=config.PHOTO_DIR), name="photos")
app.mount("/thumbs", StaticFiles(directory=config.THUMB_DIR), name="thumbs")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals.update(FIELDS=db.FIELDS, CHOICES=db.CHOICES,
                             FIELD_MAP={n: (label, kind) for n, label, kind in db.FIELDS},
                             thumb_name=images.thumb_name,
                             SCREENSAVER_IDLE_SECONDS=config.SCREENSAVER_IDLE_SECONDS)


def money(value):
    return "" if value is None else f"${value:,.0f}" if value == int(value) else f"${value:,.2f}"


templates.env.filters["money"] = money


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    if not config.APP_PASSWORD or request.url.path == "/healthz":
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
        except Exception:
            user, pw = "", ""
        if (secrets.compare_digest(user, config.APP_USERNAME)
                and secrets.compare_digest(pw, config.APP_PASSWORD)):
            return await call_next(request)
    return PlainTextResponse("Authentication required", status_code=401,
                             headers={"WWW-Authenticate": 'Basic realm="Guitars"'})


# --- helpers ---------------------------------------------------------------

def parse_guitar_form(form) -> tuple[dict, list[str]]:
    values, errors = {}, []
    for name, label, _ in db.FIELDS:
        raw = (form.get(name) or "").strip()
        if name in db.INT_FIELDS:
            if raw:
                try:
                    values[name] = int(raw)
                except ValueError:
                    errors.append(f"{label} must be a whole number")
                    values[name] = raw
            else:
                values[name] = None
        elif name in db.MONEY_FIELDS:
            cleaned = raw.replace("$", "").replace(",", "")
            if cleaned:
                try:
                    values[name] = float(cleaned)
                except ValueError:
                    errors.append(f"{label} must be a number")
                    values[name] = raw
            else:
                values[name] = None
        else:
            values[name] = raw or None

    if not values["brand"]:
        errors.append("Brand is required")
    if not values["model"]:
        errors.append("Model is required")
    if values["status"] not in db.CHOICES["status"]:
        values["status"] = "current"
    if values["status"] == "archived" and not values["archived_date"]:
        values["archived_date"] = date.today().isoformat()
    return values, errors


def get_guitar(conn, guitar_id: int):
    guitar = conn.execute("SELECT * FROM guitars WHERE id = ?", (guitar_id,)).fetchone()
    if guitar is None:
        raise HTTPException(404, "Guitar not found")
    return guitar


def get_photos(conn, guitar_id: int):
    return conn.execute(
        "SELECT * FROM photos WHERE guitar_id = ? ORDER BY is_primary DESC, sort_order, id",
        (guitar_id,)).fetchall()


async def save_photos(conn, guitar_id: int, uploads: list) -> list[str]:
    errors = []
    has_primary = conn.execute(
        "SELECT 1 FROM photos WHERE guitar_id = ? AND is_primary = 1", (guitar_id,)).fetchone()
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM photos WHERE guitar_id = ?",
        (guitar_id,)).fetchone()[0]
    for upload in uploads:
        if not isinstance(upload, UploadFile) or not upload.filename:
            continue
        data = await upload.read()
        try:
            filename = images.save_upload(data)
        except images.InvalidImage as exc:
            errors.append(f"{upload.filename}: {exc}")
            continue
        conn.execute(
            "INSERT INTO photos (guitar_id, filename, original_name, is_primary, sort_order)"
            " VALUES (?, ?, ?, ?, ?)",
            (guitar_id, filename, upload.filename, 0 if has_primary else 1, next_order))
        has_primary = True
        next_order += 1
    return errors


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# --- pages -----------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index(request: Request, q: str = "", status: str = "current", type: str = "",
          brand: str = "", sort: str = "brand", view: str = "grid"):
    where, params = [], []
    if status in ("current", "archived"):
        where.append("g.status = ?")
        params.append(status)
    if type:
        where.append("g.guitar_type = ?")
        params.append(type)
    if brand:
        where.append("g.brand = ? COLLATE NOCASE")
        params.append(brand)
    for term in q.split():
        where.append("(" + " OR ".join(f"g.{c} LIKE ?" for c in SEARCH_COLUMNS) + ")")
        params.extend([f"%{term}%"] * len(SEARCH_COLUMNS))
    sql = ("SELECT g.*, (SELECT filename FROM photos p WHERE p.guitar_id = g.id"
           " ORDER BY is_primary DESC, sort_order, id LIMIT 1) AS photo,"
           " (SELECT COUNT(*) FROM photos p WHERE p.guitar_id = g.id) AS photo_count"
           " FROM guitars g")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + SORTS.get(sort, SORTS["brand"])

    with db.get_conn() as conn:
        guitars = conn.execute(sql, params).fetchall()
        stats = conn.execute(
            "SELECT SUM(status = 'current') AS current, SUM(status = 'archived') AS archived,"
            " SUM(CASE WHEN status = 'current' THEN estimated_value END) AS value,"
            " SUM(CASE WHEN status = 'current' THEN purchase_price END) AS cost"
            " FROM guitars").fetchone()
        brands = [r[0] for r in conn.execute(
            "SELECT DISTINCT brand FROM guitars WHERE brand IS NOT NULL"
            " ORDER BY brand COLLATE NOCASE")]

    return templates.TemplateResponse(request, "index.html", {
        "guitars": guitars, "stats": stats, "brands": brands,
        "filters": {"q": q, "status": status, "type": type, "brand": brand,
                    "sort": sort, "view": "table" if view == "table" else "grid"},
    })


def form_page(request: Request, guitar: dict, errors=(), guitar_id=None, status_code=200):
    with db.get_conn() as conn:
        suggestions = {
            col: [r[0] for r in conn.execute(
                f"SELECT DISTINCT {col} FROM guitars WHERE {col} IS NOT NULL"
                f" ORDER BY {col} COLLATE NOCASE")]
            for col in ("brand", "finish", "body_style", "country", "body_wood",
                        "top_wood", "neck_wood", "fretboard_wood", "case_type",
                        "storage_location", "purchased_from")
        }
    return templates.TemplateResponse(request, "form.html", {
        "guitar": guitar, "errors": errors, "guitar_id": guitar_id,
        "suggestions": suggestions,
    }, status_code=status_code)


@app.get("/guitars/new")
def new_guitar(request: Request):
    return form_page(request, {"status": "current", "num_strings": 6,
                               "handedness": "Right", "guitar_type": "Electric"})


@app.post("/guitars")
async def create_guitar(request: Request):
    form = await request.form()
    values, errors = parse_guitar_form(form)
    if errors:
        return form_page(request, values, errors, status_code=400)
    cols = ", ".join(db.FIELD_NAMES)
    marks = ", ".join("?" for _ in db.FIELD_NAMES)
    with db.get_conn() as conn:
        cur = conn.execute(f"INSERT INTO guitars ({cols}) VALUES ({marks})",
                           [values[n] for n in db.FIELD_NAMES])
        guitar_id = cur.lastrowid
        photo_errors = await save_photos(conn, guitar_id, form.getlist("photos"))
    return redirect(f"/guitars/{guitar_id}" + ("?photo_error=1" if photo_errors else ""))


@app.get("/guitars/{guitar_id}")
def show_guitar(request: Request, guitar_id: int, photo_error: str = ""):
    with db.get_conn() as conn:
        guitar = get_guitar(conn, guitar_id)
        photos = get_photos(conn, guitar_id)
    return templates.TemplateResponse(request, "detail.html", {
        "guitar": guitar, "photos": photos, "photo_error": bool(photo_error),
    })


@app.get("/guitars/{guitar_id}/edit")
def edit_guitar(request: Request, guitar_id: int):
    with db.get_conn() as conn:
        guitar = dict(get_guitar(conn, guitar_id))
    return form_page(request, guitar, guitar_id=guitar_id)


@app.post("/guitars/{guitar_id}")
async def update_guitar(request: Request, guitar_id: int):
    form = await request.form()
    values, errors = parse_guitar_form(form)
    with db.get_conn() as conn:
        get_guitar(conn, guitar_id)
        if errors:
            return form_page(request, values, errors, guitar_id, status_code=400)
        sets = ", ".join(f"{n} = ?" for n in db.FIELD_NAMES)
        conn.execute(f"UPDATE guitars SET {sets}, updated_at = datetime('now') WHERE id = ?",
                     [values[n] for n in db.FIELD_NAMES] + [guitar_id])
        photo_errors = await save_photos(conn, guitar_id, form.getlist("photos"))
    return redirect(f"/guitars/{guitar_id}" + ("?photo_error=1" if photo_errors else ""))


@app.post("/guitars/{guitar_id}/archive")
def archive_guitar(guitar_id: int):
    with db.get_conn() as conn:
        get_guitar(conn, guitar_id)
        conn.execute(
            "UPDATE guitars SET status = 'archived',"
            " archived_date = COALESCE(archived_date, date('now')),"
            " updated_at = datetime('now') WHERE id = ?", (guitar_id,))
    return redirect(f"/guitars/{guitar_id}")


@app.post("/guitars/{guitar_id}/restore")
def restore_guitar(guitar_id: int):
    with db.get_conn() as conn:
        get_guitar(conn, guitar_id)
        conn.execute(
            "UPDATE guitars SET status = 'current', archived_date = NULL,"
            " updated_at = datetime('now') WHERE id = ?", (guitar_id,))
    return redirect(f"/guitars/{guitar_id}")


@app.post("/guitars/{guitar_id}/delete")
def delete_guitar(guitar_id: int):
    with db.get_conn() as conn:
        get_guitar(conn, guitar_id)
        files = [p["filename"] for p in get_photos(conn, guitar_id)]
        conn.execute("DELETE FROM guitars WHERE id = ?", (guitar_id,))
    for f in files:
        images.delete_files(f)
    return redirect("/")


@app.post("/guitars/{guitar_id}/photos")
async def upload_photos(request: Request, guitar_id: int):
    form = await request.form()
    with db.get_conn() as conn:
        get_guitar(conn, guitar_id)
        errors = await save_photos(conn, guitar_id, form.getlist("photos"))
    return redirect(f"/guitars/{guitar_id}" + ("?photo_error=1" if errors else ""))


def get_photo(conn, photo_id: int):
    photo = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if photo is None:
        raise HTTPException(404, "Photo not found")
    return photo


@app.post("/photo/{photo_id}/primary")
def make_primary(photo_id: int):
    with db.get_conn() as conn:
        photo = get_photo(conn, photo_id)
        conn.execute("UPDATE photos SET is_primary = (id = ?) WHERE guitar_id = ?",
                     (photo_id, photo["guitar_id"]))
    return redirect(f"/guitars/{photo['guitar_id']}")


@app.post("/photo/{photo_id}/caption")
async def caption_photo(request: Request, photo_id: int):
    form = await request.form()
    with db.get_conn() as conn:
        photo = get_photo(conn, photo_id)
        conn.execute("UPDATE photos SET caption = ? WHERE id = ?",
                     ((form.get("caption") or "").strip() or None, photo_id))
    return redirect(f"/guitars/{photo['guitar_id']}")


@app.post("/photo/{photo_id}/delete")
def delete_photo(photo_id: int):
    with db.get_conn() as conn:
        photo = get_photo(conn, photo_id)
        conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
        if photo["is_primary"]:
            conn.execute(
                "UPDATE photos SET is_primary = 1 WHERE id = (SELECT id FROM photos"
                " WHERE guitar_id = ? ORDER BY sort_order, id LIMIT 1)",
                (photo["guitar_id"],))
    images.delete_files(photo["filename"])
    return redirect(f"/guitars/{photo['guitar_id']}")


@app.get("/api/gallery")
def gallery():
    """Every photo in the collection, for the showroom screensaver."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT p.filename, p.caption, g.id AS guitar_id, g.brand, g.model, g.year,"
            " g.finish, g.guitar_type, g.status FROM photos p JOIN guitars g ON g.id = p.guitar_id"
            " ORDER BY g.status = 'archived', g.brand COLLATE NOCASE, g.model COLLATE NOCASE,"
            " p.is_primary DESC, p.sort_order, p.id").fetchall()
    return [{
        "src": f"/photos/{r['filename']}",
        "thumb": f"/thumbs/{images.thumb_name(r['filename'])}",
        "caption": r["caption"] or "",
        "guitar_id": r["guitar_id"],
        "brand": r["brand"] or "",
        "model": r["model"] or "",
        "details": " · ".join(str(v) for v in (r["year"], r["finish"], r["guitar_type"]) if v),
        "status": r["status"],
    } for r in rows]


@app.get("/export.csv")
def export_csv():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id"] + db.FIELD_NAMES + ["photo_count", "created_at", "updated_at"])
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT g.*, (SELECT COUNT(*) FROM photos p WHERE p.guitar_id = g.id) AS photo_count"
            " FROM guitars g ORDER BY brand COLLATE NOCASE, model COLLATE NOCASE").fetchall()
    for r in rows:
        writer.writerow([r["id"]] + [r[n] for n in db.FIELD_NAMES]
                        + [r["photo_count"], r["created_at"], r["updated_at"]])
    return Response(buf.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="guitars-{date.today()}.csv"'})
