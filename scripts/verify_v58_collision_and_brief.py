#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI圆桌 v5.8 — 五阶多 AI 互评纠偏闭环与无损单一真源决策包专项回归验收套件
(scripts/verify_v58_collision_and_brief.py)

覆盖验收：
1. 热会话 `_seen_msg_ids` 按消息唯一 ID 增量切片零丢席（修复第 2 轮漏看首席立论漏洞）与会话级席位名 `@点名` 解析；
2. 宽容多格式互评/吸收解析器（兼容加粗括号外冒号、列表标题）与 `D1..Dn` 编号争议精确局部销账（修复“修一漏二却全部销账”）；
3. 5 席 `adversarial_review` 红蓝编组全员参战（修复第 4–6 席闲置旁观问题）；
4. 双层无损精华卷宗（保留代码块、接口契约与独创签名快照，不作 220 字截断）与块级多席会签补丁提取合入；
5. 单一真源完整决策包三端对齐（`decision-brief` / `decision-brief?include_transcript=1` / `export`），同前缀约束零误吞，未勾选与已勾选任务、新增风险、跨席吸收精华与防回流弃案 100% 保留。
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


class _MemoryWriter:
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
    hdrs = {"Host": "127.0.0.1:18799", "X-Roundtable-Token": token}
    body = b""
    if payload is not None:
        hdrs["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Length"] = str(len(body))
    raw_req = ("\r\n".join([f"{method} {target} HTTP/1.1"] + [f"{k}: {v}" for k, v in hdrs.items()]) + "\r\n\r\n").encode("latin-1") + body
    reader = asyncio.StreamReader(limit=65536)
    reader.feed_data(raw_req)
    reader.feed_eof()
    writer = _MemoryWriter()
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


