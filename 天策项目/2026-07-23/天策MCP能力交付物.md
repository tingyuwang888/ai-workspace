# 天策 MCP 能力交付物

## 1. 天策MCP能力建设体系

基于天策决策中台现有架构与AI Agent集成需求，MCP（Model Context Protocol）能力建设聚焦于将平台核心管理能力封装为标准化、可审计、可编排的工具接口，使AI Agent能够安全、高效地与天策平台交互。

### 1.1 平台适配层

平台适配层是天策MCP能力的核心基础设施，负责将Agent的高层意图映射到天策平台的底层操作。该层需要解决现有平台API的碎片化、身份认证的不一致性以及操作审计的缺失问题。

**核心适配能力**

- **身份认证适配**：将Agent的OAuth 2.1 Bearer Token映射为天策平台的bifrost身份上下文（ActorContext），包含用户、机构、应用、环境、角色、会话、权限版本等维度。MCP会话与浏览器会话完全分离，不共用tokenMD5，避免互相踢出登录状态。
- **元数据适配**：统一封装天策平台15+类实体的查询、解析、Schema获取和依赖关系查询，消除底层API的分页协议差异（curPage/page/currentPage）、嵌套结构差异（预警信号四层嵌套、外数指标四层嵌套）和响应格式差异（双嵌套response["data"]["data"]）。
- **校验适配**：提供平台真实语义校验（而非仅JSON Schema校验），覆盖节点类型白名单、字段编码格式、指标去重指纹（SHA-256）、编码分配冲突等平台业务规则。
- **计划-执行适配**：所有写操作采用两阶段模式（plan_component_change → execute_component_change），在计划阶段返回影响范围、语义差异和风险评估，执行阶段重新校验权限和版本，支持幂等键和乐观锁。
- **审计适配**：每次调用记录完整的操作上下文（用户、机构、Tool、环境、输入摘要、操作类型、权限决策、执行结果、traceId、planId、幂等键、操作时间），但不记录Token、密码、密钥等敏感信息。

### 1.2 现有Skills能力替代

天策MCP能力的建设目标是逐步替代现有20个tiance-* Skills中的平台交互逻辑，使Skills专注于需求理解、配置生成和流程编排。

**完全可替代的Skills（3个）**

- **tiance-metadata**（15个端点）：通过MCP的tiance.search_entities、tiance.resolve_entities、tiance.get_entity、tiance.get_schema、tiance.get_dependencies、tiance.export_metadata_snapshot等6个工具完全替代。消除CSRF管理、手动XHR调用、window.__d全局累积等复杂度。
- **tiance-metadata-scout**（42个端点）：通过MCP工具按需调用完全替代。消除4种连接模式的分支逻辑、各端点分页协议差异、Captain API四层嵌套等复杂度。
- **tiance-component-lifecycle**（组件导入导出流程）：通过MCP的tiance.plan_component_change和tiance.execute_component_change完全替代check→confirm两步流程。消除payload编码（JSON→gzip→base64）、CORS HTTP server、引用阻塞规则手动判断等复杂度。

**大部分可替代、Skill变薄的Skills（8个Forge类）**

- **tiance-rule-forge**：引用解析（字段、函数、指标、名单）下沉到MCP，Skill保留Excel语义理解、规则模板多维评分、条件分类逻辑。
- **tiance-field-forge**：查重和导入下沉到MCP，Skill保留字段命名约束、数据类型映射、编码规则。
- **tiance-datasource-forge**：导入和引用下沉到MCP，Skill保留Excel扫描、协议类型处理、SQL构造。
- **tiance-function-forge**：引用解析下沉到MCP，Skill保留DSL公式语法、α类型前缀系统、Java脚本模板。
- **tiance-etl-forge**：导入下沉到MCP，Skill保留4种ETL类型Java模板、LLM代码生成、Groovy编译兼容。
- **tiance-policy-forge**：引用解析和校验下沉到MCP，Skill保留20+节点类型属性规格、Sugiyama自动布局、中间JSON格式。
- **tiance-realtime-metric-forge**：引用解析下沉到MCP，Skill保留模板分类决策树、Formula DSL/Groovy实现、两阶段处理。
- **tiance-service-config-forge**：引用解析下沉到MCP，Skill保留6列CSV格式、ServiceFieldMapping命名规则。

**部分可替代的Skills（3个）**

- **tiance-policy-test**：平台交互（提交/获取/日志）大部分下沉到MCP，Skill保留六层验证体系编排、比较框架、Excel报告生成。
- **tiance-model-strategy**：全链路平台交互下沉到MCP，Skill保留26个已知陷阱/坑点、组件上线顺序编排、三层测试方法论。
- **tiance-agent-loop**：继承policy-test的MCP下沉，编排逻辑（触发检测、收敛判断、反馈分类）全部保留。

**不可替代的Skills（4个基础设施部署类）**

- tiance-app-deploy、tiance-nginx-frontend、tiance-sql-init、tiance-troubleshoot：操作服务器基础设施（SSH/JumpServer），与天策平台API无关，MCP不覆盖。

## 2. 平台适配性分析

### 2.1 现有平台交互流程

天策平台现有的外部交互能力分散在多个AI Skill中，主要通过以下方式与平台API通信：

- **浏览器自动化**：通过Chrome Extension或Puppeteer模拟用户操作，执行同步XHR请求，手动管理sessionStorage._csrf_和X-Cf-Random。
- **Cookie注入**：从已登录的浏览器会话中提取Cookie和CSRF Token，注入到curl或Python requests调用中。
- **Gateway Proxy模式**：通过tiance_proxy.py代理层管理登录态，处理双嵌套响应格式（response["data"]["data"]），自动重登录。
- **本地JSON文件缓存**：将元数据（字段、函数、规则、指标等）导出为10-25个JSON文件，供Forge类Skill离线使用。

**交互流程分类**

- **元数据查询流程**：涉及15-42个REST端点，分页协议不统一（curPage/page/currentPage），嵌套结构差异大（预警信号四层、外数指标四层），响应格式不一致（部分API双嵌套、部分API扁平）。
- **配置生成流程**：从本地JSON文件读取元数据，通过规则模板多维评分选择模板，分类条件，生成导入文件（.rss/.fun/.ds/.etl/.pls/.xls/.csv），手动校验引用正确性。
- **组件导入流程**：check→confirm两步模式，payload需要JSON→gzip→base64编码，文件上传需要启动CORS HTTP server（端口18765），引用阻塞规则需要手动判断。
- **策略测试流程**：浏览器JS fetch提交测试用例，CSRF Token管理，Session健康检查，多层执行数据获取（nodeType=8/1/5），getAllCompontlog获取完整组件日志。

### 2.2 当前流程痛点

**身份认证痛点**

- Cookie和CSRF Token与浏览器会话绑定，MCP调用与浏览器操作互相踢出登录状态。
- Gateway Proxy模式需要维护额外的代理进程，登录态过期后需要手动重登录。
- 无法为AI Agent提供独立的、可审计的身份认证机制。

**元数据查询痛点**

- 底层API分页协议不统一，Skill中需要编写大量适配代码（curPage/page/currentPage、pageSize/size）。
- 嵌套结构差异大，Skill中需要手动扁平化（预警信号四层嵌套、外数指标四层嵌套）。
- 响应格式不一致，部分API双嵌套（response["data"]["data"]）、部分API扁平，Skill中需要大量条件判断。
- 本地JSON文件缓存存在版本滞后，元数据变更后Skill仍在使用旧版本。

**配置生成痛点**

- 引用解析依赖本地JSON文件，无法实时校验引用对象是否存在、是否唯一、是否有权限。
- 校验逻辑停留在JSON Schema层面，无法执行平台真实语义校验（节点类型白名单、字段编码格式、指标去重指纹等）。
- 编码分配冲突无法预检，导入后才发现错误。

**组件导入痛点**

- check→confirm两步流程无法支持批量操作的原子性。
- payload编码（JSON→gzip→base64）和文件上传（CORS HTTP server）复杂度高。
- 引用阻塞规则需要手动判断，批量导入顺序需要人工编排。

**策略测试痛点**

- 浏览器JS fetch方式脆弱，CSRF Token过期、Session失效等问题频繁出现。
- 执行数据获取需要多层遍历（nodeType=8/1/5），Skill中需要大量条件判断和数据结构转换。
- 批量测试进度轮询需要手动实现，重复提交风险无法控制。

### 2.3 平台适配层设计方案

**适配层架构**

```
AI Agent
  ↓ MCP协议
MCP Server（平台适配层）
  ↓ 内部API
天策平台后端
  ├─ bifrost（身份认证）
  ├─ bridgeApi（元数据、组件）
  ├─ noahApi（组件导入导出）
  ├─ indexApi（指标管理）
  ├─ tradeApi（交易映射）
  └─ modelApi（模型管理）
```

**身份认证适配方案**

