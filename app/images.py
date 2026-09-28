import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from . import config

try:  # iPhone HEIC/HEIF support
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

# Formats browsers can display directly; anything else is converted to JPEG.
WEB_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}


class InvalidImage(ValueError):
    pass


def save_upload(data: bytes) -> str:
    """Validate and store an uploaded image. Returns the stored filename."""
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise InvalidImage(f"File is larger than {config.MAX_UPLOAD_MB} MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("Not a supported image file") from exc

    stem = uuid.uuid4().hex
    fmt = img.format
    if fmt in WEB_FORMATS:
        filename = stem + WEB_FORMATS[fmt]
        (config.PHOTO_DIR / filename).write_bytes(data)
    else:
        filename = stem + ".jpg"
        rgb = ImageOps.exif_transpose(img).convert("RGB")
        rgb.save(config.PHOTO_DIR / filename, "JPEG", quality=92)

    make_thumbnail(img, filename)
    return filename


def thumb_name(filename: str) -> str:
    return Path(filename).stem + ".jpg"


def make_thumbnail(img: Image.Image, filename: str) -> None:
    thumb = ImageOps.exif_transpose(img)
    if thumb.mode not in ("RGB", "L"):
        background = Image.new("RGB", thumb.size, "white")
        rgba = thumb.convert("RGBA")
        background.paste(rgba, mask=rgba.getchannel("A"))
        thumb = background
    thumb = thumb.convert("RGB")
    thumb.thumbnail(config.THUMB_SIZE)
    thumb.save(config.THUMB_DIR / thumb_name(filename), "JPEG", quality=85)


def delete_files(filename: str) -> None:
    for path in (config.PHOTO_DIR / filename, config.THUMB_DIR / thumb_name(filename)):
        path.unlink(missing_ok=True)
