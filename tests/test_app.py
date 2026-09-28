import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "guitars.db")
    monkeypatch.setattr(config, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(config, "THUMB_DIR", tmp_path / "thumbs")
    config.ensure_dirs()
    from app import main
    # Re-point the static mounts at the temp dirs.
    for route in main.app.routes:
        if getattr(route, "name", None) == "photos":
            route.app.directory = str(config.PHOTO_DIR)
            route.app.all_directories = [str(config.PHOTO_DIR)]
        if getattr(route, "name", None) == "thumbs":
            route.app.directory = str(config.THUMB_DIR)
            route.app.all_directories = [str(config.THUMB_DIR)]
    with TestClient(main.app) as c:
        yield c


def jpeg_bytes(color="red", size=(1200, 800)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def add_guitar(client, **overrides):
    data = {"brand": "Fender", "model": "Stratocaster", "year": "1965",
            "guitar_type": "Electric", "status": "current", "handedness": "Right",
            "purchase_price": "$1,500", "estimated_value": "25000"}
    data.update(overrides)
    r = client.post("/guitars", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1].split("?")[0])


def test_empty_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "No guitars found" in r.text


def test_create_and_view(client):
    gid = add_guitar(client)
    r = client.get(f"/guitars/{gid}")
    assert r.status_code == 200
    assert "1965 Fender Stratocaster" in r.text
    assert "$1,500" in r.text and "$25,000" in r.text
    assert "Stratocaster" in client.get("/").text


def test_validation(client):
    r = client.post("/guitars", data={"brand": "", "model": "X", "year": "abc"})
    assert r.status_code == 400
    assert "Brand is required" in r.text
    assert "Year must be a whole number" in r.text


def test_edit(client):
    gid = add_guitar(client)
    r = client.post(f"/guitars/{gid}", data={"brand": "Fender", "model": "Telecaster",
                                             "status": "current"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Telecaster" in client.get(f"/guitars/{gid}").text
    assert "Edit guitar" in client.get(f"/guitars/{gid}/edit").text


def test_archive_and_restore(client):
    gid = add_guitar(client)
    client.post(f"/guitars/{gid}/archive")
    assert "Stratocaster" not in client.get("/?status=current").text
    assert "Stratocaster" in client.get("/?status=archived").text
    assert "Restore to current" in client.get(f"/guitars/{gid}").text
    client.post(f"/guitars/{gid}/restore")
    assert "Stratocaster" in client.get("/?status=current").text


def test_archive_via_form_sets_date(client):
    gid = add_guitar(client, status="archived", archive_reason="Sold")
    page = client.get(f"/guitars/{gid}").text
    assert "Sold" in page and "Archived" in page


def test_search_and_filters(client):
    add_guitar(client)
    add_guitar(client, brand="Gibson", model="Les Paul", guitar_type="Electric",
               serial_number="ABC123")
    add_guitar(client, brand="Martin", model="D-28", guitar_type="Acoustic")
    assert "Les Paul" in client.get("/?q=abc123").text
    assert "Stratocaster" not in client.get("/?q=abc123").text
    r = client.get("/?type=Acoustic")
    assert "D-28" in r.text and "Les Paul" not in r.text
    r = client.get("/?brand=gibson&view=table&sort=year_desc")
    assert "Les Paul" in r.text and "D-28" not in r.text


def test_photo_upload_primary_and_delete(client):
    gid = add_guitar(client)
    files = [("photos", ("a.jpg", jpeg_bytes("red"), "image/jpeg")),
             ("photos", ("b.jpg", jpeg_bytes("blue"), "image/jpeg"))]
    r = client.post(f"/guitars/{gid}/photos", files=files, follow_redirects=False)
    assert r.status_code == 303 and "photo_error" not in r.headers["location"]

    from app import db
    with db.get_conn() as conn:
        photos = conn.execute("SELECT * FROM photos ORDER BY id").fetchall()
    assert [p["is_primary"] for p in photos] == [1, 0]
    assert client.get(f"/photos/{photos[0]['filename']}").status_code == 200
    thumb = client.get("/thumbs/" + photos[0]["filename"].rsplit(".", 1)[0] + ".jpg")
    assert thumb.status_code == 200
    assert max(Image.open(io.BytesIO(thumb.content)).size) <= 600

    client.post(f"/photo/{photos[1]['id']}/primary")
    client.post(f"/photo/{photos[1]['id']}/caption", data={"caption": "Headstock"})
    with db.get_conn() as conn:
        rows = conn.execute("SELECT id, is_primary, caption FROM photos ORDER BY id").fetchall()
    assert [r["is_primary"] for r in rows] == [0, 1]
    assert rows[1]["caption"] == "Headstock"

    client.post(f"/photo/{photos[1]['id']}/delete")
    with db.get_conn() as conn:
        rows = conn.execute("SELECT id, is_primary FROM photos").fetchall()
    assert len(rows) == 1 and rows[0]["is_primary"] == 1
    assert client.get(f"/photos/{photos[1]['filename']}").status_code == 404


def test_create_with_photo_and_png_alpha(client):
    buf = io.BytesIO()
    Image.new("RGBA", (300, 200), (0, 0, 255, 128)).save(buf, "PNG")
    r = client.post("/guitars", data={"brand": "PRS", "model": "Custom 24", "status": "current"},
                    files=[("photos", ("p.png", buf.getvalue(), "image/png"))],
                    follow_redirects=False)
    assert r.status_code == 303 and "photo_error" not in r.headers["location"]
    assert "/thumbs/" in client.get("/").text


def test_reject_non_image(client):
    gid = add_guitar(client)
    r = client.post(f"/guitars/{gid}/photos",
                    files=[("photos", ("x.jpg", b"not an image", "image/jpeg"))],
                    follow_redirects=False)
    assert "photo_error=1" in r.headers["location"]


def test_delete_guitar_removes_photos(client, tmp_path):
    gid = add_guitar(client)
    client.post(f"/guitars/{gid}/photos",
                files=[("photos", ("a.jpg", jpeg_bytes(), "image/jpeg"))])
    assert any((tmp_path / "photos").iterdir())
    client.post(f"/guitars/{gid}/delete")
    assert client.get(f"/guitars/{gid}").status_code == 404
    assert not any((tmp_path / "photos").iterdir())
    assert not any((tmp_path / "thumbs").iterdir())


def test_csv_export(client):
    add_guitar(client)
    r = client.get("/export.csv")
    assert r.status_code == 200
    assert r.text.splitlines()[0].startswith("id,brand,model,year")
    assert "Stratocaster" in r.text


def test_basic_auth(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "APP_PASSWORD", "secret")
    assert client.get("/").status_code == 401
    assert client.get("/healthz").status_code == 200
    assert client.get("/", auth=("admin", "wrong")).status_code == 401
    assert client.get("/", auth=("admin", "secret")).status_code == 200
