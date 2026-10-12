# 环境故障排查

- Chat ID: `mojqozd0fc1jpaeh`
- 分类：环境运维
- 起始日期：2026-04-29
- 会话文件数：1

---


## 会话 1/1 · `75a2c088`

### 🧑 用户 · 2026-04-29T07:34:42.534Z

/Users/td/.qoderwork/workspace/mn73j641hy8bqrxk/outputs/三峡项目部署详情清单.docx 现在 这个环境打不开了，检查一下是什么原因

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

### 🤖 助手 · 2026-04-29T07:34:42.546Z

让我先检查一下这个文件的状态。

### 🤖 助手 · 2026-04-29T07:34:49.516Z

文件存在且被识别为有效的 Word 2007+ 格式（约 29KB）。让我进一步验证文件完整性，并把它复制到当前会话的输出目录。

### 🤖 助手 · 2026-04-29T07:35:04.643Z

文件本身完好无损（95个段落、7个表格），内容也能正常读取。问题在于这个文件位于之前会话的工作目录（`mn73j641hy8bqrxk`），而当前会话是另一个工作空间，所以之前的文件链接在当前环境中无法打开。

我把它复制到当前会话的输出目录，你就可以正常访问了：

### 🤖 助手 · 2026-04-29T07:35:18.375Z

文件没有损坏，打不开的原因是它属于之前的会话工作空间（`mn73j641hy8bqrxk`），当前会话无法直接通过链接访问旧会话的文件。

