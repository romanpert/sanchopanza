"""The BrowseComp-Plus retrieval server both arms get: an MCP server over stdio with two tools,
`search(query, k)` and `get_document(docid)`, the official names its prompt uses (Claude Code
calls them `mcp__bcp__search` and `mcp__bcp__get_document`).

  <bcp venv>/python benchmarks/h2h/bcp_server.py [--docs D] [--index I] [--log L]

It mirrors the official server (`searcher/mcp_server.py` with the BM25 searcher): the same tool
descriptions, top 5 by default, each hit as docid, score and a snippet of the document's start,
and `get_document` returning the whole document. Differences, declared in the runner's report:
`k` is a parameter (default 5, at most `K_MAX`) where the official server fixes it per session; the
snippet is the first `SNIPPET_CHARS` characters instead of 512 Qwen3 tokens (about the same
length, no tokenizer download); the ranking is bm25s with Pyserini's parameters
(`bcp_data.py`), not Lucene.

The protocol is written here with the standard library (JSON-RPC 2.0, one message per line):
initialize, tools/list, tools/call and ping. Every call is appended to `--log` (query, k,
returned docids; or the docid fetched), which the runner reads for the official retrieval
metrics (search calls, evidence recall). The index (about 17 s to load) is loaded in a thread
from the start, so Claude Code's connection does not wait for it and the first call rarely does.
A document can be far longer than Claude Code's MCP output limit (the longest evidence document
of the draw is ~610K characters); `get_document` returns it whole, as the official one does, and
Claude Code applies the same limit in both arms.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

HERE = pathlib.Path(__file__).resolve().parent
CACHE = pathlib.Path.home() / ".cache" / "sanchopanza" / "bcp"
K_DEFAULT = 5
K_MAX = 10
SNIPPET_CHARS = 2048  # about 512 Qwen3 tokens of English prose
PROTOCOL = "2025-06-18"
SEARCH_DESCRIPTION = (
    "Perform a search on a knowledge source. Returns top-{k} hits with docid, score, and "
    "snippet. The snippet contains the document's contents (may be truncated based on token "
    "limits)."
)
GET_DESCRIPTION = "Retrieve a full document by its docid."
TOOLS = [
    {
        "name": "search",
        "description": SEARCH_DESCRIPTION.format(k=K_DEFAULT),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "k": {
                    "type": "integer",
                    "description": f"Number of hits (default {K_DEFAULT}, at most {K_MAX})",
                    "minimum": 1,
                    "maximum": K_MAX,
                },  # fmt: skip
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_document",
        "description": GET_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {"docid": {"type": "string", "description": "Document ID to retrieve"}},
            "required": ["docid"],
        },
    },
]


class Retriever(Protocol):
    def search(self, query: str, k: int) -> list[tuple[str, float]]: ...

    def text(self, docid: str) -> str | None: ...


class Bm25Retriever:  # pragma: no cover - needs the bcp venv and the built index
    """bm25s over `bcp_data`'s index; row n-1 of the index is row n of the doc store."""

    def __init__(self, docs: pathlib.Path, index: pathlib.Path) -> None:
        import bm25s
        import Stemmer

        self._db = sqlite3.connect(f"file:{docs}?mode=ro", uri=True, check_same_thread=False)
        self._model = bm25s.BM25.load(index, mmap=True, load_corpus=False)
        self._tok = bm25s.tokenization.Tokenizer(stemmer=Stemmer.Stemmer("porter"))
        self._tok.load_vocab(index)
        self._tok.load_stopwords(index)

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        ids = self._tok.tokenize([query], update_vocab=False, show_progress=False)
        if not any(ids[0]):
            return []
        docs, scores = self._model.retrieve(ids, k=k, show_progress=False)
        out = []
        for row, score in zip(docs[0].tolist(), scores[0].tolist(), strict=True):
            if score <= 0:
                continue
            found = self._db.execute("SELECT docid FROM docs WHERE n = ?", (row + 1,)).fetchone()
            if found:
                out.append((found[0], float(score)))
        return out

    def text(self, docid: str) -> str | None:
        found = self._db.execute("SELECT text FROM docs WHERE docid = ?", (docid,)).fetchone()
        return found[0] if found else None


