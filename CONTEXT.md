# Trail 上下文压缩

> 生成时间：2026-03-10
> 用途：快速恢复产品与实现上下文

## 当前结论

- 产品名先定为 `Trail`
- 方向从“全桌面输入记忆”进一步收敛为“AI CLI 会话记忆层”
- 第一版不做全局终端监听，而是做显式 PTY wrapper
- 第一版不做 OCR、不做全桌面采集、不做云同步、不做 GUI

## 为什么继续收敛到 AI CLI

- Kayce 的高价值终端行为主要发生在 `Codex` / `Claude Code` 这类交互式 AI CLI 内
- 单纯 shell hook 只能记住“启动过 codex / claude”，记不住真正有价值的 prompt 和会话
- PTY wrapper 不需要系统级权限，能直接拿到交互式 stdin/stdout
- 对当前真实使用场景来说，AI CLI 会话比普通命令历史更重要

## 产品一句话

Trail 是一个面向 `Codex`、`Claude Code` 等 AI CLI 的会话记忆层：通过 PTY wrapper 显式代理交互会话，记录提示词、上下文和会话轨迹，让用户能搜索、回放、总结，并把这些历史继续喂给 AI。

## 目标用户

- 重度使用 `Codex` / `Claude Code` 的开发者
- 把终端当主工作界面的 AI coding 用户
- 需要在 repo、排障和 prompt 之间反复切换的技术用户

## 用户价值

- 找回：我上周在 Codex 里问过什么
- 复盘：哪轮 Claude / Codex 会话把问题真正解决掉了
- 总结：我今天在 AI CLI 里做了哪些事
- AI 调用：把过去的 prompt 和回复继续喂给 AI

## 不做什么

- 全桌面输入记录
- OCR
- 屏幕录制
- 逐键捕获
- 非终端应用采集
- 云端同步
- 第一版 GUI
- 所有终端程序通吃

## MVP 范围

- 显式支持：
  - `trail wrap codex`
  - `trail wrap claude`
- 记录：
  - `tool`
  - `cwd`
  - `repo root / branch`
  - `started_at / ended_at`
  - 用户输入块
  - AI 输出文本块
- 本地 `SQLite` 存储
- 原始事件流按 session 落本地 `jsonl`
- `FTS5` 搜索
- CLI 能力：
  - `trail sessions`
  - `trail search`
  - `trail show`
  - `trail day`
- 基础敏感信息打码

## 技术路线

### 采集

- `Trail` 自己作为启动入口
- 用 `PTY wrapper` 拉起 `codex` / `claude`
- 代理 stdin/stdout 并记录事件流
- 会话结束后提取 `user` / `assistant` turns

### 存储

- SQLite
- `sessions` 表
- `session_events` 表
- `turns` 表
- FTS5 索引

### 形态

- MVP 用 `CLI + PTY wrapper`
- 菜单栏 App 不是第一阶段必需

## 数据模型草案

### sessions

- id
- tool
- argv_redacted
- cwd
- repo_root
- git_branch
- hostname
- terminal_program
- started_at
- ended_at
- exit_code
- raw_log_path

### session_events

- id
- session_id
- seq
- stream
- event_type
- ts
- payload_text_redacted
- payload_meta_json

### turns

- id
- session_id
- seq
- role
- text_redacted
- started_at
- ended_at
- parser_version
- confidence

## 为什么它不等于 shell history

- history 只能看到“启动过 codex / claude”
- history 看不到交互式 prompt 和 AI 回复
- history 不关心会话边界和 repo 上下文
- history 很难直接喂给 AI

一句话差异：

`history 是命令日志，Trail 是 AI CLI 会话记忆。`

## 3 周路线

### Week 1

- 定义 `sessions / session_events / turns` schema
- 跑通 `trail wrap codex` / `trail wrap claude`
- 打通 PTY 代理和本地日志
- 跑通 `trail sessions` / `trail show`

### Week 2

- 基础打码
- turn 提取
- `trail search`
- `trail init zsh`

### Week 3

- `trail day`
- repo 维度摘要
- prompt 搜索优化
- AI 总结接口

## 当前已落文档

- [README.md](/Users/xujian/Code/trail/README.md)
- [ARCHITECTURE.md](/Users/xujian/Code/trail/ARCHITECTURE.md)
- [todo.md](/Users/xujian/Code/trail/todo.md)

## 下一步

1. 建 `pyproject.toml`
2. 起 `trail/cli.py`、`trail/pty_runner.py`、`trail/db.py`
3. 先实现最小闭环：
   - `trail wrap codex`
   - session 入库
   - 事件流日志
   - `trail sessions`