已经把它复制到当前会话了，现在可以正常打开：[查看文件](file:///Users/td/.qoderwork/workspace/mojqozd0fc1jpaeh/outputs/三峡项目部署详情清单.docx)

### 🧑 用户 · 2026-04-29T07:36:05.306Z

是这个部署的三峡项目环境打不开了

### 🤖 助手 · 2026-04-29T07:36:05.311Z

明白了，是部署的三峡项目环境本身打不开了，不是文档。让我先看看文档里的部署详情，了解环境信息。

### 🤖 助手 · 2026-04-29T07:37:11.104Z

好的，让我全面检查一下这个环境。先看看之前部署时留下的连接脚本和配置。

### 🤖 助手 · 2026-04-29T07:37:28.713Z

我注意到今天（4月29日）有几张截图，看起来你已经尝试过访问了。让我先看看这些截图和连接脚本。

### 🤖 助手 · 2026-04-29T07:37:40.896Z

从截图来看，登录页面能打开，也能进到大盘页面，但所有业务和系统指标都显示为 0。这说明 Nginx 和 bifrost 基本在运行，但后端服务可能有部分挂掉了。让我通过堡垒机检查三台服务器的服务状态。

### 🤖 助手 · 2026-04-29T07:38:15.037Z

好的，工具齐全。让我同时检查三台服务器上的 Java 进程和关键中间件状态。

### 🤖 助手 · 2026-04-29T07:44:27.890Z

71 的输出被截断了，让我重新检查一下，同时确认 231 上缺失的服务。

### 🤖 助手 · 2026-04-29T07:49:53.672Z

71 的输出被 Kafka 的长 classpath 截断了。让我更精确地检查 71 和其他关键服务。

### 🤖 助手 · 2026-04-29T07:53:41.700Z

好消息是中间件（71 上的 ZK/Kafka/Nacos）都在正常运行。问题定位到了——让我查一下崩溃日志确认原因。

### 🤖 助手 · 2026-04-29T07:57:23.521Z

让我看看最近的应用日志，确认崩溃原因。

### 🤖 助手 · 2026-04-29T08:02:01.338Z

排查完了，问题定位到了。整体来看中间件层（71 上的 ZooKeeper/Kafka/Nacos）和 MySQL/ES 都正常，问题出在两个关键 Java 应用挂了：

**1. tiangong-admin（232，端口 8503）—— 已挂，这是主要原因**

tiangong-admin 在 4 月 24 日 JVM 崩溃（有 hs_err 日志），之后虽然有多次重启尝试（GC 日志记录到今天 10:09），但目前进程不在、端口 8503 没有监听。这个服务是天策大盘的核心后端，负责处理 /noahApi/、/dataApi/、/dashboardApi/、/rosterApi/ 等路由。它挂了之后，大盘所有业务资产概览数字全部显示为 0，规则管理、数据管理等功能也全部 502。

**2. bifrost（231，端口 8501）—— 近期崩溃**

bifrost 在今天 15:01 还在正常处理请求（wty 用户登录），但到 15:04 之后日志就断了，现在进程已经不在。231 上目前跑了 7 个 Java 应用（salaxy 2g + atreus 1g + tdjob 512m + tianzuo-api/captain/consumer 各 512m），堆内存合计约 5g，加上 bifrost 原来的 1g，8GB 的服务器内存非常紧张，很可能是被 OOM Killer 杀掉的。

**其他说明：** tianzuo-api、tianzuo-captain、tianzuo-consumer 已经从 71 迁移到 231 运行（端口分别是 8080、8082、8088）。galaxy-guard 的 jar 不在 231 上。

需要我现在帮你把 tiangong-admin 和 bifrost 拉起来吗？bifrost 启动时可以把内存调低一些（比如 -Xms256m -Xmx512m）来缓解 231 的内存压力。

### 🧑 用户 · 2026-04-29T08:04:15.347Z

把这两个服务拉起来

### 🤖 助手 · 2026-04-29T08:04:27.487Z

好，先查一下两个服务的启动方式。

### 🤖 助手 · 2026-04-29T08:07:32.679Z

(agent interrupted)

### 🧑 用户 · 2026-04-29T08:07:32.711Z

帮我启动一下tiangong-admin就行

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

### 🤖 助手 · 2026-04-29T08:07:32.717Z

好的，只启动 tiangong-admin。我先确认一下它之前的启动方式，然后拉起来。

### 🤖 助手 · 2026-04-29T08:09:18.246Z

确认了 tiangong-admin 没在运行（端口 8503 无监听）。参照同机器上 tiangong-api 的启动方式，直接拉起来。

### 🤖 助手 · 2026-04-29T08:11:06.730Z

进程已启动，PID 16737。Java 应用启动需要一些时间，等大约 40 秒后检查端口是否就绪。

### 🤖 助手 · 2026-04-29T08:13:25.077Z

进程在运行中，Spring Boot 正在加载决策组件缓存，还没完成初始化。再等一会儿。

### 🤖 助手 · 2026-04-29T08:15:59.105Z

tiangong-admin 已经成功启动了，端口 8503 正常监听中（PID 16742）。日志显示各项缓存刷新都在正常运行，没有报错。

你现在可以刷新页面试试，大盘的业务资产概览数据应该能正常加载了。另外之前提到 bifrost 也挂了（231 上的认证服务），如果遇到登录问题，随时告诉我帮你拉起来。

### 🧑 用户 · 2026-04-29T08:29:53.486Z

<user-pasted-image file="/Users/td/.qoderwork/workspace/mojqozd0fc1jpaeh/uploads/image_1777451392996_36r0zz4.png" /> 这个galaxy是启动成功了吗？

### 🧑 用户 · 2026-04-29T08:30:03.237Z

<command-message>The "bailian-vision" skill is running</command-message>
<command-name>/bailian-vision</command-name>
<command-args>--mode text --file /Users/td/.qoderwork/workspace/mojqozd0fc1jpaeh/uploads/image_1777451392996_36r0zz4.png --prompt "这是一个Java应用的启动日志截图，请仔细阅读所有日志内容，告诉我：1. 这个应用是否启动成功？2. 最后几行日志显示了什么？3. 有没有ERROR或异常信息？"</command-args>

### 🤖 助手 · 2026-04-29T08:30:45.487Z

从日志来看，这个应用**启动成功了**，所有日志都是 INFO 级别，没有任何 ERROR。关键信息包括 `load tdllog success`、`Load ClientAuthService success`，以及 Nacos 插件加载成功。

最后一行 `Current Spring Boot Application is await...` 是 Dubbo 的 `AwaitingNonWebApplicationListener` 的正常输出，说明 Dubbo 服务已就绪，正在等待接收请求。

不过让我快速确认一下 galaxy-guard 的 HTTP 端口 8511 是否正常监听：

### 🤖 助手 · 2026-04-29T08:32:24.133Z

galaxy-guard 进程确实在运行（PID 15636），但有个问题：**HTTP 端口 8511 没有监听**。

日志里的 `Current Spring Boot Application is await...` 表明它以纯 Dubbo 模式启动了（没有 Web 服务器），所以不会开 HTTP 端口。对比原来部署文档里的配置，启动时需要额外指定两个关键参数：

- `--server.port=8511` — HTTP 端口
- `-Ddubbo.protocol.port=20881` — Dubbo 端口（避免跟 atreus 的 20880 冲突）

目前的启动命令里这两个参数都缺失了。你是用 `server.sh start` 启动的吗？如果需要的话，我可以帮你把当前进程停掉，用正确的参数重新启动。

### 🧑 用户 · 2026-04-29T08:42:51.809Z

galaxy这个应用的输出日志/data01/td/tiance/galaxy-guard/logs/galaxy-guard.outs 怎么没有了？

### 🤖 助手 · 2026-04-29T08:44:33.579Z

从目录内容来看，`logs/` 下没有 `galaxy-guard.outs` 文件。这是因为当前 galaxy-guard 是通过 `server.sh` 启动的，它的标准输出重定向到了不同的位置。让我查一下：

### 🤖 助手 · 2026-04-29T08:46:16.641Z

找到原因了。`nohup.out` 记录了之前的一次启动失败：

> **Cannot allocate memory** — Java 无法分配 131072000 字节（约 125MB），内存不够。

这说明之前用 `nohup` 方式启动 galaxy-guard 时因为 231 服务器内存不足直接 OOM 了，所以 `galaxy-guard.outs` 根本没有生成。之后你用 `server.sh` 启动时，`server.sh` 把标准输出重定向到了 `/tmp/galaxy-guard/deploy.log`，但这个文件也不存在（可能进程启动前堡垒机断连导致 `/tmp` 目录没被创建）。

实际的应用日志写到了 `logs/app.log`，从里面看，galaxy-guard 已经被反复启动了 3 次（15:54、16:17、16:24），每次都停留在 `Current Spring Boot Application is await...`——这说明它以纯 Dubbo 模式启动，没有开启 HTTP 端口 8511。

**核心问题是 231 内存太紧张了**。目前 231 上同时跑了 salaxy（2g）、atreus（1g）、tdjob（512m）加上 tianzuo 系列三个应用，再加 galaxy-guard（1g），8GB 内存基本撑满了。你想怎么处理？我可以帮你把 galaxy-guard 的 JVM 调小一些（比如 `-Xms256m -Xmx512m`）并加上 `--server.port=8511 -Ddubbo.protocol.port=20881` 重新启动试试。

### 🧑 用户 · 2026-04-29T08:47:45.933Z

现在tianzuo的进程应该被杀掉了吧，内存应该大一些了

### 🤖 助手 · 2026-04-29T08:49:30.133Z

对，tianzuo 系列三个进程已经被杀掉了，现在 231 上的情况：

**运行中的 Java 应用：**
- bifrost（2g） — PID 3399，你也重新启动过了
- salaxy（2g） — PID 13850
- tdjob（512m） — PID 18749
- atreus（1g） — PID 26250
- **galaxy-guard（1g）** — PID 23238

**galaxy-guard 这次启动成功了**，端口 8511 已经在正常监听。看起来你自己又重新启动了一次（PID 23238，16:45 启动），这次内存够了所以起来了。

当前剩余可用内存约 1.6GB，刚好够用但不算宽裕。之前 `galaxy-guard.outs` 找不到的问题就是因为 `server.sh` 的输出重定向路径和手动 `nohup` 不同，实际日志在 `logs/app.log` 里。

### 🧑 用户 · 2026-04-29T09:00:03.975Z

可以把tianzuo这几个应用放到别的服务器中吗？这个服务器好像内存不够了，考虑下10.57.83.86
10.57.80.163
10.57.80.161这三台服务器中哪一台合适

### 🤖 助手 · 2026-04-29T09:00:03.980Z

好的，让我同时检查这三台服务器的资源情况。

### 🤖 助手 · 2026-04-29T09:04:33.964Z

三台服务器的情况对比如下：

| 服务器 | 总内存 | 可用内存 | CPU | 当前负载 |
|--------|--------|----------|-----|----------|
| **10.57.83.86** | 8GB | **~5GB** | 2C | ZK + Kafka + Nacos（中间件，较轻） |
| 10.57.80.163 | 8GB | ~3GB | 2C | 6 个 Java 应用（另一套完整环境） |
| 10.57.80.161 | 8GB | ~3.5GB | 2C | 5 个 Java 应用（含 tianzuo 全套） |

**建议选 10.57.83.86**，理由是：

它目前只跑了 ZK、Kafka、Nacos 三个中间件，可用内存约 5GB，足够承载 tianzuo 三个应用（tianzuo-api 512m + tianzuo-captain 512m + tianzuo-consumer 512m，合计约 1.5GB 堆 + 系统开销）。另外两台已经各跑了 5-6 个 Java 应用，再加进去会很紧张。而且 86 上已经有 JDK 1.8 环境，不需要额外安装。

需要我把 tianzuo 三个应用部署到 83.86 上吗？大致流程是：从 231 把应用包和配置传过去，调整 Nacos 地址指向 71，然后启动并更新 231 上 Nginx 的 upstream 指向新 IP。

### 🧑 用户 · 2026-04-29T09:05:26.652Z

帮我部署一下

### 🤖 助手 · 2026-04-29T09:06:11.715Z

先看看 231 上 tianzuo 的目录结构和当前 Nginx 配置。

### 🤖 助手 · 2026-04-29T09:08:09.921Z

好的，目录和 Nginx 配置都清楚了。现在开始部署。先在 231 上打包三个 tianzuo 应用（排除日志），然后通过 HTTP 传到 86。

### 🤖 助手 · 2026-04-29T09:11:36.175Z

打包完成（662MB）。现在在 231 上启动临时 HTTP 服务，然后从 86 下载。

### 🤖 助手 · 2026-04-29T09:12:46.252Z

HTTP 服务已启动。现在到 86 上下载并解压。

### 🤖 助手 · 2026-04-29T09:17:40.610Z

输出被截断了，让我确认一下文件是否到位。

### 🤖 助手 · 2026-04-29T09:19:08.134Z

文件下载为空（0 字节），HTTP 服务可能没存活过堡垒机断连。换个方式，用 scp 直接在服务器之间传输。

### 🤖 助手 · 2026-04-29T09:20:28.298Z

HTTP 服务随堡垒机断连一起死了。用 `setsid` 方式让它脱离终端。

### 🤖 助手 · 2026-04-29T09:25:09.656Z

python3 不在 231 的 PATH 里。让我检查下有哪些工具可以用来传文件。

### 🤖 助手 · 2026-04-29T09:26:39.677Z

有 python2 和 ncat。用 python2 起 HTTP 服务。

### 🤖 助手 · 2026-04-29T09:27:47.668Z

HTTP 服务这次起来了（HTTP 200 OK）。现在从 86 下载。

### 🤖 助手 · 2026-04-29T09:32:50.312Z

下载成功（662MB，1.8 秒）。现在解压并检查配置，然后启动三个应用。

### 🤖 助手 · 2026-04-29T09:34:58.592Z

配置没问题，Nacos 地址都指向 10.57.83.71:8848。现在创建日志目录并启动三个应用。

### 🤖 助手 · 2026-04-29T09:37:41.397Z

tianzuo-captain 启动失败了（logs 目录路径问题）。tianzuo-api 和 tianzuo-consumer 已经启动了。让我修复 captain。

### 🤖 助手 · 2026-04-29T09:38:55.280Z

三个进程都启动了。等 60 秒让它们完成初始化，然后检查端口。同时先去更新 Nginx。

### 🤖 助手 · 2026-04-29T09:40:37.169Z

配置清楚了。需要修改两个 upstream：`tianzuoApi` 和 `tianzuoCaptainApi` 从 `127.0.0.1` 改到 `10.57.83.86`。先等应用启动，然后更新 Nginx。

### 🤖 助手 · 2026-04-29T09:43:24.550Z

三个应用全部启动成功，端口都在监听：

- tianzuo-api → 8080
- tianzuo-captain → 8082
- tianzuo-consumer → 8088

现在更新 231 上的 Nginx upstream 指向 86。

### 🤖 助手 · 2026-04-29T09:45:32.336Z

继续更新 231 上的 Nginx upstream 配置，将 tianzuoApi 和 tianzuoCaptainApi 指向新的 86 服务器。

### 🤖 助手 · 2026-04-29T09:45:54.167Z

先用 sed 修改 Nginx 配置中的两个 upstream，然后验证修改结果。

### 🤖 助手 · 2026-04-29T09:47:38.177Z

tdops 用户没有直接写 /etc/nginx/ 的权限，需要用 sudo。

### 🤖 助手 · 2026-04-29T09:49:15.370Z

Nginx 配置已修改成功，两个 upstream 都已指向 `10.57.83.86`。现在 reload Nginx 使配置生效。

### 🤖 助手 · 2026-04-29T09:50:52.127Z

Nginx 配置测试通过并已成功 reload。现在验证一下 86 上的三个 tianzuo 服务是否仍正常运行。

### 🤖 助手 · 2026-04-29T09:52:35.533Z

86 上三个 tianzuo 应用运行正常，端口 8080/8082/8088 全部在监听。再快速验证下通过 231 Nginx 代理能否正确转发到 86。

### 🤖 助手 · 2026-04-29T09:54:06.931Z

HTTP 404 说明 Nginx 已经成功转发请求到 86 上的 tianzuo 服务了（如果后端不可达会返回 502/503，而 404 是后端应用正常响应，只是根路径没有对应 handler）。代理链路通畅。

再确认一下 231 的内存情况——迁走 tianzuo 后应该释放了不少。

### 🤖 助手 · 2026-04-29T09:55:55.824Z

全部完成了。总结一下这次 tianzuo 迁移的结果：

**Nginx upstream 已更新并 reload 成功**，两个 upstream 的改动：
- `tianzuoApi` → `10.57.83.86:8080`（原 127.0.0.1:8080）
- `tianzuoCaptainApi` → `10.57.83.86:8082`（原 127.0.0.1:8082）

**86 服务器**上 tianzuo-api（8080）、tianzuo-captain（8082）、tianzuo-consumer（8088）三个端口全部正常监听，通过 231 Nginx 代理请求能成功转发到 86（HTTP 404 说明后端正常响应）。

**231 服务器**目前只剩 bifrost、salaxy、galaxy-guard、atreus、tdjob 五个 Java 进程，tianzuo 的三个进程已经不在了。不过 231 的可用内存还是偏紧（available 约 1.5GB），如果后续还有 OOM 的风险，可以考虑把 231 上旧的 tianzuo 目录清理掉释放磁盘空间。

### 🧑 用户 · 2026-04-29T10:00:23.884Z

<user-pasted-image file="/Users/td/.qoderwork/workspace/mojqozd0fc1jpaeh/uploads/image_1777456822818_zceo6ur.png" /> 但是现在tianzuo的菜单第一次刷新进入的时候还是报错，后面再点进去就正常了，排查一下这个问题

### 🤖 助手 · 2026-04-29T10:00:23.894Z

先用百炼分析一下截图中的具体 URL 和错误信息。

### 🤖 助手 · 2026-04-29T10:00:48.649Z

看到了，URL 是 `10.57.80.231/params/exception/404`，第一次进入 tianzuo 菜单报 404，后面再点就正常。这很可能是服务首次调用时的连接超时或 Dubbo 服务注册延迟导致的。我来排查一下。

### 🤖 助手 · 2026-04-29T10:02:55.766Z

日志文件只有 outs，让我看看 outs 和 Nginx error log。

### 🤖 助手 · 2026-04-29T10:04:33.439Z

tianzuo-api 没有明显报错。让我看看 Nginx 的 error log 和 access log，找找首次请求具体是哪个接口返回了错误。

### 🤖 助手 · 2026-04-29T10:06:18.681Z

错误日志显示的都是更新前的旧错误。让我看看完整的 Nginx 配置，特别是查找 `/params/` 路径对应的 upstream——这个可能也需要更新。

### 🤖 助手 · 2026-04-29T10:08:13.705Z

让我看看最近的 Nginx access log，找出首次访问 tianzuo 菜单时具体哪个请求失败了。

### 🤖 助手 · 2026-04-29T10:15:53.800Z

Nginx error log 在 reload 之后（17:49）没有新的错误，说明 Nginx 到 86 的代理是正常的。问题可能出在 Nacos 服务注册或 Dubbo 连接上。让我检查一下 Nacos 中 tianzuo 服务的注册情况。

### 🤖 助手 · 2026-04-29T10:17:54.769Z

找到关键线索了 — tianzuo-api 的 Nacos 注册为空（hosts: []）。让我进一步检查所有 tianzuo 相关服务的注册状态。

### 🤖 助手 · 2026-04-29T10:19:53.276Z

`tiance` 命名空间里没有服务。让我查查 Nacos 里实际使用的命名空间。

### 🤖 助手 · 2026-04-29T10:21:31.582Z

Nacos 中有 198 个 Dubbo 服务注册，包括 tianzuo 相关的服务。让我检查一下 tianzuo-captain 的 Dubbo 注册实例 IP 是否已经更新到 86。

### 🤖 助手 · 2026-04-29T10:23:22.147Z

Dubbo 注册正常，IP 已经是 86。让我检查 tianzuo-admin（232:8081）的状态，因为前端"参数管理"菜单可能调用的是 tianzuoAdminApi。

### 🤖 助手 · 2026-04-29T10:25:13.653Z

让我仔细看看 Nginx 中前端路由和 `try_files` 的配置，以及 `/params/` 路径的处理。

### 🤖 助手 · 2026-04-29T10:27:17.119Z

看到了，`/params/` 路径由 catch-all 的 `location ~ ^/ {try_files $uri /lightbox-resource/index.html;}` 处理，属于 lightbox (tiangong) 前端。前端 SPA 加载了但是内部路由导向了 404 页面，说明是前端调 API 时收到了错误。

让我直接模拟前端首次访问 tianzuoAdminApi 的场景，看看是否有延迟或错误。

### 🤖 助手 · 2026-04-29T10:29:33.626Z

后端响应速度正常。这个问题可能是前端层面的。让我直接用浏览器自动化来复现这个问题，抓取第一次访问时的具体网络请求错误。

### 🤖 助手 · 2026-04-29T10:34:47.805Z

发现 tiangong-admin 有 `DataSourceClosedException` 错误。让我检查 tiangong-admin 当前状态——它可能又崩了。

### 🤖 助手 · 2026-04-29T10:36:48.666Z

tiangong-admin 正在重启中（18:33 启动，端口 8503 还没起来）。它刚被人用 `server_debug.sh restart` 重启了。让我等它启动完成，然后再排查 tianzuo 菜单的首次 404 问题。

### 🤖 助手 · 2026-04-29T10:38:55.624Z

tiangong-admin 已重启完毕，端口 8503/8504/8081 都在监听。现在让我深入排查 tianzuo-admin 的日志，看看它调用 tianzuo-api（86）时是否有 Dubbo 连接超时。

### 🤖 助手 · 2026-04-29T10:40:56.520Z

找到重要线索了！tianzuo-admin 有 `NoClassDefFoundError: org/elasticsearch/client/Request` 错误。让我验证一下——这很可能就是首次 404 的根因。

### 🤖 助手 · 2026-04-29T10:42:49.775Z

健康检查确实返回了错误（`"success":false,"code":2`）。这个 ES 类缺失导致了 actuator health 报错。让我检查一下前端首次进入 tianzuo 菜单时实际调用了哪些接口，看看是否跟这个 ES 错误有关联。

### 🤖 助手 · 2026-04-29T10:46:19.052Z

这个 ES 错误只影响 actuator health 端点。让我测试一下 tianzuo-admin 的实际业务接口是否正常，并看看前端首次进入时到底请求了哪个接口。

### 🤖 助手 · 2026-04-29T10:48:20.332Z

让我检查一下 231 上前端静态文件中是否有 tianzuo 相关的 JS 模块文件缺失。

### 🤖 助手 · 2026-04-29T10:53:33.503Z

找到关键线索了！`appConfig.js` 中 **`params` 映射到 `captain-resource`**。lightbox 前端在进入 `/params/` 路由时会尝试加载 `/captain-resource/v3/index.html`。让我检查这个文件是否存在！

### 🤖 助手 · 2026-04-29T10:55:22.336Z

`captain-resource` 文件存在。问题不在静态文件缺失。让我看看 captain-resource 的前端配置和它加载时的 API 调用。

### 🤖 助手 · 2026-04-29T11:01:39.240Z

排查完成，以下是分析结论。

这个"第一次刷新进入 404，再点就正常"的问题**不是本次 tianzuo 迁移导致的**，而是天策前端微前端架构本身的一个竞态条件问题。

具体根因在于：lightbox 主应用的 `appConfig.js` 中 **`params` 模块映射到 `captain-resource` 子应用**。当用户刷新页面后首次点进 tianzuo 菜单时，流程是这样的：

1. 浏览器刷新 → lightbox 主 SPA 加载并初始化（获取 token、菜单等）
2. 用户点击 tianzuo 菜单（`/params/...` 路由）
3. lightbox 动态加载 `captain-resource/v3/index.html` 子应用
4. captain-resource 的 `index.html` 中有 sessionStorage 同步机制——它检查 `if (!sessionStorage.length)` 发现为空后，通过 `localStorage` 事件向其他标签页请求 token
5. 但这个 token 同步是**异步**的，子应用的 JS 代码（`app.edfaf519.js`）已经开始执行 API 调用了，此时 token 还没拿到
6. API 调用因缺少认证 token 而返回错误 → 前端路由跳转到 `/params/exception/404`

第二次点击时，sessionStorage 已通过上一次的异步同步拿到了 token，所以就正常了。

另外 tianzuo-admin（232:8081）有一个 `NoClassDefFoundError: org/elasticsearch/client/Request` 的问题，影响了 actuator health 端点，但不影响正常业务接口。

**临时规避方案**：刷新页面后稍等 2-3 秒再点 tianzuo 菜单，让 lightbox 主应用完成初始化和 token 同步后再进入。这个问题需要前端团队从代码层面修复（在子应用加载前确保 token 已同步到 sessionStorage，或改用 cookie 传递认证信息）。
