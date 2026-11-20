# 验证记录 · Verification

[English](../README.md) · [简体中文](../README.zh-CN.md)

## 真实 CLI 并行 · Live CLI concurrency

2026-11-14，Apple Silicon Mac，macOS 27.0.1。在独立的会议数据目录内，使用桌面包自带的后端，通过会议启动接口提出同一个活动室排期问题。各席共用 `agy` 和 `gemini-4-carbon / low`。并发峰值来自实际存活的 CLI 子进程数。每席使用独立临时目录，结束后均已清理。

The 3.0.0 Mac build was tested with signed-in CLIs. Each seat answered the same scheduling question. Peak concurrency counts simultaneously live CLI child processes. Opening time covers all opening statements. Meeting time includes synthesis. These are individual observations.

| 席位 / Seats | 有效立论 / Replies | 进程峰值 / Peak | 立论 / Openings | 含汇总 / Full meeting |
|---:|---:|---:|---:|---:|
| 3 | 3/3 | 3 | 55.3 s | 86.4 s |
| 4 | 4/4 | 4 | 30.0 s | 63.4 s |
| 5 | 5/5 | 5 | 70.3 s | 102.7 s |
| 6 | 6/6 | 6 | 29.3 s | 57.7 s |

同一台 Mac 的一次三路探活中，Grok 用时 12.22 秒，Gemini 用时 26.19 秒，Codex 用时 50.18 秒。可用模型取决于个人账号；上述时间包括启动、网络和模型服务。

A separate three-driver request returned a valid model reply from Grok in 12.22 s, Gemini in 26.19 s and Codex in 50.18 s. Model availability depends on the local account.

## 研讨纠偏与无损决策包回归 · Deliberation & Decision Brief Suites

仓库内置离线确定性回归套件，无需消耗云端模型额度即可在本地验证研讨状态机、争议验收与安全护栏：

Offline deterministic verification suites validate the multi-seat deliberation state machine, challenger verification gates, lossless brief synthesis, and workspace safety invariants without cloud API calls:

| 脚本 / Suite | 覆盖重点 / Coverage |
| :--- | :--- |
| `python3 scripts/verify_v59_signoff_and_delta_brief.py` | 条件式质询方答辩验收（防自证销账）、倒序终态契约快照、逆向对照会签、Delta Guard 差集补录、决议脏态置顶增量与主刀契约直通 / Conditional challenger sign-off, reverse-chronological contract snapshot, reverse-anchored audit, Delta Guard brief, stale-resolution guard & executor contract pass-through |
| `python3 scripts/verify_v58_collision_and_brief.py` | 热会话 `_seen_msg_ids` 精确切片、多格式 `D1..Dn` 局部销账、5 席红蓝全员参战、块级会签合入与三出口同源对齐 / Warm-session delta tracking, itemized `D1..Dn` closure, 5-seat adversarial panel & unified export |
| `python3 scripts/verify_v5_resolution_upgrade.py` | 盲评隔离、同源/异构认知防伪徽章、三级准入、缺席拦截与弃案负面清单物理隔离 / Blind opening isolation, epistemic provenance badges, absent-seat guard & negative-list quarantine |
| `python3 scripts/verify_full_convergence.py` | 纯标准库零第三方依赖 AST 审计、子进程凭据清零、写前 CAS 快照、跨进程写锁与四阶段崩溃恢复回滚 / Zero-dependency stdlib AST audit, credential stripping, CAS snapshot & atomic rollback |

## Windows 发布检查 · Windows package checks

Windows 工作流从发行 ZIP 中启动原生程序，检查 WebView2、已鉴权的实时事件、模型配置重开读回和席位切换。后端检查覆盖 CLI 进程回收、跨进程写锁、工作区字节回滚和手动编辑冲突。自动化环境使用本地测试输入。

The Windows job tests the extracted release with local fixtures. It exercises the desktop window, authenticated event stream, settings persistence, roster changes, subprocess cleanup, cross-process locking and rollback. Hosted-model latency figures above are from macOS. [Windows workflow and run history](https://github.com/Catcherog/ai-roundtable/actions/workflows/windows.yml)