async def mem_json(app: Any, token: str, method: str, target: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
    st, _, rb = await mem_http(app, token, method, target, payload)
    return st, (json.loads(rb.decode("utf-8")) if rb else {})


def make_exec(path: Path, code: str) -> Path:
    path.write_text(textwrap.dedent(code).lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


async def wait_idle(app: Any, sid: str, max_iters: int = 120) -> Any:
    sess = app.orchestrator.get_session(sid)
    assert sess is not None
    for _ in range(max_iters):
        await asyncio.sleep(0.05)
        if not sess.is_busy and sess.exec_state == "idle":
            return sess
    raise AssertionError(f"Session {sid} did not become idle in time (stage={sess.stage})")


async def run_v58_suite() -> None:
    passed: List[str] = []

    def ok(label: str, detail: str = "") -> None:
        suf = f" ({detail})" if detail else ""
        print(f"  [PASS] {label}{suf}", flush=True)
        passed.append(label)

    with tempfile.TemporaryDirectory(prefix="ai_rt_v58_verify_") as tmp_str:
        tmp_root = Path(tmp_str).resolve()
        rt_home = tmp_root / "rt_home"
        rt_home.mkdir(parents=True, exist_ok=True)
        os.environ["AI_ROUNDTABLE_HOME"] = str(rt_home)
        os.environ["AI_ROUNDTABLE_FAST_TEST"] = "1"

        prompt_log_path = tmp_root / "codex_prompts.jsonl"

        mock_codex_warm = make_exec(
            tmp_root / "mock_codex_warm",
            f"""
            #!/usr/bin/env python3
            import json, os, sys
            from pathlib import Path
            args = sys.argv[1:]
            if "--version" in args:
                print("mock-codex-warm 5.8.0")
                sys.exit(0)
            if "--help" in args:
                print("Usage: codex exec resume --json --sandbox read-only -m MODEL")
                sys.exit(0)
            prompt = sys.stdin.read()
            seat_id = os.environ.get("AI_ROUNDTABLE_SEAT_ID", "unknown")
            log_p = Path({str(prompt_log_path)!r})
            with log_p.open("a", encoding="utf-8") as f:
                f.write(json.dumps({{"seat": seat_id, "is_resume": "resume" in args, "prompt": prompt}}, ensure_ascii=False) + "\\n")

            mode = os.environ.get("V58_MODE", "warm_collision")
            if mode == "warm_collision":
                if "【当前环节：终稿核验修订定稿" in prompt or "【当前环节：形成 6 段式无损《会议最终决议》" in prompt:
                    has_code_in_dossier = "CREATE TABLE state_ledger_v58" in prompt
                    has_block_patch = "MAX_LOCK_WAIT_MS = 150" in prompt
                    txt = (
                        "## 一、核心决策总览（TL;DR）\\n"
                        f"- 采纳双缓冲快照 + 原子引用计数屏障（dossier_code={{has_code_in_dossier}}, merged_patch={{has_block_patch}}）。\\n\\n"
                        "## 二、已确认共识与完整实施方案\\n"
                        "- 采纳首席架构 `state_ledger_v58` 表契约与研发主程零拷贝流式落盘：\\n"
                        "```sql\\nCREATE TABLE state_ledger_v58 (rev INTEGER PRIMARY KEY, payload_hash TEXT NOT NULL);\\n```\\n"
                        + ("```python\\nMAX_LOCK_WAIT_MS = 150\\n```\\n" if has_block_patch else "")
                        + "\\n## 三、多 AI 思想精华与纠偏演进表\\n"
                        "| 核心议题 | 初始方案 | 纠偏来源与盲区指出 | 终态采纳方案与精华归属 |\\n"
                        "| :--- | :--- | :--- | :--- |\\n"
                        "| 快照切换 | 直接裸切指针 | 红队审计指出悬空读 | 原子引用计数屏障（首席架构 + 红队审计） |\\n\\n"
                        "## 四、已确认放弃与证伪淘汰方案（防回流负面清单）\\n"
                        "- [放弃原方案：同步裸切无引用计数双缓冲指针] —— 高并发悬空读风险。\\n\\n"
                        "## 五、高价值少数派意见与条件触发预案\\n"
                        "- 若单节点写入 QPS > 5000，启用分片 WAL 环形缓冲（来源：红队审计）。\\n\\n"
                        "## 六、边界风险防线、参会披露与文件级待执行任务清单\\n"
                        "- 风险防线：保持 150ms 锁超时熔断；D2 大对象哈希阻塞仍需异步化评估。\\n"
                        "- [ ] 建立 state_ledger_v58 表并接入原子读引用计数屏障\\n"
                        "- [ ] 为大对象 payload_hash 增加后台线程池计算候选方案\\n\\n"
                        "[白板: 共识=采用双缓冲快照配合原子读引用计数屏障 | 弃案=同步裸切无引用计数双缓冲指针 | 风险=超过64MB大对象哈希计算需防止阻塞事件循环 | 任务=建立 state_ledger_v58 表并接入原子读引用计数屏障；为大对象 payload_hash 增加后台线程池计算候选方案]\\n"
                        "[状态: 决议已成 | 共识: 已达成 | 点名: 无]"
                    )
                elif "【当前环节：终稿多席块级会签" in prompt:
                    if seat_id == "grok":
                        txt = (
                            "### [补录章节 二：补充 150ms 熔断状态机契约]\\n"
                            "```python\\nMAX_LOCK_WAIT_MS = 150  # 红队会签强制补回阈值常量\\n```\\n"
                            "[少数派预案：当单节点写入 QPS > 5000 -> 切换为分片 WAL 环形缓冲]\\n"
                            "[状态: 终稿核验完成 | 共识: 已达成 | 点名: 无]"
                        )
                    else:
                        txt = "[终稿无遗漏]\\n[状态: 终稿核验完成 | 共识: 已达成 | 点名: 无]"
                elif "【当前环节：D1..Dn 编号争议逐项交锋闭环" in prompt:
                    # carbon 只回应 D1，故意漏答 D2，检验 D1 已闭环、D2 仍保持未决！
                    txt = (
                        "[回应 D1：接受修正 | 在双缓冲指针切换前引入原子读引用计数屏障]\\n"
                        "[修正原方案：无保护直接切换快照指针 -> 引入原子读引用计数屏障后再切换]\\n"
                        "[放弃原方案：同步裸切无引用计数双缓冲指针]\\n"
                        "[状态: 答辩完成 | 共识: 需继续 | 点名: 无]"
                    )
                elif "【当前环节：全覆盖对等互评与纠偏矩阵" in prompt:
                    if seat_id == "grok":
                        txt = (
                            "**[吸收 @首席架构]**：双缓冲状态快照读写互不阻塞，值得保留。\\n"
                            "- **反驳 @首席架构**：快照切换瞬间缺少并发读引用计数保护，高并发下存在悬空读风险。\\n"
                            "[建议修正 @首席架构]：切换前增加原子引用计数屏障。\\n"
                            "[状态: 互评完成 | 共识: 需继续 | 点名: 无]"
                        )
                    elif seat_id == "astra":
                        txt = (
                            "**[吸收 @红队审计]**：150ms 死锁熔断阈值非常关键。\\n"
                            "**[反驳 @首席架构]**：全量 payload_hash 在大于 64MB 对象上同步计算会阻塞事件循环。\\n"
                            "[状态: 互评完成 | 共识: 需继续 | 点名: 首席架构]"
                        )
                    else:
                        txt = (
                            "[吸收 @研发主程：零拷贝流式落盘管道显著降低内存峰值]\\n"
                            "[无异议]\\n"
                            "[状态: 互评完成 | 共识: 已达成 | 点名: 无]"
                        )
                elif "【当前环节：独立立论" in prompt:
                    if seat_id == "carbon":
                        txt = (
                            "首席立论：SEAT1_R1_PROPOSAL_ALPHA 采用双缓冲状态快照。\\n\\n"
                            "### 本席独创贡献与关键契约\\n"
                            "```sql\\nCREATE TABLE state_ledger_v58 (rev INTEGER PRIMARY KEY, payload_hash TEXT NOT NULL);\\n```\\n"
                            "[白板: 共识=采用双缓冲状态快照 | 任务=建立 state_ledger_v58 表]\\n"
                            "[状态: 首席立论完成 | 共识: 需继续 | 点名: 无]"
                        )
                    elif seat_id == "grok":
                        txt = (
                            "次席立论：SEAT2_R1_PROPOSAL_BETA 强调跨进程死锁超时熔断（阈值 150ms）。\\n\\n"
                            "### 本席独创贡献与关键契约\\n"
                            "- 死锁熔断阈值：`lock_wait_ms <= 150`\\n"
                            "[白板: 风险=跨进程锁等待超过 150ms 需主动熔断]\\n"
                            "[状态: 次席立论完成 | 共识: 需继续 | 点名: 无]"
                        )
                    else:
                        txt = (
                            "三席立论：SEAT3_R1_PROPOSAL_GAMMA 提供零拷贝流式落盘管道。\\n\\n"
                            "[白板: 任务=实现流式落盘写入器]\\n"
                            "[状态: 三席立论完成 | 共识: 需继续 | 点名: 无]"
                        )
                else:
                    txt = "阶段收敛完成。\\n[状态: 已收敛 | 共识: 已达成 | 点名: 无]"
            else:
                txt = (
                    f"席位 {{seat_id}} 完成对抗发言。\\n"
                    f"[吸收 @首席架构：保留核心边界设计]\\n"
                    f"[反驳 @首席架构：{{seat_id}} 提出独立压力反例]\\n"
                    "[状态: 对抗发言完成 | 共识: 需继续 | 点名: 无]"
                )

            tid = f"tid_warm_{{seat_id}}"
            print(json.dumps({{"type": "thread.started", "thread_id": tid}}))
            print(json.dumps({{"type": "item.completed", "item": {{"id": "m1", "type": "agent_message", "text": txt}}}}))
            print(json.dumps({{"type": "turn.completed"}}))
            """,
        )

        mock_agy_hetero = make_exec(
            tmp_root / "mock_agy_hetero",
            """
            #!/usr/bin/env python3
            import os, sys
            args = sys.argv[1:]
            if "--version" in args:
                print("mock-agy-hetero 5.8.0")
                sys.exit(0)
            if "--help" in args:
                print("Usage: agy -p PROMPT --model MODEL --effort EFFORT --sandbox")
                sys.exit(0)
            seat_id = os.environ.get("AI_ROUNDTABLE_SEAT_ID", "unknown")
            print(
                f"异构席位 {seat_id} 独立压力审计完成。\\n"
                "[吸收 @架构师：主链路清晰]\\n"
                f"[反驳 @架构师：{seat_id} 指出极端背压溢出反例]\\n"
                "[白板: 风险=极端背压队列溢出风险 | 任务=补齐背压限流阈值]\\n"
                "[状态: 审计完成 | 共识: 需继续 | 点名: 架构师]"
            )
            """,
        )

        from backend.server import AsyncHTTPServer

        tok = "v58_secret_token"
        app = AsyncHTTPServer(
            host="127.0.0.1",
            port=18799,
            workspace_dir="",
            boot_token=tok,
            boot_id="boot_v58",
        )

        try:
            # 配置 3 个独立二进制副本以启用真热会话（stateless=False, use_warm=True）+ 自定义会话席位称呼
            codex_c = make_exec(tmp_root / "codex_c", mock_codex_warm.read_text("utf-8"))
            codex_g = make_exec(tmp_root / "codex_g", mock_codex_warm.read_text("utf-8"))
            codex_a = make_exec(tmp_root / "codex_a", mock_codex_warm.read_text("utf-8"))

            st_cfg, _ = await mem_json(
                app,
                tok,
                "POST",
                "/api/config",
                {
                    "roster_preset": "product_studio",
                    "carbon_name": "首席架构",
                    "grok_name": "红队审计",
                    "astra_name": "研发主程",
                    "single_cli_concurrency": 3,
                    "agents": {
                        "carbon": {"driver": "codex", "custom_binary": str(codex_c), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "grok": {"driver": "codex", "custom_binary": str(codex_g), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "astra": {"driver": "codex", "custom_binary": str(codex_a), "model": "gpt-6-astra", "discussion_effort": "high"},
                        "vega": {"driver": "agy", "custom_binary": str(mock_agy_hetero), "model": "gemini-4-carbon", "discussion_effort": "high"},
                        "titan": {"driver": "agy", "custom_binary": str(mock_agy_hetero), "model": "gemini-4-carbon", "discussion_effort": "high"},
                    },
                },
            )
            assert st_cfg == 200

            # 1 & 2. 验证热会话第 2 轮零丢席 + 宽容多格式互评/吸收解析 + D1/D2 精确局部闭环
            os.environ["V58_MODE"] = "warm_collision"
            _, d_s1 = await mem_json(app, tok, "POST", "/api/sessions", {"title": "热会话碰撞与D编号闭环验收"})
            sid1 = d_s1["session"]["session_id"]

            st_go, _ = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid1}/start",
                {
                    "topic": "设计高可靠双缓冲状态持久化引擎",
                    "collab_mode": "deep_deliberation",
                    "enabled_agents": ["carbon", "grok", "astra"],
                },
            )
            assert st_go == 200
            sess1 = await wait_idle(app, sid1)

            logs = [json.loads(ln) for ln in prompt_log_path.read_text("utf-8").splitlines() if ln.strip()]
            astra_r2 = [x for x in logs if x["seat"] == "astra" and x["is_resume"] and "对等互评与纠偏矩阵" in x["prompt"]]
            assert astra_r2, f"研发主程未走热会话 resume 互评通道: {[(x['seat'], x['is_resume']) for x in logs]}"
            r2_prompt = astra_r2[0]["prompt"]
            assert "SEAT1_R1_PROPOSAL_ALPHA" in r2_prompt and "SEAT2_R1_PROPOSAL_BETA" in r2_prompt, (
                f"P0 回归失败：热会话增量切片漏掉了首轮早发席位立论！prompt={r2_prompt}"
            )
            ok("1. 热会话 `_seen_msg_ids` 精确消息 ID 切片零丢席（第 2 轮完整读取全部同侪首轮立论）")

            wb1 = sess1.whiteboard
            absorbed1 = wb1.get("absorbed_highlights") or []
            dis1 = wb1.get("disagreements") or []
            rs1 = wb1.get("round_summaries") or []
            assert len(absorbed1) >= 3, f"宽容多格式 `[吸收]` / `**[吸收 @席位]**：` 解析缺失: {absorbed1}"
            d_by_code = {d.get("issue_code"): d for d in dis1 if isinstance(d, dict)}
            assert "D1" in d_by_code and "D2" in d_by_code, f"未生成确定性编号 D1/D2: {dis1}"
            assert d_by_code["D1"]["resolved"] is True and d_by_code["D1"]["stance_delta"] == "revised", (
                f"D1 应按 `[回应 D1：接受修正]` 精确标为已闭环: {d_by_code['D1']}"
            )
            assert d_by_code["D2"]["resolved"] is False, (
                f"D2 未被回应，严禁被 `[修正原方案` 一刀切误标为 resolved=True: {d_by_code['D2']}"
            )
            assert rs1 and all("summary" in r and "highlights" in r for r in rs1), f"round_summaries 前后端字段未对齐: {rs1}"
            ok("2. 宽容多格式互评/吸收解析与 D1..Dn 编号争议精确局部闭环（D1 闭环、未答 D2 保持挂起）")

            # 3. 验证双层无损精华卷宗（保留代码块）+ 块级多席会签补丁合入 + 三大导出出口单一真源对齐
            dossier_txt, dossier_meta = app.orchestrator._build_resolution_synthesis_dossier(sess1)
            assert "CREATE TABLE state_ledger_v58" in dossier_txt, (
                f"双层无损卷宗丢失了首轮 SQL 代码块契约: {dossier_txt}"
            )
            assert dossier_meta.get("seat_essence_count", 0) >= 2

            st_conc, _ = await mem_json(app, tok, "POST", f"/api/sessions/{sid1}/conclude", {})
            assert st_conc in (200, 202)
            sess1 = await wait_idle(app, sid1)

            res_cards = [m for m in sess1.messages if m.get("phase_label") == "最终决议"]
            assert res_cards, "未生成最终决议卡"
            final_res_txt = res_cards[-1]["content"]
            assert "dossier_code=True" in final_res_txt and "merged_patch=True" in final_res_txt, (
                f"终稿未同时接收到无损代码块卷宗与多席块级会签补丁: {final_res_txt}"
            )
            assert "MAX_LOCK_WAIT_MS = 150" in final_res_txt, "块级会签补丁中的代码块未合入终稿"
            ok("3. 双层无损精华卷宗（代码块零剥离）与多席块级会签补丁（`### [补录章节 ...]`）合入终稿")

            # 注入两条共享前 26 个字符的不同主持硬约束 + 1 勾选任务 + 1 未勾选任务 + 1 会后新增风险
            shared_prefix = "针对高并发状态写入与跨进程锁竞争边界场景下的安全策略，"
            c_a = shared_prefix + "必须启用写前字节级快照校验"
            c_b = shared_prefix + "严禁绕过只读自动化回归验证钩子"
            await mem_json(app, tok, "POST", f"/api/sessions/{sid1}/whiteboard", {"op": "add", "kind": "decision", "author": "chair", "text": c_a})
            await mem_json(app, tok, "POST", f"/api/sessions/{sid1}/whiteboard", {"op": "add", "kind": "decision", "author": "chair", "text": c_b})
            await mem_json(app, tok, "POST", f"/api/sessions/{sid1}/whiteboard", {"op": "add", "kind": "risk", "author": "grok", "text": "会后新增极端断网重连幂等风险核查"})

            act_items = [it for it in sess1.whiteboard["items"] if it.get("kind") == "action"]
            assert len(act_items) >= 2, f"期望至少 2 条待办任务，实际: {act_items}"
            await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid1}/whiteboard",
                {"op": "toggle_check", "item_id": act_items[0]["id"], "checked": True},
            )

            st_b_clean, d_b_clean = await mem_json(app, tok, "GET", f"/api/sessions/{sid1}/decision-brief")
            st_b_full, d_b_full = await mem_json(app, tok, "GET", f"/api/sessions/{sid1}/decision-brief?include_transcript=1")
            st_exp, _, raw_exp = await mem_http(app, tok, "GET", f"/api/sessions/{sid1}/export")
            assert st_b_clean == 200 and st_b_full == 200 and st_exp == 200

            md_clean = d_b_clean["markdown"]
            md_full = d_b_full["markdown"]
            md_export = raw_exp.decode("utf-8")

            for label_exit, doc_txt in (
                ("复制决策包(decision-brief)", md_clean),
                ("复制纪要(include_transcript=1)", md_full),
                ("导出.md(/export)", md_export),
            ):
                assert "CREATE TABLE state_ledger_v58" in doc_txt, f"{label_exit} 丢失了六段式决议中的 SQL 契约代码块"
                assert "多 AI 思想精华与纠偏演进表" in doc_txt, f"{label_exit} 丢失了六段式决议中的纠偏演进表"
                assert c_a in doc_txt and c_b in doc_txt, f"{label_exit} 发生同前缀约束去重误吞！"
                assert "- [x] " in doc_txt and "- [ ] " in doc_txt, f"{label_exit} 未同时保留已勾选与未勾选任务全集！"
                assert "会后新增极端断网重连幂等风险核查" in doc_txt, f"{label_exit} 漏掉了会后新增白板风险项！"
                assert "同步裸切无引用计数双缓冲指针" in doc_txt, f"{label_exit} 漏掉了防回流弃案！"

            assert "## 完整发言记录" not in md_clean, "纯净决策包不应混入冗长原始聊天记录"
            assert "## 完整发言记录" in md_full and "## 完整发言记录" in md_export, "完整纪要导出应包含原始发言全录"
            ok("4. 单一真源完整决策包三端 100% 同源无损（同前缀约束零误吞 + 已选/未选待办全集 + 风险/精华/弃案全保留）")

            # 5. 验证 5 席 adversarial_review 全员参战（第 4–5 席绝不闲置旁观）
            os.environ["V58_MODE"] = "adv_panel_5"
            _, d_s2 = await mem_json(app, tok, "POST", "/api/sessions", {"title": "五席红蓝编组全参战验证"})
            sid2 = d_s2["session"]["session_id"]
            st_adv, _ = await mem_json(
                app,
                tok,
                "POST",
                f"/api/sessions/{sid2}/start",
                {
                    "topic": "评估五席红蓝对抗模式下第 4–5 席是否全员参与压力审计",
                    "collab_mode": "adversarial_review",
                    "enabled_agents": ["carbon", "grok", "astra", "vega", "titan"],
                },
            )
            assert st_adv == 200
            sess2 = await wait_idle(app, sid2)
            spoke_seats = {m["speaker"] for m in sess2.messages if m.get("speaker") in ("carbon", "grok", "astra", "vega", "titan")}
            assert spoke_seats == {"carbon", "grok", "astra", "vega", "titan"}, (
                f"5 席红蓝辩证存在旁观闲置席位！实际发言席位={spoke_seats}"
            )
            ok("5. 4–6 席 `adversarial_review` 红蓝编组全员参战（5/5 席全部完成实质交锋，零闲置席位）")

        finally:
            await app.orchestrator.shutdown()

    print("\n" + "=" * 78, flush=True)
    print(f"✔ AI圆桌 v5.8 五阶互评纠偏闭环与单一真源无损决策包全部 {len(passed)}/5 大项验收 100% 通过！", flush=True)
    print("=" * 78, flush=True)


if __name__ == "__main__":
    asyncio.run(run_v58_suite())
