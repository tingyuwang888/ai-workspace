## 天策 MCP 平台能力需求规格说明书

| 项目 | 内容 |
|------|------|
| 版本 | v1.0 |
| 日期 | 2026-07-21 |
| 状态 | 草案 |

---

### 1 概述

#### 1.1 背景与目标

天策（Tiance）决策中台当前的外部交互能力分散在多个 AI Skill 中，通过浏览器自动化、手动 Cookie 注入、本地 JSON 文件缓存等方式与平台 API 通信。这种方式存在接口不稳定、鉴权脆弱、元数据版本不可控、操作不可审计等问题。

本需求定义 Tiance MCP（Model Context Protocol）层应具备的平台能力，将接口发现、身份处理、元数据查询、配置校验、组件操作和策略测试等能力下沉为稳定、结构化、可审计的平台服务。

#### 1.2 设计原则

MCP 层应遵循以下设计原则：

（1）MCP 不是 HTTP API 转发器。SHALL 返回领域化结果，使调用方无需理解底层接口细节。

（2）默认只读。所有写操作 SHALL 经过显式的计划-审批-执行流程。

（3）会话隔离。MCP 会话 SHALL 与浏览器会话完全分离，不共用 Token 或 Cookie。

（4）结构化返回。所有响应 SHALL 为确定性结构，避免让调用方解析自然语言。

（5）完整审计。每次调用 SHALL 记录完整的操作上下文，但不记录敏感信息。

#### 1.3 适用范围

本需求覆盖以下四类能力域：

| 能力域 | 说明 |
|--------|------|
| 元数据与配置 | 实体搜索、解析、Schema 获取、配置校验、引用解析 |
| 组件生命周期 | 组件的查询、导入、更新、发布、上线、下线、删除 |
| 策略测试 | 策略测试的提交、执行、结果获取、批量测试、诊断 |
| 安全与治理 | 身份认证、权限控制、变更审批、幂等、审计 |

基础设施部署（服务器 SSH 操作、Nginx 配置、数据库初始化）不在本需求范围内。

---

### 2 身份与权限（AUTH）

#### AUTH-001 OAuth 2.1 认证

MCP HTTP 层 SHALL 使用 OAuth 2.1/OIDC Bearer Token 进行身份认证。

不接受 Cookie、CSRF Token 或浏览器会话凭证作为 MCP 层的认证方式。

#### AUTH-002 统一身份上下文

MCP SHALL 将外部身份映射为统一的 ActorContext，至少包含以下属性：

| 属性 | 说明 | 必选 |
|------|------|------|
| userId | 用户唯一标识 | 是 |
| orgCode | 所属机构编码 | 是 |
| appCode | 所属应用编码 | 是 |
| environment | 环境标识（test/prod） | 是 |
| roles | 角色列表 | 是 |
| sessionId | 会话标识 | 是 |
| permissionVersion | 权限版本号 | 是 |

bifrost SHALL 继续作为用户、机构、角色和权限的权威来源。

#### AUTH-003 工具级权限声明

每个 MCP Tool SHALL 声明所需的 capability，并在执行前进行权限校验。

capability 至少包括：

| capability | 说明 |
|------------|------|
| tiance.metadata.read | 读取元数据 |
| tiance.component.import | 导入组件 |
| tiance.component.publish | 发布组件 |
| tiance.component.invoke | 调用组件 |
| tiance.policy.test | 提交策略测试 |
| tiance.policy.test.read | 读取测试结果 |

#### AUTH-004 身份上下文约束

Tool 参数 SHALL NOT 覆盖 ActorContext 中的机构、应用和环境范围。

身份上下文缺失时 SHALL 拒绝请求，不得回退为系统账号。

不得在 Tool 返回值、日志或错误信息中暴露 Token、密码、Cookie 或 CSRF Token。

#### AUTH-005 会话隔离

MCP 会话 SHALL 与浏览器会话完全分离，不共用 tokenMD5，避免互相踢出登录状态。

---

### 3 元数据能力（META）

