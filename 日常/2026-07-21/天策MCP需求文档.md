## 天策 MCP 需求文档

当前对 Tiance MCP 的需求，可以归纳为：把原来由 `tiance-*` skills 负责的接口发现、身份处理、元数据查询、配置校验、组件操作和策略测试，下沉为稳定、结构化、可审计的平台能力；Skill 主要保留需求理解、配置生成和流程编排。

本文档结合本地 19 个 tiance-* skill 的实际代码分析，将策略配置和策略测试两类 skill 的具体下沉需求统一纳入 MCP 能力设计。

---

### 一、总体定位

Tiance MCP 应当承担四类职责：

1. 提供可信的 Tiance 系统上下文。
2. 提供确定性的查询、校验和操作能力。
3. 隔离底层接口、鉴权方式、字段映射和版本差异。
4. 提供结构化的策略测试调用、结果获取和诊断能力。

不建议把 MCP 做成简单的 HTTP API 转发器。它应返回领域化结果，让模型不需要理解大量内部接口细节。

---

### 二、身份与权限需求

这是所有 MCP 能力的基础。

- MCP HTTP 层使用 OAuth 2.1/OIDC Bearer Token。
- bifrost 继续作为用户、机构、角色和权限的权威来源。
- 不复用浏览器的 `tdToken Cookie + CSRF` 调用方式。
- 将外部身份映射为统一 `ActorContext`，至少包含：
  - 用户
  - 机构
  - 应用
  - 环境
  - 角色
  - 会话
  - 权限版本
- 每个 Tool 都声明并检查 capability，例如：
  - `tiance.metadata.read`
  - `tiance.component.import`
  - `tiance.component.publish`
  - `tiance.component.invoke`
  - `tiance.policy.test`
  - `tiance.policy.test.read`
- Tool 参数不能覆盖身份上下文中的机构、应用和环境范围。
- MCP 会话与浏览器会话分离，避免共用 `tokenMD5` 后互相踢出。
- 身份上下文缺失时必须拒绝，不能回退为系统账号。
- 不向模型暴露 Token、密码、Cookie、CSRF Token 等敏感信息。

**当前 skill 痛点（来自 tiance-metadata-scout、tiance-component-lifecycle、tiance-policy-test、tiance-model-strategy）：**

- 5 个 skill 各自维护 CSRF 管理、`sessionStorage._csrf_` 提取、`X-Cf-Random` 头注入。
- tiance-metadata-scout 有 4 种连接模式（Gateway Proxy > 原生浏览器 > Puppeteer > 手动），每种模式的认证处理不同。
- Gateway Proxy 模式的双嵌套响应格式 `response["data"]["data"]` 需要在每个调用方手动解包。
- tiance-policy-test 在每次提交前做 Session 健康检查，浏览器 JS fetch + CSRF 管理占大量 skill 代码。
- tiance-model-strategy 要求 6 个 Cookie（TSESSIONID/NSESSIONID/YSESSIONID/GFSESSIONID/\_salt\_/\_qjt_ac\_）且登录有验证码，只能浏览器手动登录。

---

### 三、元数据能力

这部分用于大幅替代 `tiance-metadata-scout`。

建议提供：

- 搜索字段、函数、规则、数据源、指标、服务参数等实体。
- 根据名称、别名、编码解析唯一实体。
- 获取实体详情和稳定 ID。
- 获取实体 Schema、字段约束、枚举和默认值。
- 获取组件之间的依赖关系和引用关系。
- 获取当前机构、应用、环境下的可见范围。
- 支持分页、过滤、批量查询。
- 返回元数据版本或快照标识。
- 支持导出可复现的元数据快照和采集凭据。
- 对歧义、无结果、权限不足返回结构化错误和候选项。

核心工具可以包括：

```text
tiance.search_entities
tiance.resolve_entities
tiance.get_entity
tiance.get_schema
tiance.get_dependencies
tiance.export_metadata_snapshot
```

**当前 skill 下沉需求（来自 tiance-metadata-scout）：**

- 42 个端点分 13 类（A-M），输出 25+ JSON 文件。MCP 可按需查询，消除全量拉取。
- 各端点分页协议不统一（curPage vs page vs currentPage），MCP 内部封装。
- Captain API 四层嵌套（报文类型→模板→指标→指标包）和预警信号四层嵌套（业务分类→分组→子分组→信号），MCP 返回扁平化结构。
- 规则详情需逐条异步拉取（/noahApi/rule/detail），MCP 可批量返回。
- `X-Td-Signature` 请求签名（uniteApi）由 MCP 服务端内部处理。

