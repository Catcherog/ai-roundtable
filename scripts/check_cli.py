# -*- coding: utf-8 -*-
"""
AI圆桌 — 本地 CLI 连通自检与全链路耗时基准测试工具
用法：
    python3 scripts/check_cli.py            # 完整检测（环境探测耗时 + 真实 Ping + 并发初评）
    python3 scripts/check_cli.py --bench    # 仅测本地启动、探测缓存与编排拓扑耗时（毫秒级离线压测）
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

from backend.orchestrator import RoundtableOrchestrator  # noqa: E402


async def run_local_benchmark(orch: RoundtableOrchestrator) -> None:
    print("\n" + "=" * 68)
    print("全链路编排拓扑离线压测（单轮模拟延迟 = 200ms）")
    print("=" * 68)

    orig_inspect = orch.settings.inspect_status
    orig_stream = orch.runner.stream_discussion_turn
    try:
        orch.settings.inspect_status = lambda: {
            aid: {"binary_detected": True, "binary_path": f"mock://{aid}", "version": "1.0"}
            for aid in ("carbon", "grok", "astra")
        }

        for mode_key, badge_txt in [
            ("fast_align", "方案对齐"),
            ("standard_roundtable", "共识通过"),
            ("red_blue_debate", "存疑待核"),
        ]:
            calls = []

            async def _mock_turn(**kw):
                calls.append(f"{kw['stage']}:{kw['agent_id']}")
                await asyncio.sleep(0.20)
                yield {"type": "delta", "text": "压测响应片段"}
                yield {
                    "type": "done",
                    "full_text": "- 采用并发探测与增量上下文续接降低端到端延迟",
                    "badge": badge_txt,
                    "target": None,
                    "ttft_ms": 25,
                    "elapsed_ms": 200,
                }

            orch.runner.stream_discussion_turn = _mock_turn
            sess = orch.create_session(title=f"压测-{mode_key}", collab_mode=mode_key)
            t0 = time.perf_counter()
            await orch.start_topic_meeting(sess, "全链路性能压测议题", collab_mode=mode_key)
            if sess.active_task:
                await sess.active_task
            wall_ms = (time.perf_counter() - t0) * 1000
            await orch.delete_session(sess.session_id)
            print(
                f"[{mode_key:20s}] 总耗时: {wall_ms:6.1f} ms "
                f"(等效串行步数: {wall_ms / 200.0:.2f}x) | 调用序列: {' -> '.join(calls)}"
            )
    finally:
        orch.settings.inspect_status = orig_inspect
        orch.runner.stream_discussion_turn = orig_stream


async def main() -> None:
    parser = argparse.ArgumentParser(description="AI圆桌 CLI 连通检测与全链路耗时测试")
    parser.add_argument("--bench", action="store_true", help="仅运行本地初始化与编排拓扑耗时压测")
    args = parser.parse_args()

    t_boot = time.perf_counter()
    orch = RoundtableOrchestrator(workspace_dir=str(ROOT_DIR))
    boot_ms = (time.perf_counter() - t_boot) * 1000

    t_status = time.perf_counter()
    status = orch.get_system_status()
    status_ms = (time.perf_counter() - t_status) * 1000

    print("=" * 68)
    print(f"1. 编排器冷启动: {boot_ms:.1f} ms | 缓存态状态读取: {status_ms:.2f} ms")
    print("=" * 68)
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

    if args.bench:
        await run_local_benchmark(orch)
        await orch.runner.shutdown()
        return

    print("\n" + "=" * 68)
    print("2. 并发实测三个 CLI 真实请求响应 (Ping)")
    print("=" * 68)
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

    print("\n" + "=" * 68)
    print("3. 发起一轮真实议题并发初评实测")
    print("=" * 68)
    sess = orch.create_session(title="实测会话", collab_mode="fast_align")
    sess.topic = "为一个本地 Web 服务设计简洁的健康检查接口，请从各自职责给出核心要点。"
    sess.whiteboard["topic"] = sess.topic
    print(f"测试议题：{sess.topic}\n")

    await asyncio.gather(
        *(orch._run_single_agent_turn(sess, aid, "opening", "并发初评") for aid in ready_agents)
    )

    for m in sess.messages:
        print(f"--- {m['speaker_name']}（{m['role_title']}） [TTFT {m['ttft_ms']}ms / 总计 {m['elapsed_ms']}ms] ---")
        print(m["content"])
        print()

    await orch.delete_session(sess.session_id)
    await orch.runner.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