- MCP Server实现OAuth 2.1 Bearer Token认证，Agent通过认证后获取Token。
- Token映射为ActorContext（用户、机构、应用、环境、角色、会话、权限版本），bifrost作为权威来源。
- 每个Tool声明所需capability（tiance.metadata.read、tiance.component.import、tiance.component.publish、tiance.component.invoke、tiance.policy.test、tiance.policy.test.read），执行前进行权限校验。
- MCP会话与浏览器会话完全分离，不共用tokenMD5。

**元数据适配方案**

- 统一封装底层API的分页协议差异，对外暴露统一的分页参数（page、pageSize）。
- 对多层嵌套的元数据，返回扁平化结构或支持按层级过滤查询。
- 统一响应格式，所有Tool返回标准结构（success、errorCode、message、fieldPath、data、candidates、retryable、traceId、environment、metadataVersion、permissionDecision、warnings、nextActions）。
- 支持元数据快照导出（tiance.export_metadata_snapshot），确保下游工具基于同一快照进行一致性操作。

**校验适配方案**

- 提供tiance.validate_draft工具，执行平台真实语义校验（节点类型白名单、字段编码格式、指标去重指纹、编码分配冲突等）。
- 提供tiance.resolve_references工具，解析草稿中引用的字段、函数、规则、指标等对象，返回每个引用的解析结果（唯一实体ID或错误信息）。
- 校验结果包含错误位置（fieldPath）、错误代码（errorCode）、修改建议（suggestion）。

**计划-执行适配方案**

- 所有写操作采用两阶段模式：tiance.plan_component_change → 返回影响范围、差异、风险和planId → 用户确认 → tiance.execute_component_change(planId)。
- 计划阶段不产生副作用，执行阶段重新校验权限和版本。
- 支持幂等键（idempotencyKey），防止重试导致重复操作。
- 支持乐观锁，防止并发修改覆盖他人变更。

**审计适配方案**

- 每次调用记录完整操作上下文（用户、机构、Tool、环境、输入摘要、操作类型、权限决策、执行结果、traceId、planId、幂等键、操作时间）。
- 审计日志不记录Token、密码、密钥等敏感信息。
- 支持按策略编码、版本号、时间范围查询历史操作记录。

## 3. 优先级能力详细设计

### 3.1 策略管理能力

#### 现有平台交互流程

策略管理是天策决策中台的核心能力，涉及策略的创建、配置、测试、发布、上线、下线等全生命周期操作。当前AI Agent与策略管理的交互主要通过以下方式：

- **策略发现**：通过tiance-metadata-scout的G类端点（策略分页+策略字典）获取策略列表和详情，输出policy_list.json和policy_dict.json。
- **策略配置**：通过tiance-policy-forge生成.pls策略/决策流导入文件，从本地JSON文件（function_definitions.json、ruleset_definitions.json、deal_types.json、policy_dict.json）解析引用，校验节点类型白名单和引用存在性。
- **策略测试**：通过tiance-policy-test提交测试用例，浏览器JS fetch调用/noahApi/lab/policytest/create，获取执行数据（runData多层遍历）和完整组件日志（getAllCompontlog）。
- **策略发布**：通过tiance-component-lifecycle执行check→confirm两步导入，然后手动发布、上线。

#### 当前流程痛点

- 策略发现依赖元数据导出文件，版本滞后于平台实际状态，每次提交前需要重新刷新。
- 策略配置中的引用解析（函数UUID、规则集UUID、处置类型编码）依赖本地JSON文件，无法实时校验引用是否存在、是否唯一。
- 节点类型白名单（per businessType）校验停留在本地规则，与平台实际规则可能存在偏差。
- 策略测试的浏览器JS fetch方式脆弱，CSRF Token过期、Session失效等问题频繁出现。
- 策略发布后的上线操作需要手动确认，无法自动化闭环。

#### 工具接口设计

**tiance.policy.list**

- 功能：按机构查询可用策略列表，返回策略编码、名称、当前发布版本号、业务类型和状态。此查询始终返回平台实时数据，不使用缓存。
- 输入：orgCode（机构编码，必填）、businessType（业务类型，可选）、status（状态过滤，可选）、page（页码，可选）、pageSize（每页大小，可选）。
- 输出：策略列表（编码、名称、版本号、业务类型、状态）、总数、分页信息。

**tiance.policy.detail**

- 功能：获取策略详情，包括子策略编排、路由字段、决策结果配置。
- 输入：policyCode（策略编码，必填）或policyId（策略ID，必填）。
- 输出：策略完整详情（子策略列表、路由字段、决策结果配置、节点连接关系）。

**tiance.policy.test_config**

- 功能：获取策略的测试参数Schema，包括必填字段、枚举约束、默认值。
- 输入：policyCode（策略编码，必填）。
- 输出：测试参数Schema（字段列表、必填标记、枚举值、默认值、数据类型）。

**tiance.policy.version_diff**

- 功能：比较调用方持有的策略配置版本与平台当前版本的差异。
- 输入：policyCode（策略编码，必填）、clientVersion（调用方持有的版本号，必填）。
- 输出：版本差异（新增字段、修改字段、删除字段）、当前最新版本号。

**tiance.policy.submit_test**

- 功能：提交单条或批量测试用例，自动处理分批逻辑，返回每用例的uuid、token和childToken映射关系。提交前对用例参数进行预校验（必填字段、数据类型、枚举范围、JSON数组格式）。
- 输入：policyCode（策略编码，必填）、testCases（用例列表，必填，每用例为参数键值对）、idempotencyKey（幂等键，可选）。
- 输出：每用例的提交状态（已受理/已拒绝/参数错误）、uuid、token、childToken。

**tiance.policy.get_test_result**

- 功能：按uuid查询测试执行结果，返回每用例的通过/未通过状态和最终决策等级。支持一次请求获取多条用例的执行结果。
- 输入：uuids（用例标识列表，必填）。
- 输出：每用例的执行状态（通过/未通过/执行中）、决策等级、子策略执行状态列表。

**tiance.policy.get_execution_trace**

- 功能：按detailLevel分级查询执行轨迹，将底层内部数据结构转换为领域化结果。
- 输入：token（执行数据查询标识，必填）、detailLevel（详情级别，必填，枚举：sub_policy/rules/functions/full）。
- 输出：分级执行轨迹（sub_policy级：子策略执行状态；rules级：规则命中详情；functions级：函数输出详情；full级：完整组件执行日志）。

**tiance.policy.plan_publish**

- 功能：计划阶段，生成策略发布计划，返回影响范围、语义差异和风险评估。
- 输入：policyCode（策略编码，必填）、targetEnvironment（目标环境，必填，枚举：test/prod）、idempotencyKey（幂等键，可选）。
- 输出：planId、影响范围（引用的规则集、函数、指标）、语义差异（与当前线上版本的差异）、风险评估（高/中/低）。

**tiance.policy.execute_publish**

- 功能：执行阶段，经用户确认后发布策略。执行前重新校验权限和版本。
- 输入：planId（计划ID，必填）。
- 输出：操作状态（成功/失败/执行中）、操作进度、成功/失败明细、失败原因和恢复建议。

**tiance.policy.plan_online / tiance.policy.plan_offline**

- 功能：计划阶段，生成策略上线/下线计划。
- 输入：policyCode（策略编码，必填）、targetEnvironment（目标环境，必填）。
- 输出：planId、影响范围、风险评估。

**tiance.policy.execute_online / tiance.policy.execute_offline**

- 功能：执行阶段，经用户确认后上线/下线策略。
- 输入：planId（计划ID，必填）。
- 输出：操作状态、操作进度。

#### 平台适配层实现方案

**复用现有能力**

- 策略发现和详情查询复用bridgeApi/noahApi的策略查询接口，MCP层统一封装分页和响应格式。
- 策略测试提交复用/noahApi/lab/policytest/create接口，MCP层处理CSRF Token和Session管理。
- 策略发布/上线/下线复用tiance-component-lifecycle的check→confirm流程，MCP层封装为plan→execute两阶段模式。

**需要平台后端新增的能力**

- 策略版本差异比对接口：当前平台不提供版本差异API，需要后端新增接口，比较指定版本与当前版本的配置差异。
- 测试参数Schema接口：当前测试参数配置散落在策略配置中，需要后端提供独立的Schema查询接口。
- 执行轨迹分级查询接口：当前getAllCompontlog返回完整日志，需要后端支持按detailLevel分级查询，并将底层数据结构（ChildFlowNode.extension.tokenIds、RuleSetServiceNode.extension.executeDetail.hitRules）转换为领域化结果。

**适配层新增的逻辑**

- 测试提交预校验：在提交前对用例参数进行预校验（必填字段S_S_BIZID、数据类型、枚举范围、JSON数组格式C_O_*INFO），校验失败直接返回错误，不提交到平台。
- 批量提交分批处理：根据平台每批次大小限制，自动拆分批量用例为多批提交，返回统一的映射关系。
- 幂等键处理：生成和校验idempotencyKey，防止重复提交。

**改造工作量评估**