如果这些能力完整，`tiance-metadata-scout` 可以退化为很薄的编排 Skill，甚至在常规任务中完全取消。

---

### 四、配置生成辅助与校验能力

Forge Skill 仍负责理解用户需求和生成配置草稿，MCP 负责提供确定性的校验。

需要支持：

- 获取组件类型对应的配置 Schema。
- 根据当前环境解析字段、函数、规则、指标等引用。
- 校验必填字段、数据类型、枚举和范围。
- 校验引用对象是否存在、是否唯一、是否有权限。
- 校验组件之间的依赖关系。
- 执行平台真实语义校验，而不仅是 JSON Schema 校验。
- 返回明确的错误位置、错误代码、修改建议。
- 将草稿规范化为 Tiance 可接受的标准 payload。
- 对已有组件生成语义差异。

建议工具：

```text
tiance.validate_draft
tiance.normalize_draft
tiance.resolve_references
tiance.diff_component
tiance.check_dependencies
```

**当前 skill 下沉需求（来自 8 个 Forge skill）：**

- tiance-rule-forge：从 13 个本地 JSON 文件做引用解析（字段/模板/函数/指标/名单），3 层校验（文件/结构/语义）。MCP 的 `resolve_references` 和 `validate_draft` 统一替代。
- tiance-field-forge：与平台已有字段做四重冲突检测（displayName/name 内部+平台），MCP 的 `resolve_entities` + `validate_draft` 替代。
- tiance-function-forge：从 `field_groups.json` 查 groupUuid（严格禁止生成 UUIDv4）、从 `function_definitions.json` 做三重去重预检（精确名称/签名/模糊名称），MCP 统一处理。
- tiance-policy-forge：校验 20+ 节点类型的属性规格和 businessType 白名单，MCP 的 `validate_draft` 执行平台真实语义校验。
- tiance-realtime-metric-forge：指标去重（SHA-256 指纹）和 10 位 hex 编码分配，MCP 可在 `plan_component_change` 时自动分配。
- tiance-datasource-forge：DES/CBC 加密可保留在 Skill 或下沉到 MCP（视安全策略）。
- tiance-etl-forge：导入后刷新元数据，MCP 导入后自动返回最新实体。
- tiance-service-config-forge：默认字段集合校验和 ServiceFieldMapping 命名规则校验。

这样可以显著降低各类 Forge Skill 对模型精确拼装底层 payload 的要求。

---

### 五、组件生命周期能力

这部分用于替代 `tiance-component-lifecycle` 中的接口调用和状态判断。

至少覆盖：

- 查询组件列表和详情。
- 导出组件及依赖信息。
- 新建或导入组件。
- 更新组件。
- 发布、上线、下线。
- 删除组件。
- 查询操作状态。
- 查询组件版本和历史。
- 校验当前状态是否允许目标操作。
- 处理异步任务和轮询。
- 提供失败原因和恢复建议。

不建议让模型直接调用单个危险操作。写操作采用两阶段模式：

```text
plan_component_change
        ↓
返回影响范围、差异、风险和 planId
        ↓
用户或策略批准
        ↓
execute_component_change(planId)
```

核心工具可以是：

```text
tiance.get_component
tiance.list_components
tiance.export_component
tiance.plan_component_change
tiance.execute_component_change
tiance.get_operation
```

**当前 skill 下沉需求（来自 tiance-component-lifecycle）：**

- 导入 CHECK（`/noahApi/component/import/check/{CATEGORY}` step=1）和 CONFIRM（step=2）直接映射为 plan→execute。
- 引用检查（`/bridgeApi/bifrost/checkComponentReference`）映射为 `check_dependencies`。
- 强/弱引用阻塞规则：POLICY=always block、RULE_SET=STRONG blocks/WEAK allows、INDEX_REALTIME/API_SERVICE=STRONG blocks/WEAK+NO_EXIST allows，编码为 `plan_component_change` 返回中的阻塞策略。
- 跨组件批量导入顺序（basic-config→fields→datasource→functions→indices→rulesets→policies），MCP 接受批量组件自动排序返回执行计划。
- 字段/数据源/ETL 文件上传（当前需本地 CORS HTTP server 端口 18765 + Puppeteer fetch），MCP 直接接收文件上传。
- payload 编码（JSON→gzip→base64）由 MCP 内部处理。

**来自 tiance-model-strategy 的额外需求：**

