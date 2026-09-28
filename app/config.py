import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")).resolve()
DB_PATH = DATA_DIR / "guitars.db"
PHOTO_DIR = DATA_DIR / "photos"
THUMB_DIR = DATA_DIR / "thumbs"

# Optional HTTP Basic auth. Leave APP_PASSWORD unset to disable.
APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
THUMB_SIZE = (600, 600)


def ensure_dirs() -> None:
    for d in (DATA_DIR, PHOTO_DIR, THUMB_DIR):
        d.mkdir(parents=True, exist_ok=True)
