import sqlite3
from contextlib import contextmanager

from . import config

# Editable guitar fields, in form order: (column, label, input type).
FIELDS = [
    ("brand", "Brand", "text"),
    ("model", "Model", "text"),
    ("year", "Year", "number"),
    ("guitar_type", "Type", "select"),
    ("serial_number", "Serial number", "text"),
    ("finish", "Finish / color", "text"),
    ("body_style", "Body style", "text"),
    ("country", "Country of origin", "text"),
    ("num_strings", "Strings", "number"),
    ("handedness", "Handedness", "select"),
    ("body_wood", "Body wood", "text"),
    ("top_wood", "Top wood", "text"),
    ("neck_wood", "Neck wood", "text"),
    ("fretboard_wood", "Fretboard wood", "text"),
    ("pickups", "Pickups / electronics", "text"),
    ("bridge", "Bridge / tremolo", "text"),
    ("scale_length", "Scale length", "text"),
    ("weight", "Weight", "text"),
    ("condition", "Condition", "select"),
    ("modifications", "Modifications", "textarea"),
    ("case_type", "Case", "text"),
    ("storage_location", "Storage location", "text"),
    ("purchase_date", "Purchase date", "date"),
    ("purchase_price", "Purchase price", "money"),
    ("purchased_from", "Purchased from", "text"),
    ("estimated_value", "Estimated value", "money"),
    ("notes", "Notes", "textarea"),
    ("status", "Status", "select"),
    ("archived_date", "Archived date", "date"),
    ("archive_reason", "Archive reason", "select"),
    ("archive_notes", "Archive notes (sold to, price, etc.)", "textarea"),
]

FIELD_NAMES = [f[0] for f in FIELDS]
INT_FIELDS = {"year", "num_strings"}
MONEY_FIELDS = {"purchase_price", "estimated_value"}

CHOICES = {
    "guitar_type": ["Electric", "Acoustic", "Acoustic-Electric", "Classical",
                    "Bass", "Acoustic Bass", "Archtop", "Resonator",
                    "Lap Steel", "Other"],
    "handedness": ["Right", "Left"],
    "condition": ["Mint", "Excellent", "Very Good", "Good", "Fair", "Poor",
                  "Project"],
    "status": ["current", "archived"],
    "archive_reason": ["Sold", "Traded", "Gifted", "Lost / Stolen",
                       "Returned", "Other"],
}

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS guitars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    {", ".join(
        f"{name} {'INTEGER' if name in INT_FIELDS else 'REAL' if name in MONEY_FIELDS else 'TEXT'}"
        for name in FIELD_NAMES
    )},
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guitar_id INTEGER NOT NULL REFERENCES guitars(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    original_name TEXT,
    caption TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_photos_guitar ON photos(guitar_id);
CREATE INDEX IF NOT EXISTS idx_guitars_status ON guitars(status);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    config.ensure_dirs()
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        # Add any columns introduced after the table was first created.
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(guitars)")}
        for name in FIELD_NAMES:
            if name not in existing:
                col_type = ("INTEGER" if name in INT_FIELDS
                            else "REAL" if name in MONEY_FIELDS else "TEXT")
                conn.execute(f"ALTER TABLE guitars ADD COLUMN {name} {col_type}")
