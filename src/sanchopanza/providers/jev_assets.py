"""Images for Jev: from `media.Attachment` leaves in a state to TypeSafe's `assets` wire.

    {"model": ..., "state": {"screenshot": "<ref>", ...}, "questions": {...},
     "assets": {"<ref>": {"data_base64": "...", "format": "png" | "jpeg"}}}

Every attachment becomes a ref, a UUID derived from its bytes (the same image twice is one
asset, and the same state gives the same request), and the leaf that held it holds the ref,
so instructions cite it the usual way: "the Submit button in `screenshot`". Sent only with
the `TypeSafe-Danger-Zone-Images: true` header (`JevDecider(images=True)`).

The API refuses rather than resizes: 256 to 1568 px a side, 78,400 to 2,458,624 px, 16 MiB a
file, 32 MiB a request (docs.typesafe.ai/images, 2026-10-15). So an image is fitted here, by
the `max_side` hint when the caller gives one: inside the bounds the bytes go untouched; outside
them, or in another format, Pillow resizes or converts (the optional `sanchopanza[images]`
extra). Without Pillow an image that fits still goes, and one that does not is refused with the
extra named. Each citation of a ref is billed again: cite an image once per request.
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
import uuid
from collections.abc import Mapping
from typing import Any

from ..contract import DeciderUnavailable
from ..media import Attachment, attachment_bytes, image_size

MIN_SIDE, MAX_SIDE = 256, 1568
MIN_PIXELS, MAX_PIXELS = 78_400, 2_458_624
MAX_FILE_BYTES = 16 * 2**20
MAX_REQUEST_BYTES = 32 * 2**20
JPEG_QUALITY = 90


def _pillow() -> Any | None:
    """`PIL.Image`, or None when the `images` extra is not installed."""
    try:
        from PIL import Image
    except ImportError:
        return None
    return Image


def ref_of(data: bytes) -> str:
    """A UUID (version 4 layout) taken from the bytes' SHA-256: stable and collision-free."""
    return str(uuid.UUID(bytes=hashlib.sha256(data).digest()[:16], version=4))


def target_size(width: int, height: int, max_side: int = MAX_SIDE) -> tuple[int, int]:
    """The size an image is sent at: itself when it fits, else scaled keeping its shape."""
    cap = min(max(int(max_side), MIN_SIDE), MAX_SIDE)
    down = min(1.0, cap / max(width, height), math.sqrt(MAX_PIXELS / (width * height)))
    up = max(MIN_SIDE / min(width, height), math.sqrt(MIN_PIXELS / (width * height)))
    if up > 1.0:  # rounded up to reach the minimum, down to stay under the maximum
        size = (math.ceil(width * up - 1e-9), math.ceil(height * up - 1e-9))
    else:
        size = (max(1, math.floor(width * down + 1e-9)), max(1, math.floor(height * down + 1e-9)))
    if not _fits(*size, cap):
        raise DeciderUnavailable(
            f"a {width}x{height} image cannot fit Jev's bounds ({MIN_SIDE}-{cap} px a side, "
            f"{MIN_PIXELS:,}-{MAX_PIXELS:,} px): crop it first"
        )
    return size


def _fits(width: int, height: int, cap: int = MAX_SIDE) -> bool:
    sides = min(width, height) >= MIN_SIDE and max(width, height) <= cap
    return sides and MIN_PIXELS <= width * height <= MAX_PIXELS


def fitted(attachment: Attachment) -> tuple[str, bytes]:
    """(format, bytes) ready for the wire, or `DeciderUnavailable` saying why not."""
    if not attachment.is_image:
        raise DeciderUnavailable(f"Jev reads images, not {attachment.media_type}")
    try:
        data = attachment_bytes(attachment)
    except (ValueError, OSError) as error:
        raise DeciderUnavailable(f"image not sent: {error}") from error
    found = image_size(data)
    max_side = int(attachment.hints.get("max_side", MAX_SIDE))
    if found is not None:
        fmt, width, height = found
        size = target_size(width, height, max_side)
        if size == (width, height):
            return fmt, _within_file_limit(data)
    return _redrawn(data, found, max_side)


def _redrawn(data: bytes, found: tuple[str, int, int] | None, max_side: int) -> tuple[str, bytes]:
    pil = _pillow()
    if pil is None:
        why = "is not PNG or JPEG" if found is None else "is outside Jev's size bounds"
        raise DeciderUnavailable(
            f"the image {why}; install sanchopanza[images] (Pillow) to convert or resize it"
        )
    try:
        picture = pil.open(io.BytesIO(data))
        picture.load()
    except Exception as error:  # noqa: BLE001 - Pillow raises many types for a bad file
        raise DeciderUnavailable("image not sent: the bytes are not an image") from error
    size = target_size(*picture.size, max_side)
    fmt = found[0] if found is not None else "png"
    if size != picture.size:
        picture = picture.resize(size, pil.Resampling.LANCZOS)
    buffer = io.BytesIO()
    if fmt == "jpeg":
        picture.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY)
    else:
        mode = picture.mode if picture.mode in ("RGB", "RGBA", "L", "LA") else "RGBA"
        picture.convert(mode).save(buffer, format="PNG")
    return fmt, _within_file_limit(buffer.getvalue())


def _within_file_limit(data: bytes) -> bytes:
    if len(data) > MAX_FILE_BYTES:
        raise DeciderUnavailable(
            f"an image of {len(data) / 2**20:.1f} MiB is over the {MAX_FILE_BYTES / 2**20:g} "
            "MiB Jev takes a file"
        )
    return data


def to_assets(state: Any) -> tuple[Any, dict[str, dict[str, str]]]:
    """The state with every attachment replaced by its ref, and the `assets` map."""
    assets: dict[str, dict[str, str]] = {}
    sizes: dict[str, int] = {}

    def swap(value: Any) -> Any:
        if isinstance(value, Attachment):
            fmt, data = fitted(value)
            ref = ref_of(data)
            if ref not in assets:
                assets[ref] = {"data_base64": base64.b64encode(data).decode("ascii"),
                               "format": fmt}  # fmt: skip
                sizes[ref] = len(data)
            return ref
        if isinstance(value, Mapping):
            return {key: swap(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [swap(item) for item in value]
        return value

    swapped = swap(state)
    total = sum(sizes.values())
    if total > MAX_REQUEST_BYTES:
        raise DeciderUnavailable(
            f"{len(assets)} image(s) of {total / 2**20:.1f} MiB in all are over the "
            f"{MAX_REQUEST_BYTES / 2**20:g} MiB Jev takes a request"
        )
    return swapped, assets