- 策略发现/详情/测试配置：复用现有接口，MCP层封装工作量小（约2-3人天）。
- 策略版本差异比对：需要后端新增接口，MCP层适配工作量中等（约5-7人天）。
- 策略测试提交/结果获取：复用现有接口，MCP层增加预校验和分批处理工作量中等（约5-7人天）。
- 执行轨迹分级查询：需要后端新增接口或MCP层做大量数据结构转换，工作量较大（约8-10人天）。
- 策略发布/上线/下线：复用组件生命周期流程，MCP层封装工作量小（约2-3人天）。

### 3.2 规则管理能力

#### 现有平台交互流程

规则管理涉及规则的创建、配置、测试、验证、发布和版本管理。当前AI Agent与规则管理的交互主要通过以下方式：

- **规则发现**：通过tiance-metadata-scout的F类端点（规则集分页+规则详情逐条拉取）获取规则集列表和规则详情，输出ruleset_list.json和rule_details.json。
- **规则配置**：通过tiance-rule-forge从本地JSON文件（field_metadata.json、rule_templates.json、function_definitions.json、metric_definitions.json、roster_definitions.json）解析引用，通过规则模板多维评分选择模板，分类条件（直接/指标/模板/函数），生成.rss规则集文件。
- **规则校验**：3层校验（文件/结构/语义），但停留在本地规则，无法执行平台真实语义校验。
- **规则导入**：通过tiance-component-lifecycle执行check→confirm两步导入。

#### 当前流程痛点

- 规则条件表达式中引用的字段编码、函数返回值、指标值等，正确性依赖本地JSON文件的版本，无法实时校验。
- 规则模板选择依赖多维评分算法，模板库更新后Skill中的评分规则可能滞后。
- 规则集内部的规则优先级和冲突策略配置复杂，缺乏可视化的冲突检测。
- 规则风险等级（低/中/高/极高）分配缺乏一致性校验，不同规则集中的相同条件可能分配不同等级。
- 规则集版本对比缺乏语义级别的差异分析，只能看到配置文本差异。

#### 工具接口设计

**tiance.rule.list**

- 功能：按机构查询规则集列表，返回规则集编码、名称、版本号、规则数量、状态。
- 输入：orgCode（机构编码，必填）、status（状态过滤，可选）、page（页码，可选）、pageSize（每页大小，可选）。
- 输出：规则集列表、总数、分页信息。

**tiance.rule.detail**

- 功能：获取规则集详情，包括所有规则的条件表达式、风险等级、引用关系。
- 输入：ruleSetCode（规则集编码，必填）或ruleSetId（规则集ID，必填）。
- 输出：规则集完整详情（规则列表、条件表达式、风险等级、引用关系、优先级配置）。

**tiance.rule.validate**

- 功能：校验规则集配置的合法性，包括引用完整性、条件表达式语法、风险等级一致性、规则冲突检测。执行平台真实语义校验。
- 输入：ruleSetDraft（规则集配置草稿，必填）。
- 输出：校验结果（通过/失败）、错误列表（fieldPath、errorCode、suggestion）、警告列表。

**tiance.rule.plan_create / tiance.rule.plan_update**

- 功能：计划阶段，生成规则集创建/更新计划，返回影响范围、语义差异和风险评估。
- 输入：ruleSetDraft（规则集配置草稿，必填）、idempotencyKey（幂等键，可选）。
- 输出：planId、影响范围（引用的字段、函数、指标、名单）、语义差异（与当前版本的差异）、风险评估。

**tiance.rule.execute_create / tiance.rule.execute_update**

- 功能：执行阶段，经用户确认后创建/更新规则集。
- 输入：planId（计划ID，必填）。
- 输出：操作状态、操作进度、成功/失败明细。

**tiance.rule.plan_publish / tiance.rule.execute_publish**

- 功能：规则集发布的计划和执行。
- 输入/输出：同策略发布。

**tiance.rule.version_diff**

- 功能：比较规则集两个版本的语义差异，标明新增/修改/删除的规则和条件。
- 输入：ruleSetCode（规则集编码，必填）、versionA（版本A，必填）、versionB（版本B，可选，默认当前版本）。
- 输出：语义差异（新增规则、修改规则、删除规则、条件变更详情）。

#### 平台适配层实现方案

**复用现有能力**

- 规则集查询复用bridgeApi的规则集查询接口。
- 规则集导入导出复用组件生命周期的check→confirm流程。

**需要平台后端新增的能力**

- 规则集校验引擎扩展：当前校验仅覆盖JSON Schema层面，需要扩展到平台真实语义校验（引用完整性、字段类型匹配、函数签名匹配、规则优先级冲突检测、风险等级一致性校验）。
- 规则集版本对比接口：需要后端提供语义级别的版本差异API，而非文本差异。
- 规则集批量更新接口：当前更新操作逐条执行，需要支持批量更新的原子性。

**改造工作量评估**

- 规则集查询/详情：复用现有接口，工作量小（约2人天）。
- 规则集校验：需要后端扩展校验引擎，MCP层适配工作量中等（约5-7人天）。
- 规则集创建/更新：复用组件生命周期流程，工作量小（约2-3人天）。
- 规则集版本对比：需要后端新增接口，工作量中等（约5人天）。

### 3.3 指标管理能力

#### 现有平台交互流程

指标管理涉及指标的定义、配置、计算、发布和监控。当前AI Agent与指标管理的交互主要通过以下方式：

- **指标发现**：通过tiance-metadata-scout的G类端点（/indexApi/metricManagement/list分页拉取）获取指标配置列表，输出metric_definitions.json。
- **指标配置**：通过tiance-realtime-metric-forge从本地JSON文件（field_metadata.json、channel_apps.json、metric_catalog.json）解析引用，通过模板分类决策树（15优先级）选择指标模板，生成指标配置，执行SHA-256去重指纹检查和10位hex编码分配。
- **指标导入**：通过tiance-component-lifecycle执行check→confirm两步导入。
- **指标发布**：通过tiance-model-strategy按依赖顺序发布（指标→规则集→策略）。

#### 当前流程痛点

- 指标类型多样（实时指标、统计指标、衍生指标等），平台提供11+种指标模板，每种模板的参数配置和计算逻辑不同，Skill中需要维护复杂的模板分类决策树。
- 指标计算逻辑（公式型DSL或脚本型Groovy）的正确性难以预验证，导入后才发现语法错误或引用不存在。
- 指标编码分配（10位hex）需要手动确保不与现有指标冲突，缺乏自动化的编码分配服务。
- 指标去重检查（SHA-256指纹）依赖本地JSON文件的版本，无法实时判断是否重复。
- 指标发布需要按依赖顺序（指标→规则集→策略），当前缺乏自动化的依赖排序和批量发布。
- 指标被多个规则集和决策流引用，变更影响范围难以评估。

#### 工具接口设计

**tiance.metric.list**

- 功能：按机构查询指标列表，返回指标编码、名称、类型、模板、状态。
- 输入：orgCode（机构编码，必填）、metricType（指标类型过滤，可选）、status（状态过滤，可选）、page（页码，可选）、pageSize（每页大小，可选）。
- 输出：指标列表、总数、分页信息。

**tiance.metric.detail**

- 功能：获取指标详情，包括计算逻辑、参数配置、引用关系。
- 输入：metricCode（指标编码，必填）或metricId（指标ID，必填）。
- 输出：指标完整详情（计算逻辑、参数配置、模板类型、引用关系、版本号）。

**tiance.metric.schema**

- 功能：获取指标模板的配置Schema，包括必填参数、枚举约束、默认值。支持11+种指标模板的Schema查询。
- 输入：templateType（模板类型，必填）。
- 输出：模板Schema（参数列表、必填标记、枚举值、默认值、数据类型）。

**tiance.metric.validate**

- 功能：校验指标配置的合法性，包括引用完整性、计算逻辑语法、模板参数匹配、去重指纹检查。
- 输入：metricDraft（指标配置草稿，必填）。
- 输出：校验结果（通过/失败）、错误列表（fieldPath、errorCode、suggestion）、去重检查结果（是否存在相同指纹的指标）、警告列表。

**tiance.metric.plan_create / tiance.metric.plan_update**

- 功能：计划阶段，生成指标创建/更新计划，返回影响范围、语义差异和风险评估。自动分配编码（10位hex）。
- 输入：metricDraft（指标配置草稿，必填）、idempotencyKey（幂等键，可选）。
- 输出：planId、分配的编码、影响范围（引用的字段、函数）、语义差异、风险评估（引用阻塞关系）。

**tiance.metric.execute_create / tiance.metric.execute_update**

- 功能：执行阶段，经用户确认后创建/更新指标。
- 输入：planId（计划ID，必填）。
- 输出：操作状态、操作进度。

**tiance.metric.plan_publish / tiance.metric.execute_publish**

- 功能：指标发布的计划和执行。
- 输入/输出：同策略发布。

**tiance.metric.version_diff**

- 功能：比较指标两个版本的语义差异。
- 输入：metricCode（指标编码，必填）、versionA（版本A，必填）、versionB（版本B，可选）。
- 输出：语义差异（计算逻辑变更、参数变更、模板变更）。

**tiance.metric.check_duplicate**

