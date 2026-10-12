# cicd流水线部署都需要什么材料

- Chat ID: `mogiz21kvipvv4vv`
- 分类：CICD
- 起始日期：2026-04-27
- 会话文件数：1

---


## 会话 1/1 · `c7fb39f8`

### 🧑 用户 · 2026-04-27T01:35:16.360Z

cicd流水线部署都需要什么材料？

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

### 🤖 助手 · 2026-04-27T01:35:16.370Z

让我先查阅CICD部署相关的技能文档，获取准确的材料清单。

### 🧑 用户 · 2026-04-27T01:35:26.071Z

<command-message>The "cicd-quick-deploy" skill is running</command-message>
<command-name>/cicd-quick-deploy</command-name>

### 🤖 助手 · 2026-04-27T01:35:26.076Z

根据同盾CI/CD平台（dragon.tongdun.cn）的部署流程，进行CICD流水线部署前需要准备以下材料：

**基本信息（必需）：**

1. **应用名称** — 在"我的应用"中的应用名，例如 bifrost、salaxy、tiangong-admin 等
2. **基于哪个 tag** — 用于创建版本的 tag 分支，例如 `release.v2.8.0.20260108`
3. **项目名缩写** — 用于拼接分支名，比如梅州客商缩写为 `mzks`
4. **产品CICD页面链接** — 产品版本页面的 URL，需要有管理员权限，例如 `https://dragon.tongdun.cn/#/Enterprise/NewProductOverview/Version/xxx`

**配置相关（二选一）：**

- **选择一：上传配置文件** — 直接提供应用的 bootstrap.properties 配置文件
- **选择二：从 tiance-2505-test 复制（推荐）** — 这种方式还需要额外提供：
  - **Nacos 地址**，例如 `10.57.80.76:8848`
  - **Nacos Group**，例如 `tiance2505_test`

准备好这些材料后，平台会按照"创建应用版本 → 创建 ConfigMap → 添加到产品CICD → 绑定文件挂载 → 检查打包 → 部署 → 验证"的顺序完成整个流程。如果你准备好了这些信息，我可以直接帮你在 dragon 平台上执行部署操作。

### 🧑 用户 · 2026-04-27T01:36:33.818Z

这个是从技能中得出来的吗？

### 🤖 助手 · 2026-04-27T01:36:33.823Z

是的，这些信息来自我内置的「cicd-quick-deploy」技能文档。这个技能是专门针对同盾CI/CD平台（dragon.tongdun.cn）的开发环境部署流程编写的，里面详细记录了从版本创建到部署验证的完整步骤和所需材料。

如果你实际的部署场景和这个技能描述的流程有差异，或者你用的是其他CI/CD平台，欢迎告诉我，我可以根据你的实际情况来调整。

### 🧑 用户 · 2026-04-27T01:37:07.083Z

我用的蓝鲸云cicd平台，这是在客户环境部署的

### 🤖 助手 · 2026-04-27T01:37:07.090Z

了解，蓝鲸云CICD平台的部署流程和同盾内部的 dragon 平台不一样。我看到有一个针对 K8s + 蓝鲸云的部署技能，让我查一下里面关于蓝鲸云CICD的具体材料要求。

### 🧑 用户 · 2026-04-27T01:37:13.856Z

<command-message>The "k8s-tiance-deploy" skill is running</command-message>
<command-name>/k8s-tiance-deploy</command-name>

### 🤖 助手 · 2026-04-27T01:37:13.864Z

这个确实和之前说的 dragon 平台完全不同。根据「k8s-tiance-deploy」技能，在客户环境使用蓝鲸云CICD平台部署天策，需要准备的材料分为以下几大类：

**一、网络接入信息**

根据客户环境不同，通常需要 VPN 连接信息（类型、地址、账号密码）以及堡垒机地址和登录凭据。有些客户环境可以直连 SSH，具体看现场情况。

**二、基础设施信息**

这部分是核心材料，包括：K8s 集群信息（主节点IP、Dashboard地址、kubeconfig或token）、Harbor 镜像仓库信息（地址、域名、账号密码）、蓝鲸云CICD平台的地址和账号密码、中间件虚拟机服务器信息（IP、用户名、密码）、以及数据库信息（类型如TDSql/MySQL、地址、端口、账号密码）。

**三、交付物**

hera 交付物的本地路径（包含中间件包、应用包、前端静态资源、配置文件等）、Docker 镜像的来源方式（交付物中的tar包、从内部仓库拉取、或通过CICD构建）、以及 ApexDB 的 product-key。

**四、部署范围确认**

