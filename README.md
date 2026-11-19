<h1 align="center">AI Roundtable</h1>
<p align="center"><strong>Give your best idea a dissenting voice.</strong></p>
<p align="center">English · <a href="README.zh-CN.md">简体中文</a></p>

AI Roundtable is a Windows and macOS desktop app for decisions that deserve a second opinion. Give **1–6 AI seats** the same question. One can propose a plan, another can look for the case that breaks it, and a third can design a test. As chair, you can question a specific seat, trace a whiteboard item to the remark behind it, and choose which tasks go forward.

Start with one working command-line AI tool, or seat **Codex, Claude Code, Antigravity, Grok and Ollama** at the same table. Each seat can use its own model and supported reasoning settings. The app interface is in Simplified Chinese.

**[Download for Windows x64](https://github.com/Catcherog/ai-roundtable/releases/latest/download/AI-Roundtable-Windows-x64.zip)** · **[Download for Apple silicon](https://github.com/Catcherog/ai-roundtable/releases/latest/download/AI-Roundtable-macOS-arm64.zip)** · [Release notes & checksums](https://github.com/Catcherog/ai-roundtable/releases/latest)

[Highlights](#highlights) · [Try your first session](#try-a-question-that-forces-a-choice) · [User guide (Chinese)](docs/guide.zh-CN.md) · [Upgrading from v4.0.2](#upgrading-from-v402)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/roundtable-5.5.1-dark.png">
  <img src="docs/images/roundtable-5.5.1.png" alt="The 5.5.1 start screen with three seats, the trade-off debate selected, and a question about offline capture versus cross-device sync ready to send.">
</picture>

<a name="核心亮点"></a>

## Highlights

- **Get independent first impressions.** In Deep discussion, the opening seats start from the same context before they see each other’s answers. They can then question one another’s assumptions. Trade-off debate uses a different sequence. The proposer has to answer the critic’s objection and can revise the plan.
- **See who actually agrees.** One Codex installation can play architect, auditor and engineer. The minutes flag that shared origin. When different drivers participate and complete a round of questioning, the board can record a cross-checked conclusion. Decisions you make yourself carry the chair’s label.
- **Reopen one point of disagreement.** Pick a risk on the board and give two seats one more round on that point. Use `@` and a seat name to direct a question. On a board item linked to a message, click its author badge to read the original wording and qualifications.
- **Review the evidence in context.** Bind a project folder and cite a file and line range, such as `@backend/storage.py:73-84`. For a design review, paste or drop in a screenshot and ask an image-capable model which control a first-time user would click and what drew their eye there.
- **Keep the reasoning alongside the decision.** The whiteboard tracks accepted conclusions, open risks and tasks. Set a discarded proposal aside and it gets its own place in the record. Export Markdown to keep the task selections, discarded options and original remarks together for the next review.
- **Turn selected tasks into a reviewable change.** Choose the tasks and the seat doing the work, then start with a read-only preview of its proposal or patch. If you enable workspace writes, Roundtable snapshots managed files first. A rollback checks for later edits and shows conflicts so you can inspect them. [Execution and rollback guide (Chinese)](docs/guide.zh-CN.md#执行与回滚)

**How many seats can one tool serve at once?** In one v3.0.0 run on an Apple silicon Mac, a single signed-in Antigravity CLI installation ran six processes at the same time. All six opening statements finished in 29.3 seconds. The session took 57.7 seconds including the summary. [Model, test conditions and results for three through six seats](docs/verification.md)

<a name="看一场真实讨论"></a>

## A real three-seat discussion

**How should a fruit poll return a single winner when the top choices tie?** In one session, the architect suggested a runoff among the tied choices. The auditor spotted a fairness issue. Voters should know the tie-breaker before the poll opens. The engineer noticed a different failure mode. Recalculating the same poll should reuse the first draw.

The resulting rule could go straight into an implementation. Announce the rule before voting, allow one runoff, draw with equal odds if the tie persists, and keep the first valid result for that poll. All three roles used Codex. [Read the original exchange in a screenshot from an earlier release](docs/images/roundtable-session.png)

<a name="你手边的事适合哪一桌"></a>

## Pick a session for the decision at hand

| Bring this | Choose this preset in the app | Try asking |
| --- | --- | --- |
| Two competing product plans | Trade-off debate (方案利弊红蓝辩证包) | “We can fund one. What evidence would make the advocate for A switch to B?” |
| Code you are about to change | Engineering review (工程研发与代码审查包) | “What happens if this operation is submitted twice? Cite the relevant lines and propose a test.” |
| A screen that confuses users | Design critique (产品体验与多模态走查包) | “Where would a new user click first? Point to the visual cue that steers them there.” |
| An incident report or a draft | Troubleshooting and editing (故障排查与文稿打磨包) | “Which statements describe observations? What evidence would we need before naming the cause?” |

<a name="第一场会就问一道有取舍的题"></a>

## Try a question that forces a choice

1. Make sure a supported AI tool can answer a question in your terminal. For Ollama, prepare a local model first. Open Settings (Ctrl+, on Windows or ⌘, on Mac), assign a tool and model to each participating seat under **Seats & models** (席位与模型), then save.
2. Select **Trade-off debate** (方案利弊红蓝辩证包), paste the prompt below and click **Start** (开始研讨). You can try this without binding a project folder.

   > Our two-person team ships a to-do app in a week. We can build one feature, either offline capture or cross-device sync. Ask one seat to argue for each. What evidence would make each side change its mind? Give us one test we can run tomorrow.

3. After the opening exchange, add one fact. **“Our first users commute on trains with no signal.”** See who revises their advice and which assumption changed. Click **Form a decision** (形成决议), review the board, then use **Export .md** (导出 .md) to save the minutes.

<a name="安装与数据"></a>

## Installation and data

| Platform | First launch |
| --- | --- |
| Windows 10/11 x64 | Extract the entire ZIP and open `AI-Roundtable.exe`. Python and .NET are bundled. The desktop window uses Microsoft’s [Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). |
| Apple silicon | Requires macOS 12 or later and Python 3.9+. Extract the ZIP and move `AI圆桌.app` to Applications. If macOS asks you to verify its source, check the release checksum and see [Apple’s guidance](https://support.apple.com/en-us/102445). |

Meetings and settings are stored on your computer. Bring your own model access or local model. Cloud tools may send questions, attachments and cited code to their provider and use your quota. [Model setup (Chinese)](docs/guide.zh-CN.md#配置-16-个席位) · [Run or build from source (Chinese)](docs/guide.zh-CN.md#源码运行与目录) · [Concurrency measurements and Windows checks](docs/verification.md)

<a name="从-v402-升级"></a>

### Upgrading from v4.0.2

**Quit the app and back up the whole data directory first.** The default is `~/.ai-roundtable/` on Mac or `%USERPROFILE%\.ai-roundtable` on Windows. If you set `AI_ROUNDTABLE_HOME`, back up that directory instead. On save, 5.5.1 retains the 50 most recent meetings. A full rewrite of a meeting retains its last 500 messages. Deleted meetings have no recovery bin. For projects with more than 128 MiB of managed files, bind a smaller subfolder. If you depend on the older history or large-folder behavior, you can [stay on v4.0.2](https://github.com/Catcherog/ai-roundtable/releases/tag/v4.0.2).

[Report an issue or share a question worth debating](https://github.com/Catcherog/ai-roundtable/issues)