- 功能：检查指标是否与现有指标重复（基于SHA-256指纹）。
- 输入：calculationLogic（计算逻辑，必填）、templateType（模板类型，必填）。
- 输出：是否重复、重复的指标列表（编码、名称、版本号）。

**tiance.metric.check_references**

- 功能：查询指标被哪些规则集和决策流引用，评估变更影响范围。
- 输入：metricCode（指标编码，必填）。
- 输出：引用列表（规则集编码/名称、决策流编码/名称）、影响评估。

#### 平台适配层实现方案

**复用现有能力**

- 指标查询复用indexApi的指标查询接口，MCP层统一封装分页和响应格式。
- 指标导入导出复用组件生命周期的check→confirm流程。

**需要平台后端新增的能力**

- 指标校验引擎扩展：支持计算逻辑语法校验（DSL和Groovy）、模板参数匹配校验、去重指纹计算和比对。
- 编码自动分配服务：提供10位hex编码的自动分配和冲突检测。
- 指标引用关系查询接口：查询指标被哪些规则集和决策流引用。
- 指标版本对比接口：语义级别的版本差异API。

**改造工作量评估**

- 指标查询/详情/Schema：复用现有接口，工作量小（约3人天）。
- 指标校验（含去重检查）：需要后端扩展校验引擎，工作量较大（约8-10人天）。
- 指标创建/更新：复用组件生命周期流程，增加编码自动分配工作量中等（约5人天）。
- 指标引用关系查询：需要后端新增接口，工作量中等（约5人天）。
- 指标版本对比：需要后端新增接口，工作量中等（约5人天）。

### 3.4 AI技能管理能力

#### 现有平台交互流程

AI技能（Skill）管理是天策平台的新增能力，涉及AI技能的定义、配置、测试、发布和绑定。当前AI技能的配置主要通过以下方式：

- **技能配置**：在天策平台后台管理界面手动配置AI技能，包括技能名称、描述、触发条件（关键词、斜杠命令、自然语言）、参数Schema、执行脚本等。
- **技能绑定**：将AI技能绑定到指定的AI Agent，使Agent能够发现和调用该技能。
- **技能测试**：通过TdAlly平台的斜杠命令或自然语言触发技能执行，观察执行结果和日志。

#### 当前流程痛点

- AI技能的配置完全手动，需要在后台管理界面逐项填写，缺乏批量操作能力。
- 技能的触发条件（关键词、斜杠命令）配置分散，缺乏统一的触发条件管理和冲突检测。
- 技能的版本管理缺失，修改后无法回滚到历史版本。
- 技能与Agent的绑定关系手动管理，难以追踪哪些技能绑定了哪些Agent。
- 技能的运行状态（调用次数、成功率、平均耗时）缺乏可视化监控。
- 技能的发布流程不规范，测试环境和生产环境的技能配置缺乏一致性保障。

#### 工具接口设计

**tiance.skill.list**

- 功能：查询AI技能列表，返回技能名称、描述、触发条件、绑定Agent数量、状态。
- 输入：status（状态过滤，可选）、keyword（关键词搜索，可选）、page（页码，可选）、pageSize（每页大小，可选）。
- 输出：技能列表、总数、分页信息。

**tiance.skill.detail**

- 功能：获取AI技能详情，包括完整配置、触发条件、参数Schema、执行脚本、绑定Agent列表。
- 输入：skillId（技能ID，必填）或skillName（技能名称，必填）。
- 输出：技能完整详情（配置、触发条件、参数Schema、执行脚本、绑定Agent列表、版本号）。

**tiance.skill.validate**

- 功能：校验AI技能配置的合法性，包括触发条件语法、参数Schema完整性、执行脚本语法、Agent模型兼容性。
- 输入：skillDraft（技能配置草稿，必填）。
- 输出：校验结果（通过/失败）、错误列表、警告列表（触发条件冲突、模型兼容性警告）。

**tiance.skill.plan_publish / tiance.skill.execute_publish**

- 功能：AI技能发布的计划和执行。计划阶段返回影响范围（绑定的Agent列表）和风险评估。
- 输入/输出：同策略发布。

**tiance.skill.plan_bind / tiance.skill.execute_bind**

- 功能：将AI技能绑定到指定Agent的计划和执行。计划阶段返回Agent当前已绑定的技能列表和潜在冲突。
- 输入：skillId（技能ID，必填）、agentId（Agent ID，必填）、idempotencyKey（幂等键，可选）。
- 输出：planId、Agent当前绑定技能列表、潜在冲突（触发条件重叠）、风险评估。

**tiance.skill.agent_config**

- 功能：查询指定Agent的技能配置列表，包括已绑定的技能、触发条件、运行状态。
- 输入：agentId（Agent ID，必填）。
- 输出：Agent的技能配置列表（技能名称、触发条件、状态、调用次数、成功率）。

**tiance.skill.diagnose**

- 功能：诊断AI技能执行问题，包括触发条件未匹配、参数校验失败、执行脚本错误、模型调用超时等。
- 输入：skillId（技能ID，必填）、executionId（执行记录ID，可选，用于诊断特定执行）。
- 输出：诊断结果（问题分类、问题描述、修复建议）。

#### 平台适配层实现方案

**复用现有能力**

- AI技能配置存储复用天策平台的技能管理数据库表。
- Agent绑定关系复用天策平台的Agent配置接口。

**需要平台后端新增的能力**

- AI技能查询API：当前技能配置仅在UI中管理，需要后端提供REST API（技能列表、详情、配置查询）。
- 技能校验引擎：新增技能配置校验层（触发条件语法校验、参数Schema校验、执行脚本语法校验、Agent模型兼容性校验）。
- 技能发布流程：新增技能发布的plan→execute两阶段流程，支持环境迁移（测试→生产）。
- 技能运行监控API：新增技能运行状态查询接口（调用次数、成功率、平均耗时）。
- 技能诊断API：新增技能执行问题诊断接口（触发条件匹配分析、执行日志分析、模型调用链路追踪）。

**改造工作量评估**

- AI技能管理是平台适配层中改造工作量最大的能力，因为当前平台缺乏完整的技能管理API体系。
- 技能查询/详情/配置：需要后端新增API，工作量中等（约5-7人天）。
- 技能校验引擎：需要后端新增校验层，工作量中等（约5-7人天）。
- 技能发布/绑定：需要新增plan→execute流程，工作量中等（约5-7人天）。
- 技能监控/诊断：需要后端新增API，工作量较大（约8-10人天）。

### 3.5 规则集管理能力

#### 现有平台交互流程

规则集管理涵盖规则集的创建、配置、测试、验证、发布和版本管理。当前AI Agent与规则集管理的交互主要通过以下方式：

- **规则集发现**：通过tiance-metadata-scout的F类端点（规则集分页+规则详情逐条拉取）获取规则集列表和规则详情，输出ruleset_list.json和rule_details.json。
- **规则集配置**：通过tiance-rule-forge从本地JSON文件（field_metadata.json、rule_templates.json、function_definitions.json、metric_definitions.json、roster_definitions.json）解析引用，通过规则模板多维评分选择模板，分类条件（直接/指标/模板/函数），生成.rss规则集文件。
- **规则集校验**：3层校验（文件/结构/语义），但停留在本地规则，无法执行平台真实语义校验。
- **规则集导入**：通过tiance-component-lifecycle执行check→confirm两步导入。

#### 当前流程痛点

- 规则条件表达式中引用的字段编码、函数返回值、指标值等，正确性依赖本地JSON文件的版本，无法实时校验引用是否存在、是否唯一。
- 规则集内部的规则优先级和冲突策略配置复杂，缺乏自动化的冲突检测机制。
- 规则集之间的引用关系（规则集A引用规则集B的结果）难以自动检查和验证。
- 规则风险等级（低/中/高/极高）分配缺乏一致性校验，不同规则集中的相同条件可能分配不同等级。
- 规则集版本对比缺乏语义级别的差异分析，只能看到配置文本差异，无法识别条件逻辑变更。
- 批量修改规则集中的多条规则时，缺乏原子性保证，部分更新成功部分失败的情况难以回滚。

#### 工具接口设计

**tiance.ruleset.list**

- 功能：按机构查询规则集列表，返回规则集编码、名称、版本号、规则数量、状态。
- 输入：orgCode（机构编码，必填）、status（状态过滤，可选）、page（页码，可选）、pageSize（每页大小，可选）。
- 输出：规则集列表（编码、名称、版本号、规则数量、状态）、总数、分页信息。

**tiance.ruleset.detail**

- 功能：获取规则集详情，包括所有规则的条件表达式、风险等级、引用关系、优先级配置。
- 输入：ruleSetCode（规则集编码，必填）或ruleSetId（规则集ID，必填）。
- 输出：规则集完整详情（规则列表、条件表达式、风险等级、引用关系、优先级配置、版本号）。

**tiance.ruleset.validate**

