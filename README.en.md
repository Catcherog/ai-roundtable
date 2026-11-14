# AI Roundtable

A Mac workbench for reviewing a question with an architect, a risk reviewer and an engineer. Watch their replies arrive side by side with a shared whiteboard, ask one seat to defend a claim, then choose which tasks to hand to an execution agent.

**[Download for Apple silicon](https://github.com/Catcherog/ai-roundtable/releases/latest/download/AI-Roundtable-macOS-arm64.zip)** · [简体中文](README.md) · [Detailed guide in Chinese](docs/guide.zh-CN.md)

![Three seats discussing a tied vote in the Chinese-language Mac interface, with decisions and risks on the right.](docs/images/roundtable-session.png)

## Try a meeting

1. On an Apple silicon Mac, check that `python3 --version` reports Python 3.9 or later. Install and sign in to at least one supported AI CLI such as Codex (`codex`), Antigravity (`agy`) or Grok (`grok`).
2. Unzip the release, drag `AI圆桌.app` into Applications and open it. The release uses an ad-hoc signature and has no Apple notarization. If macOS prompts you about the download, follow [Apple’s instructions](https://support.apple.com/en-us/102445).
3. Open settings with **⌘,**. Choose a CLI and a model available to your account, run **实测模型连通** (test connection), and save. **应用单引擎多角色配置** lets one CLI play all three roles.
4. Choose **快速合议** (quick consensus) and ask *“Two fruits tie for first place in a vote. How should we pick a winner? One sentence per seat.”* Click **开始研讨** to start, **形成决议** for the resolution, and **导出 .md** on the whiteboard to export the minutes. The current application interface is in Chinese.

In the recorded meeting above, the architect suggested one runoff. The reviewer wanted the tie-breaker published before voting. The engineer pointed out that retrying the same draw must return the original winner. All three seats used the same Codex CLI. The final resolution combined those constraints into a single rule.

## Working with a project

- Choose from five discussion formats, including adversarial review, divergent thinking and code review. Use one seat for a focused conversation or give each seat its own driver and role.
- Bind a project folder and type `@` to select a file. A reference such as `@backend/server.py:31-62` supplies the specified lines to the discussion.
- During the meeting you can interrupt, question a particular seat, promote a risk to a decision, or uncheck tasks. Export includes the discussion record, decisions, risks and task list.
- The execution tab starts in read-only preview mode. Select **写入工作区** to allow changes to the bound workspace. For Git projects, the app snapshots the worktree and index for the run. Rollback checks for later edits to the same paths. Its snapshot lasts for the current app session.

The UI, HTTP service and meeting history run locally. Configured CLIs may send prompts and project context to their model providers using your existing account. Provider access and usage charges apply.

## Run from source

```bash
git clone https://github.com/Catcherog/ai-roundtable.git
cd ai-roundtable
bash scripts/start_web.sh
```

The web entry point opens `http://127.0.0.1:8765` on your Mac. To build the desktop app, install Apple’s Command Line Tools and run `bash scripts/build_macos_app.sh`. The release binary targets macOS 12 or later and was tested on macOS 27.0.1 on Apple silicon.

[Release notes and SHA-256 checksum](https://github.com/Catcherog/ai-roundtable/releases/latest) · [Report an issue](https://github.com/Catcherog/ai-roundtable/issues)
