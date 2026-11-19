<p align="center"><img src="docs/images/app-icon.png" alt="AI 圆桌图标" width="88" height="88"></p>

# AI 圆桌 · 好方案，值得一个反对席。

[English](README.en.md) · 简体中文

一个 AI 说「这个方案可行」时，你最想追问什么？在 AI 圆桌，你可以让另一个席位专门回答：**「什么情况下，它会失败？」**

在 Windows 或 Mac 上，把 1–6 个 AI 席位请到同一张桌上。让一个提案、一个找反例、一个把争论整理成明天能做的事。不用在几个聊天窗口之间搬运答案，也不用为了凑齐一桌去开六个账号。**最后拍板的是你。**

**[下载 Windows x64 版](https://github.com/Catcherog/ai-roundtable/releases/latest/download/AI-Roundtable-Windows-x64.zip)** · **[下载 Apple 芯片 Mac 版](https://github.com/Catcherog/ai-roundtable/releases/latest/download/AI-Roundtable-macOS-arm64.zip)** · [安装与首次打开](docs/guide.zh-CN.md#安装与首次打开) · [版本与校验值](https://github.com/Catcherog/ai-roundtable/releases/latest)

已有 v4.0.2 会议记录？请先看[升级前的备份提醒](#从-v402-升级)。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/roundtable-5.5.1-dark.png">
  <img src="docs/images/roundtable-5.5.1.png" alt="AI 圆桌 5.5.1 实拍：三个席位就座，已选中方案辩证，输入框里是离线记录与跨设备同步的取舍题。">
</picture>

## 第一场会，就问一道有取舍的题

先在终端确认一个受支持的模型工具（例如 Codex 或 Claude Code）能回答问题。打开圆桌，在「设置 → 席位与模型」给参会席位选好驱动和模型，保存配置。**只有一个已登录的工具也可以分饰多角**；想比较不同模型，再给席位换搭档。

选「方案利弊红蓝辩证包」，粘贴这段话，点「开始研讨」。这道题不用绑定项目：

> 我们两个人做的待办 App 一周后上线，只够做「离线记录」或「跨设备同步」中的一个。请正反两席各替一个方案辩护，再各说一条会让自己改主意的证据。最后，给我一个明天就能做的验证。

听到两边的理由之后，再追问一句：**「如果首批用户每天都坐没信号的地铁呢？」** 看哪一席会改口、为什么。点「形成决议」，把你认同的判断放上白板，连同仍有分歧的地方一起导出为 Markdown。多席的价值不在票数，而在你能看见每条建议依赖什么假设。

## 哪些事值得开一桌？

| 你手边的事 | 试试这样开场 | 散会时带走什么 |
| --- | --- | --- |
| 两个方案都说得通 | 「如果只能选一个，哪个判断错了会付出更大代价？」 | 取舍理由、还没验证的假设、一个小实验。 |
| 准备改代码 | 用 `@文件名:起始行-结束行` 引用实现：「先找会在哪种输入下出错，再讨论怎么改。」 | 有出处的风险和修复任务；可以先做只读预演，再决定是否允许写入。 |
| 一个界面总让人点错 | 粘贴或拖入截图：「第一次来的人下一步会点哪？请指出画面里的依据。」 | 可以逐条核对的问题清单，而不只是一句「优化体验」。看图需所选模型支持。 |

想先看看一场真实的讨论？[看三席怎样为一次平票定规则](docs/images/roundtable-session.png)：一席建议加投，一席坚持投票前公布规则，第三席提醒重试时不能重新抽签。这是早期版本留下的真实会议截图。

## 下载前知道两件事

- **桌面程序不附送模型或额度。** Windows 10/11 x64：完整解压再打开 `AI-Roundtable.exe`，包内含 Python 和 .NET，需要 Edge WebView2。Apple 芯片 Mac：需要 macOS 12 或更高版本及 Python 3.9+，解压后把 `AI圆桌.app` 拖入「应用程序」。[详细安装说明](docs/guide.zh-CN.md#安装与首次打开)
- **会议存在本机，不等于模型请求都离线。** 接入云端 CLI 时，议题、附件或引用的代码可能发给对应服务，并使用你的额度。仅讨论不需要绑定项目；要动文件时先用「只读预演」。[配置、执行与回滚](docs/guide.zh-CN.md)

### 从 v4.0.2 升级

**先完全退出应用，备份整个数据目录**：Mac 为 `~/.ai-roundtable/`，Windows 为 `%USERPROFILE%\.ai-roundtable`。5.5.1 在保存时只保留最近 50 场会议；整场重写时只保留最近 500 条发言。删除没有「最近删除」可恢复，受管文件合计超过 128 MiB 的目录也不能绑定。若你依赖旧版的不限量历史、删除恢复或大项目根目录支持，可以[继续用 v4.0.2](https://github.com/Catcherog/ai-roundtable/releases/tag/v4.0.2)。

[使用手册](docs/guide.zh-CN.md) · [源码运行与构建](docs/guide.zh-CN.md#源码运行与目录) · [验证记录](docs/verification.md) · [分享一个值得开圆桌的问题，或反馈使用体验](https://github.com/Catcherog/ai-roundtable/issues)
