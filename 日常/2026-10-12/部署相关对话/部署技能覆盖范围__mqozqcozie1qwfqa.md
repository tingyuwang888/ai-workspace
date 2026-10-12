# 部署技能覆盖范围

- Chat ID: `mqozqcozie1qwfqa`
- 分类：部署技能维护
- 起始日期：2026-06-22
- 会话文件数：1

---


## 会话 1/1 · `dc7163e5`

### 🧑 用户 · 2026-06-22T09:05:58.921Z

<system-reminder>
User environment — Timezone: Asia/Shanghai (UTC+08:00). Locale: en-US. OS: darwin.
Note: If you need the current date or time, run `date` via Bash to get a fresh, accurate value. Do not assume a fixed time.

You are operating in awareness mode. The following files define your persona,
operating manual, and memory. Follow them as authoritative guidelines.

Contents of /Users/td/.qoderwork/awareness/main/AGENTS.md (operating manual)

# AGENTS.md - 工作手册

<!-- 工作手册：沉淀稳定的项目约定、编码标准、架构规则和工作流偏好，不放临时事实，可随时更新。 -->

IMPORTANT: You are operating in awareness mode. The files above are ALWAYS
relevant to your work. Follow them as authoritative guidelines.
══════════════════════════════════════════════
MEMORY (your personal notes) [28% — 2,964/10,240 bytes]
Managed exclusively by the `memory` tool (target="memory"). Do NOT use Edit/Write/create_file on any MEMORY.md or USER.md file, anywhere — those edits will not be persisted to the real memory store and will create stray files in your workspace.
══════════════════════════════════════════════
mock_server_py2.py可在Python3中import，需先sys.modules['BaseHTTPServer']=types.ModuleType包装。核心变量：RULE_CODE_MAP(规则→KYC+endpoints)、_v21_KYC_MAP(kyc类型→函数)。部署目标10.57.80.163:8899，通过JumpServer上传。
§
保后检查贷前主策略测试报告约定：251用例/3sheet，表头蓝底(4472C4)白字，仅测试状态列保留颜色(通过绿/未通过红/异常黄)，Col14用UUID不用token，测试步骤追加【关键入参】和【数据源返回】
§
Mock数据设计应优先选择贴近真实业务的方案（如笔数>=5比单笔>=1000万更合理），用户会纠正不符合业务直觉的选择。边界测试时，不同场景（如TC_206-209的"5笔小额"vs"1笔大额"等OR分支）须分配独立searchKey并在mock中做路由区分，避免同key返回相同数据导致无法区分分支。
§
天策887裁判文书ETL输出key(如ent3mselfprosecutioncountqcc)需通过数据源出参配置映射到系统字段(C_N_开头)，规则条件引用系统字段。规则不触发时排查链路：ETL输出key→出参配置映射→系统字段→规则入参表达式。
§
887 mock自诉原告规则(ELLP06/ELDP06/ELNP06/ARGS02/ARGP06)配置要点：1) RULE_CODE_MAP须映射到_v21_yellow_887_plaintiff(原告,IsProsecutor=1)，避免误用_v22i_yellow_887(被告,IsProsecutor=0)；2) searchKey必须等于引擎传入的C_S_QCCSEARCHKEY，ETL才会按PartyList[].RoleType含"原"且Name==searchKey匹配原告记录。排查rule不触发时先grep mock日志确认items数、IsProsecutor值及searchKey匹配情况。
§
天策策略测试不应仅依赖getHitRuleList API（可能返回0条即使规则已触发）。正确排查路径：1) 用create API的token调用nodeType=8获取子策略tokenId和finalDecision；2) 再用子策略tokenId调用nodeType=1查看规则集入参(inputFieldList)、出参(resFieldList)和命中规则(hitRuleList)。真实命中应结合平台UI入参详情中的系统字段值或整体决策结果判断。
§
保后检查自诉原告规则预期命中结果以V27 Excel"规则"sheet的"命中结果"列为准：ELLS06/ELDS06/ELLP06/ELDP06/ARGS02/ARGP06=中风险预警，ELNS06/ELNP06(非融类)=低风险预警，无高风险预警。测试用例expected必须与平台真实配置一致。
§
三峡项目Nginx(10.57.80.231)的tiangongAdminApi upstream曾被人误改为127.0.0.1:8503导致前端页面无法加载。正确配置应为10.57.80.161:8503(主)+10.57.80.232:8503(备)。排查前端无请求问题时优先检查此upstream配置。
§
天策mock边界测试局限：平台发给887数据源的searchKey不由S_S_UNIFSOCLCRCOD/S_S_BIZID控制，而是平台自有逻辑(如SAFE_TC_NNN格式)。BOUNDARY_* searchKey写在测试用例params中无法到达mock。TC_206能命中是因为直接预设了C_N_ENT3MSELFPROSECUTIONCOUNTQCC=5绕过了数据源调用。要真正测OR条件分支需搞清楚数据源searchKey入参映射配置。

Available MCP servers:
- builtin_browser: Browser automation via Chrome Extension V2

Use qw_mcp_list to see all tools, qw_mcp_get to get tool schema (ALWAYS call this before qw_mcp_call to get correct arguments), qw_mcp_call to execute.

