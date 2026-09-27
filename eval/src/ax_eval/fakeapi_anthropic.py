"""a fake Anthropic Messages API for claude code dry runs: no model, no cost.

answers `POST /v1/messages` (streamed or not) with a scripted sequence of
steps, one per agent request: a Bash tool_use per `sh:` step, any other tool
per `tool:` step, and finally a plain text message. requests that don't offer
the Bash tool (claude code's side calls: titles, quota checks and the like)
get a short text answer and don't use up a step. every request is appended to
a jsonl file so tests can see exactly what claude code sent.

    uv run python -m ax_eval.fakeapi_anthropic --port 18556 --record req.jsonl \\
        --step 'sh:ax read src/app.ts' --step 'msg:done'

steps: `sh:<command>`, `tool:<Name> <json input>`, `msg:<text>`, and
`err:<http status>` to answer that request with an api error instead.
"""

from __future__ import annotations

import argparse
import http.server
import itertools
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

USAGE = {"input": 200, "cache_write": 1000, "cache_read": 3000, "output": 40}
MODEL = "claude-opus-5"


@dataclass
class Script:
    steps: list[str]
    record: Path | None = None
    usage: dict = field(default_factory=lambda: dict(USAGE))
    _n: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def next(self) -> str:
        with self._lock:
            step = self.steps[min(self._n, len(self.steps) - 1)]
            self._n += 1
            return step


_ids = itertools.count(1)


def block_for(step: str) -> dict:
    kind, _, arg = step.partition(":")
    n = next(_ids)
    if kind == "sh":
        return {"type": "tool_use", "id": f"toolu_{n:04d}", "name": "Bash", "input": {"command": arg, "description": "run it"}}
    if kind == "tool":
        name, _, js = arg.partition(" ")
        return {"type": "tool_use", "id": f"toolu_{n:04d}", "name": name, "input": json.loads(js or "{}")}
    return {"type": "text", "text": arg or "done"}


def offers_bash(body: dict) -> bool:
    return any(t.get("name") == "Bash" for t in body.get("tools") or [])


def message(block: dict, model: str, usage: dict) -> dict:
    return {
        "id": f"msg_{next(_ids):04d}", "type": "message", "role": "assistant", "model": model,
        "content": [block], "stop_reason": "tool_use" if block["type"] == "tool_use" else "end_turn",
        "stop_sequence": None, "usage": usage,
    }


def api_usage(u: dict) -> dict:
    return {"input_tokens": u["input"], "cache_creation_input_tokens": u["cache_write"],
            "cache_read_input_tokens": u["cache_read"], "output_tokens": u["output"]}


def sse(block: dict, model: str, usage: dict) -> bytes:
    m = message(block, model, usage)
    start = {**m, "content": [], "stop_reason": None, "usage": {**usage, "output_tokens": 1}}
    if block["type"] == "tool_use":
        head = {**block, "input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
    else:
        head = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": block["text"]}
    events = [
        ("message_start", {"message": start}),
        ("content_block_start", {"index": 0, "content_block": head}),
        ("content_block_delta", {"index": 0, "delta": delta}),
        ("content_block_stop", {"index": 0}),
        ("message_delta", {"delta": {"stop_reason": m["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": usage["output_tokens"]}}),
        ("message_stop", {}),
    ]
    return b"".join(f"event: {name}\ndata: {json.dumps({'type': name, **body})}\n\n".encode() for name, body in events)


def handler(script: Script) -> type:
    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, payload: bytes, ctype: str = "application/json"):
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("content-length", str(len(payload)))
            self.send_header("request-id", f"req_{next(_ids):04d}")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if script.record:
                with open(script.record, "a") as f:
                    f.write(json.dumps({"method": "GET", "path": self.path}) + "\n")
            self._send(404, json.dumps({"type": "error", "error": {"type": "not_found_error", "message": "fake api"}}).encode())

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            req = json.loads(body or b"{}")
            if script.record:
                with open(script.record, "a") as f:
                    f.write(json.dumps({"method": "POST", "path": self.path, "body": req}) + "\n")
            path = self.path.split("?", 1)[0].rstrip("/")
            if path.endswith("/count_tokens"):
                return self._send(200, json.dumps({"input_tokens": 1000}).encode())
            if not path.endswith("/messages"):
                return self._send(404, json.dumps({"type": "error", "error": {"type": "not_found_error", "message": "fake api"}}).encode())
            model = req.get("model") or MODEL
            if offers_bash(req):
                step = script.next()
                if step.startswith("err:"):
                    code = int(step[4:] or 500)
                    kind = {401: "authentication_error", 429: "rate_limit_error", 529: "overloaded_error"}.get(code, "api_error")
                    return self._send(code, json.dumps({"type": "error", "error": {"type": kind, "message": f"fake {code}"}}).encode())
                block, usage = block_for(step), api_usage(script.usage)
            else:
                block, usage = {"type": "text", "text": "ok"}, api_usage({"input": 10, "cache_write": 0, "cache_read": 0, "output": 1})
            if req.get("stream"):
                self._send(200, sse(block, model, usage), "text/event-stream")
            else:
                self._send(200, json.dumps(message(block, model, usage)).encode())

        def log_message(self, *a):
            pass

    return H


def serve(script: Script, port: int = 0, host: str = "127.0.0.1") -> tuple[http.server.ThreadingHTTPServer, int]:
    """start in a background thread; returns (server, port)."""
    srv = http.server.ThreadingHTTPServer((host, port), handler(script))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=18556)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--record", type=Path)
    p.add_argument("--step", action="append", default=[], help="sh:<command>, tool:<Name> <json>, msg:<text> or err:<status>")
    a = p.parse_args(argv)
    _, port = serve(Script(a.step or ["msg:done"], a.record), a.port, a.host)
    print(f"fake messages api on http://{a.host}:{port}", flush=True)
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
