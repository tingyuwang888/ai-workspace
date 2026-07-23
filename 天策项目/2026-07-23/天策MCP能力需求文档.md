## 天策 MCP 平台能力需求文档

当前对 Tiance MCP 的需求，归纳为：把原来由 `tiance-*` skills 负责的接口发现、身份处理、元数据查询、配置校验、组件操作和策略测试，下沉为稳定、结构化、可审计的平台能力；Skill 保留需求理解、配置生成和流程编排。

---

### 一、总体定位

Tiance MCP 须承担四类职责：

1. 提供可信的 Tiance 系统上下文。
2. 提供确定性的查询、校验和操作能力。
3. 隔离底层接口、鉴权方式、字段映射和版本差异。
4. 提供结构化的策略测试调用、结果获取和诊断能力。

MCP 不应做成 HTTP API 转发器，须返回领域化结果，使调用方无需理解大量内部接口细节。

---

### 二、身份与权限需求

身份与权限是所有 MCP 能力的基础，须满足以下要求：

- MCP HTTP 层须使用 OAuth 2.1/OIDC Bearer Token 进行认证，不接受 Cookie、CSRF Token 或浏览器会话凭证。
- bifrost 继续作为用户、机构、角色和权限的权威来源。
- 须将外部身份映射为统一 `ActorContext`，至少包含：用户、机构、应用、环境、角色、会话、权限版本。
- 每个 Tool 须声明并检查 capability，至少包括：`tiance.metadata.read`、`tiance.component.import`、`tiance.component.publish`、`tiance.component.invoke`、`tiance.policy.test`、`tiance.policy.test.read`。
- Tool 参数不得覆盖身份上下文中的机构、应用和环境范围。
- MCP 会话须与浏览器会话分离，不共用 `tokenMD5`，避免互相踢出登录状态。
- 身份上下文缺失时须拒绝请求，不得回退为系统账号。
- 不得向调用方暴露 Token、密码、Cookie、CSRF Token 等敏感信息。

---

### 三、元数据能力

本部分用于替代 `tiance-metadata-scout` 的平台交互逻辑。

MCP 须支持以下元数据能力：

- 搜索字段、函数、规则、规则集、数据源、指标、服务参数、名单、模板、策略、决策工具、预警信号、外数指标等实体。
- 根据名称、别名、编码解析唯一实体；解析不唯一时须返回歧义错误和候选项列表，无匹配时须返回未找到错误和建议搜索词，权限不足时须返回权限拒绝错误。
- 获取实体详情和稳定 ID。
- 获取实体 Schema、字段约束、枚举和默认值。
- 获取组件之间的依赖关系和引用关系。
- 获取当前机构、应用、环境下的可见范围。
- 支持分页、过滤、批量查询。
- 返回元数据版本或快照标识，支持导出可复现的元数据快照和采集凭据。
- 内部须统一封装各底层 API 的分页协议差异（curPage/page/currentPage 等），对外暴露统一的分页参数。
- 对多层嵌套的元数据（如预警信号的业务分类→分组→子分组→信号、外数指标的报文类型→模板→指标→指标包），须返回扁平化结构或支持按层级过滤查询。

核心工具：

```text
tiance.search_entities
tiance.resolve_entities
tiance.get_entity
tiance.get_schema
tiance.get_dependencies
tiance.export_metadata_snapshot
```

上述能力完整后，`tiance-metadata-scout` 可退化为薄编排 Skill，或在常规任务中完全取消。

---

### 四、配置生成辅助与校验能力

Forge Skill 仍负责理解用户需求和生成配置草稿，MCP 负责提供确定性的校验。

MCP 须支持以下校验能力：

- 获取组件类型对应的配置 Schema。
- 根据当前环境解析字段、函数、规则、指标等引用，返回每个引用的解析结果（唯一实体 ID 或错误信息）。
- 校验必填字段、数据类型、枚举和范围。
- 校验引用对象是否存在、是否唯一、是否有权限。
- 校验组件之间的依赖关系。
- 须执行平台真实语义校验，而非仅 JSON Schema 校验。校验范围须覆盖：节点类型白名单、字段编码格式、指标去重指纹（SHA-256）、编码分配冲突等平台业务规则。
- 返回明确的错误位置（fieldPath）、错误代码（errorCode）、修改建议（suggestion）。
- 将草稿规范化为 Tiance 可接受的标准 payload。
- 对已有组件生成语义差异（semantic diff）。

核心工具：