#### META-001 实体搜索

MCP SHALL 提供统一的实体搜索能力，支持按类型、名称、编码、标签等条件搜索以下实体：

字段（field）、函数（function）、规则（rule）、规则集（ruleset）、数据源（datasource）、指标（metric）、服务参数（service_param）、名单（roster）、模板（template）、策略（policy）、决策工具（decision_tool）、预警信号（alarm_signal）、外数指标（captain_index）。

搜索 SHALL 支持分页、过滤和批量查询。

**建议工具：** `tiance.search_entities`

#### META-002 实体解析

MCP SHALL 根据名称、别名或编码将输入解析为唯一实体。

当解析结果不唯一时，SHALL 返回 AMBIGUOUS_REFERENCE 错误码和候选项列表。

当无匹配结果时，SHALL 返回 NOT_FOUND 错误码和建议搜索词。

当权限不足时，SHALL 返回 PERMISSION_DENIED 错误码。

**建议工具：** `tiance.resolve_entities`

#### META-003 实体详情

MCP SHALL 返回实体的完整详情和稳定 ID，包括所有属性、配置和元信息。

**建议工具：** `tiance.get_entity`

#### META-004 Schema 获取

MCP SHALL 提供实体 Schema 查询能力，返回字段约束、枚举值、默认值、数据类型和校验规则。

**建议工具：** `tiance.get_schema`

#### META-005 依赖关系

MCP SHALL 提供组件之间的依赖关系和引用关系查询，包括：

- 策略引用了哪些规则集、函数、子策略。
- 规则集引用了哪些规则、字段、指标。
- 数据源被哪些 ETL 和接口服务引用。
- 当前机构、应用、环境下的可见范围。

**建议工具：** `tiance.get_dependencies`

#### META-006 元数据快照

MCP SHALL 支持导出可复现的元数据快照，包含采集时间、版本号和数据摘要，确保下游工具可基于同一快照进行一致性操作。

**建议工具：** `tiance.export_metadata_snapshot`

#### META-007 分页协议统一

MCP 内部 SHALL 统一封装各底层 API 的分页协议差异（包括但不限于 curPage/page/currentPage、pageSize/size），对外暴露统一的分页参数。

#### META-008 嵌套结构扁平化

对于多层嵌套的元数据（如预警信号的业务分类→分组→子分组→信号、外数指标的报文类型→模板→指标→指标包），MCP SHALL 返回扁平化结构或支持按层级过滤查询，避免调用方自行处理多层嵌套。

---

### 4 配置校验能力（VALID）

#### VALID-001 组件 Schema 获取

MCP SHALL 提供各组件类型对应的配置 Schema，包括必填字段、数据类型、枚举范围和嵌套结构定义。

#### VALID-002 引用解析

MCP SHALL 根据当前环境解析草稿中引用的字段、函数、规则、指标等对象，返回每个引用的解析结果（唯一实体 ID 或错误信息）。

**建议工具：** `tiance.resolve_references`

#### VALID-003 草稿校验

MCP SHALL 对配置草稿执行平台真实语义校验（而非仅 JSON Schema 校验），至少包括：

- 必填字段完整性。
- 数据类型和枚举范围。
- 引用对象存在性、唯一性和权限。
- 组件间依赖关系完整性。
- 平台业务规则（如节点类型白名单、字段编码格式、指标去重指纹）。

校验结果 SHALL 包含：错误位置（fieldPath）、错误代码（errorCode）、修改建议（suggestion）。

**建议工具：** `tiance.validate_draft`

#### VALID-004 草稿规范化

MCP SHALL 将草稿规范化为天策平台可接受的标准 payload 格式。

**建议工具：** `tiance.normalize_draft`

#### VALID-005 语义差异

MCP SHALL 对已有组件的草稿与线上版本生成语义差异（semantic diff），标明新增、修改、删除的字段和值。

**建议工具：** `tiance.diff_component`

#### VALID-006 依赖检查

MCP SHALL 检查组件之间的依赖关系，识别缺失依赖、循环依赖和版本不兼容。