- PMML 模型上传（`/modelApi/modelManage/pmmlModel`）和上下线（`/modelApi/service/changeStatus`）。
- 指标发布（`/salaxyApi/metric/publish`）、规则集发布（`/noahApi/ruleset/publish`，必须用 `ruleSetUuid` 不是 `uuid`）、策略上线验证和上线（`/noahApi/policy/onlineValidate` + `/noahApi/policy/online`，必须是 x-www-form-urlencoded 不是 JSON）。
- 组件上线顺序严格依赖：指标→模型→规则集→策略。
- 26 个已知陷阱中，与平台交互相关的应逐步编码为 MCP 的校验规则。

当上述能力成熟后，`tiance-component-lifecycle` 的主要功能可以被 MCP 取代。Forge Skill 可以直接调用 MCP 完成校验、导入和发布。

---

### 六、策略测试能力

这部分用于下沉 `tiance-policy-test`、`tiance-model-strategy`（测试部分）和 `tiance-agent-loop` 中的平台交互逻辑。`tiance-testcase-generator` 和 `tiance-report-checker` 是纯本地处理，无需 MCP。

#### 6.1 策略发现与版本管理

当前 tiance-policy-test 的 Step 1 要求**每次提交前必须从平台实时查询策略版本**，禁止使用本地缓存。

需要支持：

- 按机构查询可用策略列表，返回策略编码、名称、当前发布版本号、业务类型。
- 获取策略详情，包括子策略编排、路由字段、决策结果配置。
- 获取策略的测试配置（参数 schema、必填字段、枚举约束）。
- 比较本地配置与平台当前版本的差异。

建议工具：

```text
tiance.search_entities(type="policy", orgCode=...)
tiance.get_entity(type="policy", code=...)
tiance.get_schema(type="policy_test_config", code=...)
```

**当前 skill 痛点：**

- tiance-policy-test 通过浏览器 JS fetch `/noahApi/policy/list` 获取策略列表，每次运行前必须执行。
- `policyVersion` 和 `businessType` 是高频变更字段，缓存值会导致提交失败。
- tiance-agent-loop 在每轮迭代开始前额外执行一次平台验证（Step 1.5），作为双保险。

#### 6.2 测试提交与执行

当前 tiance-policy-test 通过浏览器 JS fetch 向 `/noahApi/lab/policytest/create` 批量提交测试用例（每批 10-11 条）。

需要支持：

- 批量提交策略测试用例，接受参数列表，返回每批次的 token 和 uuid。
- 支持 API 提交和 UI 模拟提交两种模式。
- 返回结构化的提交确认（每用例的 token、uuid、childToken 映射关系）。
- 处理异步执行，支持进度查询。
- 提交失败时返回明确的错误分类（参数格式错误、策略版本过期、Session 失效、平台资源不足）。

建议工具：

```text
tiance.submit_policy_test(policyCode, policyVersion, testCases[])
tiance.get_test_submission_status(submissionId)
```

**当前 skill 痛点：**

- UUID vs Token vs childToken 三者含义不同：UUID 用于报告 URL、Token 用于 runData 查询、childToken 用于子策略规则详情。当前 skill 需要手动维护映射关系。
- 批量提交有大小限制（每批 10-11 条），skill 需手动分批。
- `S_S_BIZID` 是必填字段，缺失会导致静默空数据返回（无报错），MCP 应在参数校验阶段拦截。

#### 6.3 测试结果获取

当前 tiance-policy-test 使用六层验证体系逐层获取结果。

需要支持：

- 获取测试执行结果，包括每用例的通过/未通过状态和决策等级。
- 获取子策略执行详情（对应 runData nodeType=8），返回子策略 token 和命中状态。
- 获取规则命中详情（对应 runData nodeType=1），返回命中规则的名称、编号、风险等级。
- 获取函数输出详情（对应 runData nodeType=5），返回函数名、入参、出参。
- 获取完整组件执行日志（对应 getAllCompontlog），返回按执行顺序排列的全组件日志。
- 获取测试报告基本信息（对应 `/noahApi/policy/report/test/baseInfo`）。
- 支持批量获取多用例结果。

建议工具：

```text
tiance.get_test_result(uuid, token)
tiance.get_execution_trace(uuid, detailLevel="sub_policy"|"rules"|"functions"|"full")
tiance.get_component_log(uuid, options)
tiance.get_test_report(uuid)
```

**当前 skill 痛点：**