```text
tiance.validate_draft
tiance.normalize_draft
tiance.resolve_references
tiance.diff_component
tiance.check_dependencies
```

上述能力可显著降低 `rule-forge`、`field-forge`、`datasource-forge`、`service-config-forge`、`function-forge`、`etl-forge`、`policy-forge`、`realtime-metric-forge` 对模型精确拼装底层 payload 的要求。

---

### 五、组件生命周期能力

本部分用于替代 `tiance-component-lifecycle` 中的接口调用和状态判断。

MCP 须覆盖以下能力：

- 查询组件列表和详情。
- 导出组件及依赖信息。
- 新建或导入组件。支持策略、规则集、函数、指标、数据源、ETL、字段、接口服务、基础配置等类型。
- 更新组件。
- 发布、上线、下线。
- 删除组件（须检查引用关系）。
- 查询操作状态，支持轮询和回调两种模式，返回操作进度、成功/失败明细、失败原因和恢复建议。
- 查询组件版本和历史。
- 校验当前状态是否允许目标操作。
- 处理异步任务。

写操作须采用两阶段模式，不得允许调用方绕过计划阶段直接执行：

```text
plan_component_change
        ↓
返回影响范围、差异、风险和 planId
        ↓
用户或策略批准
        ↓
execute_component_change(planId)
```

MCP 须支持批量组件导入，自动按依赖关系排序（基础配置→字段→数据源→函数→指标→规则集→策略），在计划阶段返回完整执行计划。

MCP 须在计划阶段检查引用阻塞关系：策略（POLICY）的强引用和弱引用均须阻塞；规则集（RULE_SET）、实时指标（INDEX_REALTIME）、接口服务（API_SERVICE）的强引用须阻塞，弱引用可放行。

核心工具：

```text
tiance.get_component
tiance.list_components
tiance.export_component
tiance.plan_component_change
tiance.execute_component_change
tiance.get_operation
```

上述能力成熟后，`tiance-component-lifecycle` 的主要功能可被 MCP 取代。Forge Skill 可直接调用 MCP 完成校验、导入和发布。

---

### 六、策略测试能力

本部分用于下沉 `tiance-policy-test`、`tiance-model-strategy`（测试部分）和 `tiance-agent-loop` 中的平台交互逻辑。`tiance-testcase-generator` 和 `tiance-report-checker` 为纯本地处理，无需 MCP 支持。

#### 6.1 策略发现与版本管理

` tiance-policy-test` 要求每次提交前须从平台实时查询策略版本，禁止使用缓存。MCP 须支持：

- 按机构查询可用策略列表，返回策略编码、名称、当前发布版本号、业务类型和状态。此查询须始终返回平台实时数据，不得使用缓存。
- 获取策略详情，包括子策略编排、路由字段、决策结果配置。
- 获取策略的测试参数 Schema，包括必填字段、枚举约束、默认值。
- 比较调用方持有的策略配置版本与平台当前版本的差异。

核心工具：

```text
tiance.search_entities(type="policy")
tiance.get_entity(type="policy")
tiance.get_schema(type="policy_test_config")
```

#### 6.2 测试提交与执行

MCP 须支持以下测试提交能力：

- 支持单用例提交和批量提交，接受参数键值对或参数列表，返回每条用例的 uuid、token 和 childToken 映射关系。
- 须自动处理分批逻辑，调用方无需关心每批大小限制。
- 须在提交前对用例参数进行预校验：必填字段缺失（如 S_S_BIZID）须返回明确错误，不得静默执行；须检查数据类型、枚举值范围、JSON 数组格式（如 C_O_*INFO 类字段）。
- 返回结构化提交确认，包含每用例的提交状态（已受理/已拒绝/参数错误）。
- uuid、token、childToken 三者须明确区分用途：uuid 用于报告和结果查询、token 用于执行数据查询、childToken 用于子策略详情查询。
- 提交失败时须返回分类错误：参数格式错误、策略版本过期、身份上下文失效、平台资源不足、平台内部错误。

核心工具：

```text
tiance.submit_policy_test
tiance.get_test_submission_status
```

#### 6.3 测试结果获取

MCP 须支持分级获取测试结果：