**建议工具：** `tiance.check_dependencies`

---

### 5 组件生命周期能力（COMP）

#### COMP-001 组件查询

MCP SHALL 支持按类型、编码、名称、状态等条件查询组件列表和详情。

**建议工具：** `tiance.list_components`、`tiance.get_component`

#### COMP-002 组件导出

MCP SHALL 支持导出组件及其依赖信息，用于跨环境迁移或离线分析。

**建议工具：** `tiance.export_component`

#### COMP-003 两阶段变更模式

所有写操作 SHALL 采用计划-执行两阶段模式：

**阶段一（计划）：** 调用 `plan_component_change` 提交变更请求，MCP 返回影响范围、语义差异、风险评估和 planId。此阶段不产生任何副作用。

**阶段二（执行）：** 经用户或策略批准后，调用 `execute_component_change(planId)` 执行变更。

MCP SHALL NOT 允许调用方绕过计划阶段直接执行写操作。

**建议工具：** `tiance.plan_component_change`、`tiance.execute_component_change`

#### COMP-004 支持的组件操作

MCP SHALL 支持以下组件操作（通过两阶段模式）：

| 操作 | 说明 |
|------|------|
| 新建/导入 | 支持策略、规则集、函数、指标、数据源、ETL、字段、接口服务、基础配置 |
| 更新 | 更新已有组件的配置 |
| 发布 | 将组件发布到指定环境 |
| 上线 | 将已发布的组件切换为在线状态 |
| 下线 | 将在线组件切换为离线状态 |
| 删除 | 删除组件（需检查引用关系） |

#### COMP-005 批量导入编排

MCP SHALL 支持批量组件导入，自动按依赖关系排序（基础配置→字段→数据源→函数→指标→规则集→策略），并在计划阶段返回完整的执行计划。

#### COMP-006 引用阻塞规则

MCP SHALL 在计划阶段检查引用阻塞关系，并按以下规则处理：

| 组件类型 | 强引用 | 弱引用 |
|----------|--------|--------|
| 策略（POLICY） | 阻塞 | 阻塞 |
| 规则集（RULE_SET） | 阻塞 | 放行 |
| 实时指标（INDEX_REALTIME） | 阻塞 | 放行 |
| 接口服务（API_SERVICE） | 阻塞 | 放行 |

#### COMP-007 操作状态查询

MCP SHALL 提供操作状态查询能力，支持轮询和回调两种模式，返回操作进度、成功/失败明细、失败原因和恢复建议。

**建议工具：** `tiance.get_operation`

#### COMP-008 版本与历史

MCP SHALL 支持查询组件的版本历史，包括每个版本的变更摘要和操作人。

---

### 6 策略测试能力（TEST）

#### 6.1 策略发现（TEST-DISC）

##### TEST-DISC-001 策略列表查询

MCP SHALL 按机构编码查询可用策略列表，返回每个策略的编码、名称、当前发布版本号、业务类型和状态。

此查询 SHALL 始终返回平台实时数据，不得使用缓存。

##### TEST-DISC-002 策略详情与测试配置

MCP SHALL 支持获取策略详情，包括子策略编排、路由字段、决策结果配置，以及测试所需的参数 Schema（必填字段、枚举约束、默认值）。

##### TEST-DISC-003 版本差异比对

MCP SHALL 支持比较调用方持有的策略配置版本与平台当前版本的差异，标明版本不一致的字段。

#### 6.2 测试提交（TEST-SUBMIT）

##### TEST-SUBMIT-001 单用例提交

MCP SHALL 支持向指定策略提交单条测试用例，接受参数键值对，返回该用例的 token 和 uuid。

##### TEST-SUBMIT-002 批量提交

MCP SHALL 支持批量提交测试用例（每批次不超过平台限制），返回每条用例的 uuid、token 和 childToken 映射关系。

MCP SHALL 自动处理分批逻辑，调用方无需关心每批大小限制。

##### TEST-SUBMIT-003 参数预校验

