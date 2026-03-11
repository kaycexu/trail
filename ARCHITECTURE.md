# Trail 架构草案

## 1. 设计原则

第一版遵守 6 条原则：

1. `显式包装，绝不全局偷录`
2. `先支持 AI CLI，会话比命令更重要`
3. `原始事件流和结构化 transcript 分开`
4. `默认本地优先`
5. `敏感信息宁可多打码，不要少打码`
6. `先保证终端体验不坏，再追求功能丰富`

## 2. 产品边界

Trail v0 不是：

- shell history 增强器
- 全终端录制器
- 全桌面输入层

Trail v0 是：

- `Codex` / `Claude Code` 的显式 PTY wrapper
- 面向 AI CLI 的会话记忆层

第一版只关心这类问题：

- 我在 Codex 里问过什么
- 哪轮 Claude 会话是在这个 repo 里完成的
- 今天哪些 prompt 真的解决了问题

## 3. v0 技术栈

- 语言：`Python 3.9`
- 运行时：`CLI + PTY wrapper`
- 存储：`SQLite + FTS5`
- 原始日志：按 session 落本地 `jsonl`

为什么还是 Python：

- 本机现成可用
- `pty`、`termios`、`tty`、`fcntl`、`select`、`signal`、`sqlite3` 都在标准库
- 写 PTY 代理和本地索引足够快
- 现在最关键的是尽快验证“AI CLI 会话记忆”是否成立

## 4. 组件

### CLI 层

建议命令：

- `trail wrap <tool> [args...]`
- `trail codex [args...]`
- `trail claude [args...]`
- `trail sessions`
- `trail search <query>`
- `trail show <session-id>`
- `trail day`
- `trail init zsh`

### PTY 运行时

职责：

- 拉起子进程
- 代理 stdin/stdout
- 记录事件流
- 维持原有交互体验

### 适配器层

按工具区分：

- `codex` 适配器
- `claude` 适配器

职责：

- 识别输入块
- 归一化输出文本
- 提取 turn

### 存储层

- `trail.db`
- `sessions`
- `session_events`
- `turns`
- `turns_fts`

### 摘要层

- 先做规则版摘要
- AI 总结接口放第二阶段

## 5. 执行模型

### 启动方式

推荐两种用法：

```bash
trail codex
trail claude
```

或者在 `zsh` 里装函数：

```zsh
codex() { command trail wrap codex "$@"; }
claude() { command trail wrap claude "$@"; }
```

这里的核心不是 hook，而是 `Trail 自己成为启动入口`。

### PTY 代理流程

1. 用户运行 `trail wrap codex`
2. Trail 生成 `session_id`
3. 采集会话元信息：
   - `tool`
   - `argv`
   - `cwd`
   - `repo_root`
   - `git_branch`
   - `hostname`
   - `TERM_PROGRAM`
4. Trail 创建 PTY，启动子进程
5. 父进程进入事件循环：
   - 读取用户 stdin，写入子进程 PTY
   - 读取子进程 stdout/stderr，经 PTY 回写给当前终端
   - 同时把双向事件写入日志
6. 子进程退出后，Trail 结束会话并做 turn 提取
7. parser 迭代后，可对旧 session 执行 `rebuild/reindex`

## 6. 为什么要用 PTY wrapper

因为 `preexec/precmd` 只能看到：

- 你启动了 `codex`
- 你启动了 `claude`

但看不到：

- 交互式输入
- AI 输出
- 一轮会话内部发生了什么

PTY wrapper 能拿到完整交互字节流，而且不需要系统级权限。这是当前场景下最合适的入口。

## 7. 事件流模型

第一版先保存“原始会话事件”，再从事件里抽结构化 turn。

### session_events

建议字段：

- `id`
- `session_id`
- `seq`
- `stream`
  - `stdin`
  - `stdout`
  - `stderr`
  - `meta`
- `event_type`
  - `text`
  - `resize`
  - `start`
  - `end`
- `ts`
- `payload_text_redacted`
- `payload_meta_json`

### 为什么先存事件流

- TUI 交互不是天然 line-based
- prompt 和输出块的边界不总是稳定
- 先有事件流，后面可以反复改 turn 提取逻辑
- 原始事件是调试解析器的唯一依据
- 不把“实时过滤”当成主真相，避免误删后无法恢复

## 8. 结构化 turn

Trail 的真正产品价值不在原始 transcript，而在“会话后提纯出的可搜索 transcript”。

因此需要第二层数据：

### turns

建议字段：

- `id`
- `session_id`
- `seq`
- `role`
  - `user`
  - `assistant`
- `text_redacted`
- `started_at`
- `ended_at`
- `parser_version`
- `confidence`

### turn 提取策略

第一版不要追求完美解析，先做可用解析：

- 用户连续输入的可打印文本归并成一个输入缓冲区
- 过滤方向键、控制序列、纯导航按键
- 当出现明显“提交后 AI 开始输出”的迹象时，提交一个 `user turn`
- 紧随其后的连续输出文本归并成一个 `assistant turn`

