# AI圆桌（Multi-CLI Studio）

面向本地多 CLI 协同讨论与决议执行的 macOS 原生桌面工作台。

## 目录结构

- `AI圆桌.app`：原生 macOS 桌面应用（Apple Silicon Cocoa + WKWebView），双击直接运行。
- `安装到桌面.command`：双击自动关闭旧实例、将最新版 `AI圆桌.app` 同步到桌面并启动。
- `backend/`：Python 异步 HTTP/SSE 服务、多 CLI 流式适配层与并发会议编排引擎。
  - `cli_adapters.py`：对接 Carbon（Antigravity CLI）、Grok（Grok CLI）、Astra（Codex CLI），内置并发版本探测缓存、讨论沙箱隔离与增量上下文续接。
  - `orchestrator.py`：并发初评、并行质询+主规划收敛、智能提前共识收敛、会话防抖持久化与过期临时文件自动清理。
  - `server.py`：零第三方依赖的异步 HTTP + SSE 实时流服务。
- `frontend/`：可视化圆桌工作台（四阶段导航、席位动态开关、流式合并渲染与可编辑会议白板）。
- `macos_app/`：原生桌面端入口（`main.m`）与应用图标生成器（`make_icon.m`）。
- `scripts/`：开发、编译与诊断脚本目录。
  - `build_macos_app.sh`：重新编译打包并签名 `AI圆桌.app`。
  - `start_web.sh`：纯浏览器开发模式启动脚本。
  - `check_cli.py`：CLI 连通自检与全链路耗时压测脚本（支持 `--bench` 离线拓扑压测）。

## 常用操作

- **日常使用**：直接打开 `AI圆桌.app`，或双击 `安装到桌面.command` 更新桌面快捷应用。
- **重编应用**：在项目根目录执行 `bash scripts/build_macos_app.sh`。
- **耗时压测**：在项目根目录执行 `python3 scripts/check_cli.py --bench`。