Available tools:
mcp__builtin_browser__computer, mcp__builtin_browser__read_page, mcp__builtin_browser__find, mcp__builtin_browser__form_input, mcp__builtin_browser__navigate, mcp__builtin_browser__javascript_tool, mcp__builtin_browser__get_page_text, mcp__builtin_browser__file_upload, mcp__builtin_browser__resize_window, mcp__builtin_browser__read_console_messages, mcp__builtin_browser__read_network_requests, mcp__builtin_browser__tabs_context, mcp__builtin_browser__tabs_create, mcp__builtin_browser__tabs_context_mcp, mcp__builtin_browser__tabs_create_mcp, mcp__builtin_browser__tabs_close_mcp
</system-reminder>
部署skill目前覆盖的应用和中间件有哪些

### 🤖 助手 · 2026-06-22T09:06:21.409Z

从 skill 列表来看，部署相关 skill 覆盖的应用和中间件大致如下：

**中间件层：**

JDK、MySQL、Nacos、ZooKeeper、Kafka、Elasticsearch、Cassandra、ApexDB、Nginx、tdjob（定时任务调度）、TD-Scheduler、Seatunnel，以及大数据组件（通过 ark-deploy）Hadoop2/Hadoop3、Ambari、HDFS、YARN、HBase、Hive。

**应用层：**

核心应用包括 bifrost、salaxy、tiangong、kratos-consumer；交易账户类有 spartan、spartan-account；场景应用有 atreus（信贷）和 galaxy-guard（贷中）；布局管理类有 tianzuo-admin、tianzuo-api、tianzuo-c；模型管理类有 holmes-web、holmes-python；此外还有 tdjob 定时任务服务。Python 服务也在覆盖范围内。

**前端资源：**

通过 tiance-nginx-frontend 覆盖前端静态资源部署和 Nginx 反向代理配置，包括 creditApi、galaxyApi、rosterApi 等场景路由。

**数据库初始化：**

tiance-sql-init 覆盖 i18n、common、bifrost、aflow、roster、salaxy、tiangong、holmes、tianzuo、spartan、tdscheduler、atreus、galaxy-guard 等模块的建库建表和初始化脚本。

**部署方式支持：**

覆盖了直接 SSH 部署（hera-deploy）、通过 JumpServer 堡垒机部署（jumpserver 系列）、K8s 容器化 + 虚拟机混合部署（k8s-tiance-deploy）、离线部署（td-kb-offline-deploy），以及 CI/CD 流水线构建部署（bkci-cicd-deploy、cicd-quick-deploy）。还有三峡项目的定制化部署（sanxia-tiance-deploy）。

整体来看，部署 skill 主要围绕天策（Tiance）决策中台的完整技术栈构建，从底层中间件到上层应用、前端资源、数据库初始化、冒烟测试形成了比较完整的链路。

### 🧑 用户 · 2026-06-22T09:09:30.936Z

给我生成一个列表

### 🤖 助手 · 2026-06-22T09:13:30.990Z

文档已生成，包含 6 个章节：中间件（18 个组件）、应用服务（14 个应用，6 个模块）、前端资源与路由（5 项）、数据库初始化（13 个模块）、部署方式总览（14 个 Skill）和统计概览。每个条目都标注了功能说明和关联的 Skill 名称。

[查看文档](file:///Users/td/.qoderwork/workspace/mqozqcozie1qwfqa/outputs/%E9%83%A8%E7%BD%B2Skill%E8%A6%86%E7%9B%96%E6%B8%85%E5%8D%95.docx)

### 🧑 用户 · 2026-06-22T09:19:56.890Z

<system-reminder>
Note: /Users/td/.qoderwork/awareness/main/MEMORY.md was modified. Entry-level diff: 1 added, 0 removed.

[ADDED] (1)
+ Node.js 找不到全局 npm 包（如 docx），需在 workspace 目录 `npm install docx` 本地安装，全局路径 ~/.npm-global/lib/node_modules 不在默认搜索路径中。

These are the exact strings the `memory` tool persists (target="memory").
Use the `memory` tool to inspect or modify entries; do NOT edit USER.md / MEMORY.md directly.
</system-reminder>
tianzuo-c是什么？

### 🤖 助手 · 2026-06-22T09:22:46.905Z

根据部署 Skill 中的详细信息，**"tianzuo-c" 并不是一个真实的服务名称**。在之前的文档中我引用了 tiance-app-deploy skill 描述里的缩写，这不够准确。

实际上，天座（tianzuo）在新版本中拆分为四个微服务：

- **tianzuo-admin**（天作管理端，端口 8512）— 管理后台，负责布局配置、数据源导入导出
- **tianzuo-api**（天作 API，端口 8515/8514）— 运行时 API 服务层，处理决策引擎的三方数据查询请求
- **tianzuo-captain**（天作队长，端口 8513/8088）— 调度/分发器，协调三方数据调用
- **tianzuo-consumer**（天作消费者，端口 8514）— 异步消息消费者，标记为可选，内存紧张时可不部署

skill 描述中写的 "tianzuo-c" 大概率是 **tianzuo-captain** 或 **tianzuo-consumer** 的缩写。旧版本只有一个单体 tianzuo-server（端口 8512），后来才拆分成了这四个服务。

需要我把文档里的这条更新一下吗？