- 按 uuid 查询测试执行结果，返回每用例的通过/未通过状态和最终决策等级。
- 按 detailLevel 分级查询执行轨迹：sub_policy 级返回子策略执行状态（名称、childToken、是否执行）；rules 级返回规则命中详情（规则名称、编号、风险等级、所属规则集）；functions 级返回函数输出详情（函数名、入参、出参）；full 级返回完整组件执行日志（按执行顺序排列）。
- 须将底层内部数据结构（ChildFlowNode.extension.tokenIds、RuleSetServiceNode.extension.executeDetail.hitRules 等）转换为领域化结果，调用方无需理解平台内部节点模型。
- 提供测试报告基本信息查询，返回报告 URL、策略版本、测试时间、用例数量、通过率等汇总。
- 支持一次请求获取多条用例的执行结果。

核心工具：

```text
tiance.get_test_result
tiance.get_execution_trace
tiance.get_test_report
```

#### 6.4 批量测试

`tiance-model-strategy` 的批量测试场景须独立支持。MCP 须支持：

- 通过上传测试文件创建批量测试任务，返回任务 ID。
- 查询批量测试任务的执行进度，返回已完成/总数/失败数。
- 获取批量测试的完整结果明细，包括每用例的通过/未通过状态、决策等级和命中规则。
- 在创建任务前校验上传文件格式，对已知不兼容的格式返回明确的格式错误和修正建议。

核心工具：

```text
tiance.submit_batch_test
tiance.get_batch_test_status
tiance.get_batch_test_results
```

#### 6.5 测试诊断辅助

MCP 须支持以下诊断能力：

- 对测试失败提供结构化诊断，区分以下类型：输入参数错误、目标规则未命中、函数执行异常（脚本错误/超时）、ETL 输出异常（字段缺失/类型不匹配）、平台执行超时、平台内部错误。
- 支持 dry-run 模式，仅校验测试参数格式和引用完整性，不实际执行策略调用。

核心工具：

```text
tiance.diagnose_test_failure
tiance.validate_test_params
```

**与 Skill 的分工：** `tiance-testcase-generator`（测试用例生成）为纯本地处理，可选通过 MCP 获取策略配置辅助用例设计。`tiance-report-checker`（报告质量检查）为纯本地四维检查，不需要 MCP。`tiance-agent-loop`（自动化闭环）的编排逻辑全部保留在 Skill，平台交互部分继承 policy-test 的 MCP 下沉。

---

### 七、安全和变更控制

所有写操作须满足以下要求：

- 默认只读，写操作须通过 plan-execute 两阶段模式执行。
- 明确区分查询、计划和执行。
- 高风险操作须用户确认或审批凭据。
- `planId` 须绑定：用户、机构、环境、组件、变更内容摘要、有效期。
- 执行时须重新检查权限和组件版本，确保计划创建后未发生权限变更或组件被他人修改。
- 须支持幂等键（idempotencyKey），防止因重试导致重复导入或重复发布。相同幂等键的重复请求须返回首次执行结果，不产生额外副作用。
- 须使用乐观锁或版本号机制，防止并发修改导致覆盖他人变更。版本冲突时须返回错误码和当前最新版本号。
- 生产环境和测试环境须采取不同控制策略，生产环境的写操作须要求更高权限等级和更严格审批流程。
- 第一期仅支持测试环境，生产环境的发布、下线、删除放到后续阶段。
- Token、密钥和敏感配置不得出现在 Tool 返回值、错误信息及审计日志中。
- 策略测试提交须限制并发数，避免对平台造成压力。

---

### 八、结构化返回与模型友好性

MCP 返回值须尽可能确定，避免让调用方解析自然语言。统一返回结构须包含：

```json
{
  "success": false,
  "errorCode": "AMBIGUOUS_REFERENCE",
  "message": "存在多个同名字段",
  "fieldPath": "$.conditions[0].field",
  "candidates": [
    {
      "id": "field-101",
      "name": "客户等级",
      "ownerOrg": "ORG001"
    }
  ],
  "retryable": false
}
```

统一返回中还须包含：`traceId`、`environment`、`metadataVersion`、`permissionDecision`、`warnings`、`nextActions`。

须定义标准错误码体系，至少包括：AMBIGUOUS_REFERENCE（解析不唯一）、NOT_FOUND（实体不存在）、PERMISSION_DENIED（权限不足）、MISSING_REQUIRED_FIELD（必填字段缺失）、INVALID_TYPE（数据类型不匹配）、INVALID_ENUM（枚举值不合法）、REFERENCE_NOT_FOUND（引用对象不存在）、VERSION_CONFLICT（版本冲突）、VERSION_EXPIRED（策略版本过期）、SESSION_INVALID（身份上下文失效）、RESOURCE_LIMIT（资源限制）、OPERATION_BLOCKED（引用阻塞）、INTERNAL_ERROR（平台内部错误）。

