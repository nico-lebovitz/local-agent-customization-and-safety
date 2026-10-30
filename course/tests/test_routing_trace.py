import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import io
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from course.agent.routing_trace import Trace, RoutedChat, model_router, timeline
from course.agent.learning import run_learning


class RoutingTraceTests(unittest.TestCase):
    def test_real_routes_and_relay_in_a_running_notebook_loop(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append(body)
                payload = json.dumps({"id": "fixture", "object": "chat.completion", "created": 0,
                    "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "fixture answer"}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp, patch(
                    "course.agent.routing_trace.BASE_URL", f"http://127.0.0.1:{server.server_port}"):
                async def notebook():
                    with model_router() as router, Trace(Path(tmp) / "events.json") as trace:
                        router.trace = trace
                        for model in ("base", "specialist"):
                            result = trace.tool({"tool": "ask"}, lambda a:
                                router(model, [{"role": "user", "content": "test"}]))
                            self.assertEqual(result, "fixture answer")
                    return trace
                trace = asyncio.run(notebook())
                self.assertEqual([x["model"] for x in received], ["base", "specialist"])
                rows = timeline(trace.events)
                self.assertEqual(len(rows), 4)
                self.assertTrue(all(r["status"] == "OK" for r in rows))
                self.assertEqual([r["model"] for r in rows if r["kind"] == "llm"],
                                 ["base", "specialist"])
                starts = {e["uuid"] for e in trace.events if e.get("scope_category") == "start"}
                ends = {e["uuid"] for e in trace.events if e.get("scope_category") == "end"}
                self.assertEqual(starts, ends)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_failed_tool_preserves_exception_and_records_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Trace(Path(tmp) / "events.json") as trace:
                def fail(action):
                    raise ValueError("Evidence missing")
                with self.assertRaisesRegex(ValueError, "Evidence missing"):
                    trace.tool({"tool": "triage"}, fail)
            rows = timeline(trace.events)
            self.assertEqual(rows[0]["status"], "ERROR")
            self.assertEqual(rows[0]["name"], "triage")

    def test_unrelated_trace_cannot_launch_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "failed-agent-run.json").write_text(json.dumps({
                "events": [{"action": {"tool": "perceive"}, "result": {}}], "state": {}}))
            (output / "failed-relay-events.json").write_text("[]")
            with patch("course.agent.learning.subprocess.run") as train:
                with self.assertRaises(ValueError):
                    run_learning(output)
                train.assert_not_called()

    def test_wrong_model_and_incomplete_answer_remain_failures(self):
        for model, reason in [("base", "stop"), ("specialist", "length")]:
            with self.subTest(model=model, finish_reason=reason):
                payload={"model":model,"choices":[{"finish_reason":reason,
                                                 "message":{"content":"answer"}}]}
                with patch("course.agent.routing_trace.urlopen",
                           return_value=io.BytesIO(json.dumps(payload).encode())):
                    with self.assertRaises(ValueError):
                        RoutedChat("http://fixture")("specialist",[])


if __name__ == "__main__":
    unittest.main()
