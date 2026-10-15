"""Images to Jev: `media.Attachment` leaves become refs in the state and entries of the
top-level `assets` map, PNG or JPEG of 256-1568 px a side. A mocked transport, no network."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import uuid
from typing import Any

import httpx
import pytest

from sanchopanza.contract import DeciderUnavailable, Truth
from sanchopanza.media import attachment_bytes, image, image_size
from sanchopanza.providers import jev, jev_assets
from sanchopanza.providers.jev import JevDecider

Image = pytest.importorskip("PIL.Image")

OK = {"answers": {"q": {"type": "noul", "noul": 0.9}}, "usage": {"input_tokens": 900},
      "model": "jev-1.14.0"}  # fmt: skip


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SANCHOPANZA_JEV_IMAGES", "SANCHO_JEV_IMAGES"):
        monkeypatch.delenv(name, raising=False)


def picture(width: int = 640, height: int = 480, fmt: str = "PNG", color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format=fmt)
    return buffer.getvalue()


def sent(decider_kwargs: dict[str, Any], state: Any) -> dict[str, Any]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=OK)

    client = httpx.AsyncClient(base_url=jev.BASE_URL, transport=httpx.MockTransport(handler))
    decider = JevDecider("k", client=client, **decider_kwargs)
    asyncio.run(decider.decide("p", state, {"q": Truth("Does `screenshot` show a button?")}))
    return {"body": json.loads(seen[-1].content), "headers": seen[-1].headers}


# --- the media helpers ---------------------------------------------------------------------


def test_image_size_reads_png_and_jpeg_headers_without_decoding() -> None:
    assert image_size(picture(640, 480)) == ("png", 640, 480)
    assert image_size(picture(300, 1000, "JPEG")) == ("jpeg", 300, 1000)
    assert image_size(b"GIF89a....") is None
    assert image_size(b"") is None


def test_attachment_bytes_reads_data_or_a_local_path(tmp_path: Any) -> None:
    data = picture()
    assert attachment_bytes(image(data=data)) == data
    path = tmp_path / "a.png"
    path.write_bytes(data)
    assert attachment_bytes(image(path=str(path))) == data
    with pytest.raises(ValueError, match="url"):
        attachment_bytes(image(url="https://x.test/a.png"))
    with pytest.raises(ValueError, match="ref"):
        attachment_bytes(image(ref="file-1"))


# --- the wire ------------------------------------------------------------------------------


def test_an_image_goes_as_a_ref_in_the_state_and_an_entry_in_assets() -> None:
    data = picture()
    out = sent({"images": True}, {"screenshot": image(data=data), "task": "t"})
    body = out["body"]
    ref = body["state"]["screenshot"]
    assert uuid.UUID(ref).version == 4
    assert body["state"]["task"] == "t"
    assert set(body["assets"]) == {ref}
    assert body["assets"][ref] == {"data_base64": base64.b64encode(data).decode("ascii"),
                                   "format": "png"}  # fmt: skip
    assert out["headers"][jev.IMAGES_HEADER] == "true"


def test_the_same_image_twice_is_one_asset_and_the_ref_is_stable() -> None:
    data = picture()
    first = sent({"images": True}, {"a": image(data=data), "b": [image(data=data)]})["body"]
    again = sent({"images": True}, {"a": image(data=data)})["body"]
    assert first["state"]["a"] == first["state"]["b"][0] == again["state"]["a"]
    assert len(first["assets"]) == 1


def test_a_jpeg_keeps_its_format() -> None:
    body = sent({"images": True}, {"screenshot": image(data=picture(fmt="JPEG"))})["body"]
    (asset,) = body["assets"].values()
    assert asset["format"] == "jpeg"


def test_the_format_comes_from_the_bytes_not_the_declared_media_type() -> None:
    attachment = image(data=picture(), media_type="image/jpeg")
    (asset,) = sent({"images": True}, {"s": attachment})["body"]["assets"].values()
    assert asset["format"] == "png"


def test_a_text_state_sends_no_assets_even_with_images_on() -> None:
    assert "assets" not in sent({"images": True}, {"text": "no picture"})["body"]


def test_with_images_the_decider_accepts_attachments() -> None:
    assert JevDecider("k", images=True).accepts_attachments is True
    assert JevDecider("k").accepts_attachments is False


def test_without_images_an_attachment_is_refused_and_the_way_to_turn_it_on_named() -> None:
    with pytest.raises(DeciderUnavailable) as raised:
        sent({}, {"screenshot": image(data=picture())})
    message = str(raised.value)
    assert "images=True" in message and "SANCHOPANZA_JEV_IMAGES" in message


# --- sizes ---------------------------------------------------------------------------------


def _sent_size(data: bytes, **hints: Any) -> tuple[str, int, int]:
    body = sent({"images": True}, {"s": image(data=data, **hints)})["body"]
    (asset,) = body["assets"].values()
    found = image_size(base64.b64decode(asset["data_base64"]))
    assert found is not None
    return found


def test_an_image_inside_the_bounds_is_sent_untouched() -> None:
    data = picture(1568, 882)
    body = sent({"images": True}, {"s": image(data=data)})["body"]
    (asset,) = body["assets"].values()
    assert base64.b64decode(asset["data_base64"]) == data


def test_a_large_image_is_scaled_down_to_1568_keeping_its_shape() -> None:
    fmt, width, height = _sent_size(picture(3136, 1764))
    assert fmt == "png" and width == 1568 and height == 882


def test_a_max_side_hint_scales_further() -> None:
    _, width, height = _sent_size(picture(1600, 800), max_side=800)
    assert (width, height) == (800, 400)


def test_a_small_image_is_scaled_up_to_the_minimum() -> None:
    _, width, height = _sent_size(picture(128, 200))
    assert min(width, height) >= jev_assets.MIN_SIDE
    assert width * height >= jev_assets.MIN_PIXELS


def test_a_side_jev_refuses_in_practice_is_scaled_up_to_280() -> None:
    # Measured 2026-10-15 (docs/results/2026-10-15-jev114-l5): 256 and 270 px refused, 280 taken.
    assert jev_assets.MIN_SIDE == 280
    _, width, height = _sent_size(picture(600, 270))
    assert min(width, height) >= 280


def test_an_image_too_thin_to_fit_both_bounds_is_refused() -> None:
    with pytest.raises(DeciderUnavailable, match="cannot fit"):
        sent({"images": True}, {"s": image(data=picture(4000, 100))})


def test_another_format_is_converted_to_png() -> None:
    fmt, width, height = _sent_size(picture(400, 300, "GIF"))
    assert (fmt, width, height) == ("png", 400, 300)


def test_without_pillow_a_fitting_image_still_goes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jev_assets, "_pillow", lambda: None)
    assert _sent_size(picture(640, 480)) == ("png", 640, 480)


def test_without_pillow_an_image_that_needs_resizing_names_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jev_assets, "_pillow", lambda: None)
    with pytest.raises(DeciderUnavailable, match=r"sanchopanza\[images\]"):
        sent({"images": True}, {"s": image(data=picture(3000, 2000))})


def test_a_url_or_a_non_image_attachment_is_refused() -> None:
    from sanchopanza.media import Attachment

    with pytest.raises(DeciderUnavailable, match="url"):
        sent({"images": True}, {"s": image(url="https://x.test/a.png")})
    with pytest.raises(DeciderUnavailable, match="audio/wav"):
        sent({"images": True}, {"s": Attachment("audio/wav", data=b"RIFF")})


def test_bytes_that_are_no_image_are_refused() -> None:
    with pytest.raises(DeciderUnavailable, match="not an image"):
        sent({"images": True}, {"s": image(data=b"not an image at all")})


def test_a_request_over_its_byte_limit_is_refused_before_sending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jev_assets, "MAX_REQUEST_BYTES", 10)
    with pytest.raises(DeciderUnavailable, match="MiB"):
        sent({"images": True}, {"s": image(data=picture())})
