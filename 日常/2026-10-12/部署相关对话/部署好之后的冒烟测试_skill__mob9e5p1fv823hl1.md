# 部署好之后的冒烟测试 skill

- Chat ID: `mob9e5p1fv823hl1`
- 分类：部署技能维护
- 起始日期：2026-04-23
- 会话文件数：1

---


## 会话 1/1 · `071180d6`

### 🧑 用户 · 2026-04-23T09:08:17.950Z

是不是有个skill是做部署好之后的冒烟测试的？

<system-reminder>
User environment — Timezone: Asia/Shanghai (UTC+08:00). Locale: en-US. OS: darwin.
Note: If you need the current date or time, run `date` via Bash to get a fresh, accurate value. Do not assume a fixed time.
</system-reminder>
<system-reminder>
Available MCP servers:
- builtin_browser: Browser automation for web interaction. Core workflow: (1) Use list_tabs to get available tabs, (2) Use navigate to open URLs, (3) Use snapshot to read page content (lightweight, preferred) or screenshot for visual needs, (4) Use click/type/scroll/press_key to interact with elements via refs from snapshot. Also supports: hover, drag, select_option for forms, wait_for for delays, evaluate for JavaScript execution, and console_messages/network_requests for debugging.

Use qw_mcp_list to see all tools, qw_mcp_get to get tool schema (ALWAYS call this before qw_mcp_call to get correct arguments), qw_mcp_call to execute.

Available tools:
mcp__builtin_browser__list_tabs, mcp__builtin_browser__close_tab, mcp__builtin_browser__navigate, mcp__builtin_browser__snapshot, mcp__builtin_browser__screenshot, mcp__builtin_browser__click, mcp__builtin_browser__type, mcp__builtin_browser__hover, mcp__builtin_browser__drag, mcp__builtin_browser__select_option, mcp__builtin_browser__press_key, mcp__builtin_browser__scroll, mcp__builtin_browser__wait_for, mcp__builtin_browser__evaluate, mcp__builtin_browser__upload_file, mcp__builtin_browser__handle_dialog, mcp__builtin_browser__console_messages, mcp__builtin_browser__network_requests, mcp__builtin_browser__page_errors
</system-reminder>

### 🤖 助手 · 2026-04-23T09:08:17.968Z

让我帮你找一下，看看是否有冒烟测试相关的 skill。

### 🤖 助手 · 2026-04-23T09:08:50.117Z

找到了！是的，有一个叫 **tiangong-policy-smoke-test** 的 skill，就是做部署好之后的冒烟测试的。

它是天宫(Tiangong)决策平台的策略全链路冒烟测试，也叫天策系统冒烟测试。支持两种模式：

1. **模式 A**：提供 `.pls` 策略文件，自动导入策略并完成全链路验证（登录 → 服务预检 → 策略导入 → 上线 → 实验室测试 → 接口服务创建 → 多轮调用命中验证 → 事件历史闭环校验）。

2. **模式 B**：不提供 `.pls` 文件时，自动在 Salaxy 创建实时指标、通过 RSS 格式导入规则集并创建冒烟策略，完成全链路验证。

两种模式最终都会输出一份 Markdown 冒烟测试报告。调用时的 skill 名称是 `smoke-test`，需要的话我可以帮你跑起来。

### 🧑 用户 · 2026-04-23T09:10:15.149Z

需要执行模式B这种，我需要提供些什么？

### 🤖 助手 · 2026-04-23T09:10:20.250Z

模式 B 需要你提供的信息很少，只有三个必填项：

1. **平台地址** — 部署好的天策平台 URL，比如 `https://zhice.tcloud.tongdun.cn`
2. **登录账号** — 需要有策略管理和接口服务管理权限
3. **登录密码**

另外还有两个可选项，一般用默认值就行：

- **机构编码** — 默认 `TongDun`，如果你的环境用了自定义机构编码才需要改
- **导入渠道（appCode）** — 默认 `test_app`，账号需要对这个渠道有 Salaxy 指标管理权限

准备好这些信息告诉我就可以开始跑了。

### 🧑 用户 · 2026-04-23T09:13:12.903Z

