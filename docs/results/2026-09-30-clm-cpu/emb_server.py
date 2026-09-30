"""An OpenAI-compatible /v1/embeddings server for CLM on a machine without CUDA.

CLM's reference encoder is `vllm serve Qwen/Qwen3-8B --runner pooling`: the final hidden state
(after the model's last norm) of the last token. vLLM does not run on this AMD card, so this
serves the same weights, unquantised, on the CPU with transformers. Slow, same numbers up to
float rounding. Only what `clm.embedder.Embedder` sends is handled: `input` (list of strings),
`encoding_format` ("base64" or "float") and `truncate_prompt_tokens` (keep the last N).

    python emb_server.py --port 8090 [--dtype bfloat16]
"""

from __future__ import annotations

import argparse
import base64
import threading
import time

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI
from transformers import AutoModel, AutoTokenizer

MODEL = "Qwen/Qwen3-8B"
app = FastAPI()
state: dict = {}
lock = threading.Lock()


def embed(text: str, keep: int | None) -> tuple[np.ndarray, int]:
    tok, model = state["tok"], state["model"]
    ids = tok(text, add_special_tokens=True)["input_ids"] or tok(" ")["input_ids"]
    if keep:
        ids = ids[-keep:]
    with lock, torch.inference_mode():
        out = model(input_ids=torch.tensor([ids]))
    vec = out.last_hidden_state[0, -1].float().numpy()
    return vec.astype(np.float32), len(ids)


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list", "data": [{"id": state["name"], "object": "model"}]}


@app.post("/v1/embeddings")
def embeddings(body: dict) -> dict:
    texts = body.get("input") or []
    texts = [texts] if isinstance(texts, str) else list(texts)
    keep = body.get("truncate_prompt_tokens")
    b64 = body.get("encoding_format") == "base64"
    data, tokens, started = [], 0, time.time()
    for i, text in enumerate(texts):
        vec, n = embed(str(text), keep)
        tokens += n
        payload = base64.b64encode(vec.tobytes()).decode() if b64 else vec.tolist()
        data.append({"object": "embedding", "index": i, "embedding": payload})
    print(f"[emb] {len(texts)} texts, {tokens} tokens, {time.time() - started:.1f} s", flush=True)
    return {"object": "list", "data": data, "model": state["name"],
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--name", default="qwen3-8b")
    parser.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float32"])
    args = parser.parse_args()
    torch.set_num_threads(max(1, (torch.get_num_threads() or 6)))
    state["name"] = args.name
    state["tok"] = AutoTokenizer.from_pretrained(MODEL)
    state["model"] = AutoModel.from_pretrained(MODEL, dtype=getattr(torch, args.dtype)).eval()
    print(f"[emb] {MODEL} loaded ({args.dtype}), serving on :{args.port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
