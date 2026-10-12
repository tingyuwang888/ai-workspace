# tdjob是什么？通过堡垒机部署

- Chat ID: `mol7jpgdis35ovlk`
- 分类：堡垒机部署
- 起始日期：2026-04-30
- 会话文件数：1

---


## 会话 1/1 · `64f0d600`

### 🧑 用户 · 2026-04-30T08:14:17.175Z

tdjob是个什么东西？通过堡垒机部署tiance这个skill里包含tdjob的部署吗？

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

### 🤖 助手 · 2026-04-30T08:14:17.188Z

让我先查看一下相关的 skill 内容，了解 tdjob 的具体信息。

### 🤖 助手 · 2026-04-30T08:14:34.763Z

根据 skill 中的信息，**tdjob** 是天策（Tiance）决策中台中的**定时任务服务**，负责调度和执行系统内部的定时任务。它运行在 HTTP 端口 8011 上，推荐 JVM 内存为 256m~512m，是天策平台的必装组件之一。

关于你的第二个问题——**是的，jumpserver-tiance-deploy 这个 skill 包含了 tdjob 的部署**。从 skill 描述和内容来看，tdjob 被归类在应用服务器（APP_SERVER）上，和 Nginx、其他应用服务、前端资源部署在一起。在整个部署流程中，tdjob 的部署顺序排在 Nginx 之后、bifrost 之前。另外 hera-deploy 这个 skill 同样也包含 tdjob 的部署。

值得一提的是，skill 中还记录了一个已知问题：tdjob 的启动脚本 `server.sh` 存在变量解析缺陷，可能在实际已启动成功的情况下报 "Start Failed"，具体排查方法可以参考 troubleshooting 文档中的案例 15。

### 🧑 用户 · 2026-04-30T08:15:41.176Z

<user-pasted-image file="/Users/td/.qoderwork/workspace/mol7jpgdis35ovlk/uploads/image_1777536940276_p8orjo2.png" /> 那这里tiangong-admin这里会出现地址为空的这种情况吗？

### 🤖 助手 · 2026-04-30T08:15:41.184Z

从截图来看，这是 tdjob（基于 XXL-Job）的**执行器管理**页面。红框标注的 `tiangong-admin-batch`（AppName: `tiangong-admin-2501-mysql`）注册方式是"自动注册"，但 OnLine 机器地址显示为"无"。

这种情况是**会出现的**，而且比较常见。地址为"无"说明 tiangong-admin 的定时任务执行器没有成功注册到 tdjob 调度中心。通常有几种原因：

1. **tiangong-admin 服务没有启动**，或者启动过程中失败了，执行器自然无法向 tdjob 注册。

2. **tiangong-admin 已启动但执行器组件注册失败**，常见于配置文件中 tdjob 的地址配错了（比如 `xxl.job.admin.addresses` 指向了错误的 IP 或端口），导致执行器找不到调度中心。

3. **网络不通**，tiangong-admin 所在机器无法访问 tdjob 的 8011 端口，防火墙或网络策略阻断了通信。

4. **注册延迟**，如果 tiangong-admin 刚刚启动，执行器的自动注册有一个心跳周期（默认约 30 秒），可能还没来得及上报。

你可以按这个顺序排查：先确认 tiangong-admin 是否正常运行（检查进程和日志），然后检查其配置中 xxl-job 相关的地址是否正确指向了 tdjob 服务，最后确认两者之间的网络连通性。如果服务是正常的，等一两个心跳周期后刷新页面一般就能看到机器地址了。
