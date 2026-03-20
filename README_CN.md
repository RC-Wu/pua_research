# pua_research

面向 Codex 的 ARIS 分支，用于自动化科研工作流。

这个仓库基于 `dev-intern-02` 上实际运行的 ARIS 工作树提交 `405eaf5` 打包而成，保留了 ARIS 原本的目录结构（`docs/`、`skills/`、`mcp-servers/`、`tools/`），但把默认执行端切到了 Codex，并把用户当前本地与远端环境里已经在用的 PUA、AgentDoc 桥接、远端 subagent、heartbeat、summary、账号路由和 peer-review 能力一起整理进来。

## 这个分支额外增加了什么

- `agentdoc-startup`
  - 连接外部 AgentDoc 检出，不把 AgentDoc 本体打进仓库
- `pua-complex-task-method`
  - 面向复杂任务的高主动性执行方法
- `remote-codex-subagents`
  - 通过 SSH 在远端启动脱离终端的 Codex worker
- `heartbeat-subagent-template`
  - 长跑任务的周期性监控模板
- `final-summary-subagent`
  - 汇总日志与笔记的最终总结 worker
- `peer-review`
  - 结构化论文与基金评审能力
- `tools/codex_route_preview.py`
  - 账号路由与任务难度到推理等级的预览工具

原始 ARIS 的研究工作流与 Codex 技能树仍然保留。

## 快速开始

```bash
git clone https://github.com/RC-Wu/pua_research.git
cd pua_research

mkdir -p ~/.codex/skills
cp -r skills/skills-codex/* ~/.codex/skills/

npm install -g @openai/codex
codex setup
codex
```

推荐入口：

- `Use skill agentdoc-startup`
- `Use skill pua-complex-task-method`
- `/idea-discovery "你的研究方向"`
- `/experiment-bridge`
- `/auto-review-loop "你的论文主题或范围"`
- `/paper-writing "NARRATIVE_REPORT.md"`
- `/research-pipeline "你的研究方向"`
- `Use skill peer-review`

## 关键文档

- [`docs/CODEX_PUA_STACK.md`](docs/CODEX_PUA_STACK.md)
- [`docs/AGENTDOC_BRIDGE.md`](docs/AGENTDOC_BRIDGE.md)
- [`docs/CODEX_CONTROL_PLANE.md`](docs/CODEX_CONTROL_PLANE.md)
- [`docs/CODEX_CLAUDE_REVIEW_GUIDE_CN.md`](docs/CODEX_CLAUDE_REVIEW_GUIDE_CN.md)
- [`docs/CURSOR_ADAPTATION.md`](docs/CURSOR_ADAPTATION.md)
- [`docs/MODELSCOPE_GUIDE.md`](docs/MODELSCOPE_GUIDE.md)

## 目录说明

- `skills/`
  - 保留 ARIS 原有技能树，并在 `skills/skills-codex/` 下加入 Codex-first 扩展技能
- `mcp-servers/`
  - ARIS 的 MCP 集成，包括 Codex/Claude 审稿桥
- `docs/`
  - 保留 ARIS 文档，并新增 PUA 与 AgentDoc 桥接说明
- `tools/`
  - 保留 ARIS 工具，并新增轻量级 control-plane 路由预览脚本

## AgentDoc 说明

AgentDoc 本体没有被打包进这个仓库。这里仅提供桥接 skill 和公开说明，用来安全地接入外部 AgentDoc 检出。

约定的外部 AgentDoc 路径：

- 本地 PC：`F:\InformationAndCourses\Code\AgentDoc`
- 开发机：`/dev_vepfs/rc_wu/AgentDoc`

## 兼容性

- 默认路径是 Codex-first。
- 原始 ARIS 风格的工作流和文档仍然保留。
- 如果你想保留“Codex 执行 + Claude 审稿”，仍可使用 `skills/skills-codex-claude-review/` 作为 overlay。