- 功能：校验规则集配置的合法性，包括引用完整性、条件表达式语法、风险等级一致性、规则冲突检测、跨规则集引用检查。执行平台真实语义校验。
- 输入：ruleSetDraft（规则集配置草稿，必填）。
- 输出：校验结果（通过/失败）、错误列表（fieldPath、errorCode、suggestion）、冲突检测结果（规则间冲突、跨规则集冲突）、警告列表。

**tiance.ruleset.plan_create / tiance.ruleset.plan_update**

- 功能：计划阶段，生成规则集创建/更新计划，返回影响范围、语义差异和风险评估。支持批量规则更新的原子性。
- 输入：ruleSetDraft（规则集配置草稿，必填）、idempotencyKey（幂等键，可选）。
- 输出：planId、影响范围（引用的字段、函数、指标、名单、其他规则集）、语义差异（与当前版本的差异）、风险评估（高/中/低）。

**tiance.ruleset.execute_create / tiance.ruleset.execute_update**

- 功能：执行阶段，经用户确认后创建/更新规则集。执行前重新校验权限和版本。
- 输入：planId（计划ID，必填）。
- 输出：操作状态（成功/失败/执行中）、操作进度、成功/失败明细、失败原因和恢复建议。

**tiance.ruleset.plan_publish / tiance.ruleset.execute_publish**

- 功能：规则集发布的计划和执行。
- 输入/输出：同策略发布。

**tiance.ruleset.version_diff**

- 功能：比较规则集两个版本的语义差异，标明新增/修改/删除的规则和条件。
- 输入：ruleSetCode（规则集编码，必填）、versionA（版本A，必填）、versionB（版本B，可选，默认当前版本）。
- 输出：语义差异（新增规则列表、修改规则列表、删除规则列表、条件变更详情、风险等级变更）。

#### 平台适配层实现方案

**复用现有能力**

- 规则集查询复用bridgeApi的规则集查询接口，MCP层统一封装分页和响应格式。
- 规则集导入导出复用组件生命周期的check→confirm流程，MCP层封装为plan→execute两阶段模式。

**需要平台后端新增的能力**

- 规则集校验引擎扩展：当前校验仅覆盖JSON Schema层面，需要扩展到平台真实语义校验，包括：引用完整性校验（字段编码是否存在、函数签名是否匹配、指标编码是否有效）、字段类型匹配校验（条件表达式中的字段类型与比较值类型是否一致）、函数签名匹配校验（函数入参数量和类型是否与调用处一致）、规则优先级冲突检测（同一规则集内是否存在互斥条件或覆盖关系）、风险等级一致性校验（相同条件在不同规则集中的风险等级是否一致）。
- 规则集版本对比接口：当前平台不提供版本差异API，需要后端新增接口，提供语义级别的版本差异（新增/修改/删除的规则、条件变更、风险等级变更），而非文本差异。
- 规则集批量更新接口：当前更新操作逐条执行，部分更新成功部分失败时缺乏回滚机制，需要后端支持批量更新的原子性（全部成功或全部回滚）。

**适配层新增的逻辑**

- 引用解析前置校验：在提交计划前，先通过tiance.resolve_references解析草稿中引用的所有对象，确保引用存在性和唯一性，引用解析失败直接返回错误，不进入计划阶段。
- 冲突检测前置分析：在提交计划前，通过规则集校验引擎执行冲突检测，识别规则间互斥条件和覆盖关系，冲突检测结果作为警告返回给用户确认。

**改造工作量评估**

- 规则集查询/详情：复用现有接口，MCP层封装工作量小（约2人天）。
- 规则集校验：需要后端扩展校验引擎，MCP层适配工作量中等（约5-7人天）。
- 规则集创建/更新：复用组件生命周期流程，增加批量更新原子性处理工作量中等（约3-5人天）。
- 规则集发布：复用组件生命周期流程，工作量小（约2人天）。
- 规则集版本对比：需要后端新增接口，MCP层适配工作量中等（约5人天）。

### 3.6 决策流管理能力

#### 现有平台交互流程

决策流管理涉及决策流的设计、配置、测试、验证、发布和上线。当前AI Agent与决策流管理的交互主要通过以下方式：

- **决策流发现**：通过tiance-metadata-scout的G类端点（策略分页+策略字典）获取决策流列表和详情，输出policy_list.json和policy_dict.json。
- **决策流配置**：通过tiance-policy-forge从本地JSON文件（function_definitions.json、ruleset_definitions.json、deal_types.json、policy_dict.json）解析引用，生成.pls决策流文件，校验节点类型白名单（per businessType）和引用存在性。
- **决策流导入**：通过tiance-component-lifecycle执行check→confirm两步导入。
- **决策流上线**：通过tiance-model-strategy执行上线验证和上线操作。

#### 当前流程痛点

- 决策流包含20+种节点类型（开始、结束、规则集、函数、子策略、条件分支、并行分支、汇聚、模型调用、接口服务、ETL、名单查询、指标计算、赋值、日志、人工审核、外部决策、定时器、循环、消息通知），每种节点的属性和连接规则不同，Skill中需要维护大量节点规格知识。
- 决策流的节点连接规则复杂（哪些节点可以串联、哪些可以分支、分支条件的语法、并行分支的汇聚约束），缺乏平台级的连接合法性校验。
- 决策流的businessType（业务类型）限制了可用的节点类型白名单，当前白名单规则散落在Skill中，与平台实际规则可能存在偏差。
- 决策流中引用的子策略、规则集、函数、指标等对象，存在性校验依赖本地JSON文件。
- 决策流的子策略路由字段必须存在于上游节点的输出中，正确性难以预验证。
- 决策流的决策结果映射（规则集输出→最终决策等级）需要确保所有路径都有映射，当前缺乏完整性校验。

#### 工具接口设计

**tiance.flow.list**

- 功能：查询决策流列表，返回决策流编码、名称、版本号、节点数量、状态。
- 输入：orgCode（机构编码，必填）、businessType（业务类型过滤，可选）、status（状态过滤，可选）、page（页码，可选）、pageSize（每页大小，可选）。
- 输出：决策流列表（编码、名称、版本号、节点数量、状态）、总数、分页信息。

**tiance.flow.detail**

- 功能：获取决策流详情，包括所有节点的配置、连接关系、引用关系。
- 输入：flowCode（决策流编码，必填）或flowId（决策流ID，必填）。
- 输出：决策流完整详情（节点列表、节点属性、连接关系、引用关系、Sugiyama布局信息、版本号）。

**tiance.flow.node_schema**

- 功能：获取节点类型的配置Schema，包括必填属性、枚举约束、连接规则。支持20+种节点类型的Schema查询。
- 输入：nodeType（节点类型，必填）、businessType（业务类型，可选，用于过滤节点类型白名单）。
- 输出：节点Schema（属性列表、必填标记、枚举值、默认值、数据类型、连接规则、白名单约束）。

**tiance.flow.validate**

- 功能：校验决策流配置的合法性，包括节点类型白名单、连接合法性、引用完整性、子策略路由字段存在性、决策结果映射完整性、死路径检测。执行平台真实语义校验。
- 输入：flowDraft（决策流配置草稿，必填）。
- 输出：校验结果（通过/失败）、错误列表（fieldPath、errorCode、suggestion）、死路径检测结果、未覆盖场景警告、警告列表。

**tiance.flow.plan_create / tiance.flow.plan_update**

- 功能：计划阶段，生成决策流创建/更新计划，返回影响范围、语义差异和风险评估。
- 输入：flowDraft（决策流配置草稿，必填）、idempotencyKey（幂等键，可选）。
- 输出：planId、影响范围（引用的子策略、规则集、函数、指标、数据源）、语义差异（与当前版本的差异）、风险评估（高/中/低）。

**tiance.flow.execute_create / tiance.flow.execute_update**

- 功能：执行阶段，经用户确认后创建/更新决策流。执行前重新校验权限和版本。
- 输入：planId（计划ID，必填）。
- 输出：操作状态（成功/失败/执行中）、操作进度、成功/失败明细、失败原因和恢复建议。

**tiance.flow.plan_publish / tiance.flow.execute_publish**

- 功能：决策流发布的计划和执行。
- 输入/输出：同策略发布。

**tiance.flow.plan_online / tiance.flow.plan_offline**

- 功能：决策流上线/下线的计划和执行。
- 输入/输出：同策略上线/下线。

**tiance.flow.version_diff**

- 功能：比较决策流两个版本的语义差异，标明新增/修改/删除的节点和连接。
- 输入：flowCode（决策流编码，必填）、versionA（版本A，必填）、versionB（版本B，可选，默认当前版本）。
- 输出：语义差异（新增节点列表、修改节点列表、删除节点列表、连接变更、引用变更）。

#### 平台适配层实现方案

**复用现有能力**

- 决策流查询复用bridgeApi/noahApi的策略查询接口（决策流在天策平台中作为策略的一种实现）。
- 决策流导入导出复用组件生命周期的check→confirm流程，MCP层封装为plan→execute两阶段模式。

**需要平台后端新增的能力**

