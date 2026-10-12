# 堡垒机部署skill叫什么名字

- Chat ID: `mojemgfifkl0o1ys`
- 分类：堡垒机部署
- 起始日期：2026-04-29
- 会话文件数：1

---


## 会话 1/1 · `5c0ddf89`

### 🧑 用户 · 2026-04-29T01:56:49.502Z

堡垒机部署skill叫什么名字

<system-reminder>
User environment — Timezone: Asia/Shanghai (UTC+08:00). Locale: en-US. OS: darwin.
Note: If you need the current date or time, run `date` via Bash to get a fresh, accurate value. Do not assume a fixed time.
</system-reminder>
<system-reminder>
Available MCP servers:
- builtin_browser: Browser automation via Chrome Extension. Always call tabs_context_mcp first to create or get your MCP tab group before any other tool. Existing tabs may belong to other AI agents, so avoid reusing them unless the user explicitly asks; for new conversations, prefer creating your own tab. Typical flow: tabs_context_mcp -> navigate -> read_page/find -> computer or form_input. Also supports get_page_text, javascript_tool, file_upload, console, and network.

Use qw_mcp_list to see all tools, qw_mcp_get to get tool schema (ALWAYS call this before qw_mcp_call to get correct arguments), qw_mcp_call to execute.

Available tools:
mcp__builtin_browser__computer, mcp__builtin_browser__read_page, mcp__builtin_browser__find, mcp__builtin_browser__form_input, mcp__builtin_browser__navigate, mcp__builtin_browser__javascript_tool, mcp__builtin_browser__get_page_text, mcp__builtin_browser__file_upload, mcp__builtin_browser__resize_window, mcp__builtin_browser__read_console_messages, mcp__builtin_browser__read_network_requests, mcp__builtin_browser__tabs_context, mcp__builtin_browser__tabs_create, mcp__builtin_browser__tabs_context_mcp, mcp__builtin_browser__tabs_create_mcp, mcp__builtin_browser__tabs_close_mcp
</system-reminder>

### 🤖 助手 · 2026-04-29T01:56:49.511Z

从已安装的技能列表来看，跟堡垒机部署相关的 skill 主要有两个：

**`jumpserver-tiance-deploy`** — 这是主要的堡垒机部署技能，用于通过 JumpServer 部署天策决策中台 POC 环境，涵盖 expect 自动化、SSH 隧道、中间件安装、应用部署、场景应用（信贷/贷中）等完整流程。

**`jumpserver-win`** — 这是 Windows 环境专用的堡垒机操作技能，基于 Python paramiko 实现，不依赖 expect/sshpass。

另外还有一个备份版本 `jumpserver-tiance-deploy.bak.20260326135951`，是旧版存档，一般不需要用到。

需要我帮你调用其中某个技能吗？

### 🧑 用户 · 2026-04-29T02:06:56.864Z

现在这个skill在远程仓库有更新吗？使用skill-sync拉一下

### 🤖 助手 · 2026-04-29T02:07:14.557Z

`skill-sync` 是一个断开的符号链接，指向 `/Users/td/.qoderwork/skills-repo/packages/skill-sync/skills/skill-sync/`，目标路径不存在。让我检查一下 skills-repo 的情况。

### 🤖 助手 · 2026-04-29T02:07:25.599Z

找到了，`skills-repo` 存在，但 `skill-sync` 的符号链接路径不对。让我先拉取远程仓库最新代码，然后修复链接并使用它来同步 `jumpserver-tiance-deploy`。

### 🤖 助手 · 2026-04-29T02:07:37.894Z

仓库已拉取到最新。现在让我看看 `skill-sync` 的 SKILL.md 来了解它的同步机制，同时检查 `jumpserver-tiance-deploy` 是否有更新。

### 🤖 助手 · 2026-04-29T02:07:46.031Z

现在让我读取工作流 G 的详细文档，了解更新 skill 的具体步骤。

### 🤖 助手 · 2026-04-29T02:07:56.151Z

好的，现在按照工作流 G 的步骤来操作。仓库已经拉取到最新了，接下来需要对比远端和本地版本差异，然后同步。

### 🤖 助手 · 2026-04-29T02:08:42.921Z

检测到 4 个文件有远端更新。现在将远端最新版本同步到本地。

### 🤖 助手 · 2026-04-29T02:08:58.451Z

同步完成！以下是更新结果：

**jumpserver-tiance-deploy** 远端仓库版本 v1.0.6，检测到 4 个文件有更新并已同步：

- `SKILL.md` — 技能说明更新
- `deploy-steps.md` — 部署步骤文档更新
- `troubleshooting.md` — 故障排查文档更新
- `scripts/jrun.sh` — 堡垒机执行脚本更新

本地已与远端保持一致。

另外提一下，`skill-sync` 本身的符号链接是断的（指向了一个不存在的子目录），所以无法直接作为 skill 调用。如果需要修复这个链接让 skill-sync 以后能正常使用，我可以帮你处理。

### 🧑 用户 · 2026-04-29T02:09:30.673Z

现在这个skill支持哪些应用的部署？

### 🤖 助手 · 2026-04-29T02:09:34.358Z

根据最新版 SKILL.md（v1.0.6），当前支持部署的应用分为三大类：

**核心必装应用（6个）：** tdjob（定时任务）、bifrost（认证/字段管理）、salaxy（指标/决策流）、tiangong-admin（规则管理/名单管理）、tiangong-api（风控引擎）、kratos-consumer（消息消费）。

**场景应用（按需部署）：** spartan（交易风控）、spartan-account（账户风控）、atreus（贷前/信贷）、galaxy-guard（贷中监控）。

**可选/模型类应用：** tianzuo-admin（布局管理-管理端）、tianzuo-api（布局管理-服务端）、tianzuo-captain（布局管理-调度）、holmes-web（模型管理）、holmes-python（模型计算，Python 服务）。

总共支持 **15 个应用**的部署，覆盖了天策决策中台的完整功能链（基础平台 + 交易/信贷/账户/贷中场景 + 模型 + 布局管理）。相比之前的版本，v1.0.6 新增了场景应用（atreus、galaxy-guard）、tianzuo 三件套拆分部署、以及跨服务器分布式部署方案。