MCP SHALL 在提交前对用例参数进行预校验，至少包括：

- 必填字段检查（如 S_S_BIZID 缺失 SHALL 返回 MISSING_REQUIRED_FIELD 错误，不得静默执行）。
- 数据类型检查。
- 枚举值范围检查。
- JSON 数组格式检查（如 C_O_*INFO 类字段）。

##### TEST-SUBMIT-004 提交确认

MCP SHALL 返回结构化的提交确认，包含每用例的提交状态（已受理/已拒绝/参数错误）、uuid、token 和 childToken。

三者含义 SHALL 明确区分：uuid 用于报告和结果查询、token 用于执行数据查询、childToken 用于子策略详情查询。

##### TEST-SUBMIT-005 提交失败分类

提交失败时，MCP SHALL 返回以下分类之一：

| 错误分类 | 说明 |
|----------|------|
| PARAM_INVALID | 参数格式或值错误 |
| VERSION_EXPIRED | 策略版本已过期，需重新获取 |
| SESSION_INVALID | 身份上下文失效 |
| RESOURCE_LIMIT | 平台资源不足（并发测试数上限） |
| INTERNAL_ERROR | 平台内部错误 |

#### 6.3 测试结果获取（TEST-RESULT）

##### TEST-RESULT-001 执行结果查询

MCP SHALL 按 uuid 查询测试执行结果，返回每用例的通过/未通过状态和最终决策等级。

##### TEST-RESULT-002 执行轨迹查询

MCP SHALL 提供按 detailLevel 分级的执行轨迹查询：

| detailLevel | 返回内容 |
|-------------|----------|
| sub_policy | 子策略执行状态（名称、childToken、是否执行） |
| rules | 规则命中详情（规则名称、编号、风险等级、所属规则集） |
| functions | 函数输出详情（函数名、入参、出参） |
| full | 完整组件执行日志（按执行顺序排列的全组件日志） |

MCP SHALL 将底层内部数据结构（ChildFlowNode.extension.tokenIds、RuleSetServiceNode.extension.executeDetail.hitRules 等）转换为领域化结果，调用方无需理解平台内部节点模型。

##### TEST-RESULT-003 测试报告

MCP SHALL 提供测试报告基本信息查询，返回报告 URL、策略版本、测试时间、用例数量、通过率等汇总信息。

##### TEST-RESULT-004 批量结果获取

MCP SHALL 支持一次请求获取多条用例的执行结果。

**建议工具：** `tiance.get_test_result`、`tiance.get_execution_trace`、`tiance.get_test_report`

#### 6.4 批量测试（TEST-BATCH）

##### TEST-BATCH-001 批量测试任务

MCP SHALL 支持通过上传测试文件创建批量测试任务，返回任务 ID。

##### TEST-BATCH-002 进度查询

MCP SHALL 支持查询批量测试任务的执行进度，返回已完成/总数/失败数。

##### TEST-BATCH-003 结果获取

MCP SHALL 支持获取批量测试的完整结果明细，包括每用例的通过/未通过状态、决策等级和命中规则。

##### TEST-BATCH-004 文件格式校验

MCP SHALL 在创建批量测试任务前校验上传文件的格式，对已知不兼容的格式（如 inlineStr 引擎生成的 Excel）返回明确的格式错误和修正建议。

**建议工具：** `tiance.submit_batch_test`、`tiance.get_batch_test_status`、`tiance.get_batch_test_results`

#### 6.5 测试诊断（TEST-DIAG）

##### TEST-DIAG-001 失败诊断

MCP SHALL 对测试失败提供结构化诊断，区分以下失败类型：

| 失败类型 | 说明 |
|----------|------|
| PARAM_ERROR | 输入参数格式或值错误 |
| RULE_MISS | 目标规则未命中（预期命中场景） |
| FUNCTION_ERROR | 函数执行异常（脚本错误、超时） |
| ETL_ERROR | ETL 输出异常（字段缺失、类型不匹配） |
| TIMEOUT | 平台执行超时 |
| PLATFORM_ERROR | 平台内部错误 |