需要明确哪些 VM 中间件要装（ZooKeeper、Kafka、ES、ApexDB、Nacos 等）、哪些应用走 K8s 容器化部署（bifrost、salaxy、tiangong 等）、哪些应用在虚拟机上部署（如 holmes 企业版）、以及前端资源是走 K8s Nginx Pod 还是虚拟机 Nginx。

如果你现在手上有这些信息，我可以直接帮你开始部署流程。或者你也可以告诉我目前已经有哪些、还缺哪些，我帮你梳理一下待办清单。

### 🧑 用户 · 2026-04-27T01:37:57.830Z

具体部署流程是什么？

### 🤖 助手 · 2026-04-27T01:37:57.836Z

根据技能文档，K8s + 虚拟机混合模式下的完整部署流程按以下顺序执行：

**1. 网络接入**
连接客户VPN，登录堡垒机，验证到K8s集群和虚拟机服务器的网络连通性。

**2. 系统初始化（VM服务器）**
在虚拟机上创建基础目录、做系统优化、安装JDK等基础环境。

**3. 上传交付物**
中间件安装包上传到虚拟机，Docker镜像tar包加载到Harbor镜像仓库（docker load → docker tag → docker push）。如果Harbor使用自签证书，还需要配置Docker的insecure-registries信任。

**4. VM中间件部署**
在虚拟机上按顺序安装：ZooKeeper → Kafka → ES → ApexDB → Nacos，以及按需安装 td-scheduler、seatunnel、td-job、dubbo-admin。

**5. 数据库初始化**
执行SQL建库建表脚本（适配TDSql或MySQL）、ApexDB的lua初始化、ES索引创建。

**6. Nacos配置导入**
通过SSH隧道或浏览器访问Nacos控制台，导入配置zip包。

**7. K8s应用部署**
这是核心步骤，有两种方式可选：一是通过蓝鲸云CICD平台的流水线部署，二是手动生成Deployment/Service YAML后用kubectl apply直接部署。应用部署顺序为：bifrost → salaxy → tiangong-admin → tiangong-api → kratos-consumer，再按需部署atreus、galaxy-guard、tianzuo系列等。

**8. VM应用部署**
在虚拟机上部署holmes企业版等不适合容器化的应用。

**9. 前端资源部署**
根据之前确认的方式，走K8s Nginx Pod或虚拟机Nginx托管前端静态资源。

**10. Nginx配置**
配置反向代理规则，将各应用服务端口统一通过Nginx对外暴露。

**11. 系统初始化**
通过浏览器访问系统登录页（默认账号 `admin` / `Td@123456`），导入license、配置权限、初始化基础数据。

**12. 数据完整性检查**
检查重复记录、SystemVariableConfig配置、主维度数据等，确保系统功能正常可用。

整个流程从网络接入到最终验证，如果材料齐全、中间件和应用数量适中，一般需要一到两天时间。你现在处于哪个阶段，或者打算从头开始？我可以一步步带你做。

### 🧑 用户 · 2026-04-27T01:39:02.351Z

这个技能是本地的还是skill-sync从远程仓库拉的啊？

### 🤖 助手 · 2026-04-27T01:39:02.357Z

让我帮你看一下这个技能的存放位置和来源。

### 🤖 助手 · 2026-04-27T01:39:19.863Z

`k8s-tiance-deploy` 这个技能是**本地的**，直接以普通目录的形式存放在 `/Users/td/.qoderwork/skills/k8s-tiance-deploy/` 下，不是符号链接。

相比之下，从远程仓库通过 skill-sync 拉取的技能会以**符号链接**的形式指向 `/Users/td/.qoderwork/skills-repo/` 目录，比如：

- `cicd-quick-deploy` → 指向 `skills-repo/packages/cicd-quick-deploy/...`
- `deploy-plan` → 指向 `skills-repo/packages/deploy-plan/...`
- `code-analysis` → 指向 `skills-repo/packages/vulnerability-remediation/...`

所以之前回答你的两个技能来源不同：`cicd-quick-deploy` 是 skill-sync 从远程仓库同步的（当前版本 1.0.11），而 `k8s-tiance-deploy` 是本地手动创建或复制过来的，最后修改时间是 4月16日。

### 🧑 用户 · 2026-04-27T01:44:02.669Z

cicd-quick-deploy这个部署skill是谁创建的？

### 🤖 助手 · 2026-04-27T01:44:02.675Z

让我去远程仓库的 git 历史里查一下。

### 🤖 助手 · 2026-04-27T01:44:11.891Z

这个技能最早是由 **youxian.wu**（吴优先，youxian.wu@tongdun.net）在 4月9日创建的（`feat: 新增 cicd-quick-deploy skill v1.0.0`），之后**王恩浩**（enhao.wang@tongdun.net）在同一天补充了 SKILL.md 文件，youxian.wu 在第二天又做了一次修复补充。
