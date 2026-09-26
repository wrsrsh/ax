"""a fake OpenAI Responses API for dry runs: no model, no cost.

it answers `POST /v1/responses` (streamed, the way codex asks) with a
scripted sequence of steps, one per request: shell commands (sent the way
codex's code-mode `exec` tool expects them) and finally a plain message.
every request body is appended to a jsonl file so tests can inspect exactly
what codex sent, e.g. which tools a setup exposes.

    uv run python -m ax_eval.fakeapi --port 18555 --record req.jsonl \\
        --step 'sh:ax read src/app.ts' --step 'msg:done'

steps: `sh:<command>`, `patch:<codex patch, \\n for newlines>`, `msg:<text>`.
"""

from __future__ import annotations

import argparse
import http.server
import itertools
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

USAGE = {"input": 1200, "cached": 1000, "output": 40, "reasoning": 16}


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


def item_for(step: str, code_mode: bool = True) -> dict:
    """one output item per step. in code mode every tool call is javascript inside
    `exec`; with code mode off (setups Ar/Br/Cr) exec_command is a function tool and
    apply_patch a freeform custom tool."""
    kind, _, arg = step.partition(":")
    n = next(_ids)
    if kind == "patch":
        patch = arg.replace("\\n", "\n")
        if not code_mode:
            return {"type": "custom_tool_call", "id": f"ctc_{n}", "call_id": f"call_{n}", "name": "apply_patch", "input": patch, "status": "completed"}
        js = f"text(await tools.apply_patch({json.dumps(patch)}));"
    elif kind == "sh":
        if not code_mode:
            return {"type": "function_call", "id": f"fc_{n}", "call_id": f"call_{n}", "name": "exec_command",
                    "arguments": json.dumps({"cmd": arg}), "status": "completed"}
        js = f"const r = await tools.exec_command({{cmd: {json.dumps(arg)}}});\ntext(r.output ?? JSON.stringify(r));"
    else:
        return {
            "type": "message",
            "id": f"msg_{n}",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": arg or "done", "annotations": []}],
        }
    return {"type": "custom_tool_call", "id": f"ctc_{n}", "call_id": f"call_{n}", "name": "exec", "input": js, "status": "completed"}


def offers_exec(body: dict) -> bool:
    return any(t.get("name") == "exec" for item in body.get("input", []) if item.get("type") == "additional_tools"
               for ns in item.get("tools", []) for t in ns.get("tools", []))


def sse(script: Script, code_mode: bool = True) -> bytes:
    item = item_for(script.next(), code_mode)
    u = script.usage
    rid = f"resp_{next(_ids)}"
    base = {"id": rid, "object": "response", "model": "gpt-6-astra"}
    usage = {
        "input_tokens": u["input"],
        "input_tokens_details": {"cached_tokens": u["cached"]},
        "output_tokens": u["output"],
        "output_tokens_details": {"reasoning_tokens": u["reasoning"]},
        "total_tokens": u["input"] + u["output"],
    }
    events = [
        ("response.created", {"response": {**base, "status": "in_progress", "output": []}}),
        ("response.output_item.added", {"output_index": 0, "item": item}),
        ("response.output_item.done", {"output_index": 0, "item": item}),
        ("response.completed", {"response": {**base, "status": "completed", "output": [item], "usage": usage}}),
    ]
    out = b""
    for seq, (name, body) in enumerate(events):
        data = {"type": name, "sequence_number": seq, **body}
        out += f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
    return out


def handler(script: Script) -> type:
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            req = json.loads(body or b"{}")
            if script.record:
                with open(script.record, "a") as f:
                    f.write(json.dumps({"path": self.path, "body": req}) + "\n")
            if not self.path.rstrip("/").endswith("/responses"):
                self.send_response(404)
                self.end_headers()
                return
            payload = sse(script, offers_exec(req))
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

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
    p.add_argument("--port", type=int, default=18555)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--record", type=Path)
    p.add_argument("--step", action="append", default=[], help="sh:<command>, patch:<patch> or msg:<text>")
    a = p.parse_args(argv)
    _, port = serve(Script(a.step or ["msg:done"], a.record), a.port, a.host)
    print(f"fake responses api on http://{a.host}:{port}/v1", flush=True)
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
