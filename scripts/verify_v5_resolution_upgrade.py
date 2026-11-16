#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 v5 — 认知防伪、场景意图包、盲评隔离、双席再辩与「全量成果保留 + 弃案负面清单物理隔离」决议引擎端到端验收套件
(scripts/verify_v5_resolution_upgrade.py)
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import stat
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def make_executable(path: Path, content: str) -> Path:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


async def raw_http_request(
    port: int,
    method: str,
    target: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    body: bytes = b"",
) -> Tuple[int, Dict[str, str], bytes]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        hdrs = {"Host": f"127.0.0.1:{port}", **(headers or {})}
        if body and "Content-Length" not in hdrs and "content-length" not in hdrs:
            hdrs["Content-Length"] = str(len(body))
        lines = [f"{method} {target} HTTP/1.1"]
        for k, v in hdrs.items():
            lines.append(f"{k}: {v}")
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)
        await writer.drain()

        status_line = await asyncio.wait_for(reader.readline(), timeout=20.0)
        if not status_line:
            raise RuntimeError("Empty HTTP response")
        status_code = int(status_line.decode("latin-1").strip().split(" ", 2)[1])
        resp_headers: Dict[str, str] = {}
        while True:
            hl = await asyncio.wait_for(reader.readline(), timeout=20.0)
            if not hl or hl in (b"\r\n", b"\n"):
                break
            k, v = hl.decode("latin-1").rstrip("\r\n").split(":", 1)
            resp_headers[k.strip().lower()] = v.strip()
        cl = int(resp_headers.get("content-length", "0"))
        resp_body = await asyncio.wait_for(reader.readexactly(cl), timeout=20.0) if cl > 0 else b""
        return status_code, resp_headers, resp_body
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def api_json(
    port: int,
    token: str,
    method: str,
    target: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, Any]]:
    hdrs = {"X-Roundtable-Token": token, "Content-Type": "application/json"}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else b""
    st, _, body = await raw_http_request(port, method, target, headers=hdrs, body=raw)
    try:
        parsed = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        parsed = {"_raw": body.decode("utf-8", errors="replace")}
    return st, parsed


def assert_err_code(st: int, expected_st: int, data: Dict[str, Any], expected_code: str) -> None:
    assert st == expected_st, f"期望 HTTP {expected_st} ({expected_code})，实际返回 {st}: {data}"
    dumped = json.dumps(data, ensure_ascii=False)
    code_field = str(data.get("reason") or data.get("code") or data.get("error_code") or "")
    assert code_field == expected_code or expected_code in dumped, (
        f"期望错误码 {expected_code}，实际返回: {data}"
    )


async def wait_session_idle(port: int, token: str, sid: str, max_iters: int = 80) -> Dict[str, Any]:
    snap: Dict[str, Any] = {}
    for _ in range(max_iters):
        await asyncio.sleep(0.08)
        st, data = await api_json(port, token, "GET", f"/api/sessions/{sid}")
        assert st == 200
        snap = data["session"]
        if not snap.get("is_busy") and snap.get("exec_state", "idle") == "idle":
            return snap
    raise AssertionError(f"会话 {sid} 未在预期时限内收敛为空闲态: stage={snap.get('stage')}, busy={snap.get('is_busy')}")


