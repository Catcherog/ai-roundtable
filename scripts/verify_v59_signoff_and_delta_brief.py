#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 v5.9 — 条件式质询方验收、倒序终态快照、逆向对照会签、差集自包含决策包与主刀契约直通全链路回归验收套件
(scripts/verify_v59_signoff_and_delta_brief.py)

覆盖验收：
1. 倒序终态精华快照（修复旧版正序 re.search 抓第 1 轮未纠偏旧契约、丢弃答辩轮新版终态契约的逆序覆盖漏洞）；
2. 条件式质询方答辩验收（接受修正零额外轮次直通；反证拒改转入 pending_challenger_signoff 唤醒质询方短验收，区分 verified_by_challenger 与 disputed_locked）；
3. 自然小节 `@席位` 无方括号宽容解析 + `code_review` / `divergent_convergent` / `adversarial_review` 全模式补齐答辩与验收闭环；
4. `/redebate` 双席焦点再辩拒绝修改防假闭环（反证拒改时保持 resolved=False / disputed_locked）；
5. 逆向对照会签（审稿席位注入本席终态契约与名下 D# 质询锚点）+ 差集契约守卫（Delta Guard：已合入契约零重复、漏合入代码块自动补录）；
6. 决议脏状态防呆（决议后发生追问/再辩自动标记 resolution_stale=True 并在决策包顶部置顶变更增量，重算决议后自动清零）；
7. `auto_preview_exec` 统一收口无损决议管线 + 主刀执行器注入完整决议契约、差集代码契约与防回流弃案负面禁令；
8. 热会话单席就地恢复 `invalidate_seen_message_id` 跨席已读缓存精确失效与前端 `质询验收` 分桶对齐。
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class _MemWriter:
    def __init__(self) -> None:
        self.buf = bytearray()
        self._closing = False

    def write(self, data: bytes) -> None:
        self.buf.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        self._closing = True

    async def wait_closed(self) -> None:
        return


async def mem_http(
    app: Any,
    token: str,
    method: str,
    target: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, str], bytes]:
    hdrs = {"Host": "127.0.0.1:18809", "X-Roundtable-Token": token}
    body = b""
    if payload is not None:
        hdrs["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Length"] = str(len(body))
    raw_req = ("\r\n".join([f"{method} {target} HTTP/1.1"] + [f"{k}: {v}" for k, v in hdrs.items()]) + "\r\n\r\n").encode("latin-1") + body
    reader = asyncio.StreamReader(limit=65536)
    reader.feed_data(raw_req)
    reader.feed_eof()
    writer = _MemWriter()
    await app.handle_client(reader, writer)
    raw_resp = bytes(writer.buf)
    sep = raw_resp.find(b"\r\n\r\n")
    head_lines = raw_resp[:sep].decode("latin-1").split("\r\n")
    st = int(head_lines[0].split(" ", 2)[1])
    resp_hdrs = {}
    for hl in head_lines[1:]:
        if ":" in hl:
            k, v = hl.split(":", 1)
            resp_hdrs[k.strip().lower()] = v.strip()
    return st, resp_hdrs, raw_resp[sep + 4 :]


async def mem_json(
    app: Any,
    token: str,
    method: str,
    target: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, Any]]:
    st, _, rb = await mem_http(app, token, method, target, payload)
    return st, (json.loads(rb.decode("utf-8")) if rb else {})