平台地址：http://192.168.6.226:8088/ 登陆账号：wty 登陆密码：Td@1234567 机构编号使用默认的 ，导入渠道使用init

### 🧑 用户 · 2026-04-23T09:13:19.294Z

<command-message>The "smoke-test" skill is running</command-message>
<command-name>/smoke-test</command-name>
<command-args>平台地址: http://192.168.6.226:8088/ 登录账号: wty 登录密码: Td@1234567 机构编码: TongDun 导入渠道: init 模式B（不提供.pls文件）</command-args>

### 🤖 助手 · 2026-04-23T09:14:40.438Z

依赖安装完成，现在开始执行模式 B 冒烟测试。

### 🤖 助手 · 2026-04-23T09:15:21.667Z

冒烟测试在第一步登录就失败了，原因是 Bifrost 认证接口（getAuthCode）返回了 **HTTP 502 Bad Gateway**。这说明 `http://192.168.6.226:8088` 上的 Bifrost 后端服务当前不可达，请求经过了 Nginx 但没能转发到后端。

建议排查一下：

1. Bifrost 后端服务是否已启动（检查 bifrost 进程或容器状态）
2. Nginx 到 Bifrost 的反向代理配置是否正确
3. 如果平台地址带端口映射，确认端口 8088 确实指向了 Bifrost 入口

服务恢复后可以再跑一次。测试报告已生成：

[查看冒烟测试报告](file:///Users/td/.qoderwork/workspace/mob9e5p1fv823hl1/outputs/smoke_test_report.md)

### 🤖 助手 · 2026-04-23T09:15:34.107Z

冒烟测试在第一步登录就失败了。Bifrost 认证接口（getAuthCode）返回了 **HTTP 502 Bad Gateway**，说明 `http://192.168.6.226:8088` 上的 Bifrost 后端服务当前不可达——请求到了 Nginx，但 Nginx 无法将其转发到后端。

建议排查以下几点：

1. Bifrost 后端服务是否已正常启动（检查进程或容器状态）
2. Nginx 到 Bifrost 的反向代理配置是否正确
3. 端口 8088 是否确实指向了 Bifrost 的服务入口

服务恢复后告诉我，我可以立即重新跑一次。

[查看冒烟测试报告](file:///Users/td/.qoderwork/workspace/mob9e5p1fv823hl1/outputs/smoke_test_report.md)

### 🧑 用户 · 2026-04-23T09:19:23.148Z

http://192.168.6.226:8088/这个我可以登陆啊

### 🤖 助手 · 2026-04-23T09:19:23.155Z

让我先确认一下从本机到这个地址的网络连通性，以及脚本实际调用的接口情况。

### 🤖 助手 · 2026-04-23T09:19:34.591Z

网络是通的，authCode 接口也返回 200。可能是脚本拼接 URL 时有问题——你给的地址末尾带了 `/`，我来看看脚本中登录的实际请求路径。

### 🤖 助手 · 2026-04-23T09:20:00.944Z

接口现在是通的了，之前的 502 应该是瞬时的网络波动。我重新跑一次。

### 🤖 助手 · 2026-04-23T09:20:33.017Z

这次登录成功了，但在服务可达性预检中发现 **indexApi（Salaxy）** 和 **tradeApi（Spartan）** 两个服务不可达，导致后续步骤全部跳过。只有 **noahApi（天宫核心）** 是正常的。

具体来说：

- **Salaxy 不可达** → 无法创建实时指标 → 无法创建规则集和策略 → 后续实验室测试、接口服务、命中验证全部跳过
- **Spartan 不可达** → 事件历史查询也跳过了

你需要检查一下这台机器上 Salaxy 和 Spartan 服务的状态。通常是 Nginx 缺少 `/indexApi/` 和 `/tradeApi/` 的路由配置，或者对应的后端服务没有启动。可以重点看看：

1. Salaxy 服务进程是否正常运行
2. Spartan 服务进程是否正常运行
3. Nginx 配置中是否有 `indexApi` 和 `tradeApi` 的 location 代理规则

服务修复后随时告诉我，我再跑一次。

[查看冒烟测试报告](file:///Users/td/.qoderwork/workspace/mob9e5p1fv823hl1/outputs/smoke_test_report.md)
