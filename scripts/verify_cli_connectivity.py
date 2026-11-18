#!/usr/bin/env python3
"""Regression checks for connection-test budgets, queueing, targeted retries and cleanup."""

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.cli_adapters import RuntimeSettings, UnifiedAgentRunner, classify_cli_error
from backend.server import AsyncHTTPServer
from scripts.verify_full_convergence import mem_json


class ConnectivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="roundtable-connectivity-test-")
        self.env = patch.dict(os.environ, {"AI_ROUNDTABLE_HOME": self.temp.name})
        self.env.start()
        self.settings = RuntimeSettings.create_default("")
        self.runner = UnifiedAgentRunner(self.settings)
        self.config = self.settings.agents["titan"]
        self.binary = str(Path(self.temp.name) / "mock_codex")
        self.runner._require_binary = lambda aid, override=None: (
            self.config, self.binary, "", "codex", False
        )

    async def asyncTearDown(self):
        await self.runner.shutdown()
        self.env.stop()
        self.temp.cleanup()

    async def successful_stream(self, **kwargs):
        self.request = kwargs
        yield {"type": "delta", "text": "连接正常"}
        yield {"type": "terminal", "ok": True}

    async def test_configured_budget_and_model_are_used(self):
        self.runner._stream_raw_cli = self.successful_stream
        for budget in (600, 1800, 120):
            self.settings.turn_timeout_sec = budget
            result = await self.runner.ping_agent("titan")
            self.assertTrue(result["ok"])
            self.assertEqual(result["timeout_sec"], budget)
            self.assertEqual(self.request["effort"], "high")
            self.assertEqual(self.request["model"], "gpt-6-astra")

    async def test_queue_does_not_consume_request_budget(self):
        semaphore = self.runner._get_binary_semaphore(self.binary)
        for _ in range(self.settings.single_cli_concurrency):
            await semaphore.acquire()

        async def release_slot():
            await asyncio.sleep(0.25)
            semaphore.release()

        async def delayed_reply(**kwargs):
            await asyncio.sleep(0.4)
            yield {"type": "delta", "text": "连接正常"}

        self.runner._stream_raw_cli = delayed_reply
        release_task = asyncio.create_task(release_slot())
        try:
            result = await self.runner.ping_agent("titan", timeout_sec=0.5)
            self.assertTrue(result["ok"], result)
            self.assertGreaterEqual(result["queue_ms"], 240)
            self.assertGreaterEqual(result["elapsed_ms"], 600)
        finally:
            await release_task
            for _ in range(self.settings.single_cli_concurrency - 1):
                semaphore.release()

    async def test_queue_timeout_does_not_start_or_release_another_request(self):
        semaphore = self.runner._get_binary_semaphore(self.binary)
        for _ in range(self.settings.single_cli_concurrency):
            await semaphore.acquire()
        self.runner._stream_raw_cli = self.successful_stream
        try:
            result = await self.runner.ping_agent("titan", timeout_sec=0.03)
            self.assertEqual(result["error_kind"], "queue_timeout")
            self.assertEqual(result["timeout_phase"], "queue")
            self.assertEqual(result["request_elapsed_ms"], 0)
            self.assertFalse(hasattr(self, "request"))
            self.assertTrue(semaphore.locked())
        finally:
            for _ in range(self.settings.single_cli_concurrency):
                semaphore.release()

    async def test_partial_reply_timeout_closes_stream_and_releases_slot(self):
        closed = asyncio.Event()

        async def partial(**kwargs):
            try:
                yield {"type": "delta", "text": "partial"}
                await asyncio.sleep(5)
            finally:
                closed.set()

        self.runner._stream_raw_cli = partial
        result = await self.runner.ping_agent("titan", timeout_sec=0.03)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "timeout")
        self.assertEqual(result["reply"], "partial")
        self.assertTrue(closed.is_set())
        self.assertIn("重测此席位", result["error"])
        self.assertIn("已收到部分回复", result["error"])
        self.assertNotIn("降级", result["error"])
        semaphore = self.runner._get_binary_semaphore(self.binary)
        for _ in range(self.settings.single_cli_concurrency):
            await asyncio.wait_for(semaphore.acquire(), 0.1)
        for _ in range(self.settings.single_cli_concurrency):
            semaphore.release()

    async def test_limit_changes_share_one_pool_with_inflight_calls(self):
        self.settings.single_cli_concurrency = 1
        slots = self.runner._get_binary_semaphore(self.binary)
        await slots.acquire()
        waiting = asyncio.create_task(slots.acquire())
        await asyncio.sleep(0)
        self.assertFalse(waiting.done())
        self.settings.single_cli_concurrency = 2
        self.runner.refresh_binary_limits()
        self.assertIs(slots, self.runner._get_binary_semaphore(self.binary))
        await asyncio.wait_for(waiting, 0.2)
        self.settings.single_cli_concurrency = 1
        self.runner.refresh_binary_limits()
        slots.release()
        self.assertTrue(slots.locked())
        slots.release()
        self.assertFalse(slots.locked())

    def test_provider_capacity_does_not_report_quota_or_bad_effort(self):
        message = "UNAVAILABLE (code 503): No capacity available for model gemini-4-carbon-high on the server"
        err = classify_cli_error("agy", raw_err=message, exit_code=3)
        self.assertEqual(err.error_kind, "service_unavailable")
        self.assertIn("503", str(err))
        for msg, kind in [("429 Too Many Requests", "quota_rate_limit"),
                          ("model not found", "unsupported_effort_or_model"),
                          ("401 Unauthorized", "auth_expired")]:
            self.assertEqual(classify_cli_error("agy", raw_err=msg, exit_code=3).error_kind, kind)

    @unittest.skipIf(os.name == "nt", "Executable fixture uses a POSIX shebang")
    async def test_agy_drains_stderr_and_rejects_failed_final_frame_after_text(self):
        self.runner._require_binary = lambda aid, override=None: (
            self.config, self.binary, "--output-format stream-json --effort", "agy", False
        )
        events = [
            {"event":"step_update", "step_update":{"step_type":"agent_response", "text_delta":"部分正文"}},
            {"event":"result", "result":{"status":"ERROR", "error":"UNAVAILABLE (code 503): No capacity available for model"}},
        ]
        Path(self.binary).write_text(
            f"#!{sys.executable}\nimport sys,time\nsys.stderr.buffer.write(b'x' * (10 * 1024 * 1024))\n"
            + "\n".join(f"print({json.dumps(event)!r}, flush=True)" for event in events) + "\ntime.sleep(30)\n"
        )
        Path(self.binary).chmod(0o755)
        result = await self.runner.ping_agent("vega", timeout_sec=5)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "service_unavailable", result)

    async def test_empty_output_is_failure(self):
        async def empty(**kwargs):
            yield {"type": "terminal", "ok": True}
        self.runner._stream_raw_cli = empty
        result = await self.runner.ping_agent("titan")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_kind"], "process_error")

    async def test_timed_out_child_is_reaped(self):
        if os.name == "nt":
            self.skipTest("Executable fixture uses a POSIX shebang")
        marker = Path(self.temp.name) / "child.pid"
        script = (
            f"#!{sys.executable}\n"
            "import json,os,time\nfrom pathlib import Path\n"
            f"Path({str(marker)!r}).write_text(str(os.getpid()))\n"
            "print(json.dumps({'type':'thread.started','thread_id':'fixture'}),flush=True)\n"
            "time.sleep(30)\n"
        )
        Path(self.binary).write_text(script)
        Path(self.binary).chmod(0o755)
        result = await self.runner.ping_agent("titan", timeout_sec=0.5)
        self.assertEqual(result["error_kind"], "timeout")
        self.assertTrue(marker.exists())
        pid = int(marker.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse(self.runner._active_raw_procs)
        self.assertFalse(list((Path(self.temp.name) / "tmp_runs").iterdir()))

    async def test_single_seat_http_retry(self):
        app = AsyncHTTPServer("127.0.0.1", 18765, "", boot_token="connectivity-fixture")
        app.orchestrator.runner._require_binary = self.runner._require_binary
        app.orchestrator.runner._stream_raw_cli = self.successful_stream
        try:
            code, _, response = await mem_json(app, app.boot_token, "POST", "/api/cli/test",
                                                {"agent_id": "titan"})
            self.assertEqual(code, 200)
            self.assertEqual(set(response["results"]), {"titan"})
            self.assertTrue(response["results"]["titan"]["ok"])
            self.assertEqual(response["results"]["titan"]["effort"], "high")
            code, _, _ = await mem_json(app, app.boot_token, "POST", "/api/cli/test", {"agent_id": "unknown"})
            self.assertEqual(code, 400)
        finally:
            await app.orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)