def make_exec(path: Path, code: str) -> Path:
    path.write_text(textwrap.dedent(code).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


async def wait_idle(app: Any, sid: str, max_iters: int = 160) -> Any:
    sess = app.orchestrator.get_session(sid)
    assert sess is not None
    for _ in range(max_iters):
        await asyncio.sleep(0.04)
        if not sess.is_busy and sess.exec_state == "idle":
            return sess
    raise AssertionError(f"Session {sid} did not become idle in time (stage={sess.stage}, exec={sess.exec_state})")


async def run_v59_suite() -> None:
    passed: List[str] = []

    def ok(label: str, detail: str = "") -> None:
        suf = f" ({detail})" if detail else ""
        print(f"  [PASS] {label}{suf}", flush=True)
        passed.append(label)

    # 静态检查前端质询验收阶段分桶与脏态提示已同步
    app_js_src = (ROOT_DIR / "frontend" / "app.js").read_text(encoding="utf-8")
    assert '"质询验收"' in app_js_src, "frontend/app.js CROSS_REBUTTAL_PHASES_SET 未同步注册『质询验收』阶段"
    assert "resolution_stale" in app_js_src, "frontend/app.js 未同步接入 resolution_stale 脏状态提示"

    with tempfile.TemporaryDirectory(prefix="ai_rt_v59_verify_") as tmp_str:
        tmp_root = Path(tmp_str).resolve()
        rt_home = tmp_root / "rt_home"
        proj_dir = tmp_root / "demo_proj"
        rt_home.mkdir(parents=True, exist_ok=True)
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "engine.py").write_text("def sync_state():\n    return True\n", encoding="utf-8")

        os.environ["AI_ROUNDTABLE_HOME"] = str(rt_home)
        os.environ["AI_ROUNDTABLE_FAST_TEST"] = "1"

        prompt_log_path = tmp_root / "v59_prompts.jsonl"

        mock_cli = make_exec(
            tmp_root / "mock_cli_v59",
            f"""
            #!/usr/bin/env python3
            import json, os, sys
            from pathlib import Path
            args = sys.argv[1:]
            if "--version" in args:
                print("mock-cli-v59 5.9.0")
                sys.exit(0)
            if "--help" in args:
                print("Usage: codex exec resume --json --sandbox read-only -m MODEL")
                sys.exit(0)
            prompt = sys.stdin.read()
            seat_id = os.environ.get("AI_ROUNDTABLE_SEAT_ID", "unknown")
            scn = os.environ.get("V59_SCENARIO", "full_loop")
            log_p = Path({str(prompt_log_path)!r})
            with log_p.open("a", encoding="utf-8") as f:
                f.write(json.dumps({{"seat": seat_id, "scenario": scn, "prompt": prompt}}, ensure_ascii=False) + "\\n")

            if "请严格以「全部已确认共识与约束」+「已勾选的待执行任务项」为核心执行范围完成交付" in prompt:
                txt = "执行预演完成：已读取完整决议契约与防回流禁令。"
                print(txt)
                sys.exit(0)

            if scn == "full_loop":
                if "【当前环节：独立立论" in prompt:
                    if seat_id == "carbon":
                        txt = (
                            "首席初评：建议采用初版裸写锁表。\\n\\n"
                            "### 本席独创贡献与关键契约\\n"
                            "```sql\\n-- LEGACY_DRAFT_SCHEMA_V1\\nCREATE TABLE raw_lock_v1 (id INT);\\n```\\n"
                            "[白板: 共识=采用初版状态表 | 任务=落地状态契约与压测脚本]\\n"
                            "[状态: 初评完成 | 共识: 需继续 | 点名: 无]"
                        )
                    elif seat_id == "grok":
                        txt = (
                            "红队初评：强调跨机房脑裂隔离阈值。\\n\\n"
                            "### 本席独创贡献与关键契约\\n"
                            "- 脑裂隔离心跳上限：`fencing_lease_ms <= 250`\\n"
                            "[白板: 风险=跨机房脑裂双主写入隐患]\\n"
                            "[状态: 初评完成 | 共识: 需继续 | 点名: 无]"
                        )
                    else:
                        txt = (
                            "研发初评：提供退避抖动矩阵算法。\\n\\n"
                            "### 本席独创贡献与关键契约\\n"
                            "```python\\nBACKOFF_JITTER_MATRIX_V59 = (20, 50, 120, 300)\\n```\\n"
                            "[白板: 任务=实现退避抖动重试器]\\n"
                            "[状态: 初评完成 | 共识: 需继续 | 点名: 无]"
                        )
                elif "【当前环节：全覆盖对等互评与纠偏矩阵" in prompt:
                    if seat_id == "vega":
                        # 测试自然 Markdown 小节下无方括号 `- @席位：` 宽容解析 + 接受修正分支 (D1)
                        txt = (
                            "### 他席洞察吸收\\n"
                            "- @研发主程：退避抖动梯度简洁可控，可直接复用。\\n\\n"
                            "### 核心纠偏与盲区证伪\\n"
                            "- @首席架构：先强述其单表锁简单性，但裸写无 fencing token 会导致旧主覆盖新主数据，建议改为单调递增 fencing_epoch 原子表。\\n"
                            "[状态: 互评完成 | 共识: 需继续 | 点名: 首席架构]"
                        )
                    elif seat_id == "grok":
                        # 发起 D2（后续将被质询验收通过）
                        txt = (
                            "[吸收 @研发主程：四级抖动窗口避免惊群效应]\\n"
                            "[反驳 @首席架构：批量刷盘间隔 50ms 在 HDD 上可能放大尾延迟]\\n"
                            "[状态: 互评完成 | 共识: 需继续 | 点名: 首席架构]"
                        )
                    elif seat_id == "astra":
                        # 发起 D3（后续将被质询维持异议锁定）
                        txt = (
                            "[反驳 @首席架构：跨机房异步复制缺少 quorum 多数派确认，断网切换会丢最后 1 秒事务]\\n"
                            "[状态: 互评完成 | 共识: 需继续 | 点名: 首席架构]"
                        )
                    else:
                        txt = (
                            "[吸收 @红队审计：250ms 租约熔断边界清晰]\\n"
                            "[无异议]\\n"
                            "[状态: 互评完成 | 共识: 已达成 | 点名: 无]"
                        )
                elif "【当前环节：D1..Dn 编号争议逐项交锋闭环" in prompt:
                    import re as _re
                    c_map = dict(_re.findall(r"\[(D\d+)\]\s*@([^\s：:]+)\s*质询", prompt))
                    code_by_name = dict((val_n, key_d) for key_d, val_n in c_map.items())
                    d_vega = code_by_name.get("交互设计", "D3")
                    d_grok = code_by_name.get("红队审计", "D1")
                    d_astra = code_by_name.get("研发主程", "D2")
                    # 对交互设计(vega)接受修正（故意包含“不成立”字样验证头部优先级），对红队审计(grok)/研发主程(astra)主张量化反证拒改！
                    txt = (
                        f"[回应 {{d_vega}}：接受修正 | 原裸写假设不成立，引入单调递增 fencing_epoch 原子校验列]\\n"
                        "[修正原方案：CREATE TABLE raw_lock_v1 (id INT) -> CREATE TABLE fencing_ledger_v3 (epoch BIGINT PRIMARY KEY, fencing_token TEXT NOT NULL)]\\n"
                        "[放弃原方案：LEGACY_DRAFT_SCHEMA_V1 CREATE TABLE raw_lock_v1]\\n"
                        f"[回应 {{d_grok}}：量化反证 | 目标部署环境 100% 为 NVMe SSD，实测 P99 刷盘仅 0.4ms，无需修改异步队列]\\n"
                        f"[回应 {{d_astra}}：量化反证 | 业务侧允许最多 1 秒 RPO，维持异步复制无需引入多数派性能损耗]\\n\\n"
                        "### 本席独创贡献与关键契约\\n"
                        "```sql\\n-- FINAL_ATOMIC_SCHEMA_V3\\nCREATE TABLE fencing_ledger_v3 (epoch BIGINT PRIMARY KEY, fencing_token TEXT NOT NULL);\\n```\\n"
                        "[状态: 答辩完成 | 共识: 需继续 | 点名: 无]"
                    )
                elif "【当前环节：质询方答辩验收" in prompt:
                    import re as _re
                    m_code = _re.search(r"\[(D\d+)\]\s*你原质询", prompt)
                    my_d = m_code.group(1) if m_code else ("D1" if seat_id == "grok" else "D2")
                    if seat_id == "grok":
                        txt = f"[验收 {{my_d}}：认可闭环 | NVMe 实测 P99 0.4ms 反证成立，原尾延迟疑虑不成立，已无残余阻塞]\\n[状态: 验收通过 | 共识: 已达成 | 点名: 无]"
                    elif seat_id == "astra":
                        txt = f"[验收 {{my_d}}：维持异议 | 账务结算流水严禁 1 秒 RPO 丢单，断网降级时必须切换半同步多数派预案]\\n[状态: 保留分歧 | 共识: 需继续 | 点名: 无]"
                    else:
                        txt = "[无异议]\\n[状态: 验收完成 | 共识: 已达成 | 点名: 无]"
                elif "【当前环节：终稿多席块级会签" in prompt:
                    txt = "[终稿无遗漏]\\n[状态: 终稿核验完成 | 共识: 已达成 | 点名: 无]"
                elif "【当前环节：形成 6 段式无损《会议最终决议》" in prompt or "【当前环节：终稿核验修订定稿" in prompt:
                    # 主笔故意只写入 FINAL_ATOMIC_SCHEMA_V3，漏写研发主程的 BACKOFF_JITTER_MATRIX_V59，检验差集补录（Delta Guard）！
                    txt = (
                        "## 一、核心决策总览（TL;DR）\\n"
                        "- 采用 fencing_ledger_v3 租约原子状态表。\\n\\n"
                        "## 二、已确认共识与完整实施方案\\n"
                        "```sql\\n-- FINAL_ATOMIC_SCHEMA_V3\\nCREATE TABLE fencing_ledger_v3 (epoch BIGINT PRIMARY KEY, fencing_token TEXT NOT NULL);\\n```\\n\\n"
                        "## 三、多 AI 思想精华与纠偏演进表\\n"
                        "| 核心议题 | 初始方案 | 纠偏来源与盲区指出 | 终态采纳方案与精华归属 |\\n"
                        "| :--- | :--- | :--- | :--- |\\n"
                        "| 脑裂防护 | 裸写锁表 | 交互设计指出旧主覆盖 | fencing_ledger_v3（首席架构 + 交互设计） |\\n\\n"
                        "## 四、已确认放弃与证伪淘汰方案（防回流负面清单）\\n"
                        "- [放弃原方案：LEGACY_DRAFT_SCHEMA_V1 CREATE TABLE raw_lock_v1] —— 缺少 fencing 保护。\\n\\n"
                        "## 五、高价值少数派意见与条件触发预案\\n"
                        "- 涉及核心账务流水时切换半同步多数派确认（来源：研发主程）。\\n\\n"
                        "## 六、边界风险防线、参会披露与文件级待执行任务清单\\n"
                        "- [ ] 落地 fencing_ledger_v3 状态表与 250ms 租约熔断\\n\\n"
                        "[白板: 共识=采用 fencing_ledger_v3 原子状态表 | 弃案=LEGACY_DRAFT_SCHEMA_V1 CREATE TABLE raw_lock_v1 | 任务=落地 fencing_ledger_v3 状态表与 250ms 租约熔断]\\n"
                        "[状态: 决议已成 | 共识: 已达成 | 点名: 无]"
                    )
                elif "【当前环节：响应主持人追问" in prompt:
                    txt = (
                        "收到主持人补充约束：新增只读备库流量熔断上限 `replica_lag_ms <= 500`。\\n"
                        "[白板: 共识=新增只读备库延迟熔断阈值 replica_lag_ms <= 500]\\n"
                        "[状态: 追问已响应 | 共识: 已达成 | 点名: 无]"
                    )
                else:
                    txt = "阶段收敛完成。\\n[状态: 已收敛 | 共识: 已达成 | 点名: 无]"

            elif scn == "cr_and_redebate_refuse":
                if "【当前环节：代码审查 · 调用链交叉核验" in prompt:
                    if seat_id == "grok":
                        txt = "[反驳 @首席架构：engine.py 中 sync_state 未加跨协程重入锁]\\n[状态: 核验存疑 | 共识: 需继续 | 点名: 首席架构]"
                    else:
                        txt = "[无异议]\\n[状态: 核验完成 | 共识: 已达成 | 点名: 无]"
                elif "【当前环节：D1..Dn 编号争议逐项交锋闭环" in prompt:
                    txt = "[回应 D1：接受修正 | 为 sync_state 增加 asyncio.Lock 保护]\\n[修正原方案：无锁 sync_state -> 增加 asyncio.Lock 互斥保护]\\n[状态: 答辩修正 | 共识: 已达成 | 点名: 无]"
                elif "【当前环节：双席定向再辩" in prompt:
                    if seat_id == "carbon":
                        txt = "维持原方案反证：单协程同步函数无需加锁，拒绝修改。\\n[状态: 拒绝修改 | 共识: 需继续 | 点名: 红队审计]"
                    else:
                        txt = "若后续引入 await 点仍会重入，维持异议。\\n[状态: 维持质疑 | 共识: 需继续 | 点名: 首席架构]"
                else:
                    txt = (
                        "源码定位完成：`engine.py:sync_state`。\\n"
                        "[白板: 风险=sync_state 潜在并发重入隐患 | 任务=核验 engine.py 锁保护]\\n"
                        "[状态: 定位完成 | 共识: 需继续 | 点名: 无]"
                    )
            else:
                txt = (
                    "快速合议要点输出。\\n"
                    "### 本席独创贡献与关键契约\\n"
                    "```python\\nAUTO_EXEC_CONTRACT_CONST = 42\\n```\\n"
                    "[放弃原方案：DANGEROUS_EVAL_EXEC_PATH]\\n"
                    "[白板: 共识=启用安全沙箱常量 42 | 弃案=DANGEROUS_EVAL_EXEC_PATH | 任务=更新 engine.py 常量定义]\\n"
                    "[状态: 完成 | 共识: 已达成 | 点名: 无]"
                )

            print(json.dumps({{"type": "thread.started", "thread_id": f"tid_{{seat_id}}"}}))
            print(json.dumps({{"type": "item.completed", "item": {{"id": "m1", "type": "agent_message", "text": txt}}}}))
            print(json.dumps({{"type": "turn.completed"}}))
            """,
        )

        from backend.server import AsyncHTTPServer

        tok = "v59_secret_token"
        app = AsyncHTTPServer(
            host="127.0.0.1",
            port=18809,
            workspace_dir=str(proj_dir),
            boot_token=tok,
            boot_id="boot_v59",
        )

        try:
            bin_c = make_exec(tmp_root / "bin_c", mock_cli.read_text("utf-8"))
            bin_g = make_exec(tmp_root / "bin_g", mock_cli.read_text("utf-8"))
            bin_a = make_exec(tmp_root / "bin_a", mock_cli.read_text("utf-8"))
            bin_v = make_exec(tmp_root / "bin_v", mock_cli.read_text("utf-8"))

            st_cfg, _ = await mem_json(
                app,
                tok,
                "POST",
                "/api/config",
                {
                    "carbon_name": "首席架构",
                    "grok_name": "红队审计",
                    "astra_name": "研发主程",
                    "vega_name": "交互设计",
                    "single_cli_concurrency": 4,
                    "agents": {
                        "carbon": {"driver": "codex", "custom_binary": str(bin_c), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "grok": {"driver": "codex", "custom_binary": str(bin_g), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "astra": {"driver": "codex", "custom_binary": str(bin_a), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "vega": {"driver": "codex", "custom_binary": str(bin_v), "model": "gpt-6-astra", "discussion_effort": "high"},
                    },
                },
            )
            assert st_cfg == 200

            # 场景一：验证自然小节 @席位 解析 + 条件式质询方验收（D1 直通免验、D2 验收闭环、D3 维持异议锁定）+ 倒序终态快照
            os.environ["V59_SCENARIO"] = "full_loop"
            _, d_s1 = await mem_json(app, tok, "POST", "/api/sessions", {"title": "v5.9 全链路质询验收与差集决策包验证"})
            sid1 = d_s1["session"]["session_id"]
            st_start, _ = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid1}/start",
                {
                    "topic": "设计跨机房防脑裂状态账本与重试机制",
                    "collab_mode": "deep_deliberation",
                    "enabled_agents": ["carbon", "grok", "astra", "vega"],
                },
            )
            assert st_start == 200
            sess1 = await wait_idle(app, sid1)

            dis_by_chal = {d["challenger"]: d for d in sess1.whiteboard.get("disagreements", []) if isinstance(d, dict)}
            assert {"vega", "grok", "astra"}.issubset(dis_by_chal.keys()), f"小节 @席位 或内联标签未完整建账: {dis_by_chal}"
            d_vega_obj = dis_by_chal["vega"]
            d_grok_obj = dis_by_chal["grok"]
            d_astra_obj = dis_by_chal["astra"]

            # vega 在自然小节下无方括号提出，carbon 选择接受修正 -> 直通闭环，且不应唤醒 vega 跑质询验收！
            assert d_vega_obj["resolved"] is True and d_vega_obj.get("verification_state") == "accepted_by_defender", (
                f"接受修正应直通闭环（不被尾部“不成立”字样误判）: {d_vega_obj}"
            )
            signoff_msgs = [m for m in sess1.messages if m.get("phase_label") == "质询验收"]
            signoff_speakers = {m["speaker"] for m in signoff_msgs}
            assert signoff_speakers == {"grok", "astra"}, (
                f"条件式质询验收仅应唤醒被反证拒改的 grok/astra，不应唤醒已接受修正的 vega: {signoff_speakers}"
            )
            assert d_grok_obj["resolved"] is True and d_grok_obj.get("verification_state") == "verified_by_challenger", (
                f"经质询方认可闭环后应标为 verified_by_challenger（不被尾部“不成立/残余”字样误判）: {d_grok_obj}"
            )
            assert d_astra_obj["resolved"] is False and d_astra_obj.get("verification_state") == "disputed_locked", (
                f"经质询方维持异议后严禁被自证销账，必须保持 resolved=False & disputed_locked: {d_astra_obj}"
            )
            d_astra_code = d_astra_obj["issue_code"]
            absorbed_texts = [h["text"] for h in sess1.whiteboard.get("absorbed_highlights", [])]
            assert any("退避抖动梯度简洁可控" in t for t in absorbed_texts), (
                f"自然小节 `### 他席洞察吸收` 下的 `- @研发主程：...` 未被提取: {absorbed_texts}"
            )
            ok("1. 条件式质询方验收三态机（接受修正零延迟直通 / 反证拒改按需唤醒 / 认可闭环 vs 维持异议防自证销账）与自然小节 @席位 解析")

            # 验证倒序终态快照：FINAL_ATOMIC_SCHEMA_V3 必须保留，已被淘汰的初版 LEGACY_DRAFT_SCHEMA_V1 绝不能倒灌进第 7 节快照！
            dossier_str, dossier_meta = app.orchestrator._build_resolution_synthesis_dossier(sess1)
            sec7_part = dossier_str.split("7) 逐席独创思想", 1)[-1]
            assert "FINAL_ATOMIC_SCHEMA_V3" in sec7_part, f"倒序快照未抓到第 3 轮重写后的终态 SQL 契约: {sec7_part}"
            assert "LEGACY_DRAFT_SCHEMA_V1" not in sec7_part, f"已被修正淘汰的第 1 轮初版旧契约倒灌进了无损快照: {sec7_part}"
            assert dossier_meta.get("verified_disagreement_count") == 1 and dossier_meta.get("disputed_disagreement_count") == 1
            ok("2. 倒序终态精华快照提取（最新纠偏契约覆盖第 1 轮未纠偏草稿，已弃旧代码块零倒灌）")

            # 触发「形成决议」：验证逆向对照会签锚点注入 + 差集契约守卫（Delta Guard）
            st_conc, _ = await mem_json(app, tok, "POST", f"/api/sessions/{sid1}/conclude", {})
            assert st_conc in (200, 202)
            sess1 = await wait_idle(app, sid1)

            all_logs = [json.loads(ln) for ln in prompt_log_path.read_text("utf-8").splitlines() if ln.strip()]
            astra_audits = [
                x for x in all_logs if x["seat"] == "astra" and "【当前环节：终稿多席块级会签" in x["prompt"]
            ]
            assert astra_audits, "未触发研发主程终稿会签"
            audit_prompt_a = astra_audits[-1]["prompt"]
            assert "【本席专属逆向核对清单" in audit_prompt_a and "BACKOFF_JITTER_MATRIX_V59" in audit_prompt_a and d_astra_code in audit_prompt_a, (
                f"逆向会签未向审稿席注入其本席终态契约与发起的 {d_astra_code} 争议锚点: {audit_prompt_a}"
            )

            st_brief, d_brief = await mem_json(app, tok, "GET", f"/api/sessions/{sid1}/decision-brief")
            assert st_brief == 200 and d_brief.get("resolution_stale") is False
            brief_md = d_brief["markdown"]
            # FINAL_ATOMIC_SCHEMA_V3 已在主笔终稿正文中，差集补录不应重复粘贴第 2 次；
            # 而主笔漏写的 BACKOFF_JITTER_MATRIX_V59 必须被 Delta Guard 自动补录在文末！
            assert brief_md.count("FINAL_ATOMIC_SCHEMA_V3") == 1, (
                f"终稿已包含的 SQL 契约不应在文末重复粘贴: count={brief_md.count('FINAL_ATOMIC_SCHEMA_V3')}"
            )
            assert "### 未合入独创技术契约与代码块差集补录" in brief_md and "BACKOFF_JITTER_MATRIX_V59" in brief_md, (
                f"主笔漏写的研发主程独创代码契约未被 Delta Guard 自动补录至决策包: {brief_md}"
            )
            assert f"[{d_astra_code} 质询维持异议]" in brief_md and "账务结算流水严禁 1 秒 RPO 丢单" in brief_md, (
                f"决策包未完整保留 {d_astra_code} 答辩反证与质询方维持异议链条: {brief_md}"
            )
            ok("3. 逆向对照会签锚点注入与差集自包含决策包（已合入契约零重复、漏合入代码自动补录、保留分歧全链路可溯源）")

            # 验证决议脏状态防呆（Stale Resolution）：决议后发起追问 -> 自动标记 stale 并置顶增量 -> 重跑决议后恢复干净态
            st_int, _ = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid1}/interrupt",
                {"message": "补充硬约束：只读备库复制延迟超过 500ms 必须自动摘除读流量"},
            )
            assert st_int in (200, 202)
            sess1 = await wait_idle(app, sid1)

            st_stale_b, d_stale_b = await mem_json(app, tok, "GET", f"/api/sessions/{sid1}/decision-brief")
            assert st_stale_b == 200
            assert d_stale_b.get("resolution_stale") is True and d_stale_b.get("post_resolution_msg_count", 0) >= 2, (
                f"决议后发生追问研讨必须标记 resolution_stale=True: {d_stale_b}"
            )
            stale_md = d_stale_b["markdown"]
            pos_delta = stale_md.find("## 零、决议后最新追问与方案纠偏增量")
            pos_old_res = stale_md.find("## 一、核心决策总览")
            assert 0 < pos_delta < pos_old_res and "replica_lag_ms <= 500" in stale_md, (
                f"过期决议未在旧正文前先行置顶最新追问增量: pos_delta={pos_delta}, pos_old_res={pos_old_res}"
            )

            await mem_json(app, tok, "POST", f"/api/sessions/{sid1}/conclude", {})
            sess1 = await wait_idle(app, sid1)
            _, d_fresh_b = await mem_json(app, tok, "GET", f"/api/sessions/{sid1}/decision-brief")
            assert d_fresh_b.get("resolution_stale") is False, "重新合成决议后 resolution_stale 必须复位为 False"
            ok("4. 决议后追问/再辩脏状态防呆（resolution_stale 实时置位 + 顶部置顶最新增量 + 重算决议自动复位）")

            # 场景二：验证 code_review 补齐答辩闭环 + /redebate 双席再辩拒绝修改防假闭环 + 热会话重试缓存失效
            os.environ["V59_SCENARIO"] = "cr_and_redebate_refuse"
            _, d_s2 = await mem_json(app, tok, "POST", "/api/sessions", {"title": "代码审查答辩闭环与再辩拒改测试"})
            sid2 = d_s2["session"]["session_id"]
            await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid2}/start",
                {
                    "topic": "审查 engine.py 中 sync_state 并发安全性",
                    "collab_mode": "code_review",
                    "enabled_agents": ["carbon", "grok"],
                },
            )
            sess2 = await wait_idle(app, sid2)
            cr_phases = [m.get("phase_label") for m in sess2.messages]
            assert "定向答辩" in cr_phases, f"code_review 产生 D1 争议后未触发定向答辩闭环: {cr_phases}"

            # 注入一条新争议并发起双席再辩（模拟被质询方拒绝修改）
            sess2.whiteboard.setdefault("disagreements", []).append(
                {
                    "disagreement_id": "d_manual_refuse",
                    "issue_code": "D9",
                    "challenger": "grok",
                    "challenger_name": "红队审计",
                    "target": "carbon",
                    "target_name": "首席架构",
                    "claim": "sync_state 未处理异步取消异常",
                    "resolved": False,
                }
            )
            st_rd2, _ = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid2}/redebate",
                {
                    "disagreement_id": "d_manual_refuse",
                    "claim": "sync_state 未处理异步取消异常",
                    "challenger": "grok",
                    "defender": "carbon",
                },
            )
            assert st_rd2 in (200, 202)
            sess2 = await wait_idle(app, sid2)
            d9_after = next(d for d in sess2.whiteboard["disagreements"] if d.get("issue_code") == "D9")
            assert d9_after["resolved"] is False and d9_after.get("verification_state") == "disputed_locked", (
                f"双席再辩中被质询方拒绝修改时严禁强制标为 resolved=True: {d9_after}"
            )

            # 验证 invalidate_seen_message_id 精确清理同会话所有热席位的已读缓存
            app.orchestrator.runner._seen_msg_ids[(sid2, "grok")] = {"m_retry_1", "m_keep_2"}
            app.orchestrator.runner._seen_msg_ids[(sid2, "astra")] = {"m_retry_1"}
            app.orchestrator.runner.invalidate_seen_message_id(sid2, "m_retry_1")
            assert "m_retry_1" not in app.orchestrator.runner._seen_msg_ids[(sid2, "grok")]
            assert "m_keep_2" in app.orchestrator.runner._seen_msg_ids[(sid2, "grok")]
            assert "m_retry_1" not in app.orchestrator.runner._seen_msg_ids[(sid2, "astra")]
            ok("5. 代码审查全模式答辩闭环、双席再辩拒改防假销账与热会话就地重试缓存精确失效")

            # 场景三：验证 auto_preview_exec 统一走无损决议管线 + 主刀执行器注入完整决议契约与防回流负面禁令
            os.environ["V59_SCENARIO"] = "auto_exec_contract"
            _, d_s3 = await mem_json(app, tok, "POST", "/api/sessions", {"title": "自动预演无损决议与执行器契约直通验证"})
            sid3 = d_s3["session"]["session_id"]
            await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid3}/workspace",
                {"workspace_dir": str(proj_dir)},
            )
            await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid3}/start",
                {
                    "topic": "在 engine.py 落地安全常量并严禁回流淘汰路径",
                    "collab_mode": "rapid_consensus",
                    "auto_preview_exec": True,
                    "enabled_agents": ["carbon", "grok"],
                },
            )
            sess3 = await wait_idle(app, sid3)
            s3_phases = [m.get("phase_label") for m in sess3.messages]
            assert "最终决议" in s3_phases, f"开启 auto_preview_exec 时不应绕过无损《最终决议》合成管线: {s3_phases}"

            act3 = [it for it in sess3.whiteboard.get("items", []) if it.get("kind") == "action"]
            assert act3, f"期望生成待办任务项: {sess3.whiteboard}"
            _, d_wb_chk = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid3}/whiteboard",
                {"op": "toggle_check", "item_id": act3[0]["id"], "checked": True},
            )
            wb_chk3 = d_wb_chk["whiteboard"]
            checked_ids_3 = [it["id"] for it in wb_chk3.get("items", []) if it.get("kind") == "action" and it.get("checked")]
            st_ex3, d_ex3 = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid3}/execute",
                {
                    "allow_workspace_write": False,
                    "executor_id": "astra",
                    "expected_wb_version": wb_chk3["wb_version"],
                    "checked_action_ids": checked_ids_3,
                    "expected_workspace_dir": str(proj_dir),
                    "acknowledged_absent_agents": [],
                },
            )
            assert st_ex3 in (200, 202), f"/execute 调用未通过 ({st_ex3}): {d_ex3}"
            sess3 = await wait_idle(app, sid3)

            exec_logs = [
                json.loads(ln)
                for ln in prompt_log_path.read_text("utf-8").splitlines()
                if ln.strip() and "请严格以「全部已确认共识与约束」+「已勾选的待执行任务项」为核心执行范围完成交付" in ln
            ]
            assert exec_logs, "未捕获到主刀执行器提示词日志"
            exec_p = exec_logs[-1]["prompt"]
            assert "【四、会议决议终态技术契约与防回流负面禁令" in exec_p, f"主刀执行器未注入第四节决议契约块: {exec_p}"
            assert "AUTO_EXEC_CONTRACT_CONST = 42" in exec_p, f"主刀执行器丢失了未截断代码块契约: {exec_p}"
            assert "DANGEROUS_EVAL_EXEC_PATH" in exec_p and "[严禁回流实现]" in exec_p, (
                f"主刀执行器未收到已淘汰废案防回流禁令: {exec_p}"
            )
            assert "_exec_resolution_context" not in sess3.whiteboard, "执行结束后临时上下文字段未清理"
            ok("6. auto_preview_exec 统一收口无损决议管线 & 主刀执行器直通完整代码契约与防回流禁令")

        finally:
            await app.orchestrator.shutdown()

    print("\n" + "=" * 78)
    print(f"✔ AI圆桌 v5.9 质询方验收、倒序快照、逆向会签与差集自包含决策包全部 {len(passed)}/6 大项验收 100% 通过！")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(run_v59_suite())