- 决策流校验引擎：当前平台不提供决策流级别的校验API，需要后端新增校验引擎，支持：节点类型白名单校验（per businessType）、连接合法性校验（节点间连接规则、分支条件语法、并行分支汇聚约束）、引用完整性校验（子策略、规则集、函数、指标是否存在）、子策略路由字段存在性校验（路由字段是否存在于上游节点输出中）、决策结果映射完整性校验（所有路径是否都有决策结果映射）、死路径检测（是否存在不可达的节点或分支）。
- 节点Schema查询接口：提供20+种节点类型的配置Schema查询，支持按businessType过滤节点类型白名单。
- 决策流版本对比接口：提供语义级别的版本差异API（节点变更、连接变更、引用变更），而非文本差异。

**适配层新增的逻辑**

- 节点类型白名单维护：在MCP层维护节点类型白名单的缓存，定期与平台同步，确保Skill生成的决策流配置符合平台实际规则。
- 布局信息处理：决策流文件包含Sugiyama自动布局信息，MCP层在导入时需要保留或重新计算布局信息，确保决策流在平台UI中的可视化效果。

**改造工作量评估**

- 决策流查询/详情：复用现有接口，MCP层封装工作量小（约2-3人天）。
- 决策流校验引擎：需要后端新增校验引擎，工作量较大（约10-12人天）。
- 节点Schema查询：需要后端新增接口，工作量中等（约5人天）。
- 决策流创建/更新：复用组件生命周期流程，工作量小（约2-3人天）。
- 决策流版本对比：需要后端新增接口，工作量中等（约5-7人天）。

## 4. 工具使用规范

### 4.1 标准化调用链路

AI Agent通过MCP协议与天策平台交互，遵循以下标准化调用链路：

```
AI Agent
  ↓ MCP协议
MCP Server（平台适配层）
  ├─ 身份认证层（OAuth 2.1 Bearer Token → ActorContext）
  ├─ 权限校验层（capability声明与检查）
  ├─ 业务逻辑层（工具实现）
  ├─ 审计日志层（操作记录与脱敏）
  └─ 平台适配层（API封装与协议转换）
        ↓ 内部API
天策平台后端
```

**标准查询链路**

```
Agent发起查询请求
→ MCP身份认证（Token → ActorContext）
→ 权限校验（capability检查）
→ 平台API调用（封装分页、响应格式）
→ 领域化结果转换
→ 审计记录
→ 返回标准结构
```

**标准写操作链路（两阶段模式）**

```
Agent生成配置草稿
→ MCP: resolve_references（解析引用）
→ MCP: validate_draft（平台校验）
→ MCP: plan_component_change（生成变更计划）
→ 返回影响范围、差异、风险和planId
→ 用户或策略确认
→ MCP: execute_component_change(planId)
→ 执行前重新校验权限和版本
→ MCP: get_operation（查询执行状态）
→ 审计记录
→ 返回操作结果
```

**策略测试标准链路**

```
获取策略版本（MCP search_entities）
→ 提交测试用例（MCP submit_policy_test）
→ 获取执行结果（MCP get_test_result）
→ 获取执行轨迹（MCP get_execution_trace）
→ 比较框架判定（调用方本地）
→ 质量检查（调用方本地）
→ 审计记录（MCP 自动）
```

### 4.2 参数处理规则

**通用规则**

- 所有工具参数须来自用户输入或上游工具的标准返回值，不得硬编码平台内部ID。
- 引用类型的参数（字段名、函数名、规则名等）须先通过`tiance.resolve_references`解析为唯一实体ID，不得直接使用名称字符串。
- 身份相关的参数（机构编码、应用编码、环境标识）须从ActorContext中注入，工具参数不得覆盖身份上下文中的值。
- 批量操作的参数须包含每条记录的独立标识（caseId、componentId），以便返回每条记录的处理结果。
- 幂等键（idempotencyKey）须由调用方生成，格式为：`{operationType}_{objectType}_{objectCode}_{timestamp}`，重试时须使用相同的幂等键。

**分页参数**

- 所有查询工具须支持统一的分页参数：page（页码，从1开始）、pageSize（每页大小，默认20，最大100）。
- 返回结果须包含分页信息：totalCount（总数）、totalPages（总页数）、currentPage（当前页码）。

**错误处理参数**

- 校验类工具须支持`strictMode`参数（布尔值，默认true）：strictMode=true时，警告级别的问题也作为错误返回；strictMode=false时，仅错误级别的问题作为错误返回，警告级别的问题在warnings列表中返回。
- 所有写操作工具须支持`dryRun`参数（布尔值，默认false）：dryRun=true时，仅执行校验和计划阶段，不实际执行变更，返回校验结果和变更计划。

### 4.3 交互与返回规范

**统一返回结构**

所有MCP工具的返回值须遵循以下标准结构：

成功返回：

```json
{
  "success": true,
  "data": {},
  "traceId": "链路追踪标识",
  "environment": "环境标识",
  "metadataVersion": "元数据版本",
  "warnings": [],
  "nextActions": []
}
```

错误返回：

```json
{
  "success": false,
  "errorCode": "错误代码",
  "message": "人类可读描述",
  "fieldPath": "错误定位路径（校验类错误时）",
  "candidates": [],
  "retryable": false,
  "traceId": "链路追踪标识",
  "environment": "环境标识",
  "metadataVersion": "元数据版本",
  "nextActions": []
}
```

**标准错误码**

| 错误码 | 说明 | 是否可重试 |
|--------|------|-----------|
| AMBIGUOUS_REFERENCE | 解析结果不唯一 | 否 |
| NOT_FOUND | 实体不存在 | 否 |
| PERMISSION_DENIED | 权限不足 | 否 |
| MISSING_REQUIRED_FIELD | 必填字段缺失 | 否 |
| INVALID_TYPE | 数据类型不匹配 | 否 |
| INVALID_ENUM | 枚举值不合法 | 否 |
| REFERENCE_NOT_FOUND | 引用对象不存在 | 否 |
| VERSION_CONFLICT | 版本冲突 | 是 |
| VERSION_EXPIRED | 策略版本过期 | 是 |
| SESSION_INVALID | 身份上下文失效 | 是 |
| RESOURCE_LIMIT | 资源限制 | 是 |
| OPERATION_BLOCKED | 引用阻塞 | 否 |
| INTERNAL_ERROR | 平台内部错误 | 是 |

**返回规范**

- `message`字段须使用中文描述，说明具体发生了什么，涉及哪个对象。
- `candidates`字段须在AMBIGUOUS_REFERENCE错误时返回至少3个候选项，每个候选项包含id、name、ownerOrg。
- `fieldPath`字段须使用JSONPath格式（如`$.conditions[0].field`），精确定位到出错的字段。
- `nextActions`字段须返回1-3条具体可执行的操作建议（如"请重新获取策略版本"、"请联系管理员分配权限"）。
- 策略测试结果须包含结构化字段：用例标识、uuid、token、通过/未通过状态、决策等级、子策略执行状态列表、命中规则列表（名称/编号/风险等级/规则集）、函数输出列表（函数名/入参/出参）。

### 4.4 认证与安全机制

**身份认证**

- MCP工具层使用OAuth 2.1 Bearer Token进行认证，Agent须通过认证流程获取Token后调用工具。
- Token有效期由平台配置，过期后须重新获取，MCP层自动处理Token刷新。
- MCP会话与浏览器会话完全分离，不共用tokenMD5，避免互相踢出登录状态。

**权限控制**

- 每个工具声明所需的capability，认证层在执行前进行权限校验。
- capability列表：`tiance.metadata.read`、`tiance.component.import`、`tiance.component.publish`、`tiance.component.invoke`、`tiance.policy.test`、`tiance.policy.test.read`。
- 身份上下文缺失时须拒绝请求，不得回退为系统账号。
- 工具参数不得覆盖身份上下文中的机构、应用和环境范围。

**审计**

- 每次工具调用须记录完整审计信息：操作者（userId/orgCode）、时间（timestamp）、工具名称（toolName）、环境（environment）、输入摘要（脱敏）、操作类型（查询/计划/执行）、权限决策、执行结果、traceId、planId、幂等键。
- 审计日志不得记录Token、密码、密钥和敏感业务数据。
- 策略测试操作须额外记录：测试的策略版本号、提交的用例数量、通过率和失败率汇总。
- 支持按策略编码、版本号、时间范围查询历史操作记录。

**安全约束**

- Token、密钥和敏感配置不得出现在工具返回值、错误信息和审计日志中。
- 写操作须采用plan→execute两阶段模式，执行前须人类确认。
- 支持幂等键，防止重试导致重复操作。
- 使用乐观锁，防止并发修改覆盖他人变更。
- 策略测试提交须限制并发数，避免对平台造成压力。
- 第一期仅支持测试环境，生产环境的发布、下线、删除操作放到后续阶段。

## 5. 能力适配映射

### 5.1 能力适配映射表

以下映射表展示了天策MCP平台如何将Agent的高层意图映射到底层平台操作：

**身份认证与权限**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 认证身份 | OAuth 2.1 Bearer Token | bifrost身份校验 → ActorContext |
| 权限校验 | capability检查 | bifrost权限查询 |

