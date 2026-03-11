# Trail

Trail 是一个面向 `Codex`、`Claude Code` 等 AI CLI 的会话记忆层：通过 PTY wrapper 显式代理交互会话，把本地会话稳定沉淀成 markdown transcript。它的核心不是做一个很重的产品层，而是把资料记录好，让人和 agent 都能直接读取 `~/.trail/transcripts/`。

## 它解决什么问题

如果你的终端主要在跑 AI CLI，普通 shell history 基本没用，因为它只能告诉你：

- 你启动过 `codex`
- 你启动过 `claude`

但真正重要的信息在交互会话里：

- 你到底问了什么
- AI 当时怎么回的
- 这轮对话发生在哪个 repo
- 哪些 prompt 最终真的解决了问题

Trail 要解决的是这部分“会话记忆”，不是命令历史增强。

## 第一版范围

第一版只做显式包装的 AI CLI 会话，不做全局终端监听，不做全桌面输入，不做 OCR，不做云同步，不做 GUI。

MVP 包含：

- `trail wrap codex`
- `trail wrap claude`
- PTY 代理运行
- 记录会话元信息：
  - `cwd`
  - `repo`
  - `branch`
  - `started_at` / `ended_at`
  - `tool`
- 记录会话事件流：
  - 用户提交后的 prompt
  - 原始 `stdout` / `meta` 事件
  - 基础时间线
- 自动产出 markdown transcript：
  - `~/.trail/transcripts/YYYY-MM-DD/<time>--<tool>--<session_id>.md`
  - 活跃 session 期间持续更新，不必等会话结束
  - frontmatter 带 `date` / `week` / `started_at` / `ended_at` / `last_synced_at`
- `SQLite + FTS5`
- CLI：
  - `trail sessions`
  - `trail search`
  - `trail show`
  - `trail watch`
  - `trail rebuild`
  - `trail reindex`
  - `trail day`
  - `trail doctor`
  - `trail config`
- 基础敏感信息打码

## 为什么它不只是终端录制

- 它是 `opt-in` 的 wrapper，不是后台偷录
- 它关心的是 `AI CLI 会话`，不是所有终端程序
- 它默认偏向记录“提交后的 prompt + 原始 AI 会话输出”，而不是逐键输入过程
- 它把原始事件和结构化 transcript 分开存，方便重建
- 它的目标是搜索、总结和 AI 复用，不是像素级回放

一句话差异：

`script 在录屏幕，Trail 在记会话。`

## 当前技术判断

v0 先用 `Python 3.9 + SQLite`，理由比之前更充分：

- 本机现成可用
- `pty`、`termios`、`select`、`signal`、`sqlite3` 都在标准库里
- 做 PTY 代理、事件流记录和 CLI 足够快
- 先把交互式 AI CLI 这个核心闭环做出来，比一开始追求语言优雅更重要

如果产品成立，再考虑迁到单二进制栈。

## 近期目标

1. 跑通 `trail wrap codex/claude`
2. 落会话表和事件表
3. 记录用户输入块和 AI 输出块
4. 跑通 `trail sessions` / `trail search` / `trail show`
5. 做基础 prompt 搜索和日摘要

## Transcript 主线

Trail 现在的主线不是“实时过滤”，而是：

1. 保留原始 `session_events`
2. 会话过程中持续重建 `turns`
3. 持续导出 markdown transcript
4. parser 变好时，用 `rebuild` / `reindex` 重建 transcript

```bash
trail rebuild <session_id>
trail reindex --tool claude
```

对 agent 来说，最重要的接口就是目录本身：

- `~/.trail/transcripts/`：主产物，agent 应优先读取
- `~/.trail/sessions/`：原始 jsonl 证据流
- `~/.trail/trail.db`：内部索引层，不是主接口

如果你要做按天/按周复盘，最直接的输入就是：

- `~/.trail/transcripts/YYYY-MM-DD/*.md`
- markdown frontmatter 里的 `kind` / `schema_version` / `date` / `week` / `started_at` / `ended_at`

## 实时观察

`trail watch` 现在更偏向调试工具，不是核心使用路径。它可以实时看正在进行中的 session，但真正用来回顾和搜索的应该是 `show/search/day`。

```bash
trail watch --tool claude
```

它会等待一个匹配的活跃 session 出现，然后持续打印新增事件。也可以切到结构化视图：

```bash
trail watch --tool claude --mode turns
trail watch <session_id> --mode turns
```

默认情况下，`watch` 会从 `~/.trail/config.json` 读取配置；没有配置文件时使用内置默认值。

## 安装与配置

最稳的冷启动方式：

```bash
git clone <your-trail-repo>
cd trail
./install.sh
source ~/.zshrc
```

`install.sh` 会做这几件事：

- 把 `bin/trail` 链接到 `~/.local/bin/trail`
- 在 `~/.zshrc` 写入 `claude` / `codex` wrapper
- 初始化 `~/.trail/config.json`
- 跑一遍 `trail doctor`

之后你就按平常方式用：

```bash
claude
```

Trail 会自动把每个 session 持续写进本地 markdown。想自己看就直接打开：

```bash
~/.trail/transcripts/YYYY-MM-DD/*.md
```

开发时也可以直接这样跑：

```bash
python3 -m trail doctor
python3 -m trail config init
trail init zsh
```

- `trail doctor`：检查 `trail` / `claude` 是否在 `PATH`、Trail home 是否可用、`~/.zshrc` 是否已经接入包装函数。
- `trail config show`：查看当前合并后的配置。
- `trail config set watch.mode events`：修改默认 `watch` 行为。
- `trail rebuild <session_id>`：用当前 parser 重新生成单次会话 transcript。
- `trail reindex --tool claude`：批量重建 transcript。

## 文档

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [todo.md](./todo.md)

## Transcript Schema

Trail 的主接口是 markdown frontmatter，不是 JSON API。字段定义见 [TRANSCRIPT_SCHEMA.md](./TRANSCRIPT_SCHEMA.md)。agent 读取 transcript 时，应优先依赖 frontmatter + `## Transcript` 正文，不要依赖 CLI 输出格式。