这部分必须允许低置信度，因为 Codex / Claude 的 TUI 不保证稳定协议。

### `rebuild / reindex`

parser 不是一次性逻辑，而是可迭代层：

- `trail rebuild <session_id>`：重建单次会话 transcript
- `trail reindex`：批量重建多次会话 transcript

这样新规则可以直接作用到旧 session，而不是依赖运行时把每一条输出都猜对。

## 9. 工具适配器

### `codex` / `claude` 为什么要做单独适配

虽然底层都是 PTY，但不同工具的 UI 行为不同：

- alternate screen 使用方式不同
- spinner / progress 输出形式不同
- 输入提交前后的可观察模式不同

所以产品上必须接受一个事实：

`Trail 不是做“所有 TUI 通吃”，而是做“少数高价值 AI CLI 深适配”。`

### v0 适配器职责

- 清洗 ANSI 控制序列
- 折叠高频重复输出
- 提取相对干净的文本块
- 基于启发式规则划分 turn

## 10. 终端体验要求

这部分是成败点，不是边角料。

Trail 必须尽量不破坏这些行为：

- `Ctrl-C`
- 窗口 resize
- alternate screen
- 光标移动
- 粘贴大段 prompt

第一版可以暂时不优先处理：

- job control
- `Ctrl-Z`
- 复杂鼠标事件

## 11. 存储设计

### 建议目录

```text
~/.trail/
├── trail.db
└── sessions/
    ├── <session-id>.jsonl
    └── ...
```

### sessions

建议字段：

- `id`
- `tool`
- `argv_redacted`
- `cwd`
- `repo_root`
- `git_branch`
- `hostname`
- `terminal_program`
- `started_at`
- `ended_at`
- `exit_code`
- `raw_log_path`
- `bytes_in`
- `bytes_out`

### session_events

保存 redacted 后的文本事件和 meta 事件。

### turns

保存可搜索的用户 prompt 和 AI 输出块。

### FTS

对这些字段做全文索引：

- `turns.text_redacted`
- `sessions.cwd`
- `sessions.repo_root`
- `sessions.git_branch`
- `sessions.tool`

## 12. 敏感信息策略

这是产品合法性和可用性的底线。

第一版策略：

- 所有落库文本默认先打码
- 不存未打码原文
- 事件流日志也存 redacted 版本

至少处理：

- `TOKEN=xxx`
- `PASSWORD=xxx`
- `COOKIE=xxx`
- `AUTHORIZATION=xxx`
- `--token xxx`
- `--password xxx`
- `Bearer xxx`

后续要补：

- SSH 私钥片段
- API key 常见前缀
- `.env` 内容误贴

## 13. CLI 设计

### `trail wrap <tool>`

通用入口，用来包任意支持的 AI CLI。

### `trail codex`

等价于：

```bash
trail wrap codex
```

### `trail claude`

等价于：

```bash
trail wrap claude
```

### `trail sessions`

- 默认列最近会话
- 支持 `--tool`
- 支持 `--repo`

### `trail search <query>`

- 默认搜 `turns`
- 支持 `--role user|assistant|all`
- 支持 `--tool`
- 支持 `--repo`
- 支持 `--since`

### `trail show <session-id>`

- 看单次会话摘要
- 展示关键 turns
- 后续可加原始 transcript 查看

### `trail day`

- 汇总当天的 AI CLI 会话
- 输出：
  - 跑了多少次 Codex/Claude
  - 哪些 repo 最活跃
  - 哪些 prompt 最常见
  - 哪些 session 最长

### `trail init zsh`

- 输出包装函数到终端
- 第一版不自动改 `.zshrc`

## 14. 目录建议

```text
trail/
├── README.md
├── ARCHITECTURE.md
├── todo.md
├── pyproject.toml
├── trail/
│   ├── __init__.py
│   ├── cli.py
│   ├── db.py
│   ├── pty_runner.py
│   ├── redact.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── codex.py
│   │   └── claude.py
│   └── commands/
│       ├── wrap_cmd.py
│       ├── sessions_cmd.py
│       ├── search_cmd.py
│       ├── show_cmd.py
│       └── day_cmd.py
└── tests/
```

## 15. 风险点

### 最容易低估的点

- PTY 代理会不会破坏 TUI 体验
- ANSI / alternate screen 清洗
- turn 边界提取不稳定
- AI 输出量大导致日志膨胀
- 打码误伤和漏打码

### 先别碰的点

- 所有终端程序通吃
- 全量像素级回放
- AI 自动续写和自动执行
- 云同步
- shell hook 全覆盖

## 16. 第一版成败标准

- 用户愿意用 `trail codex` / `trail claude` 代替直接启动
- 会话体验没有明显变差
- 能搜回过去一周问过的一条 prompt
- 能知道某个 repo 下最近做过哪些 AI 会话
- 用户不会因为隐私问题不敢开