##### TEST-DIAG-002 参数预校验（Dry-run）

MCP SHALL 支持 dry-run 模式，仅校验测试参数格式和引用完整性，不实际执行策略调用。

**建议工具：** `tiance.diagnose_test_failure`、`tiance.validate_test_params`

---

### 7 安全与变更控制（SEC）

#### SEC-001 默认只读

MCP SHALL 默认所有 Tool 为只读模式。写操作 SHALL 通过 plan-execute 两阶段模式执行。

#### SEC-002 计划绑定

每个 planId SHALL 绑定以下信息：

| 绑定项 | 说明 |
|--------|------|
| 用户 | 创建计划的用户 |
| 机构 | 操作的机构范围 |
| 环境 | 目标环境（test/prod） |
| 组件 | 涉及的组件标识和类型 |
| 变更摘要 | 变更内容的结构化描述 |
| 有效期 | 计划的过期时间 |

#### SEC-003 执行前重校验

执行阶段 SHALL 重新校验权限和组件版本，确保计划创建后未发生权限变更或组件被他人修改。

#### SEC-004 幂等

MCP SHALL 支持幂等键（idempotencyKey），防止因重试导致重复导入或重复发布。

相同幂等键的重复请求 SHALL 返回首次执行的结果，不产生额外副作用。

#### SEC-005 乐观锁

MCP SHALL 使用乐观锁或版本号机制，防止并发修改导致覆盖他人变更。

版本冲突时 SHALL 返回 VERSION_CONFLICT 错误码和当前最新版本号。

#### SEC-006 环境隔离

测试环境和生产环境 SHALL 采取不同的控制策略。

生产环境的写操作 SHALL 要求更高权限等级和更严格的审批流程。

第一期 SHALL 仅支持测试环境，生产环境的发布、下线、删除操作放到后续阶段。

#### SEC-007 敏感信息保护

Token、密钥和敏感配置 SHALL NOT 出现在 Tool 返回值、错误信息和审计日志中。

---

### 8 结构化返回规范（RESP）

#### RESP-001 统一返回结构

所有 MCP Tool 的返回值 SHALL 遵循统一结构：

```json
{
  "success": true | false,
  "errorCode": "错误代码（失败时）",
  "message": "人类可读描述",
  "fieldPath": "错误定位路径（校验类错误时）",
  "data": "业务数据（成功时）",
  "candidates": "候选项列表（歧义错误时）",
  "retryable": true | false,
  "traceId": "链路追踪标识",
  "environment": "环境标识",
  "metadataVersion": "元数据版本",
  "permissionDecision": "权限决策记录",
  "warnings": "警告列表",
  "nextActions": "建议的后续操作"
}
```

#### RESP-002 错误码规范

MCP SHALL 定义标准错误码体系，至少包括：

| 错误码 | 说明 |
|--------|------|
| AMBIGUOUS_REFERENCE | 解析结果不唯一 |
| NOT_FOUND | 实体不存在 |
| PERMISSION_DENIED | 权限不足 |
| MISSING_REQUIRED_FIELD | 必填字段缺失 |
| INVALID_TYPE | 数据类型不匹配 |
| INVALID_ENUM | 枚举值不合法 |
| REFERENCE_NOT_FOUND | 引用对象不存在 |
| VERSION_CONFLICT | 版本冲突 |
| VERSION_EXPIRED | 策略版本过期 |
| SESSION_INVALID | 身份上下文失效 |
| RESOURCE_LIMIT | 资源限制 |
| OPERATION_BLOCKED | 引用阻塞 |
| INTERNAL_ERROR | 平台内部错误 |

#### RESP-003 批量接口

MCP SHALL 提供批量查询和批量操作接口，避免调用方逐条请求。

批量接口 SHALL 返回每条记录的处理结果（成功/失败/跳过）。

#### RESP-004 策略测试结果结构

策略测试结果 SHALL 包含以下结构化字段：

