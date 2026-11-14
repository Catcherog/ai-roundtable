# 验证记录 · Verification

[简体中文](../README.md) · [English](../README.en.md)

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

## Windows 发布检查 · Windows package checks

Windows 工作流从发行 ZIP 中启动原生程序，检查 WebView2、已鉴权的实时事件、模型配置重开读回和席位切换。后端检查覆盖 CLI 进程回收、跨进程写锁、工作区字节回滚和手动编辑冲突。自动化环境使用本地测试输入。

The Windows job tests the extracted release with local fixtures. It exercises the desktop window, authenticated event stream, settings persistence, roster changes, subprocess cleanup, cross-process locking and rollback. Hosted-model latency figures above are from macOS. [Windows workflow and run history](https://github.com/Catcherog/ai-roundtable/actions/workflows/windows.yml)
