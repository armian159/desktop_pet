import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from phoebe_pet.chat import MSG_BROKEN, MSG_OFFLINE, ChatError, ChatSession, ChatWorker, parse_stream_line
from phoebe_pet.config import Config

CFG = Config(history_turns=2)


def test_payload_shape():
    p = ChatSession(CFG).begin("안녕")
    assert p["model"] == "phoebe" and p["stream"] is True and p["think"] is False
    assert p["keep_alive"] == "30m" and p["messages"] == [{"role": "user", "content": "안녕"}]


def test_history_grows_only_on_success():
    s = ChatSession(CFG)
    s.begin("a")
    s.succeed("A")
    assert s.history == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "A"}] and not s.busy


def test_failed_turn_leaves_history_unchanged():
    s = ChatSession(CFG)
    s.begin("a")
    s.succeed("A")
    before = list(s.history)
    s.begin("b")
    s.fail()
    assert s.history == before and not s.busy


def test_begin_while_busy_is_rejected():
    s = ChatSession(CFG)
    s.begin("a")
    assert s.begin("b") is None
    s.succeed("A")
    assert [m["content"] for m in s.history] == ["a", "A"]


def test_only_last_turns_are_sent():
    s = ChatSession(CFG)
    for i in range(5):
        s.begin(f"q{i}")
        s.succeed(f"a{i}")
    msgs = s.begin("now")["messages"]
    assert [m["content"] for m in msgs] == ["q3", "a3", "q4", "a4", "now"]


def test_blank_input_rejected():
    s = ChatSession(CFG)
    assert s.begin("   ") is None and not s.busy


def test_input_is_stripped():
    assert ChatSession(CFG).begin("  hi \n")["messages"][-1]["content"] == "hi"


def test_reset_clears():
    s = ChatSession(CFG)
    s.begin("a")
    s.succeed("A")
    s.reset()
    assert s.history == []


def test_reset_mid_request_drops_the_late_reply():
    s = ChatSession(CFG)
    s.begin("a")
    s.reset()
    s.succeed("A")
    assert s.history == [] and not s.busy


def test_empty_reply_counts_as_failure():
    s = ChatSession(CFG)
    s.begin("a")
    s.succeed("   ")
    assert s.history == [] and not s.busy


def test_only_latest_monologue_is_kept():
    s = ChatSession(CFG)
    s.add_monologue("하나")
    s.begin("안녕")
    s.succeed("네")
    s.add_monologue("둘")
    assert [m["content"] for m in s.history] == ["안녕", "네", "둘"]


def test_blank_monologue_is_ignored():
    s = ChatSession(CFG)
    s.add_monologue("  ")
    assert s.history == []


def test_reset_forgets_monologue():
    s = ChatSession(CFG)
    s.add_monologue("하나")
    s.reset()
    s.add_monologue("둘")
    assert [m["content"] for m in s.history] == ["둘"]


def test_parse_delta_and_done():
    assert parse_stream_line('{"message":{"content":"안"},"done":false}'.encode()) == ("안", False)
    assert parse_stream_line(b'{"message":{"content":""},"done":true}') == ("", True)


def test_blank_line_is_ignored():
    assert parse_stream_line(b"\n") == ("", False)


def test_error_line_raises():
    with pytest.raises(ChatError):
        parse_stream_line(b'{"error":"boom"}')


def test_garbage_line_raises():
    with pytest.raises(ChatError):
        parse_stream_line(b"<html>")


# ---- worker against a local fake server ------------------------------------


def serve(handler_body):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            handler_body(self)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def chunks(*parts, done=True):
    def body(h):
        h.send_response(200)
        h.send_header("Content-Type", "application/x-ndjson")
        h.end_headers()
        for part in parts:
            h.wfile.write((json.dumps({"message": {"content": part}, "done": False}) + "\n").encode())
        if done:
            h.wfile.write(b'{"message":{"content":""},"done":true}\n')

    return body


def run_worker(qapp, url):
    worker = ChatWorker(url, {"model": "phoebe", "messages": []}, "phoebe")
    got = {"delta": [], "done": [], "failed": []}
    worker.delta.connect(got["delta"].append)
    worker.done.connect(got["done"].append)
    worker.failed.connect(got["failed"].append)
    worker.start()
    assert worker.wait(10000)
    qapp.processEvents()
    return got


def test_worker_streams_then_done(qapp):
    server = serve(chunks("안녕", "하세요"))
    got = run_worker(qapp, f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()
    assert got == {"delta": ["안녕", "하세요"], "done": ["안녕하세요"], "failed": []}


def test_worker_connection_refused_reports_offline(qapp):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    got = run_worker(qapp, f"http://127.0.0.1:{port}")
    assert got == {"delta": [], "done": [], "failed": [MSG_OFFLINE]}


def test_worker_404_reports_missing_model(qapp):
    def body(h):
        h.send_response(404)
        h.end_headers()
        h.wfile.write(b'{"error":"model not found"}')

    server = serve(body)
    got = run_worker(qapp, f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()
    assert got["failed"] == ["'phoebe' 모델을 찾을 수 없어요."] and got["done"] == []


def test_worker_truncated_stream_reports_broken(qapp):
    server = serve(chunks("안녕", done=False))
    got = run_worker(qapp, f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()
    assert got["failed"] == [MSG_BROKEN] and got["done"] == []


def test_worker_error_line_mid_stream_reports_failure_once(qapp):
    def body(h):
        h.send_response(200)
        h.end_headers()
        h.wfile.write(b'{"message":{"content":"a"},"done":false}\n{"error":"out of memory"}\n')

    server = serve(body)
    got = run_worker(qapp, f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()
    assert len(got["failed"]) == 1 and got["done"] == []