- 六层验证体系（create 响应→runData nodeType=8→nodeType=1→nodeType=5→getAllCompontlog→浏览器导航）每层有不同的 API 格式和解析逻辑。
- 子策略定位：通过 ChildFlowNode.extension.tokenIds 关联子策略 token。
- 规则命中定位：通过 RuleSetServiceNode.extension.executeDetail.hitRules[].name。
- 函数输出定位：通过 FunctionServiceNode.nodeOutputList。
- 这些内部数据结构对模型不友好，MCP 应返回领域化结果。

#### 6.4 批量测试（模型策略场景）

tiance-model-strategy 的 Phase 3 使用批量测试（不同于 policy-test 的单用例提交）。

需要支持：

- 上传批量测试 Excel 文件。
- 创建批量测试任务。
- 轮询测试进度。
- 获取批量测试结果和明细。

建议工具：

```text
tiance.submit_batch_test(policyCode, testFile)
tiance.get_batch_test_status(taskId)
tiance.get_batch_test_results(taskId)
```

**当前 skill 痛点：**

- 模板下载（`/noahApi/lab/policyBatchTest/export`）、创建（`/noahApi/lab/policyBatchTest/create` 上传文件）、轮询（`/noahApi/lab/policyBatchTest/list`）、获取结果（`/noahApi/lab/policyBatchTest/detail` + `getListAll`）四步串行。
- 批量测试 Excel 必须用 xlsxwriter 引擎（openpyxl 的 inlineStr 导致服务端解析失败）。
- DCFLAG 列必须跳过（服务端对空枚举值有 bug）。

#### 6.5 测试比较与诊断辅助

tiance-policy-test 和 tiance-report-checker 的比较框架依赖结构化结果。

需要支持：

- 返回的测试结果应包含足够信息供比较框架使用：别名组（alias_group）、穿透字段（pass_through）、模糊别名（fuzzy_alias）、数值容差（numeric_tolerance）。
- 对测试失败提供结构化诊断：区分参数错误、规则未命中、函数异常、ETL 输出异常、平台超时等类型。
- 支持 dry-run 模式，仅校验参数格式不实际执行。

建议工具：

```text
tiance.diagnose_test_failure(uuid, token)
tiance.validate_test_params(policyCode, testCases[])
```

**与 Skill 的分工：**

- tiance-testcase-generator（测试用例生成）：纯本地处理，解析 Excel 生成测试用例 JSON。不直接需要 MCP，但可选通过 `tiance.get_entity(type="policy")` 获取完整策略配置辅助用例设计。
- tiance-report-checker（报告质量检查）：纯本地 Excel 四维质量检查（判定矛盾、数据缺失、语义重复、实际结果异常）。不需要 MCP。
- tiance-agent-loop（自动化闭环）：编排逻辑（触发检测、收敛判断、反馈分类）全部保留在 Skill，平台交互部分继承自 policy-test 的 MCP 下沉。

---

### 七、安全和变更控制

所有写操作必须满足：

- 默认只读。
- 明确区分查询、计划和执行。
- 高风险操作需要用户确认或审批凭据。
- `planId` 必须绑定：
  - 用户
  - 机构
  - 环境
  - 组件
  - 变更内容摘要
  - 有效期
- 执行时重新检查权限和组件版本。
- 支持幂等键，防止模型重试造成重复导入或发布。
- 使用乐观锁或版本号避免覆盖他人修改。
- 生产环境和测试环境采取不同控制策略。
- Token、密钥和敏感配置不得出现在 Tool 返回值及日志中。
- 策略测试提交应限制并发数，避免对平台造成压力。
- 批量测试文件应做病毒扫描和格式校验后再执行。

---

### 八、结构化返回与模型友好性

MCP 返回值应当尽可能确定，避免让模型解析自然语言：

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

统一返回中还应包含：

- `traceId`
- `environment`
- `metadataVersion`
- `permissionDecision`
- `warnings`
- `nextActions`

同时应支持批量接口，避免模型逐条查询几十个字段或函数。

**策略测试结果的结构化返回示例：**

```json
{
  "success": true,
  "traceId": "abc-123",
  "metadataVersion": "v2026.07.21",
  "results": [
    {
      "caseId": "TC001",
      "uuid": "32位hex",
      "token": "35位token",
      "status": "PASS",
      "decisionLevel": "REJECT",
      "subPolicies": [
        {
          "name": "企业信用评估子策略",
          "childToken": "...",
          "status": "EXECUTED"
        }
      ],
      "hitRules": [
        {
          "name": "规则编号(规则中文名)",
          "riskLevel": "HIGH",
          "ruleSet": "规则集名称"
        }
      ],
      "functionOutputs": [
        {
          "name": "函数名",
          "inputs": {},
          "outputs": {}
        }
      ]
    }
  ]
}
```

