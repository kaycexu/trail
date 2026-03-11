# Changelog

## 0.1.0 (2026-03-11)

首次发布。

### 核心功能
- PTY 会话包装与录制（`trail wrap`、`trail claude`、`trail codex`）
- SQLite 存储 + FTS5 全文搜索
- Claude / Codex 专用适配器，启发式 turn 提取
- Markdown 转录文件自动生成（`~/.trail/transcripts/`）
- 实时会话监控（`trail watch`）
- 会话搜索（`trail search`）与每日汇总（`trail day`）
- 敏感数据自动脱敏（API 密钥、令牌、密码等）
- 安装健康检查（`trail doctor`）
- 零外部依赖，纯 Python 标准库
