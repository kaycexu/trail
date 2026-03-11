# Trail TODO

## P0：最小闭环

- [x] 确定 v0 用 Python 3.9
- [x] 建 `pyproject.toml`
- [x] 定义 `sessions` / `session_events` / `turns` schema
- [x] 实现 `trail wrap <tool>`
- [x] 实现 `trail codex`
- [x] 实现 `trail claude`
- [x] 跑通 PTY 代理循环
- [x] 记录 `stdin/stdout` 事件到本地日志
- [x] 把 session metadata 写入 SQLite
- [x] 实现基础敏感信息打码
- [x] 实现 `trail sessions`
- [x] 实现 `trail search`
- [x] 实现 `trail show`
- [x] 实现 `trail watch`
- [x] 实现 `trail init zsh`
- [x] 实现 `trail doctor`
- [x] 实现 `trail config`

## P1：可用性

- [ ] 做更稳的 `codex` 适配器
- [x] 做第一版可用的 `claude` 适配器
- [x] 提取基础 `user` / `assistant` turns
- [x] 支持可配置的 `watch` 默认值
- [x] 支持 `--tool`
- [x] 支持 `--repo`
- [x] 支持 `--role`
- [x] 支持 `--since`
- [x] 实现 `trail day`
- [x] 实现 `trail rebuild`
- [x] 实现 `trail reindex`
- [ ] 处理窗口 resize
- [ ] 处理 `Ctrl-C`

## P2：产品感

- [ ] 最近这个 repo 下有哪些 AI 会话
- [ ] 最近问过哪些相似 prompt
- [ ] 长会话摘要
- [ ] 每日 AI CLI 工作摘要
- [ ] AI 总结接口
- [ ] 支持 parser 版本迁移说明
- [ ] 可选 shell hook 补充普通命令上下文

## 先不做

- [ ] 所有终端程序通吃
- [ ] 像素级终端回放
- [ ] GUI
- [ ] 云同步
- [ ] 全桌面输入记录