---

### 九、审计和可观测性

每次 MCP 调用都应记录：

- 用户和机构
- MCP Client
- Tool 名称
- 环境和资源范围
- 输入摘要
- 查询、计划或执行类型
- 权限决策
- 执行结果
- `traceId`
- `planId`
- 幂等键
- 操作时间

审计日志不得记录原始 Token、密码、密钥和敏感业务数据。

**策略测试额外审计需求：**

- 记录每次测试提交的策略版本号，便于追溯"哪个版本做了哪些测试"。
- 记录测试用例数量和通过率汇总。
- 支持按策略、版本、时间范围查询历史测试记录。

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
| 测试获取 | 结果、执行轨迹、组件日志、报告 | 六层验证编排、比较框架 |
| 批量测试 | 文件上传、任务创建、轮询、结果 | 测试方法论、Excel 生成 |
| 测试诊断 | 结构化错误分类、参数预校验 | 综合分析、提出修改方案 |
| 测试用例生成 | 可选：提供策略配置辅助设计 | 表达式识别、条件分解、场景组合 |
| 报告质量检查 | 不处理 | 四维检查（纯本地） |
| 自动化闭环 | 继承上述测试能力 | 触发检测、收敛判断、反馈分类 |
| 审批控制 | planId、权限、幂等、审计 | 发起确认、选择执行策略 |

因此：

- `tiance-metadata-scout`：可以被基本取代。
- `tiance-component-lifecycle`：接口执行部分可以被完全取代。
- 各类 `*-forge`：仍然需要，但会变薄，集中于需求理解、配置生成和验收。
- `tiance-policy-test`：平台交互部分（提交/获取/日志）大部分下沉到 MCP，Skill 保留六层验证编排、比较框架和 Excel 报告生成。
- `tiance-model-strategy`：全链路平台交互下沉到 MCP，Skill 保留 26 个陷阱知识库、组件上线顺序编排和三层测试方法论。
- `tiance-testcase-generator`：基本不变，纯本地处理。
- `tiance-report-checker`：基本不变，纯本地处理。
- `tiance-agent-loop`：继承 policy-test 的 MCP 下沉，编排逻辑全部保留。

---

### 十一、建议的第一期范围

第一期不必一次覆盖所有组件，建议先实现：

1. bifrost 身份上下文和 capability 权限（含 `tiance.policy.test` 权限）。
2. 元数据搜索、解析、详情、Schema 和依赖查询。
3. 配置草稿校验和引用解析。
4. 组件查询、导出、导入的计划与执行。
5. 操作状态、幂等和完整审计。
6. 策略发现：策略列表查询、版本获取、测试配置 Schema。
7. 策略测试提交：批量提交、token/uuid 返回、参数校验。
8. 测试结果获取：执行结果、子策略详情、规则命中、函数输出。
9. 先支持测试环境，生产发布、下线、删除、批量测试放到后续阶段。

第一期完成后，配置类 Forge Skill 形成稳定调用链：

```text
用户需求
→ Forge 生成草稿
→ MCP 解析引用
→ MCP 校验
→ MCP 生成变更计划
→ 用户确认
→ MCP 执行
→ MCP 返回状态和审计证据
```

策略测试 Skill 形成稳定调用链：

```text
tiance-agent-loop 触发检测
→ tiance-testcase-generator 生成用例
→ MCP 获取策略版本（替代浏览器 JS fetch）
→ MCP 提交测试（替代浏览器批量 fetch）
→ MCP 获取结果和执行轨迹（替代六层 runData 查询）
→ tiance-policy-test 比较框架判定
→ tiance-report-checker 质量检查
→ MCP 记录审计
→ 反馈下一轮或收敛
```

---

### 附录：不可下沉的 Skill（基础设施部署类）

以下 skill 操作的是服务器基础设施（SSH/JumpServer），与天策平台 API 无关，MCP 不覆盖：

| Skill | 原因 |
|-------|------|
| tiance-app-deploy | 通过 SSH 部署 14+ Java 应用，操作 Nacos/JVM/启动脚本 |
| tiance-nginx-frontend | SSH 配置 Nginx 反向代理和前端静态资源 |
| tiance-sql-init | SSH 隧道执行 MySQL 建表脚本和数据完整性验证 |
| tiance-troubleshoot | 35+ 故障案例的诊断指南，涉及 SSH/MySQL/Nacos/Nginx 排查 |
