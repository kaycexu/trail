# 贡献指南

感谢你对 Trail 的关注！以下是参与开发的基本流程。

## 开发环境搭建

```bash
git clone https://github.com/your-username/trail.git
cd trail
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## 测试要求

- 新功能需附带测试用例
- 提交前确保 `pytest` 全部通过
- 测试文件放在 `tests/` 目录下

## 代码风格

- **零外部依赖**：只使用 Python 标准库，这是本项目的核心原则
- 保持代码简洁，避免过度抽象

## 提交规范

- 使用简短、描述性的 commit message
- 一个 commit 做一件事

## 添加新工具适配器

如需支持新的 AI 工具，参考 `trail/adapters.py` 中 Claude 和 Codex 适配器的实现：

1. 在 `adapters.py` 中新建适配器类
2. 实现 turn 提取的启发式逻辑
3. 在 CLI 中注册对应的子命令
4. 编写测试覆盖主要场景