```json
{
  "caseId": "用例标识",
  "uuid": "报告标识",
  "token": "执行数据查询标识",
  "status": "PASS | FAIL",
  "decisionLevel": "决策等级",
  "subPolicies": [
    { "name": "子策略名", "childToken": "...", "status": "EXECUTED | SKIPPED" }
  ],
  "hitRules": [
    { "name": "规则名", "code": "规则编号", "riskLevel": "风险等级", "ruleSet": "规则集名" }
  ],
  "functionOutputs": [
    { "name": "函数名", "inputs": {}, "outputs": {} }
  ]
}
```

---

### 9 审计与可观测性（AUDIT）

#### AUDIT-001 调用审计

每次 MCP 调用 SHALL 记录以下信息：

| 审计字段 | 说明 |
|----------|------|
| userId / orgCode | 用户和机构 |
| mcpClient | 调用方标识 |
| toolName | Tool 名称 |
| environment | 环境 |
| inputSummary | 输入参数摘要（脱敏） |
| operationType | 查询 / 计划 / 执行 |
| permissionDecision | 权限决策结果 |
| result | 执行结果（成功/失败） |
| traceId | 链路追踪标识 |
| planId | 关联的计划标识（写操作） |
| idempotencyKey | 幂等键（写操作） |
| timestamp | 操作时间 |

#### AUDIT-002 敏感信息过滤

审计日志 SHALL NOT 记录原始 Token、密码、密钥和敏感业务数据。

#### AUDIT-003 测试审计

策略测试操作 SHALL 额外记录：

- 测试的策略版本号。
- 提交的用例数量。
- 通过率和失败率汇总。

MCP SHALL 支持按策略编码、版本号、时间范围查询历史测试记录。

---

### 10 分期规划

#### 10.1 第一期范围

第一期 SHALL 实现以下能力，仅支持测试环境：

| 序号 | 能力 | 对应需求 |
|------|------|----------|
| 1 | bifrost 身份上下文和 capability 权限 | AUTH-001 ~ AUTH-005 |
| 2 | 元数据搜索、解析、详情、Schema 和依赖查询 | META-001 ~ META-006 |
| 3 | 配置草稿校验和引用解析 | VALID-002 ~ VALID-003 |
| 4 | 组件查询、导出、导入的计划与执行 | COMP-001 ~ COMP-003, COMP-007 |
| 5 | 策略列表查询、版本获取、测试配置 Schema | TEST-DISC-001 ~ TEST-DISC-002 |
| 6 | 策略测试提交（单用例和批量） | TEST-SUBMIT-001 ~ TEST-SUBMIT-005 |
| 7 | 测试结果获取（执行结果、子策略、规则命中、函数输出） | TEST-RESULT-001 ~ TEST-RESULT-004 |
| 8 | 操作状态、幂等和完整审计 | SEC-004, AUDIT-001 ~ AUDIT-003 |

#### 10.2 后续阶段

后续阶段 SHALL 逐步扩展：

- 生产环境的发布、上线、下线、删除操作。
- 批量测试（TEST-BATCH）。
- 测试诊断和 dry-run（TEST-DIAG）。
- 组件更新和语义差异（COMP-004 更新、VALID-005）。
- 配置规范化和草稿标准化（VALID-004）。

#### 10.3 预期调用链

第一期完成后，配置生成场景形成标准调用链：

```text
调用方生成配置草稿
→ MCP resolve_references（解析引用）
→ MCP validate_draft（平台校验）
→ MCP plan_component_change（生成变更计划）
→ 用户确认
→ MCP execute_component_change（执行变更）
→ MCP get_operation（查询状态）
```

策略测试场景形成标准调用链：

```text
获取策略版本（MCP search_entities）
→ 提交测试用例（MCP submit_policy_test）
→ 获取执行结果（MCP get_test_result）
→ 获取执行轨迹（MCP get_execution_trace）
→ 比较框架判定（调用方本地）
→ 质量检查（调用方本地）
→ 审计记录（MCP 自动）
```