须支持批量接口，避免调用方逐条查询。批量接口须返回每条记录的处理结果。

策略测试结果须包含结构化字段：用例标识、uuid、token、通过/未通过状态、决策等级、子策略执行状态列表、命中规则列表（名称/编号/风险等级/规则集）、函数输出列表（函数名/入参/出参）。

---

### 九、审计和可观测性

每次 MCP 调用须记录以下信息：用户和机构、调用方标识（MCP Client）、Tool 名称、环境和资源范围、输入摘要（脱敏）、操作类型（查询/计划/执行）、权限决策、执行结果、`traceId`、`planId`、幂等键、操作时间。

审计日志不得记录原始 Token、密码、密钥和敏感业务数据。

策略测试操作须额外记录：测试的策略版本号、提交的用例数量、通过率和失败率汇总。MCP 须支持按策略编码、版本号、时间范围查询历史测试记录。

---

### 十、Skill 与 MCP 的最终分工

| 能力 | MCP 负责 | Skill 负责 |
|---|---|---|
| 身份认证 | Token 校验、身份上下文、权限 | 不处理 |
| 元数据 | 查询、解析、快照、依赖 | 决定查询什么、解释结果 |
| 配置生成 | Schema、引用解析、平台校验 | 理解需求、生成草稿 |
| 生命周期 | 计划、导入、更新、发布、下线 | 编排流程、向用户说明影响 |
| 策略发现 | 策略列表、版本、详情、Schema | 决定测试哪个策略 |
| 测试提交 | 批量提交、参数校验、进度跟踪 | 准备用例、分批策略 |
| 测试获取 | 结果、执行轨迹、组件日志、报告 | 验证编排、比较框架 |
| 批量测试 | 文件上传、任务创建、轮询、结果 | 测试方法论、Excel 生成 |
| 测试诊断 | 结构化错误分类、参数预校验 | 综合分析、提出修改方案 |
| 测试用例生成 | 可选：提供策略配置辅助设计 | 表达式识别、条件分解、场景组合 |
| 报告质量检查 | 不处理 | 四维检查（纯本地） |
| 自动化闭环 | 继承上述测试能力 | 触发检测、收敛判断、反馈分类 |
| 审批控制 | planId、权限、幂等、审计 | 发起确认、选择执行策略 |

因此：

- `tiance-metadata-scout`：可被基本取代。
- `tiance-component-lifecycle`：接口执行部分可被完全取代。
- 各类 `*-forge`：仍须保留，但会变薄，集中于需求理解、配置生成和验收。
- `tiance-policy-test`：平台交互部分（提交/获取/日志）大部分下沉到 MCP，Skill 保留验证编排、比较框架和报告生成。
- `tiance-model-strategy`：全链路平台交互下沉到 MCP，Skill 保留陷阱知识库、上线顺序编排和测试方法论。
- `tiance-testcase-generator`：基本不变，纯本地处理。
- `tiance-report-checker`：基本不变，纯本地处理。
- `tiance-agent-loop`：继承 policy-test 的 MCP 下沉，编排逻辑全部保留。

---

### 十一、建议的第一期范围

第一期不必一次覆盖所有能力，建议先实现：

1. bifrost 身份上下文和 capability 权限（含 `tiance.policy.test` 权限）。
2. 元数据搜索、解析、详情、Schema 和依赖查询。
3. 配置草稿校验和引用解析。
4. 组件查询、导出、导入的计划与执行。
5. 操作状态、幂等和完整审计。
6. 策略发现：策略列表查询、版本获取、测试配置 Schema。
7. 策略测试提交：单用例和批量提交、参数预校验。
8. 测试结果获取：执行结果、子策略详情、规则命中、函数输出。
9. 仅支持测试环境，生产发布、下线、删除、批量测试放到后续阶段。

第一期完成后，配置生成场景形成标准调用链：

```text
调用方生成配置草稿
→ MCP 解析引用
→ MCP 校验
→ MCP 生成变更计划
→ 用户确认
→ MCP 执行
→ MCP 返回状态和审计证据
```

策略测试场景形成标准调用链：

```text
获取策略版本
→ 提交测试用例
→ 获取执行结果
→ 获取执行轨迹
→ 比较框架判定（本地）
→ 质量检查（本地）
→ 审计记录（自动）
```