**元数据查询**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 搜索实体 | tiance.search_entities | bridgeApi各端点统一封装 |
| 解析引用 | tiance.resolve_entities | 多端点联合查询+歧义处理 |
| 获取详情 | tiance.get_entity | 对应端点详情查询 |
| 获取Schema | tiance.get_schema | 模板/约束查询 |
| 查询依赖 | tiance.get_dependencies | 引用关系查询 |
| 导出快照 | tiance.export_metadata_snapshot | 批量查询+版本标记 |

**配置校验**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 解析引用 | tiance.resolve_references | 多端点联合查询+引用验证 |
| 校验草稿 | tiance.validate_draft | 平台语义校验引擎 |
| 规范化草稿 | tiance.normalize_draft | 标准payload转换 |
| 语义差异 | tiance.diff_component | 版本对比API |
| 依赖检查 | tiance.check_dependencies | 引用关系+阻塞规则查询 |

**组件生命周期**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询组件 | tiance.list_components | bridgeApi组件列表查询 |
| 获取组件详情 | tiance.get_component | bridgeApi组件详情查询 |
| 导出组件 | tiance.export_component | noahApi组件导出 |
| 计划变更 | tiance.plan_component_change | noahApi导入check+影响分析 |
| 执行变更 | tiance.execute_component_change | noahApi导入confirm |
| 查询操作状态 | tiance.get_operation | 操作状态轮询 |

**策略管理**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询策略列表 | tiance.policy.list | noahApi/policy/list（实时查询） |
| 获取策略详情 | tiance.policy.detail | noahApi/policy/detail |
| 获取测试Schema | tiance.policy.test_config | 策略测试参数Schema查询 |
| 版本差异比对 | tiance.policy.version_diff | 平台版本对比API（新增） |
| 提交测试 | tiance.policy.submit_test | noahApi/lab/policytest/create |
| 获取测试结果 | tiance.policy.get_test_result | noahApi测试结果查询 |
| 获取执行轨迹 | tiance.policy.get_execution_trace | getAllCompontlog（分级封装） |
| 发布计划 | tiance.policy.plan_publish | 组件发布check |
| 执行发布 | tiance.policy.execute_publish | 组件发布confirm |
| 上线/下线 | tiance.policy.plan_online/offline | 组件上下线操作 |

**规则管理**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询规则集 | tiance.rule.list | bridgeApi规则集列表 |
| 获取规则详情 | tiance.rule.detail | bridgeApi规则详情 |
| 校验规则 | tiance.rule.validate | 校验引擎扩展 |
| 创建/更新计划 | tiance.rule.plan_create/update | 组件导入check |
| 执行创建/更新 | tiance.rule.execute_create/update | 组件导入confirm |
| 发布规则 | tiance.rule.plan_publish/execute_publish | 组件发布操作 |
| 版本差异 | tiance.rule.version_diff | 版本对比API（新增） |

**指标管理**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询指标 | tiance.metric.list | indexApi指标列表 |
| 获取指标详情 | tiance.metric.detail | indexApi指标详情 |
| 获取模板Schema | tiance.metric.schema | 指标模板Schema查询 |
| 校验指标 | tiance.metric.validate | 校验引擎扩展+SHA-256去重 |
| 创建/更新计划 | tiance.metric.plan_create/update | 组件导入check+编码分配 |
| 执行创建/更新 | tiance.metric.execute_create/update | 组件导入confirm |
| 发布指标 | tiance.metric.plan_publish/execute_publish | 组件发布操作 |
| 重复检查 | tiance.metric.check_duplicate | SHA-256指纹比对（新增） |
| 引用检查 | tiance.metric.check_references | 引用关系查询（新增） |

**AI技能管理**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询技能 | tiance.skill.list | 技能管理API（新增） |
| 获取技能详情 | tiance.skill.detail | 技能详情API（新增） |
| 校验技能 | tiance.skill.validate | 技能校验引擎（新增） |
| 发布计划 | tiance.skill.plan_publish | 技能发布check（新增） |
| 执行发布 | tiance.skill.execute_publish | 技能发布confirm（新增） |
| 绑定计划 | tiance.skill.plan_bind | Agent配置check（新增） |
| 执行绑定 | tiance.skill.execute_bind | Agent配置confirm（新增） |
| 查询Agent配置 | tiance.skill.agent_config | Agent配置查询 |
| 诊断技能 | tiance.skill.diagnose | 技能诊断API（新增） |

**规则集管理**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询规则集 | tiance.ruleset.list | bridgeApi规则集列表 |
| 获取规则集详情 | tiance.ruleset.detail | bridgeApi规则集详情 |
| 校验规则集 | tiance.ruleset.validate | 校验引擎扩展+冲突检测 |
| 创建/更新计划 | tiance.ruleset.plan_create/update | 组件导入check |
| 执行创建/更新 | tiance.ruleset.execute_create/update | 组件导入confirm |
| 发布规则集 | tiance.ruleset.plan_publish/execute_publish | 组件发布操作 |
| 版本差异 | tiance.ruleset.version_diff | 版本对比API（新增） |

**决策流管理**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询决策流 | tiance.flow.list | noahApi策略列表 |
| 获取决策流详情 | tiance.flow.detail | noahApi策略详情 |
| 获取节点Schema | tiance.flow.node_schema | 节点类型Schema查询（新增） |
| 校验决策流 | tiance.flow.validate | 决策流校验引擎（新增） |
| 创建/更新计划 | tiance.flow.plan_create/update | 组件导入check |
| 执行创建/更新 | tiance.flow.execute_create/update | 组件导入confirm |
| 发布决策流 | tiance.flow.plan_publish/execute_publish | 组件发布操作 |
| 上线/下线 | tiance.flow.plan_online/offline | 组件上下线操作 |
| 版本差异 | tiance.flow.version_diff | 版本对比API（新增） |

**执行与审计**

| Agent意图 | MCP工具 | 平台操作 |
|----------|---------|---------|
| 查询操作状态 | tiance.get_operation | 操作状态轮询/回调 |
| 查询审计日志 | tiance.get_audit_log | 审计日志查询（新增） |

### 5.2 现有Skills盘点清单

**完全可替代的Skills（3个）**

| Skill | 当前端点数 | MCP替代方案 | 迁移优先级 |
|-------|-----------|------------|-----------|
| tiance-metadata | 15端点 | 6个MCP工具完全替代 | 第一批 |
| tiance-metadata-scout | 42端点 | MCP工具按需调用完全替代 | 第一批 |
| tiance-component-lifecycle | ~12端点+编排 | plan→execute两阶段模式完全替代 | 第二批 |

**大部分可替代、Skill变薄的Skills（8个Forge类）**

| Skill | MCP替代部分 | Skill保留部分 | 迁移优先级 |
|-------|-----------|-------------|-----------|
| tiance-rule-forge | 引用解析+校验下沉 | Excel语义理解、模板评分、条件分类 | 第三批 |
| tiance-field-forge | 查重+导入下沉 | 字段命名约束、数据类型映射、编码规则 | 第三批 |
| tiance-datasource-forge | 导入+引用下沉 | Excel扫描、协议类型处理、SQL构造 | 第三批 |
| tiance-function-forge | 引用解析下沉 | DSL公式语法、α类型前缀、Java脚本模板 | 第三批 |
| tiance-etl-forge | 导入下沉 | 4种ETL类型Java模板、LLM代码生成 | 第三批 |
| tiance-policy-forge | 引用解析+校验下沉 | 20+节点类型属性规格、Sugiyama布局 | 第三批 |
| tiance-realtime-metric-forge | 引用解析下沉 | 模板分类决策树、Formula DSL/Groovy | 第三批 |
| tiance-service-config-forge | 引用解析下沉 | 6列CSV格式、ServiceFieldMapping命名 | 第三批 |

**部分可替代的Skills（3个）**

| Skill | MCP替代部分 | Skill保留部分 | 迁移优先级 |
|-------|-----------|-------------|-----------|
| tiance-policy-test | 提交/获取/日志大部分下沉 | 六层验证编排、比较框架、Excel报告 | 第四批 |
| tiance-model-strategy | 全链路平台交互下沉 | 26个陷阱/坑点、上线顺序编排、测试方法论 | 第四批 |
| tiance-agent-loop | 继承policy-test的MCP下沉 | 触发检测、收敛判断、反馈分类 | 第四批 |

**不可替代的Skills（6个）**

| Skill | 原因 |
|-------|------|
| tiance-testcase-generator | 纯本地处理（表达式识别、条件分解、场景组合） |
| tiance-report-checker | 纯本地处理（四维检查） |
| tiance-app-deploy | 操作服务器基础设施（SSH/JumpServer） |
| tiance-nginx-frontend | SSH配置Nginx反向代理和前端静态资源 |
| tiance-sql-init | SSH隧道执行MySQL建表脚本 |
| tiance-troubleshoot | 35+故障案例诊断，涉及SSH/MySQL/Nacos/Nginx |

**迁移实施顺序**