# --- the tools ----------------------------------------------------------------------------------


def clamp_k(value: Any) -> int:
    try:
        k = int(value)
    except (TypeError, ValueError):
        return K_DEFAULT
    return max(1, min(K_MAX, k))


def do_search(retriever: Retriever, args: Mapping[str, Any]) -> tuple[list[dict], dict]:
    query = str(args.get("query") or "").strip()
    k = clamp_k(args.get("k", K_DEFAULT))
    hits = retriever.search(query, k) if query else []
    results = [
        {"docid": docid, "score": round(score, 4), "snippet": (retriever.text(docid) or "")[
            :SNIPPET_CHARS]}
        for docid, score in hits
    ]  # fmt: skip
    return results, {"tool": "search", "query": query, "k": k, "docids": [d for d, _ in hits]}


def do_get(retriever: Retriever, args: Mapping[str, Any]) -> tuple[dict | None, dict]:
    docid = str(args.get("docid") or "").strip()
    text = retriever.text(docid) if docid else None
    result = None if text is None else {"docid": docid, "text": text}
    return result, {"tool": "get", "docid": docid, "found": text is not None}


class Server:
    def __init__(self, make: Callable[[], Retriever], log: pathlib.Path | None = None) -> None:
        self._make = make
        self._retriever: Retriever | None = None
        self._log = log
        self._lock = threading.Lock()

    def retriever(self) -> Retriever:
        with self._lock:
            if self._retriever is None:
                self._retriever = self._make()
            return self._retriever

    def warm(self) -> None:
        threading.Thread(target=self.retriever, daemon=True).start()

    def _record(self, entry: Mapping[str, Any]) -> None:
        if self._log is not None:
            with self._log.open("a", encoding="utf-8") as sink:
                sink.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def call(self, name: str, args: Mapping[str, Any]) -> dict[str, Any]:
        if name == "search":
            result, entry = do_search(self.retriever(), args)
        elif name == "get_document":
            result, entry = do_get(self.retriever(), args)
        else:
            return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
        self._record(entry)
        text = json.dumps(result, ensure_ascii=False) if result is not None else "null"
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def handle(self, message: Mapping[str, Any]) -> dict[str, Any] | None:
        """One JSON-RPC message; the reply, or None for a notification."""
        method = message.get("method")
        if "id" not in message:
            return None
        reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
        params = message.get("params") or {}
        if method == "initialize":
            return {**reply, "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "bcp", "version": "1.0"},
            }}  # fmt: skip
        if method == "tools/list":
            return {**reply, "result": {"tools": TOOLS}}
        if method == "tools/call":
            try:
                result = self.call(str(params.get("name")), params.get("arguments") or {})
            except Exception as error:  # noqa: BLE001 - a tool error goes back to the agent
                result = {"content": [{"type": "text", "text": f"error: {error}"}], "isError": True}
            return {**reply, "result": result}
        if method == "ping":
            return {**reply, "result": {}}
        return {**reply, "error": {"code": -32601, "message": f"method not found: {method}"}}

    def serve(self, stdin: Any = None, stdout: Any = None) -> None:
        source, sink = stdin or sys.stdin, stdout or sys.stdout
        for line in source:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            reply = self.handle(message)
            if reply is not None:
                sink.write(json.dumps(reply, ensure_ascii=False) + "\n")
                sink.flush()


def entry(python: str, docs: pathlib.Path, index: pathlib.Path, log: pathlib.Path) -> dict:
    """The `--mcp-config` entry that starts this server."""
    return {
        "type": "stdio",
        "command": python,
        "args": [
            str(HERE / "bcp_server.py"),
            "--docs",
            str(docs),
            "--index",
            str(index),
            "--log",
            str(log),
        ],  # fmt: skip
        "env": {"PYTHONIOENCODING": "utf-8"},
    }


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - stdio
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--docs", default=str(CACHE / "docs.sqlite"))
    ap.add_argument("--index", default=str(CACHE / "bm25s"))
    ap.add_argument("--log", default=None)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    log = pathlib.Path(args.log) if args.log else None
    server = Server(lambda: Bm25Retriever(pathlib.Path(args.docs), pathlib.Path(args.index)), log)
    server.warm()
    server.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
