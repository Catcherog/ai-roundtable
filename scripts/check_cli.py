# -*- coding: utf-8 -*-
"""
AI圆桌 — 本地 CLI 连通自检与全链路编排拓扑基准测试工具
用法：
    python3 scripts/check_cli.py            # 完整检测（环境探测耗时 + 真实 Ping + 并发初评）
    python3 scripts/check_cli.py --bench    # 毫秒级离线基准测试（覆盖 5 大讨论拓扑、单席非阻塞跳过、三级恢复与三区白板兼容断言）
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# AI_ROUNDTABLE_V2_UPGRADE_20261114
from backend.cli_adapters import (  # noqa: E402
    PERSONA_PRESETS,
    ROSTER_NAME_PRESETS,
    normalize_model_effort,
    parse_structured_tail_with_kinds,
)
from backend.orchestrator import (  # noqa: E402
    COLLAB_MODES,
    RoundtableOrchestrator,
    _normalize_and_sync_whiteboard,
    is_whiteboard_noise,
)


async def run_local_benchmark(orch: RoundtableOrchestrator) -> None:
    print("\n" + "=" * 74)
    print("全链路编排拓扑离线压测与模块契约验收（单轮模拟延迟 = 120ms）")
    print("=" * 74)

    # 1. 断言模块一：7 项角色职责与 5 项讨论策略规范命名
    assert set(PERSONA_PRESETS.keys()) == {
        "planner",
        "red_team",
        "implementer",
        "fullstack_solo",
        "product_ux",
        "perf_sre",
        "qa_audit",
    }, "PERSONA_PRESETS 键集合不匹配"
    assert PERSONA_PRESETS["red_team"]["label"] == "风险审计"
    assert PERSONA_PRESETS["implementer"]["label"] == "工程实现"
    assert PERSONA_PRESETS["fullstack_solo"]["label"] == "全栈架构"
    assert set(COLLAB_MODES.keys()) == {
        "deep_deliberation",
        "adversarial_review",
        "divergent_convergent",
        "code_review",
        "rapid_consensus",
    }, "COLLAB_MODES 键集合不匹配"

    orig_inspect = orch.settings.inspect_status
    orig_stream = orch.runner.stream_discussion_turn
    orig_exec_stream = orch.runner.stream_agent_execution
    try:
        orch.settings.inspect_status = lambda *a, **kw: {
            "carbon": {
                "binary_detected": True,
                "binary_path": "mock://agy",
                "effective_driver": "agy",
                "effective_model": "gemini-4-carbon",
                "effective_discussion_effort": "high",
                "version": "1.0",
            },
            "grok": {
                "binary_detected": True,
                "binary_path": "mock://grok",
                "effective_driver": "grok",
                "effective_model": "grok-4.7",
                "effective_discussion_effort": "xhigh",
                "version": "1.0",
            },
            "astra": {
                "binary_detected": True,
                "binary_path": "mock://codex",
                "effective_driver": "codex",
                "effective_model": "gpt-6-astra",
                "effective_discussion_effort": "max",
                "version": "1.0",
            },
        }

        async def _mock_exec_stream(**kw):
            yield {"type": "term_log", "line": "[Bench] 只读执行预演启动"}
            yield {"type": "exec_delta", "text": "预演补丁摘要生成完毕"}
            yield {
                "type": "exec_artifact",
                "summary": "### 预演执行交付完成\n- 已按勾选范围生成变更方案",
                "diff": "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new",
            }

        orch.runner.stream_agent_execution = _mock_exec_stream

        # 2. 压测 5 大讨论策略 + 旧版 arch_to_exec 自动预演归一化兼容
        bench_cases = [
            ("deep_deliberation", "深度研讨（含定向答辩）"),
            ("adversarial_review", "正反辩证（四步非对称博弈）"),
            ("divergent_convergent", "发散收敛（正交发散+矩阵收敛）"),
            ("code_review", "代码审查（证据定位+调用链核验）"),
            ("rapid_consensus", "快速合议（单轮直出+清单整合）"),
            ("arch_to_exec", "旧键兼容（归一化快速合议+自动预演）"),
        ]

        for mode_key, desc in bench_cases:
            calls = []

            async def _mock_turn(**kw):
                stage = kw["stage"]
                aid = kw["agent_id"]
                calls.append(f"{stage}:{aid}")
                yield {
                    "type": "status",
                    "detail": "正在推演边界条件",
                    "driver": aid,
                    "model": f"mock-{aid}",
                    "effort": "high",
                }
                await asyncio.sleep(0.12)
                # 在深度研讨交叉质询阶段让 Grok 定向点名 @Carbon，验证 rebuttal 定向答辩子回合自动触发
                mention_target = "carbon" if (mode_key == "deep_deliberation" and stage == "cross_talk" and aid == "grok") else None
                body = (
                    "@Carbon 请回应高并发锁竞争反例\n[白板: 共识=锁定幂等契约 | 风险=极端重连风暴 | 任务=补充超时单测]"
                    if mention_target
                    else "- 采用多引擎协同与确定性白板哈希保障一致性\n[白板: 共识=统一错误码契约 | 任务=实现流式状态透传]"
                )
                yield {"type": "delta", "text": "压测响应片段"}
                yield {
                    "type": "done",
                    "full_text": body,
                    "badge": "阶段完成",
                    "target": mention_target,
                    "ttft_ms": 20,
                    "elapsed_ms": 120,
                }

            orch.runner.stream_discussion_turn = _mock_turn
            sess = orch.create_session(title=f"压测-{mode_key}", collab_mode=mode_key)
            if mode_key == "arch_to_exec":
                assert sess.collab_mode == "rapid_consensus" and sess.auto_preview_exec is True, "arch_to_exec 兼容归一化失败"

            t0 = time.perf_counter()
            await orch.start_topic_meeting(sess, "全链路编排拓扑基准测试议题", collab_mode=mode_key)
            if sess.active_task:
                await sess.active_task
            wall_ms = (time.perf_counter() - t0) * 1000

            if mode_key == "deep_deliberation":
                assert any(c.startswith("rebuttal:carbon") for c in calls), f"未触发定向答辩子回合: {calls}"
            if mode_key == "adversarial_review":
                stages_only = [c.split(":")[0] for c in calls]
                assert stages_only == ["adv_propose", "adv_attack", "adv_defend", "adv_verdict"], f"正反辩证顺序异常: {calls}"
            if mode_key == "arch_to_exec":
                assert sess.whiteboard.get("exec_diff"), "自动执行预演未生成预期 Diff"

            await orch.delete_session(sess.session_id)
            print(
                f"[{mode_key:20s}] {desc:28s} | {wall_ms:6.1f} ms | 拓扑: {' -> '.join(calls)}"
            )

        # 3. 验证单席非阻塞「跳过本轮」：跳过 Grok 不中断 Carbon / Astra
        skip_sess = orch.create_session(title="单席跳过验证", collab_mode="rapid_consensus")

        async def _slow_grok_turn(**kw):
            aid = kw["agent_id"]
            if aid == "grok":
                await asyncio.sleep(5.0)
            else:
                await asyncio.sleep(0.10)
            yield {"type": "delta", "text": f"{aid} 正常发言"}
            yield {
                "type": "done",
                "full_text": f"- {aid} 输出有效架构要点",
                "badge": "已完成",
                "target": None,
                "ttft_ms": 15,
                "elapsed_ms": 100,
            }

        orch.runner.stream_discussion_turn = _slow_grok_turn
        await orch.start_topic_meeting(skip_sess, "验证单席跳过不阻塞同批其余席位", collab_mode="rapid_consensus")
        await asyncio.sleep(0.04)
        skip_res = await orch.skip_agent_turn(skip_sess, "grok")
        assert skip_res.get("ok") is True and skip_res.get("badge") == "已跳过本轮"
        if skip_sess.active_task:
            await skip_sess.active_task
        grok_msgs = [m for m in skip_sess.messages if m.get("speaker") == "grok"]
        assert grok_msgs and grok_msgs[0].get("skipped") is True and grok_msgs[0].get("error") is False
        other_ok = [m for m in skip_sess.messages if m.get("speaker") in ("carbon", "astra") and not m.get("error")]
        assert len(other_ok) >= 2, "跳过单席误中断了同批次其余席位"

        # 验证三级就地恢复参数生成（unlimited / downgrade / borrow）
        ov_unlim, _ = orch._build_retry_turn_override(skip_sess, "grok", grok_msgs[0], "unlimited")
        ov_down, _ = orch._build_retry_turn_override(skip_sess, "grok", grok_msgs[0], "downgrade")
        ov_borrow, _ = orch._build_retry_turn_override(skip_sess, "grok", grok_msgs[0], "borrow")
        assert ov_unlim.get("unlimited_timeout") is True
        assert ov_down.get("effort") == "high"
        assert ov_borrow.get("driver") in ("agy", "codex") and ov_borrow.get("stateless") is True
        await orch.delete_session(skip_sess.session_id)
        print("[skip & 3-tier retry ] 单席非阻塞跳过 + 三级恢复（不限时 / 降级档位 / 备用引擎代答）断言通过")

        # 4. 验证模块四：三区结构化白板双向兼容、噪音硬拦截、勾选范围过滤与乐观锁版本校验
        assert is_whiteboard_noise("我先只读前端布局，不改任何文件") is True
        assert is_whiteboard_noise("先核对源码路径和字段名称") is True
        assert is_whiteboard_noise("采用乐观锁版本号 ver 防止并发编辑互相覆盖") is False

        _, parsed_tail = parse_structured_tail_with_kinds(
            "正文分析\n[白板: 共识=采用乐观锁版本号校验 | 风险=旧配置迁移空值边界 | 任务=更新 app.js 白板渲染]"
        )
        assert [x["kind"] for x in parsed_tail] == ["decision", "risk", "action"]

        legacy_wb = {
            "topic": "白板历史迁移测试",
            "chair_constraints": ["严禁破坏旧会话读取"],
            "carbon_plan": ["采用三区结构化白板模型"],
            "grok_risks": ["我先只读前端布局", "高并发 SSE 重绘可能覆盖行内编辑草稿"],
            "astra_actions": ["实现 checked 勾选范围联动执行", "补充离线基准断言"],
        }
        migrated_wb_1 = _normalize_and_sync_whiteboard(dict(legacy_wb), topic="白板历史迁移测试")
        migrated_wb_2 = _normalize_and_sync_whiteboard(dict(legacy_wb), topic="白板历史迁移测试")
        assert [it["id"] for it in migrated_wb_1["items"]] == [
            it["id"] for it in migrated_wb_2["items"]
        ], "确定性白板哈希 ID 不稳定"
        assert not any("只读前端布局" in it["text"] for it in migrated_wb_1["items"]), "过程性探索独白未被噪音黑名单拦截"

        wb_sess = orch.create_session(title="白板操作验证", collab_mode="deep_deliberation")
        wb_sess.whiteboard = migrated_wb_1
        risk_item = next(it for it in wb_sess.whiteboard["items"] if it["kind"] == "risk")
        await orch.update_whiteboard_manual(wb_sess, {"op": "adopt_decision", "item_id": risk_item["id"]})
        adopted_item = next(it for it in wb_sess.whiteboard["items"] if it["id"] == risk_item["id"])
        assert adopted_item["kind"] == "decision", "采纳为共识未将 risk 移入 decision"

        action_items = [it for it in wb_sess.whiteboard["items"] if it["kind"] == "action"]
        await orch.update_whiteboard_manual(
            wb_sess, {"op": "toggle_check", "item_id": action_items[0]["id"], "checked": False}
        )
        assert action_items[0]["text"] not in wb_sess.whiteboard["astra_actions"], "取消勾选的任务未从执行列表中排除"

        conflict_res = await orch.update_whiteboard_manual(
            wb_sess,
            {"op": "update", "item_id": adopted_item["id"], "text": "过期版本修改", "ver": 1},
        )
        assert conflict_res.get("conflict") is True, "乐观锁版本号冲突校验未生效"
        await orch.delete_session(wb_sess.session_id)
        print("[3-zone whiteboard   ] 历史迁移确定性 ID + 噪音黑名单 + 采纳共识 + 勾选过滤 + 乐观锁断言通过")

        # 5. 验证 v2 修复项：normalize_model_effort(strict=True)、僵尸「思考中」卡片自愈、自定义成员名称与单引擎并发加速
        assert normalize_model_effort("agy", model="gemini-4-carbon", effort="max", strict=True) == "high"
        assert normalize_model_effort("codex", model="gpt-6-astra", effort="max", strict=True) == "max"
        assert set(ROSTER_NAME_PRESETS.keys()) >= {
            "role_experts",
            "council_alpha",
            "product_studio",
            "auto_driver",
            "classic",
        }

        zombie_sess = orch.create_session(title="僵尸卡片自愈验证", collab_mode="rapid_consensus")
        zombie_sess.seat_efforts = {"carbon": "max", "grok": "xhigh", "astra": "max"}
        orch._sync_seat_readiness(zombie_sess)
        assert zombie_sess.seat_states["carbon"]["effective_effort"] == "high", "单会话越界档位未被 strict 收敛"
        zombie_sess.messages.append(
            {
                "id": "m_zombie",
                "speaker": "carbon",
                "speaker_name": "架构师",
                "content": "",
                "badge": "思考中",
                "streaming": True,
            }
        )
        persisted_z = zombie_sess.to_persisted_dict()
        assert persisted_z["messages"][0]["streaming"] is False
        assert persisted_z["messages"][0]["badge"] == "已中断"
        assert persisted_z["messages"][0]["content"], "空白僵尸卡片未自动填充中断说明"
        await orch.delete_session(zombie_sess.session_id)

        prev_preset = orch.settings.roster_preset
        prev_carbon_cname = orch.settings.agents["carbon"].custom_name
        orch.update_runtime_config(
            {"roster_preset": "council_alpha", "agents": {"carbon": {"custom_name": "首席架构"}}}
        )
        assert orch.settings.resolve_seat_name("carbon") == "首席架构"
        assert orch.settings.resolve_seat_name("grok") == "Beta"
        _, _, parsed_tgt, _, _ = orch.runner.parse_structured_tail_with_kinds(
            "请 @首席架构 核对接口边界\n[状态: 质询完成 | 共识: 需继续 | 点名: @首席架构]",
            seat_names={"carbon": "首席架构", "grok": "Beta", "astra": "Gamma"},
        )
        assert parsed_tgt == "carbon", f"自定义成员名点名解析失败: {parsed_tgt}"
        orch.update_runtime_config(
            {"roster_preset": prev_preset, "agents": {"carbon": {"custom_name": prev_carbon_cname}}}
        )
        print("[v2 fixes & roster   ] strict 档位收敛 + 僵尸卡片自愈 + 自定义成员名点名解析断言通过")
        print("=" * 74)
        print("全部离线基准压测与契约断言 100% 通过！")
    finally:
        orch.settings.inspect_status = orig_inspect
        orch.runner.stream_discussion_turn = orig_stream
        orch.runner.stream_agent_execution = orig_exec_stream
        orch._sync_agent_meta_names()


async def main() -> None:
    parser = argparse.ArgumentParser(description="AI圆桌 CLI 连通检测与全链路耗时测试")
    parser.add_argument("--bench", action="store_true", help="运行本地初始化、5大讨论拓扑与白板三区离线基准压测")
    args = parser.parse_args()

    t_boot = time.perf_counter()
    orch = RoundtableOrchestrator(workspace_dir=str(ROOT_DIR))
    boot_ms = (time.perf_counter() - t_boot) * 1000

    t_status = time.perf_counter()
    status = orch.get_system_status()
    status_ms = (time.perf_counter() - t_status) * 1000

    print("=" * 74)
    print(
        f"1. 编排器冷启动: {boot_ms:.1f} ms | 状态读取: {status_ms:.2f} ms | "
        f"运行策略: {status['pacing_mode']} (idle={status['idle_timeout_sec']}s, turn={status['turn_timeout_sec']}s)"
    )
    print("=" * 74)
    for aid in ("carbon", "grok", "astra"):
        info = status["agents"][aid]
        if info["binary_detected"]:
            print(
                f"[已找到] {info['name']:6s} ({info['title']}) | {info['cli_name']:15s} "
                f"-> {info['binary_path']} ({info['version']})"
            )
        else:
            cands = ", ".join(info["binary_candidates"])
            print(f"[未找到] {info['name']:6s} ({info['title']}) | {info['cli_name']:15s} -> 未找到: {cands}")

    await run_local_benchmark(orch)
    if args.bench:
        await orch.runner.shutdown()
        return

    print("\n" + "=" * 74)
    print("2. 并发实测三个 CLI 真实请求响应 (Ping)")
    print("=" * 74)
    ping_res = await orch.run_cli_connectivity_test()
    ready_agents = []
    for aid in ("carbon", "grok", "astra"):
        r = ping_res[aid]
        info = status["agents"][aid]
        if r["ok"]:
            ready_agents.append(aid)
            print(f"[成功] {info['name']:6s} ({r['elapsed_ms']} ms) 回复: {r['reply']}")
        else:
            print(f"[失败] {info['name']:6s} 原因: {r['error']}")

    if not ready_agents:
        print("\n提示：当前没有可用的 CLI 通过实测，请确认各 CLI 已安装并完成终端登录鉴权。")
        await orch.runner.shutdown()
        return

    print("\n" + "=" * 74)
    print("3. 发起一轮真实议题快速合议初评实测")
    print("=" * 74)
    sess = orch.create_session(title="实测会话", collab_mode="rapid_consensus")
    sess.topic = "为一个本地 Web 服务设计简洁的健康检查接口，请从各自职责给出核心要点。"
    sess.whiteboard["topic"] = sess.topic
    print(f"测试议题：{sess.topic}\n")

    await asyncio.gather(
        *(orch._run_single_agent_turn(sess, aid, "rapid_open", "要点直出") for aid in ready_agents)
    )

    for m in sess.messages:
        print(f"--- {m['speaker_name']}（{m['role_title']}） [TTFT {m['ttft_ms']}ms / 总计 {m['elapsed_ms']}ms] ---")
        print(m["content"])
        print()

    await orch.delete_session(sess.session_id)
    await orch.runner.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