1. **第一批**：tiance-metadata、tiance-metadata-scout → MCP元数据工具层就绪后，逐步切换查询逻辑。
2. **第二批**：tiance-component-lifecycle → MCP计划/执行模式就绪后，切换导入导出流程。
3. **第三批**：8个Forge类Skill → MCP校验和引用解析就绪后，逐步切换引用解析和校验逻辑，保留核心业务智能。
4. **第四批**：tiance-policy-test、tiance-model-strategy、tiance-agent-loop → MCP策略测试能力就绪后，切换平台交互部分。

## 6. 架构决策记录

### ADR-001: 选择MCP协议作为Agent与平台的交互标准

**背景**：需要为AI Agent与天策平台之间建立标准化的交互协议。

**可选方案**：

- 方案A：自定义REST API
  - 优点：简单直接，与现有平台架构一致。
  - 缺点：每个Agent需要自行处理认证、解析、错误处理等重复逻辑，难以统一审计和权限控制。

- 方案B：MCP（Model Context Protocol）
  - 优点：提供标准化的工具发现和调用机制，天然支持Tool Schema（Agent可自主理解工具参数），统一审计和权限控制，符合行业趋势（Anthropic/微软等推动）。
  - 缺点：相对较新的标准，生态还在发展中，需要开发MCP Server端。

**决策**：采用方案B（MCP协议）。

**理由**：MCP协议为Agent与平台交互提供了标准化的工具发现、参数理解和调用管理机制。相比自定义REST API，MCP减少了Agent端的重复开发，提供了统一的审计和权限控制能力。天策平台的业务复杂度高（20+种组件类型、多层嵌套结构、多种分页协议），MCP的Tool Schema和领域化返回机制可以显著降低Agent的理解负担。

**后果**：需要开发MCP Server（包括协议框架、身份认证层、权限校验层、业务逻辑层、审计日志层、平台适配层），预计增加约4-6周开发工作量。但长期来看，MCP的标准化能力可以支撑更多Agent和更多平台的接入，降低整体集成成本。

### ADR-002: 身份认证采用OAuth 2.1 Bearer Token而非Cookie/CSRF

**背景**：天策平台当前使用Cookie + CSRF Token的认证方式，AI Agent需要与平台交互。

**可选方案**：

- 方案A：复用Cookie/CSRF认证
  - 优点：无需修改现有认证体系，开发工作量小。
  - 缺点：Cookie与浏览器会话绑定，Agent调用时需要从浏览器提取Cookie，CSRF机制对Agent无意义（Agent不是浏览器），会话共享导致互相踢出，安全性差（Cookie泄露风险），无法为不同Agent分配不同权限级别。

- 方案B：OAuth 2.1 Bearer Token
  - 优点：标准的API认证方式，支持与浏览器会话分离，可审计、可授权、可撤销，天然支持权限声明（通过scope/capability），支持Token刷新和过期管理。
  - 缺点：需要改造bifrost认证模块，开发工作量较大。

**决策**：采用方案B（OAuth 2.1 Bearer Token）。

**理由**：Cookie/CSRF认证方式是为浏览器用户设计的，不适合Agent调用场景。Agent需要独立的、可审计的、可授权的认证机制。OAuth 2.1 Bearer Token是API认证的行业标准，天然支持权限声明和Token生命周期管理，与MCP协议的capability机制契合度高。

**后果**：需要改造bifrost认证模块以支持OAuth 2.1 Token颁发和校验，预计增加约2-3周开发工作量。MCP会话与浏览器会话完全分离后，消除了互相踢出登录状态的问题，同时为Agent提供了独立的权限控制能力。

### ADR-003: 写操作采用plan→execute两阶段模式

**背景**：AI Agent需要对天策平台执行写操作（创建、更新、发布、上线、下线、删除）。

**可选方案**：

- 方案A：直接执行
  - 优点：流程简单，响应速度快。
  - 缺点：风险高，Agent生成的配置可能有错误，直接执行可能导致不可逆的影响（如错误的策略发布到生产环境），用户无法在执行前预览变更影响。

- 方案B：plan→execute两阶段模式
  - 优点：计划阶段返回影响范围、语义差异和风险评估，用户可以确认后再执行；执行前重新校验权限和版本，防止并发冲突；支持幂等键防止重复操作。
  - 缺点：流程多一步确认，UX上需要用户额外操作；增加planId管理复杂度。

**决策**：采用方案B（plan→execute两阶段模式）。

**理由**：天策平台的配置操作影响范围大（一个策略配置错误可能导致整个决策流异常），且写操作不可逆（发布后无法自动回滚）。两阶段模式通过计划阶段的预览和确认，显著降低了误操作风险。执行前的重新校验机制可以防止计划创建后发生的权限变更或组件被他人修改导致的并发冲突。用户的确认操作可以通过自动化策略逐步减少（如低风险操作自动批准）。

**后果**：所有写操作需要两次调用（plan + execute），增加约30%的调用量。但显著降低了误操作风险，并为审计提供了完整的变更记录（planId关联计划和执行）。

### ADR-004: 工具返回值采用领域化结构而非原始API响应

**背景**：天策平台底层API返回的是原始数据结构（如ChildFlowNode.extension.tokenIds、RuleSetServiceNode.extension.executeDetail.hitRules），AI Agent需要理解这些结构才能处理结果。

**可选方案**：

- 方案A：返回原始API响应
  - 优点：实现简单，无需MCP层做数据转换。
  - 缺点：Agent需要理解大量平台内部数据结构，不同API的响应格式不一致，Agent端需要大量适配代码，平台内部变更会直接破坏Agent逻辑。

- 方案B：返回领域化结构
  - 优点：Agent无需理解平台内部实现，返回值语义清晰（如"规则命中详情"而非"hitRules"），不同工具的返回值格式统一，平台内部变更不影响Agent。
  - 缺点：需要MCP层理解业务语义并做数据转换，开发工作量较大。

**决策**：采用方案B（返回领域化结构）。

**理由**：天策平台的内部数据结构复杂且不统一（不同API的嵌套层级不同、字段命名不一致、响应格式不一致），如果直接返回原始响应，Agent端需要维护大量适配代码，且平台内部变更会直接破坏Agent逻辑。领域化返回使Agent专注于业务逻辑（如"哪些规则命中了"、"函数的输出是什么"），而非平台实现细节（如"如何从extension对象中提取hitRules"）。

**后果**：MCP层需要开发数据转换逻辑，预计增加约2-3周开发工作量。但显著降低了Agent端的复杂度和维护成本，并使MCP层成为平台变更的缓冲层——平台内部重构时只需修改MCP层的转换逻辑，不影响Agent。

### ADR-005: 现有Skill采用渐进迁移而非强制切换

**背景**：天策平台现有20个tiance-* Skill在多个项目中运行，需要迁移到使用MCP工具。

**可选方案**：

- 方案A：强制一次性切换
  - 优点：切换干净，不需要维护两套系统。
  - 缺点：风险高，现有Skill在多个项目中运行，一次性切换可能导致功能中断，回滚困难。

- 方案B：渐进迁移
  - 优点：逐步验证每个能力的等价性，风险可控，可随时回滚到旧Skill，不影响现有项目运行。
  - 缺点：过渡期需要维护两套系统（Skill + MCP），增加维护成本。

**决策**：采用方案B（渐进迁移）。

**理由**：现有Skill在生产项目中运行，贸然切换可能导致策略测试、组件导入等关键操作失败。渐进迁移允许逐个能力验证功能等价性，确保MCP工具与Skill的行为一致后再废弃旧Skill。迁移顺序按依赖关系排列：先迁移元数据查询（无副作用），再迁移组件操作（有副作用），最后迁移策略测试（业务逻辑最复杂）。

**后果**：过渡期约3-6个月，期间需要维护Skill和MCP两套系统。但确保了迁移过程的平稳性，不影响现有项目的正常运行。

### ADR-006: 第一期仅支持测试环境，生产操作分阶段开放

**背景**：MCP工具需要支持测试环境和生产环境的操作。

**可选方案**：

- 方案A：同时支持测试和生产环境
  - 优点：一次开发完成所有环境支持。
  - 缺点：风险高，生产环境的误操作不可逆，需要更严格的权限控制和审批流程。

- 方案B：第一期仅支持测试环境
  - 优点：风险可控，可以在测试环境充分验证MCP工具的正确性，为生产环境积累经验，可以分阶段完善生产环境的权限控制和审批流程。
  - 缺点：生产环境的操作仍需要手动执行，MCP的价值在第一期未完全体现。

**决策**：采用方案B（第一期仅支持测试环境）。

**理由**：生产环境的配置操作影响范围大且不可逆（错误的策略发布可能导致线上决策异常），需要在测试环境充分验证MCP工具的正确性和稳定性后再开放生产操作。第一期聚焦于测试环境的策略测试、组件导入、元数据查询等能力，为后续生产环境开放积累经验和信心。

**后果**：第一期的MCP工具仅支持测试环境，生产环境的发布、上线、下线、删除操作放到后续阶段。后续阶段需要增加生产环境的权限控制（更高权限等级、更严格审批流程、环境隔离策略）。
