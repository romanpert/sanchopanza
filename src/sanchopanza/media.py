"""Attachments: how a non-text thing gets into a decision's state.

**What exists, as of 2026-10-15.** Jev reads images. With the 1.14 release (2026-10-14)
TypeSafe documents PNG and JPEG images behind an opt-in header, `TypeSafe-Danger-Zone-Images: true`,
and the header works on `jev-1.13.0` too (measured: the same answers on a 640x480 form from both
versions). Each side must be 280 to 1568 px (the docs say 256; 270 was refused in practice), 78,400
to 2,458,624 px in all, at most 16 MiB a file and 32 MiB a request; an image outside the bounds is
refused, not resized. The image travels once per request in a top-level `assets` map and its ref is
cited from the state, the instructions or the criteria; every citation is billed again as input
tokens (a 640x480 capture was about 850 tokens). `JevDecider(images=True)`
(`SANCHOPANZA_JEV_IMAGES=1`) turns an `Attachment` into that wire, resizing with Pillow
(`sanchopanza[images]`) when it has to (`providers.jev_assets`). 1.14 adds a Box primitive, where in
an image something is (`contract.Box`). Audio and video are still not supported.

Before that release (2026-09-24) the documentation said *"Jev accepts text only"*, and every
other offer was a ranking score that is not a probability, an uncalibrated vendor confidence,
or a generative model coaxed into a schema, whose self-reported confidence is not usable as a
decision score (Qwen3-VL-4B baseline ECE 0.42 on visual reasoning). Whether Jev's answers
over an image are as well calibrated as over text is not measured here yet.

**Why this module existed before any vendor did.** The shape was proven. *Visual Jev*
(arXiv 2609.25845, 2026-09-22, independent of TypeSafe) scores Choice, Score and Noul
questions over an image from raw logits with no autoregressive generation, at 5.7 ms amortized
per question when 32 questions share one image. The questions did not have to change. So the
only thing standing between this package and a multimodal decider was **the type of
`state`**, and that is what this module widens. A local vision model behind `LocalDecider`
works too.

**The economics are the design.** Against a median of 71 millionths of a dollar for a text
decision request, one question about a 1080p screenshot on a small hosted VLM is about 25x
that. Eight questions grouped into one call about a 768px image is about 1.8x. So
`Attachment` carries hints for resizing, and every decision point that grows an image should
ask all of its questions in one call, which the contract already does.

**One safety fact that does not have a workaround yet.** No production prompt-injection
classifier accepts an image: Prompt Guard 2, Azure Prompt Shields and Model Armor are all
text-in, and the best image-accepting detector in the literature reaches a true-positive rate
of 0.38 at a false-positive rate of 0.002. Image-borne injection against a shipping browser
agent has been demonstrated (faint text invisible to a human, read by the OCR path). The
`injection` question in this package reads text; it does not see pixels. An attachment that
reaches a model's context is attack surface this layer cannot screen, and the harness must
know that.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8"
# JPEG start-of-frame markers that carry the size: every SOFn except DHT, JPG and DAC.
_SOF = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}


@dataclass(frozen=True, slots=True)
class Attachment:
    """A non-text part of a state, named by media type rather than by kind.

    Four ways to say where the bytes are, because every provider prefers a different one and
    converting eagerly throws away both cost levers (a provider that can fetch a URL itself
    should not be handed base64, and an already-uploaded file should not be re-sent):

    - `data`: the bytes, inline.
    - `path`: a local file the provider reads.
    - `url`: the provider decides whether to forward the link or download it.
    - `ref`: an identifier the provider already holds from an earlier upload.

    `hints` carries provider-specific knobs (a maximum side, a detail level) so that they
    stay out of the contract. One class keyed by `media_type` rather than `Image` / `Audio`
    / `Document`, so that nothing here changes when the next modality arrives.
    """

    media_type: str
    data: bytes | None = None
    path: str | None = None
    url: str | None = None
    ref: str | None = None
    hints: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.media_type or "/" not in self.media_type:
            raise ValueError("media_type must be a media type such as 'image/png'")
        if not any((self.data, self.path, self.url, self.ref)):
            raise ValueError("an attachment needs one of data, path, url or ref")

    @property
    def is_image(self) -> bool:
        return self.media_type.startswith("image/")

    def describe(self) -> str:
        """A short text stand-in, for logs and for text-only providers to refuse against."""
        where = "inline" if self.data is not None else (self.path or self.url or self.ref or "?")
        return f"[{self.media_type}: {where}]"


def image(
    *,
    data: bytes | None = None,
    path: str | None = None,
    url: str | None = None,
    ref: str | None = None,
    media_type: str = "image/png",
    **hints: Any,
) -> Attachment:
    """`Attachment` for the common case, so a caller never has to spell the media type."""
    return Attachment(media_type=media_type, data=data, path=path, url=url, ref=ref, hints=hints)


def attachment_bytes(attachment: Attachment) -> bytes:
    """The bytes of an inline or local attachment. A `url` is not fetched here (what to fetch
    and from where is the caller's decision, not a decider's), and a `ref` names an upload
    held by some other provider: both raise `ValueError`."""
    if attachment.data is not None:
        return attachment.data
    if attachment.path:
        return Path(attachment.path).read_bytes()
    if attachment.url:
        raise ValueError(f"an attachment by url is not fetched here: {attachment.url[:200]}")
    raise ValueError(f"an attachment by ref names an upload this provider does not hold: "
                     f"{attachment.ref}")  # fmt: skip


def image_size(data: bytes) -> tuple[str, int, int] | None:
    """("png" | "jpeg", width, height) from the header alone, or None for anything else.

    No decoder needed: a PNG keeps its size in the IHDR chunk, a JPEG in its start-of-frame
    segment. Which format the bytes are comes from the bytes, never from a declared type.
    """
    if data.startswith(PNG_MAGIC) and len(data) >= 24 and data[12:16] == b"IHDR":
        return "png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if not data.startswith(JPEG_MAGIC):
        return None
    at = 2
    while at + 9 < len(data):
        if data[at] != 0xFF:
            return None
        marker = data[at + 1]
        if marker == 0xFF:  # fill byte
            at += 1
            continue
        if marker in _SOF:
            height = int.from_bytes(data[at + 5 : at + 7], "big")
            width = int.from_bytes(data[at + 7 : at + 9], "big")
            return "jpeg", width, height
        at += 2 + int.from_bytes(data[at + 2 : at + 4], "big")
    return None


def attachments_in(state: Any) -> tuple[Attachment, ...]:
    """Every attachment anywhere in a state, so a provider can find them before deciding.

    A state is text, a mapping or a sequence, and an attachment may sit at any depth. A
    text-only provider calls this to refuse loudly; a multimodal one calls it to collect what
    it has to upload.
    """
    if isinstance(state, Attachment):
        return (state,)
    if isinstance(state, Mapping):
        found: list[Attachment] = []
        for value in state.values():
            found.extend(attachments_in(value))
        return tuple(found)
    if isinstance(state, (list, tuple)):
        found = []
        for value in state:
            found.extend(attachments_in(value))
        return tuple(found)
    return ()


def without_attachments(state: Any) -> Any:
    """The same state with every attachment replaced by its short description.

    What a text-only provider would send if the caller told it to carry on regardless. It is
    not the default: silently dropping the thing the question is about produces a confident
    answer to a question nobody asked, which is worse than no answer at all.
    """
    if isinstance(state, Attachment):
        return state.describe()
    if isinstance(state, Mapping):
        return {key: without_attachments(value) for key, value in state.items()}
    if isinstance(state, (list, tuple)):
        return [without_attachments(value) for value in state]
    return state
