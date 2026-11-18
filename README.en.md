<p align="center"><img src="docs/images/app-icon.png" alt="AI Roundtable app icon" width="96" height="96"></p>

# AI Roundtable

**English** · [简体中文](README.md)

Give one question to 1–6 AI seats on Windows or macOS. Ask an architect to propose a solution, a reviewer to find a counterexample, and an engineer to work out the implementation. Each seat can have its own CLI, model and reasoning effort. Several seats can share one signed-in CLI.

**[Download for Windows x64](https://github.com/Catcherog/ai-roundtable/releases/latest/download/AI-Roundtable-Windows-x64.zip)** · **[Download for Apple silicon](https://github.com/Catcherog/ai-roundtable/releases/latest/download/AI-Roundtable-macOS-arm64.zip)** · [Release notes and checksums](https://github.com/Catcherog/ai-roundtable/releases/latest)

![Recorded meeting in the Chinese interface. Three seats discuss a tie-breaking rule on the left. Accepted constraints and open risks appear on the whiteboard on the right.](docs/images/roundtable-session.png)

## What a meeting produces

In the meeting above, three seats shared one Codex CLI and answered a small question: *How should a fruit poll pick one winner when two fruits tie?* The architect suggested one runoff. The reviewer wanted the rule published before voting. The engineer pointed out that retrying the draw should return the original winner. The final rule covered all three cases.

| What you want to do | How the workbench helps |
| --- | --- |
| Compare designs or review code | Choose quick consensus, deep deliberation, adversarial review, divergent thinking or code review. Address one seat with `@name` or give everyone the same source lines with a reference such as `@backend/server.py:31-62`. |
| Keep a reviewable decision | The whiteboard separates agreed constraints, unresolved risks and action items. Edit, accept or deselect items before exporting the decision, tasks and transcript to Markdown. |
| Hand a task to an execution agent | Start with a read-only preview. When ready, bind a project folder, choose the executing seat, allow writes and optionally supply a verification command. |

## Start your first meeting

| Platform | Open the app |
| --- | --- |
| Windows 10/11 x64 | Extract the whole ZIP and run `AI-Roundtable.exe`. Python and .NET are bundled. The desktop window uses the [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). |
| Apple silicon Mac | Drag `AI圆桌.app` into Applications. Python 3.9 or later must be available on your Mac. The release uses an ad-hoc signature. [Apple’s first-open guidance](https://support.apple.com/en-us/102445) |

1. Install and sign in to at least one supported CLI in your terminal: Antigravity (`agy`), Codex (`codex`) or Grok (`grok`).
2. Open settings with **Ctrl+,** on Windows or **⌘,** on Mac. Under **阵容与称呼** choose seats. Under **席位与模型** choose their drivers and models, then click **保存配置** to save. **实测连通** sends a real connection test.
3. Select **快速合议** (quick consensus), enter a question and click **开始研讨** (start). Use **形成决议** for a resolution and **导出 .md** to export the minutes. The desktop interface is in Chinese.

## How it works

- **Parallel seats on one CLI.** Seats that share an executable also share a concurrency limit. Each independent call gets its own temporary directory. In one Mac test, six Gemini CLI processes ran simultaneously and returned all six opening statements in 29.3 seconds. The meeting finished in 57.7 seconds including synthesis. [Test conditions and results](docs/verification.md)
- **Reconnect without starting over.** Meeting events carry ordered revisions. A window requests the events it missed or loads a snapshot if those events have left the buffer. Messages and whiteboards are stored locally in SQLite.
- **Rollback checks later edits.** Before a write, the app locks the workspace and snapshots managed files, including ordinary Git-ignored files. Untracked `output/` and `.app` directories are excluded. Larger projects can bind at the root. Their executor proposes text edits across directories, and the app verifies and applies them with snapshots of the target files. The target set can total up to 128 MiB before editing and up to 128 MiB afterward. Recovery does not undo Git commits, pushes or effects outside the workspace; conflicting edits are preserved.
- **Local orchestration.** WebView2 on Windows and WKWebView on macOS connect to an authenticated loopback service. The selected CLIs send prompts and referenced project context to their respective model providers under your account.

## Build from source

On Windows x64, run `pwsh -File scripts/build_windows.ps1` with the .NET 8 SDK installed. On an Apple silicon Mac with Apple Command Line Tools, run `bash scripts/build_macos_app.sh`. To open the browser interface on a Mac, run `bash scripts/start_web.sh`.

[Detailed Chinese guide](docs/guide.zh-CN.md) · [Report an issue](https://github.com/Catcherog/ai-roundtable/issues)
