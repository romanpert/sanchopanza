"""Screenshots of Mind2Web steps for Jev's image input and Box (Jev 1.14, lot L5).

Pure helpers over a page screenshot (a PIL image, full page, 1280 px wide) and the candidates'
boxes in page pixels (`data.py --shots`): no network, no model.

- `tiles` / `tile_image`: the page cut top to bottom into square tiles, for the presence
  question and the Box (B1).
- `page_rect` / `iou` / `by_box`: a Box answer (fractions of an image) back to page pixels,
  and the candidates ordered by how well their box matches it (B1). Box answers come in steps
  of 2 % of the image (measured), 26 px of a 1280 px tile, so `zoom_region` / `region_image`
  give a second Box a 640 px square around the first one.
- `window` / `marked_region`: for one ranking call, the band of the page that holds most of its
  elements, each visible one outlined and labelled with its id (E01...), as in the call's state
  (B2).

Every image is JPEG, inside Jev's bounds (256-1568 px a side, at most `max_pixels`), so
`providers.jev_assets` sends the bytes untouched and its cost is set here, not there.
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

TILE = 1280  # px of page per tile, top to bottom
MAX_TILES = 8  # tiles past this (a page over 10,240 px) are not shown
MIN_TILE = 256  # a last tile shorter than this is merged into the one above
PRESENCE_PIXELS = 1_048_576  # a tile in the presence call: 1024 x 1024 for a full tile
BOX_PIXELS = 1_638_400  # the tile the Box reads: 1280 x 1280, untouched
ZOOM = 640  # px of page around the first box that the second Box reads, at full size
ZOOM_PIXELS = ZOOM * ZOOM
SPAN = 2_560  # px of page a ranking call's picture covers at most
REGION_PIXELS = 1_048_576  # a ranking call's picture
PAD = 24  # px around the elements a picture holds
JPEG_QUALITY = 85
MIN_SIDE, MAX_SIDE = 256, 1568
# Measured 2026-10-15 (amendment of lot L5): Jev 1.14 answers HTTP 400 "Invalid image
# dimensions" for a side of 256 or 270 px (1280x270, 600x256, 256x1100) and takes 280 and up,
# so the documented 256 is not the real floor. A ranking call's band is at least this tall.
MIN_BAND = 300

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 in page pixels


def rect_of(box: Sequence[float]) -> Rect | None:
    """[x, y, w, h] (Mind2Web's `bounding_box_rect`) to a rect; None when it has no area."""
    x, y, w, h = (float(v) for v in box)
    if not (w > 0 and h > 0) or not all(math.isfinite(v) for v in (x, y, w, h)):
        return None
    return (x, y, x + w, y + h)


def tiles(height: int, *, tile: int = TILE, max_tiles: int = MAX_TILES) -> list[tuple[int, int]]:
    """(top, bottom) of each tile, top to bottom; a short last piece joins the tile above."""
    out: list[tuple[int, int]] = []
    top = 0
    while top < height and len(out) < max_tiles:
        out.append((top, min(top + tile, height)))
        top += tile
    if len(out) > 1 and out[-1][1] - out[-1][0] < MIN_TILE:
        last = out.pop()
        out[-1] = (out[-1][0], last[1])
    return out


def _fit(width: int, height: int, max_pixels: int) -> tuple[int, int]:
    """The size an image is sent at: within `max_pixels` and MAX_SIDE, at least MIN_SIDE a side
    (a band too thin to scale up within the bounds raises: crop it differently)."""
    scale = min(1.0, math.sqrt(max_pixels / (width * height)), MAX_SIDE / max(width, height))
    w, h = max(1, math.floor(width * scale)), max(1, math.floor(height * scale))
    if min(w, h) < MIN_SIDE:
        raise ValueError(f"a {width}x{height} region cannot be sent within Jev's bounds")
    return w, h


def jpeg(picture: Any, max_pixels: int) -> bytes:
    """`picture` (PIL) as JPEG bytes, scaled down to fit `max_pixels` and Jev's sides."""
    from PIL import Image

    size = _fit(picture.width, picture.height, max_pixels)
    if size != (picture.width, picture.height):
        picture = picture.resize(size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    picture.convert("RGB").save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def tile_image(page: Any, span: tuple[int, int], max_pixels: int) -> bytes:
    """One tile of the page, full width, as JPEG."""
    top, bottom = span
    return jpeg(page.crop((0, top, page.width, bottom)), max_pixels)


def page_rect(box: Sequence[float], region: Rect) -> Rect:
    """A Box answer (top, bottom, left, right as fractions of the image) in page pixels, for an
    image of the page's `region` (x0, y0, x1, y1)."""
    top, bottom, left, right = (float(v) for v in box)
    x0, y0, x1, y1 = region
    width, height = x1 - x0, y1 - y0
    return (x0 + left * width, y0 + top * height, x0 + right * width, y0 + bottom * height)


def zoom_region(rect: Rect, page_width: int, page_height: int, side: int = ZOOM) -> Rect:
    """A `side` x `side` region of the page centred on `rect`, moved inside the page."""
    cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    w, h = min(side, page_width), min(side, page_height)
    x0 = min(max(0.0, cx - w / 2), page_width - w)
    y0 = min(max(0.0, cy - h / 2), page_height - h)
    return (float(int(x0)), float(int(y0)), float(int(x0) + w), float(int(y0) + h))


def region_image(page: Any, region: Rect, max_pixels: int = ZOOM_PIXELS) -> bytes:
    return jpeg(page.crop(tuple(int(v) for v in region)), max_pixels)


def iou(a: Rect, b: Rect) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _centre_distance(a: Rect, b: Rect) -> float:
    return math.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)


def by_box(predicted: Rect, candidates: Mapping[str, Rect]) -> list[tuple[str, float]]:
    """(key, IoU) of every candidate with a box, best first: IoU, then nearer centre, then key."""
    scored = [(key, iou(predicted, rect), _centre_distance(predicted, rect))
              for key, rect in candidates.items()]  # fmt: skip
    scored.sort(key=lambda t: (-t[1], t[2], t[0]))
    return [(key, round(score, 4)) for key, score, _ in scored]


def window(rects: Sequence[Rect], height: int, *, span: int = SPAN) -> tuple[int, int]:
    """The band of the page (top, bottom), at most `span` tall, that holds the most of `rects`
    whole (ties: the highest band); the band hugs them, with PAD around, at least MIN_BAND."""
    if not rects:
        return (0, min(height, span))
    tops = sorted(rects, key=lambda r: r[1])
    best: list[Rect] = []
    for start in tops:
        inside = [r for r in tops if r[1] >= start[1] and r[3] <= start[1] + span]
        if len(inside) > len(best):
            best = inside
    best = best or [tops[0]]
    top = max(0, int(min(r[1] for r in best)) - PAD)
    bottom = min(height, int(math.ceil(max(r[3] for r in best))) + PAD, top + span)
    if bottom - top < MIN_BAND:
        top = max(0, min(top, height - MIN_BAND))
        bottom = min(height, top + MIN_BAND)
    return (top, bottom)


def _font(size: int) -> Any:
    from PIL import ImageFont

    return ImageFont.load_default(size=size)


def marked_region(
    page: Any,
    labelled: Sequence[tuple[str, Rect | None]],
    *,
    span: int = SPAN,
    max_pixels: int = REGION_PIXELS,
) -> tuple[bytes, int]:
    """The band of `page` holding most of `labelled` (id, rect) with each one inside it outlined
    and tagged with its id; (JPEG bytes, how many were drawn). Labels are drawn at a size that
    stays about 18 px after the picture is scaled to `max_pixels`."""
    from PIL import ImageDraw

    rects = [r for _, r in labelled if r is not None]
    top, bottom = window(rects, page.height, span=span)
    region = page.crop((0, top, page.width, bottom)).convert("RGB")
    scale = _fit(region.width, region.height, max_pixels)[0] / region.width
    font = _font(max(12, round(18 / scale)))
    line = max(1, round(2 / scale))
    draw = ImageDraw.Draw(region)
    drawn = 0
    for label, rect in labelled:
        if rect is None or rect[1] < top or rect[3] > bottom:
            continue
        box = (rect[0], rect[1] - top, rect[2], rect[3] - top)
        draw.rectangle(box, outline=(220, 0, 0), width=line)
        tx, ty = box[0], max(0.0, box[1] - font.size - 2 * line)
        text_box = draw.textbbox((tx, ty), label, font=font)
        draw.rectangle(text_box, fill=(220, 0, 0))
        draw.text((tx, ty), label, fill=(255, 255, 255), font=font)
        drawn += 1
    return jpeg(region, max_pixels), drawn


def picture_for(
    page: Any, rects: Mapping[str, Rect | None], label: Callable[[int], str]
) -> Callable[[Sequence[Any]], Any]:
    """A `browse.rank(picture=...)` callback: one call's elements (in order) to an `Attachment`
    of their band of the page, element i labelled `label(i)`."""
    from sanchopanza.media import image

    def picture(elements: Sequence[Any]) -> Any:
        labelled = [(label(i), rects.get(e.key)) for i, e in enumerate(elements)]
        data, _ = marked_region(page, labelled)
        return image(data=data, media_type="image/jpeg")

    return picture
