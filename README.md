# Trail

> AI CLI 会话记忆层 — 把你和 Claude Code / Codex 的对话录下来，变成可搜索的 Markdown。

Trail 通过 PTY 包装透明录制 AI CLI 会话，持续写入 `~/.trail/transcripts/`。零外部依赖，纯 Python 标准库。

## 安装

```bash
git clone https://github.com/kaycexu/trail.git
cd trail
./install.sh
source ~/.zshrc
```

也可以用 pip：

```bash
pip install -e ".[dev]"
```

安装后正常使用 `claude` / `codex` 即可，Trail 自动在后台录制：

```bash
claude   # 自动被 trail 包装
codex    # 同上
```

## 查看转录

每次会话自动生成 Markdown 转录文件：

```
~/.trail/transcripts/
  └── 2026-03-11/
      └── 163022--claude--a1b2c3d4.md
```

## 常用命令

```bash
# 列出最近会话
trail sessions

# 搜索历史对话
trail search "怎么部署"

# 查看某次会话详情（支持 ID 前缀匹配）
trail show a1b2c3d4

# 今日汇总
trail day

# 实时观察进行中的会话
trail watch --tool claude

# 重建转录（parser 升级后）
trail rebuild <session_id>
trail reindex --tool claude

# 检查安装状态
trail doctor

# 查看/修改配置
trail config show
trail config set watch.mode events
```

## 工作原理

Trail 是一个 opt-in 的 PTY wrapper，不是后台监听。它只在你显式通过 `trail wrap` 或 shell alias 启动时才录制。

录制的数据存在本地：
- `~/.trail/transcripts/` — Markdown 转录（主接口）
- `~/.trail/sessions/` — 原始事件流（JSONL）
- `~/.trail/trail.db` — SQLite 索引 + FTS5 全文搜索

敏感信息（API 密钥、令牌、密码）自动脱敏。

## 文档

- [架构设计](./ARCHITECTURE.md)
- [转录格式](./TRANSCRIPT_SCHEMA.md)
- [贡献指南](./CONTRIBUTING.md)
- [变更日志](./CHANGELOG.md)

## License

[MIT](./LICENSE)