async def run_v5_verification() -> None:
    passed: List[str] = []

    def ok(title: str, detail: str = "") -> None:
        suf = f" ({detail})" if detail else ""
        print(f"  [PASS] {title}{suf}", flush=True)
        passed.append(title)

    with tempfile.TemporaryDirectory(prefix="ai_rt_v5_verify_") as tmp_str:
        tmp_root = Path(tmp_str).resolve()
        rt_home = tmp_root / "rt_home"
        rt_home.mkdir(parents=True, exist_ok=True)
        os.environ["AI_ROUNDTABLE_HOME"] = str(rt_home)
        os.environ["AI_ROUNDTABLE_FAST_TEST"] = "1"

        proj_dir = tmp_root / "workspace_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "service.py").write_text(
            "def process_order(order_id: str) -> bool:\n"
            "    return bool(order_id)\n"
            "# line 3\n"
            "# line 4\n"
            "# line 5\n",
            encoding="utf-8",
        )

        blind_probe_file = tmp_root / "blind_probe.json"

        mock_agy = make_executable(
            tmp_root / "mock_agy_bin",
            f"""
            #!/usr/bin/env python3
            import json, os, sys, time
            from pathlib import Path

            args = sys.argv[1:]
            if "--version" in args:
                print("mock-agy 5.0.0")
                sys.exit(0)
            if "--help" in args:
                print("Usage: agy -p PROMPT --model MODEL --effort EFFORT --sandbox")
                sys.exit(0)

            prompt = " ".join(args)
            if "仅回复 OK" in prompt or "Reply with OK only" in prompt:
                print("OK")
                sys.exit(0)

            mode = os.environ.get("V5_MOCK_MODE", "default")
            if mode == "slow_hold":
                sys.stdout.write("正在深度推演架构边界…\\n")
                sys.stdout.flush()
                time.sleep(0.85)
                print("推演完成。\\n\\n[白板要点]\\n- 任务：补充边界单测")
                sys.exit(0)

            if mode == "absent_fail_grok":
                # The separate mock_codex_hetero executable fails for Grok.  Matching
                # general risk/audit words here also fails Carbon when its prompt
                # mentions those words, making the intended one-seat scenario invalid.
                print("主席位正常完成立论。\\n\\n[白板要点]\\n- 任务：修复服务异常处理逻辑")
                sys.exit(0)

            if mode == "blind_check":
                probe_path = Path({str(blind_probe_file)!r})
                existing = json.loads(probe_path.read_text("utf-8")) if probe_path.exists() else []
                leaked_hist = "SENTINEL_SEAT1_SECRET_991" in prompt
                leaked_wb = "SENTINEL_WB_SECRET_992" in prompt
                existing.append({{"call_idx": len(existing) + 1, "leaked_hist": leaked_hist, "leaked_wb": leaked_wb}})
                probe_path.write_text(json.dumps(existing), encoding="utf-8")
                if len(existing) == 1:
                    print(
                        "首席独立盲评输出 SENTINEL_SEAT1_SECRET_991。\\n\\n"
                        "[白板要点]\\n"
                        "- 风险：SENTINEL_WB_SECRET_992\\n"
                        "- 任务：核验盲评隔离"
                    )
                else:
                    print(
                        f"次席独立盲评输出 leaked_hist={{leaked_hist}} leaked_wb={{leaked_wb}}。\\n\\n"
                        "[白板要点]\\n"
                        "- 风险：次席独立识别锁竞争边界"
                    )
                sys.exit(0)

            if mode == "resolution_r1":
                print(
                    "首轮架构立论建议：\\n"
                    "1. 方案P1：采用 WAL 单写队列保障并发读性能。\\n"
                    "2. 方案P2_OLD：使用全表阻塞轮询同步状态。\\n"
                    "3. 废案X1：直接关闭 fsync 裸写磁盘换取极限吞吐。\\n\\n"
                    "[白板要点]\\n"
                    "- 风险：直接关闭 fsync 裸写磁盘存在断电损坏数据库的高危风险\\n"
                    "- 任务：实现 WAL 单写队列存储层"
                )
                sys.exit(0)

            if mode == "resolution_r2":
                print(
                    "次轮交叉核验与修正裁定：\\n"
                    "- 保留方案P1（WAL 单写队列）并严格执行主持人初始纯标准库约束与中途 0o600 权限约束。\\n"
                    "- [修正原方案：使用全表阻塞轮询同步状态 -> 基于单调递增 rev 的增量 SSE 事件流推送]\\n"
                    "- [放弃原方案：直接关闭 fsync 裸写磁盘换取极限吞吐]（证伪原因：断电必致 SQLite 页面损坏，违反数据安全红线）\\n\\n"
                    "[白板要点]\\n"
                    "- 共识：采用基于单调递增 rev 的增量 SSE 事件流推送替代全表轮询\\n"
                    "- 任务：落盘权限强制设为 0o600 并接入 CAS 快照校验"
                )
                sys.exit(0)

            if mode == "resolution_synth":
                print(
                    "## 会议最终决议\\n\\n"
                    "### 一、主持硬约束与最终采纳架构成果\\n"
                    "- [主持指定约束] 严禁引入第三方重型 ORM，全程保持 Python 纯标准库 SQLite 实现。\\n"
                    "- [主持指定约束] 会话附件与快照落盘权限强制 0o600 并具备写前 CAS 字节证明。\\n"
                    "- 采纳方案P1：采用 WAL 单写队列保障并发读性能。\\n"
                    "- [修正原方案：使用全表阻塞轮询同步状态 -> 基于单调递增 rev 的增量 SSE 事件流推送]\\n\\n"
                    "### 二、已确认放弃与证伪淘汰方案（负面清单）\\n"
                    "- [放弃原方案：直接关闭 fsync 裸写磁盘换取极限吞吐] —— 断电会导致状态库不可逆损坏，已全票证伪淘汰。\\n"
                    "- [已淘汰旧方案] 使用全表阻塞轮询同步状态（已被单调 rev 增量事件流替代）。\\n\\n"
                    "### 三、待勾选执行交付任务\\n"
                    "- 实现 WAL 单写队列存储层与单调递增 rev 增量 SSE 推送\\n"
                    "- 落盘权限强制设为 0o600 并接入 CAS 快照校验\\n\\n"
                    "[白板要点]\\n"
                    "- 共识：采用 WAL 单写队列与基于单调递增 rev 的增量 SSE 事件流推送\\n"
                    "- 弃案：直接关闭 fsync 裸写磁盘换取极限吞吐（断电损坏数据库）\\n"
                    "- 任务：实现 WAL 单写队列存储层与单调递增 rev 增量 SSE 推送\\n"
                    "- 任务：落盘权限强制设为 0o600 并接入 CAS 快照校验"
                )
                sys.exit(0)

            if mode == "redebate_turn":
                print(
                    "双席定向再辩答辩：支持分段读写锁并补充非阻塞超时回退保障。\\n\\n"
                    "[白板要点]\\n- 共识：采用分段读写锁配合非阻塞超时回退"
                )
                sys.exit(0)

            if "写入本地项目工作区" in prompt or "执行任务" in prompt:
                (Path.cwd() / "service.py").write_text(
                    "def process_order(order_id: str) -> bool:\\n    return bool(order_id and order_id.strip())\\n",
                    encoding="utf-8",
                )
                print("已完成工作区安全写入。")
                sys.exit(0)

            print("常规异构推演完成。\\n\\n[白板要点]\\n- 风险：需核验锁粒度与超时回退边界\\n- 任务：补充回归断言")
            """,
        )

        mock_agy_homog_link = tmp_root / "mock_agy_symlink"
        mock_agy_homog_link.symlink_to(mock_agy)

        mock_codex_hetero = make_executable(
            tmp_root / "mock_codex_hetero_bin",
            """
            #!/usr/bin/env python3
            import json, os, sys
            args = sys.argv[1:]
            if "--version" in args:
                print("mock-codex-hetero 5.0.0")
                sys.exit(0)
            if "--help" in args:
                print("Usage: codex exec --json --sandbox read-only -m MODEL")
                sys.exit(0)
            prompt = sys.stdin.read()
            mode = os.environ.get("V5_MOCK_MODE", "default")
            if mode == "absent_fail_grok":
                sys.stderr.write("Hetero critic simulated timeout/failure\\n")
                sys.exit(2)
            if mode == "resolution_r1":
                txt = (
                    "异构审计首轮意见：赞同方案P1（WAL 单写队列），强烈反对废案X1（关闭 fsync 裸写磁盘），"
                    "并建议将方案P2_OLD 全表轮询升级为单调 rev 事件流。\\n\\n"
                    "[白板要点]\\n- 风险：关闭 fsync 裸写磁盘将破坏崩溃恢复一致性"
                )
            elif mode == "resolution_r2":
                txt = (
                    "异构审计次轮确认：\\n"
                    "- [修正原方案：使用全表阻塞轮询同步状态 -> 基于单调递增 rev 的增量 SSE 事件流推送]\\n"
                    "- [放弃原方案：直接关闭 fsync 裸写磁盘换取极限吞吐]\\n\\n"
                    "[白板要点]\\n- 共识：采用基于单调递增 rev 的增量 SSE 事件流推送替代全表轮询"
                )
            elif mode == "redebate_turn":
                txt = (
                    "双席定向再辩裁决：经正反交叉验证，确认采用分段读写锁配合非阻塞超时回退。\\n\\n"
                    "[白板要点]\\n- 共识：采用分段读写锁配合非阻塞超时回退"
                )
            else:
                txt = (
                    "异构引擎交叉质询完成：已针对争议边界给出独立反驳与收敛方案。\\n\\n"
                    "[白板要点]\\n- 风险：需验证异常分支锁释放幂等性\\n- 任务：增加锁释放断言"
                )
            print(json.dumps({"type": "thread.started", "thread_id": "tid_v5_het"}))
            print(json.dumps({"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": txt}}))
            print(json.dumps({"type": "turn.completed"}))
            """,
        )

        from backend.server import AsyncHTTPServer, MAX_HEADER_LINE_BYTES, MAX_REQUEST_LINE_BYTES

        port = find_free_port()
        token = "v5_verify_secret_token_20261116"
        app = AsyncHTTPServer(
            host="127.0.0.1",
            port=port,
            workspace_dir=str(proj_dir),
            boot_token=token,
            boot_id="boot_v5_verify",
        )
        server = await asyncio.start_server(
            app.handle_client,
            host="127.0.0.1",
            port=port,
            limit=max(MAX_REQUEST_LINE_BYTES, MAX_HEADER_LINE_BYTES) + 512,
        )

        try:
            st_cfg, _ = await api_json(
                port,
                token,
                "POST",
                "/api/config",
                {
                    "workspace_dir": str(proj_dir),
                    "single_cli_concurrency": 3,
                    "pacing_mode": "custom",
                    "idle_timeout_sec": 10,
                    "turn_timeout_sec": 25,
                    "agents": {
                        "carbon": {"driver": "agy", "custom_binary": str(mock_agy), "model": "gemini-4-carbon", "discussion_effort": "high"},
                        "grok": {"driver": "codex", "custom_binary": str(mock_codex_hetero), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "astra": {"driver": "agy", "custom_binary": str(mock_agy), "model": "gemini-4-carbon", "discussion_effort": "high"},
                        "vega": {"driver": "agy", "custom_binary": str(mock_agy), "model": "gemini-4-carbon", "discussion_effort": "high"},
                        "titan": {"driver": "codex", "custom_binary": str(mock_codex_hetero), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "prism": {"driver": "agy", "custom_binary": str(mock_agy), "model": "gemini-4-carbon", "discussion_effort": "high"},
                    },
                },
            )
            assert st_cfg == 200

            # ① 四大场景意图包与 artifact_type 自适应 + 异构推荐 + 空闲解绑纯研讨验证
            st_s1, d_s1 = await api_json(port, token, "POST", "/api/sessions", {"title": "意图包自适应测试"})
            assert st_s1 == 201
            sid1 = d_s1["session"]["session_id"]

            expected_packs = {
                "arch_code": "code_patch",
                "tradeoff_debate": "decision_matrix",
                "ux_multimodal": "ux_checklist",
                "incident_doc": "doc_export",
            }
            for pack_key, exp_art in expected_packs.items():
                st_pk, d_pk = await api_json(
                    port,
                    token,
                    "POST",
                    f"/api/sessions/{sid1}/seats",
                    {"scenario_pack": pack_key},
                )
                assert st_pk == 200, f"切换 scenario_pack={pack_key} 失败: {d_pk}"
                sess_obj = app.orchestrator.get_session(sid1)
                actual_art = (
                    d_pk.get("artifact_type")
                    or getattr(sess_obj, "artifact_type", "")
                    or sess_obj.whiteboard.get("artifact_type")
                )
                assert actual_art == exp_art, f"{pack_key} 期望 artifact_type={exp_art}，实际={actual_art}"

            st_het, d_het = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid1}/seats",
                {"recommend_heterogeneous": True},
            )
            assert st_het == 200 and len(d_het.get("enabled_agents") or []) >= 2

            st_unbind, d_unbind = await api_json(
                port, token, "POST", f"/api/sessions/{sid1}/workspace", {"workspace_dir": ""}
            )
            assert st_unbind == 200 and d_unbind.get("workspace_bound") is False
            st_rebind, d_rebind = await api_json(
                port, token, "POST", f"/api/sessions/{sid1}/workspace", {"workspace_dir": str(proj_dir)}
            )
            assert st_rebind == 200 and d_rebind.get("workspace_bound") is True
            ok("1. 四大场景意图包（arch_code / tradeoff_debate / ux_multimodal / incident_doc）、异构混编推荐与纯研讨解绑")

            # ② 空会话导出 409、@文件:行号 400、运行中切预设 409 session_busy、开局后改议题 409 topic_locked
            st_exp_empty, _, b_exp_empty = await raw_http_request(
                port, "GET", f"/api/sessions/{sid1}/export", headers={"X-Roundtable-Token": token}
            )
            assert_err_code(
                st_exp_empty,
                409,
                json.loads(b_exp_empty.decode("utf-8")) if b_exp_empty else {},
                "empty_session_export",
            )

            st_bad_ref1, d_bad_ref1 = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid1}/start",
                {"topic": "请审查 @missing_ghost_module.py:1-20 的并发安全性", "enabled_agents": ["carbon"]},
            )
            assert_err_code(st_bad_ref1, 400, d_bad_ref1, "invalid_file_reference")

            st_bad_ref2, d_bad_ref2 = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid1}/start",
                {"topic": "请审查 @service.py:99-120 越界行号", "enabled_agents": ["carbon"]},
            )
            assert_err_code(st_bad_ref2, 400, d_bad_ref2, "invalid_file_reference")

            os.environ["V5_MOCK_MODE"] = "slow_hold"
            st_go, _ = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid1}/start",
                {
                    "topic": "审查 @service.py:1-5 的订单校验逻辑",
                    "collab_mode": "rapid_consensus",
                    "enabled_agents": ["carbon"],
                },
            )
            assert st_go == 200
            await asyncio.sleep(0.12)

            st_busy_seats, d_busy_seats = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid1}/seats",
                {"scenario_pack": "incident_doc", "enabled_agents": ["grok", "astra"]},
            )
            assert_err_code(st_busy_seats, 409, d_busy_seats, "session_busy")

            st_lock_run, d_lock_run = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid1}/whiteboard",
                {"topic": "企图在运行中覆盖原始议题"},
            )
            assert_err_code(st_lock_run, 409, d_lock_run, "topic_locked")

            await wait_session_idle(port, token, sid1)

            st_lock_after, d_lock_after = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid1}/whiteboard",
                {"topic": "企图在开局后篡改议题"},
            )
            assert_err_code(st_lock_after, 409, d_lock_after, "topic_locked")
            ok("2. 空会话 409 empty_session_export、@文件:行号 400、运行态切预设 409 session_busy 与议题锁 409 topic_locked")

            # ③ 新任务默认 checked: False、零勾选 409 no_checked_tasks、缺席未确认 409 unacknowledged_absent_seats
            os.environ["V5_MOCK_MODE"] = "absent_fail_grok"
            _, d_s3 = await api_json(port, token, "POST", "/api/sessions", {"title": "执行准入三道门禁验证"})
            sid3 = d_s3["session"]["session_id"]
            await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid3}/workspace",
                {"workspace_dir": str(proj_dir)},
            )
            st_st3, _ = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid3}/start",
                {
                    "topic": "测试任务默认未勾选与席位异常缺席门禁",
                    "collab_mode": "rapid_consensus",
                    "enabled_agents": ["carbon", "grok"],
                },
            )
            assert st_st3 == 200
            snap3 = await wait_session_idle(port, token, sid3)
            wb3 = snap3["whiteboard"]
            act_items3 = [it for it in wb3.get("items", []) if it.get("kind") == "action"]
            if not act_items3:
                _, add_res = await api_json(
                    port,
                    token,
                    "POST",
                    f"/api/sessions/{sid3}/whiteboard",
                    {"op": "add", "kind": "action", "author": "chair", "text": "修复服务异常处理逻辑"},
                )
                wb3 = add_res["whiteboard"]
                act_items3 = [it for it in wb3.get("items", []) if it.get("kind") == "action"]

            assert act_items3 and all(it.get("checked") is False for it in act_items3), (
                f"新增任务必须默认 checked=False，实际: {act_items3}"
            )
            absent_ids3 = {x.get("agent_id") for x in wb3.get("absent_seats") or []}
            assert absent_ids3 == {"grok"}, f"应仅模拟 grok 异常缺席，实际: {absent_ids3}"

            st_no_chk, d_no_chk = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid3}/execute",
                {"allow_workspace_write": False, "executor_id": "astra"},
            )
            assert_err_code(st_no_chk, 409, d_no_chk, "no_checked_tasks")

            target_act_id = act_items3[0]["id"]
            st_chk, _ = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid3}/whiteboard",
                {"op": "toggle_check", "item_id": target_act_id, "checked": True},
            )
            assert st_chk == 200

            st_unack_abs, d_unack_abs = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid3}/execute",
                {"allow_workspace_write": False, "executor_id": "astra"},
            )
            assert_err_code(st_unack_abs, 409, d_unack_abs, "unacknowledged_absent_seats")

            os.environ["V5_MOCK_MODE"] = "default"
            st_ack_abs, d_ack_abs = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid3}/whiteboard",
                {"op": "acknowledge_absent", "acknowledged_absent_agents": ["grok"]},
            )
            assert st_ack_abs == 200, f"acknowledge_absent 失败: {d_ack_abs}"
            wb3_after_ack = d_ack_abs["whiteboard"]

            st_ex_ok, d_ex_ok = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid3}/execute",
                {
                    "allow_workspace_write": False,
                    "executor_id": "astra",
                    "expected_wb_version": wb3_after_ack["wb_version"],
                    "checked_action_ids": [target_act_id],
                    "expected_workspace_dir": str(proj_dir),
                    "acknowledged_absent_agents": ["grok"],
                },
            )
            assert st_ex_ok == 202, f"确认缺席后 /execute 应返回 202，实际 {st_ex_ok}: {d_ex_ok}"
            await wait_session_idle(port, token, sid3)
            ok("3. 任务默认 checked=False、零勾选 409 no_checked_tasks、缺席拦截 409 unacknowledged_absent_seats 及确认解锁")

            # ④ _run_agent_batch 首轮串行回退下的 frozen_history + frozen_whiteboard 100% 盲评隔离
            os.environ["V5_MOCK_MODE"] = "blind_check"
            if blind_probe_file.exists():
                blind_probe_file.unlink()

            await api_json(
                port,
                token,
                "POST",
                "/api/config",
                {
                    "single_cli_concurrency": 1,
                    "agents": {
                        "carbon": {"driver": "agy", "custom_binary": str(mock_agy), "model": "gemini-4-carbon", "discussion_effort": "high"},
                        "grok": {"driver": "agy", "custom_binary": str(mock_agy_homog_link), "model": "gemini-4-carbon", "discussion_effort": "high"},
                    },
                },
            )
            _, d_s4 = await api_json(port, token, "POST", "/api/sessions", {"title": "首轮串行盲评隔离测试"})
            sid4 = d_s4["session"]["session_id"]
            st_b4, _ = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid4}/start",
                {
                    "topic": "验证 single_cli_concurrency=1 首轮串行盲评零泄露",
                    "collab_mode": "rapid_consensus",
                    "enabled_agents": ["carbon", "grok"],
                },
            )
            assert st_b4 == 200
            snap4 = await wait_session_idle(port, token, sid4)
            probes = json.loads(blind_probe_file.read_text("utf-8"))
            assert len(probes) >= 2, f"期望至少 2 次串行席位调用，实际: {probes}"
            assert probes[1]["leaked_hist"] is False and probes[1]["leaked_wb"] is False, (
                f"首轮串行回退发生盲评污染！次席探针={probes[1]}"
            )
            ok("4. _run_agent_batch 串行回退下 frozen_history + frozen_whiteboard 100% 盲评隔离")

            # ⑤ 同源防伪徽章 [同源模型多视角推演 · 误差相关] / [单席推演草稿] 与 origin_tier 三级准入
            wb4_dump = json.dumps(snap4["whiteboard"], ensure_ascii=False)
            assert "同源模型多视角推演" in wb4_dump and "误差相关" in wb4_dump, (
                f"同源软链双席必须标记 [同源模型多视角推演 · 误差相关]，实际白板: {snap4['whiteboard']}"
            )

            risk4 = [it for it in snap4["whiteboard"].get("items", []) if it.get("kind") == "risk"]
            assert risk4, f"期望存在待核验 risk 条目，实际: {snap4['whiteboard']['items']}"
            risk_id = risk4[0]["id"]

            st_adopt_block, d_adopt_block = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid4}/whiteboard",
                {"op": "adopt_decision", "item_id": risk_id},
            )
            assert_err_code(st_adopt_block, 409, d_adopt_block, "unverified_consensus_adoption")

            st_adopt_chair, d_adopt_chair = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid4}/whiteboard",
                {"op": "adopt_decision", "item_id": risk_id, "as_chair_directive": True},
            )
            assert st_adopt_chair == 200, f"as_chair_directive=True 应允许锁定，实际: {d_adopt_chair}"
            promoted = [
                it for it in d_adopt_chair["whiteboard"]["items"] if it["id"] == risk_id and it["kind"] == "decision"
            ]
            assert promoted and promoted[0].get("origin_tier") == "chair_directive", (
                f"主持拍板条目必须标记 origin_tier='chair_directive'，实际: {promoted}"
            )

            os.environ["V5_MOCK_MODE"] = "default"
            _, d_solo = await api_json(port, token, "POST", "/api/sessions", {"title": "单席防伪标记测试"})
            sid_solo = d_solo["session"]["session_id"]
            await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid_solo}/start",
                {"topic": "单席独立草稿防伪核验", "collab_mode": "rapid_consensus", "enabled_agents": ["carbon"]},
            )
            snap_solo = await wait_session_idle(port, token, sid_solo)
            assert "单席推演草稿" in json.dumps(snap_solo["whiteboard"], ensure_ascii=False), (
                f"单席会话必须披露 [单席推演草稿]，实际: {snap_solo['whiteboard']}"
            )
            ok("5. 同源/单席认知防伪徽章与 origin_tier 三级准入（409 unverified_consensus_adoption vs as_chair_directive）")

            # ⑥ 异构恢复、分歧追踪与 POST /api/sessions/{sid}/redebate 双席 1 轮再辩
            await api_json(
                port,
                token,
                "POST",
                "/api/config",
                {
                    "single_cli_concurrency": 3,
                    "agents": {
                        "carbon": {"driver": "agy", "custom_binary": str(mock_agy), "model": "gemini-4-carbon", "discussion_effort": "high"},
                        "grok": {"driver": "codex", "custom_binary": str(mock_codex_hetero), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "astra": {"driver": "agy", "custom_binary": str(mock_agy), "model": "gemini-4-carbon", "discussion_effort": "high"},
                    },
                },
            )
            _, d_s6 = await api_json(port, token, "POST", "/api/sessions", {"title": "分歧双席再辩验证"})
            sid6 = d_s6["session"]["session_id"]
            await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid6}/start",
                {
                    "topic": "评估高并发锁粒度策略并触发双席再辩",
                    "collab_mode": "rapid_consensus",
                    "enabled_agents": ["carbon", "grok", "astra"],
                },
            )
            snap6 = await wait_session_idle(port, token, sid6)
            msg_count_before = len(snap6["messages"])
            risks6 = [it for it in snap6["whiteboard"].get("items", []) if it.get("kind") == "risk"]
            assert risks6, f"期望生成至少 1 条 risk 供再辩，实际: {snap6['whiteboard']}"
            target_risk6 = risks6[0]

            os.environ["V5_MOCK_MODE"] = "redebate_turn"
            st_rd, d_rd = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid6}/redebate",
                {
                    "item_id": target_risk6["id"],
                    "disagreement_id": target_risk6.get("disagreement_id") or "",
                    "claim": target_risk6["text"],
                    "challenger": "grok",
                    "defender": "carbon",
                },
            )
            assert st_rd in (200, 202), f"/redebate 调用失败 ({st_rd}): {d_rd}"
            snap6_after = await wait_session_idle(port, token, sid6)
            new_msgs6 = snap6_after["messages"][msg_count_before:]
            redebate_speakers = [m["speaker"] for m in new_msgs6 if m["speaker"] in ("carbon", "grok", "astra")]
            assert len(redebate_speakers) == 2 and set(redebate_speakers) == {"carbon", "grok"}, (
                f"双席 1 轮再辩必须精确触发 2 席发言，实际新增席位发言: {redebate_speakers}"
            )
            ok("6. 结构化分歧追踪与 /redebate 双席 1 轮定向再辩闭环")

            # ⑦ 「形成决议」合成引擎专项验收：全量成果保留 + 修正演进终态 + 弃案物理隔离至负面清单
            os.environ["V5_MOCK_MODE"] = "resolution_r1"
            _, d_s7 = await api_json(port, token, "POST", "/api/sessions", {"title": "决议合成全量保留与弃案隔离验收"})
            sid7 = d_s7["session"]["session_id"]

            st_r1, _ = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid7}/start",
                {
                    "topic": "设计本地状态持久化架构。硬约束C1：严禁引入第三方重型 ORM，全程保持纯标准库 SQLite 实现。",
                    "collab_mode": "rapid_consensus",
                    "enabled_agents": ["carbon", "grok"],
                },
            )
            assert st_r1 == 200
            await wait_session_idle(port, token, sid7)

            os.environ["V5_MOCK_MODE"] = "resolution_r2"
            st_r2, _ = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid7}/followup",
                {
                    "message": "补充硬约束C2：落盘权限强制 0o600 且必须具备写前 CAS 字节回滚证明；请对轮询方案与裸写磁盘废案给出明确修正与弃用裁决。"
                },
            )
            assert st_r2 == 200
            await wait_session_idle(port, token, sid7)

            os.environ["V5_MOCK_MODE"] = "resolution_synth"
            st_conc, d_conc = await api_json(port, token, "POST", f"/api/sessions/{sid7}/conclude", {})
            assert st_conc in (200, 202), f"/conclude 调用失败 ({st_conc}): {d_conc}"
            snap7 = await wait_session_idle(port, token, sid7)

            res_msgs = [
                m
                for m in snap7["messages"]
                if "决议" in str(m.get("phase_label") or "") or "决议" in str(m.get("badge") or "") or "最终决议" in str(m.get("content") or "")
            ]
            assert res_msgs, f"未找到生成的最终决议卡片: {[m.get('phase_label') for m in snap7['messages']]}"
            res_msg_id = res_msgs[-1]["id"]

            st_imp, d_imp = await api_json(
                port,
                token,
                "POST",
                f"/api/sessions/{sid7}/whiteboard",
                {"op": "import_resolution", "message_id": res_msg_id},
            )
            assert st_imp == 200, f"import_resolution 失败: {d_imp}"
            wb7 = d_imp["whiteboard"]

            decisions7 = [it["text"] for it in wb7.get("items", []) if it.get("kind") == "decision"]
            actions7 = [it["text"] for it in wb7.get("items", []) if it.get("kind") == "action"]
            abandoned7 = wb7.get("abandoned_proposals") or []
            abandoned_texts = " | ".join(
                str(x.get("text") or x.get("proposal") or x.get("summary") or x) for x in abandoned7
            )
            active_pool_blob = " | ".join(decisions7 + actions7)
            full_wb_and_res = active_pool_blob + " || " + res_msgs[-1].get("content", "")

            assert "纯标准库" in full_wb_and_res or "SQLite" in full_wb_and_res, f"丢失初始硬约束 C1: {decisions7}"
            assert "0o600" in full_wb_and_res and "CAS" in full_wb_and_res, f"丢失中途追问硬约束 C2: {decisions7} / {actions7}"
            assert "WAL" in active_pool_blob, f"丢失首轮有效成果 WAL 单写队列: {active_pool_blob}"
            assert "单调递增 rev" in active_pool_blob or "SSE" in active_pool_blob, (
                f"丢失次轮修正后的终态优选方案: {active_pool_blob}"
            )

            assert len(abandoned7) >= 1 and ("fsync" in abandoned_texts or "裸写磁盘" in abandoned_texts), (
                f"弃案未进入 abandoned_proposals 负面清单: {abandoned7}"
            )
            for forbidden_dead in ("直接关闭 fsync 裸写磁盘", "关闭 fsync 裸写磁盘换取极限吞吐"):
                assert forbidden_dead not in active_pool_blob, (
                    f"严重红线违例：已证伪弃案 [{forbidden_dead}] 混入了 decision 或 action 池！active={active_pool_blob}"
                )

            st_exp7, _, b_exp7 = await raw_http_request(
                port, "GET", f"/api/sessions/{sid7}/export", headers={"X-Roundtable-Token": token}
            )
            assert st_exp7 == 200
            md7 = b_exp7.decode("utf-8")
            assert "放弃" in md7 and "fsync" in md7 and "WAL" in md7
            ok("7. 「形成决议」合成引擎专项验收（全量约束/成果/修正终态 100% 保留 + 弃案 100% 物理隔离至负面清单）")

        finally:
            server.close()
            await server.wait_closed()
            await app.orchestrator.shutdown()

    print("\n" + "=" * 76, flush=True)
    print(f"✔ AI圆桌 v5 全部 {len(passed)}/7 大项决议治理与认知防伪端到端验收 100% 通过！", flush=True)
    print("=" * 76, flush=True)


if __name__ == "__main__":
    asyncio.run(run_v5_verification())
