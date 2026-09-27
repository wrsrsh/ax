import json
import urllib.error
import urllib.request

import pytest

from ax_eval.fakeapi_anthropic import Script, serve

AGENT = {"model": "claude-opus-5", "stream": True, "tools": [{"name": "Bash"}, {"name": "Read"}], "messages": []}


def post(port, body, path="/v1/messages?beta=true"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(), {"content-type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return r.read().decode()


def events(sse):
    return [json.loads(l[6:]) for l in sse.splitlines() if l.startswith("data: ")]


@pytest.fixture
def api(tmp_path):
    rec = tmp_path / "req.jsonl"
    srv, port = serve(Script(['sh:ax read a.ts', 'tool:Read {"file_path": "/w/a.ts"}', "err:529", "msg:bye"], rec))
    yield port, rec
    srv.shutdown()


def test_steps_stream_as_tool_use(api):
    port, rec = api
    ev = events(post(port, AGENT))
    assert [e["type"] for e in ev] == ["message_start", "content_block_start", "content_block_delta",
                                       "content_block_stop", "message_delta", "message_stop"]
    assert ev[1]["content_block"]["name"] == "Bash" and ev[1]["content_block"]["input"] == {}
    assert json.loads(ev[2]["delta"]["partial_json"]) == {"command": "ax read a.ts", "description": "run it"}
    assert ev[4]["delta"]["stop_reason"] == "tool_use" and ev[0]["message"]["usage"]["cache_read_input_tokens"] == 3000
    # a side call (no Bash offered, not streamed) gets text and doesn't eat a step
    side = json.loads(post(port, {"model": "claude-haiku-4-5", "messages": []}))
    assert side["content"] == [{"type": "text", "text": "ok"}] and side["stop_reason"] == "end_turn"
    ev = events(post(port, AGENT))
    assert ev[1]["content_block"]["name"] == "Read" and json.loads(ev[2]["delta"]["partial_json"]) == {"file_path": "/w/a.ts"}
    with pytest.raises(urllib.error.HTTPError) as e:
        post(port, AGENT)
    assert e.value.code == 529 and json.loads(e.value.read())["error"]["type"] == "overloaded_error"
    ev = events(post(port, AGENT))
    assert ev[2]["delta"] == {"type": "text_delta", "text": "bye"} and ev[4]["delta"]["stop_reason"] == "end_turn"
    assert len(rec.read_text().splitlines()) == 5
