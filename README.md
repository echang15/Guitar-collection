# 🎸 Guitar Collection

A small self-hosted web app for cataloging a guitar collection: specs, purchase and value info, photos, and a **current** vs **archived** status for guitars you've sold, traded or given away.

It's one Docker container. Everything is stored in one data folder: a SQLite database plus your photos. That makes it easy to run and back up on a Synology NAS.

## Features

- **Guitar records**: brand, model, year, type, serial number, finish, body style, country of origin, number of strings, handedness, woods (body/top/neck/fretboard), pickups, bridge, scale length, weight, condition, modifications, case, storage location, purchase date/price/source, estimated value, and free-form notes.
- **Photos**: upload several at once, or drag and drop. iPhone HEIC photos are converted to JPEG automatically. Thumbnails are generated for fast browsing. You can pick the main photo, add captions and delete photos.
- **Current / Archive**: archive a guitar with one click, or set the status in the form. You can record the date, a reason (Sold, Traded, Gifted…) and notes such as the buyer and price. Archived guitars stay in the database and can be restored.
- **Browse**: grid or table view, search (brand, model, serial, notes…), filters by status, type and brand, and sorting by brand, year, date added or value.
- **Showroom look**: a dark, spotlit dashboard styled like a retail display, with large product cards, brand labels and price tags.
- **Showcase screensaver**: after 2 minutes idle (configurable), a full-screen slideshow of every photo in the collection starts, with slow zoom/crossfade and each guitar's brand, model and details. Moving the mouse, touching, clicking or pressing a key exits. You can also start it any time with the **▶ Showcase** button, which goes full-screen. It doesn't start on its own while you're on the add/edit form.
- **Totals**: counts of current and archived guitars, plus total paid and total estimated value for the current collection.
- **CSV export** of the whole collection.
- Autocomplete on fields such as brand, finish and woods, based on what you've entered before.
- Works on a phone.
- Optional password (HTTP Basic auth).

## Running on a Synology NAS

These steps are for **Container Manager** (DSM 7.2+). On older DSM the package is called "Docker", and you can do the same thing with `docker compose` over SSH.

1. **Copy the project to the NAS.** In File Station, create `docker/guitar-collection` inside the `docker` shared folder, then upload this repository's contents into it (or `git clone` it there over SSH). You'll end up with `/volume1/docker/guitar-collection/`.
2. **Create a project.** Open Container Manager → **Project** → **Create**.
   - Project name: `guitar-collection`
   - Path: `/volume1/docker/guitar-collection`
   - Source: **Use existing docker-compose.yml**
3. **Adjust `docker-compose.yml`** if needed. You can edit it in the wizard.
   - `ports`: the app listens on `8765` by default. Change the left-hand number if that port is taken.
   - `APP_PASSWORD`: uncomment it and set a password if other people can reach your network.
   - `TZ`: set your time zone.
4. Click **Next → Done**. Container Manager builds the image and starts it.
5. Open `http://<nas-ip>:8765`.

Data is stored in `/volume1/docker/guitar-collection/data`:

```
data/
  guitars.db   # SQLite database
  photos/      # original photos
  thumbs/      # generated thumbnails (can be regenerated)
```

**Backups:** include that `data` folder in Hyper Backup or a Snapshot Replication schedule.

**Remote access (optional):** to use it away from home, put it behind DSM's reverse proxy (Control Panel → Login Portal → Advanced → Reverse Proxy) with HTTPS, and **set `APP_PASSWORD`**. Tailscale is an even simpler option.

**File permissions:** the container runs as root by default, so the files in `data/` will be owned by root. If you want your own NAS user to own them, uncomment `user: "1026:100"` in `docker-compose.yml`, with your IDs from `id <username>` over SSH.

**Updating:** replace the app files with the new version, then in Container Manager → Project → `guitar-collection` → **Action → Build**. Your data folder is left untouched. Database columns added in newer versions are created automatically on startup.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `/data` in the container | Where the database and photos are stored |
| `APP_PASSWORD` | *(empty = no login)* | Turns on HTTP Basic auth |
| `APP_USERNAME` | `admin` | Username for Basic auth |
| `MAX_UPLOAD_MB` | `25` | Maximum size per photo |
| `SCREENSAVER_IDLE_SECONDS` | `120` | Seconds idle before the photo showcase starts (`0` = only start it manually) |

## Running locally (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # http://127.0.0.1:8000, data goes in ./data
pytest                             # run the tests
```

Or with Docker: `docker compose up --build`, then open http://localhost:8765.

## Tech

Python 3.12, FastAPI, Jinja2 server-rendered pages, SQLite and Pillow (with `pillow-heif` for HEIC). The only JavaScript is a small file for photo drag and drop and the gallery.
