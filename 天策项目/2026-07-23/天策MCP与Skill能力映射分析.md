## 天策 MCP 与现有 Skill 能力映射分析

基于本地 20 个 tiance-* skill 的逐条代码分析，对照 Tiance MCP 需求文档，梳理每个 skill 中可被 MCP 替代的具体能力点。

---

### 一、完全可被 MCP 替代的 Skill

#### 1. tiance-metadata（15 个端点 → MCP 元数据工具）

当前实现：通过浏览器执行同步 XHR，逐条调用 15 个 REST 端点，手动管理 `sessionStorage._csrf_` 和 `X-Cf-Random`，输出 10 个 JSON 文件。

可下沉到 MCP 的部分（几乎全部）：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| `/bridgeApi/app/all` 获取渠道/应用 | `tiance.search_entities(type="channel_app")` |
| `/bridgeApi/systemField/allField` 获取系统字段 | `tiance.search_entities(type="field")` |
| `/bridgeApi/org/all` 获取机构树 | `tiance.search_entities(type="organization")` |
| `/noahApi/common/dealtype/select` 获取处置类型 | `tiance.search_entities(type="deal_type")` |
| `/bridgeApi/dictionary/list` 获取事件类型/风险类型字典 | `tiance.search_entities(type="dictionary", key="事件类型")` |
| `/tradeApi/allMap` 获取综合映射表 | `tiance.get_schema(type="trade_mapping")` |
| `/noahApi/admin/template/all` 获取规则/指标模板 | `tiance.search_entities(type="rule_template")` |
| `/indexApi/metricManagement/list` 分页拉取指标配置 | `tiance.search_entities(type="metric", area="RUNNING")` |
| roster 系列端点（分组→名单→数据三级嵌套拉取） | `tiance.search_entities(type="roster")` + `tiance.get_entity()` |
| CSRF token 提取和注入 | MCP 身份层完全接管，不再需要 |
| `window.__d` 全局累积和 HTTP 回传 | MCP 直接返回结构化 JSON，不再需要 |
| 手动模式 data_receiver_server.py | MCP 连接后完全废弃 |

Skill 保留部分：无。此 skill 可完全废弃，MCP 的 `export_metadata_snapshot` 可一次返回等价于当前 10 个 JSON 文件的完整快照。

#### 2. tiance-metadata-scout（42 个端点 → MCP 元数据工具）

当前实现：tiance-metadata 的增强版，42 个端点分 13 类（A-M），支持 4 种连接模式（Gateway Proxy > 原生浏览器 > Puppeteer > 手动），输出 25+ JSON 文件。

可下沉到 MCP 的部分（几乎全部）：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 类别 F：规则集分页 + 规则详情逐条拉取 | `tiance.search_entities(type="ruleset")` + `tiance.get_entity(type="rule", id=...)` |
| 类别 G：策略分页 + 策略字典 | `tiance.search_entities(type="policy")` + `tiance.get_schema(type="policy_dict")` |
| 类别 H：决策工具/函数/自定义函数 | `tiance.search_entities(type="function")` + `tiance.get_entity(type="decision_tool")` |
| 类别 I：接口服务配置 | `tiance.search_entities(type="service_config")` |
| 类别 K：三方数据（ETL/数据源/合作方/合同嵌套拉取） | `tiance.search_entities(type="etl_handler")` + `tiance.get_dependencies(type="service_provider")` |
| 类别 L：预警信号四层嵌套（业务分类→分组→子分组→信号） | `tiance.search_entities(type="alarm_signal")` + `tiance.get_schema(type="biz_category")` |
| 类别 M：Captain 外数（报文类型→模板→指标→指标包，分页协议各不相同） | `tiance.search_entities(type="captain_index")` |
| Gateway Proxy 模式 / `tiance_proxy.py` | MCP 的 OAuth 2.1 Bearer Token 替代 |
| 双嵌套响应格式 `response["data"]["data"]` | MCP 直接返回业务层数据 |
| `X-Td-Signature` 请求签名（uniteApi） | MCP 服务端内部处理 |
| 版本自检 / skill-sync 比对 | 不再需要（MCP 端维护版本） |

Skill 保留部分：极少。选择哪些类别的元数据属于"编排决策"，可由上层 skill 或 agent 直接通过 MCP 参数指定。类别间依赖警告（如 B 类单独拉取时枚举值不完整）可编码为 MCP 的 `warnings` 返回。

#### 3. tiance-component-lifecycle（组件全生命周期 → MCP 计划/执行模式）

当前实现：调度所有组件类型的导入（check→confirm 两步）、发布、上线、下线、删除，处理强/弱引用阻塞规则，编排跨组件批量导入顺序。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 导入 CHECK：`/noahApi/component/import/check/{CATEGORY}` | `tiance.plan_component_change(action="import", category=...)` |
| 导入 CONFIRM：`/noahApi/component/import/confirm/{CATEGORY}` | `tiance.execute_component_change(planId)` |
| 引用检查：`/bridgeApi/bifrost/checkComponentReference` | `tiance.check_dependencies(componentId)` |
| 字段/数据源/ETL 文件上传 | `tiance.execute_component_change(planId)` 内含文件处理 |
| 基础配置 CRUD（机构/处置类型/字典/应用） | `tiance.plan_component_change(action="save", category="basic_config")` |
| 强/弱引用阻塞规则（POLICY=always block, RULE_SET=STRONG blocks/WEAK allows...） | MCP 在 `plan_component_change` 返回中编码阻塞策略 |
| 跨组件批量导入顺序（basic-config→fields→datasource→functions→indices→rulesets→policies） | MCP `plan_component_change` 接受批量组件，自动排序返回执行计划 |
| payload 编码（JSON→gzip→base64） | MCP 内部处理 |
| 文件上传 CORS HTTP server（端口 18765） | MCP 直接接收文件上传 |

Skill 保留部分：仅流程编排说明（向用户解释每个阶段在做什么）和人类确认交互。Skill 变为 MCP 的薄编排层。

---

### 二、大部分可下沉、Skill 变薄的类别

#### 4. 各类 Forge Skill（配置生成类，共 8 个）

##### tiance-rule-forge

当前从本地 JSON 文件读取元数据（13 个文件），通过规则模板多维评分选择模板，分类条件（直接/指标/模板/函数），生成 .rss 文件。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 从 `field_metadata.json` 解析字段编码 | `tiance.resolve_entities(type="field", names=[...])` |
| 从 `rule_templates.json` 匹配模板 | `tiance.get_schema(type="rule_template", filter=...)` |
| 从 `function_definitions.json` 查找函数 UUID | `tiance.resolve_entities(type="function", names=[...])` |
| 从 `metric_definitions.json` 查找指标编码 | `tiance.resolve_entities(type="metric", names=[...])` |
| 从 `roster_definitions.json` 查找名单 | `tiance.resolve_entities(type="roster", names=[...])` |
| 校验引用对象是否存在 | `tiance.validate_draft(draft)` |
| 3 层校验（文件/结构/语义） | `tiance.validate_draft()` 返回结构化错误 |

Skill 保留部分：Excel 语义理解、规则模板多维评分选择（30+ 模板类型的子 skill 架构）、条件分类逻辑、metric_request 协调。这些是核心业务智能，必须留在 Skill。

##### tiance-field-forge

将外部参数定义转换为天策系统字段 .xls 文件。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 与平台已有字段查重（displayName/name 四重冲突检测） | `tiance.resolve_entities(type="field", names=[...])` + `tiance.validate_draft()` |
| 从 `field_groups.json` 查找字段分组 UUID | `tiance.search_entities(type="field_group")` |
| 字段导入 .xls 到平台 | `tiance.plan_component_change(action="import", category="FIELD_SYSTEM")` |
| 导入后刷新元数据 | MCP 自动维护（导入返回更新后的实体） |

Skill 保留部分：字段命名约束（displayName 1-50 字符、suffixName 不能含下划线）、数据类型映射（7 种平台类型）、函数类型分配（VB/VD/VP/VS/VO）、`C_{typeCode}_{SUFFIXNAME}` 编码规则。

##### tiance-datasource-forge

从 Excel 生成 .ds 数据源接口文件，含 DES 加密和 tar 打包。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| ETL 导入：`POST /bridgeApi/etlHandler/import` | `tiance.execute_component_change(planId)` |
| DS 导入：`POST /bridgeApi/serviceConfig/import` | `tiance.execute_component_change(planId)` |
| 从 `raw/all_field.json` 做字段映射 | `tiance.resolve_entities(type="field", ...)` |
| 从 `raw/etl_handlers.json` 匹配 ETL | `tiance.resolve_entities(type="etl_handler", ...)` |
| DES/CBC 加密 | 可由 MCP 内部处理（或 Skill 保留，视安全策略） |

Skill 保留部分：Excel 优先扫描+按需追问模式、9 种协议类型处理、SQL 自动构造、sendSpace/keyInclude 推理规则、ETL 内联生成协调。

##### tiance-function-forge

生成 .fun 函数导入文件（公式型 DSL 或脚本型 Java）。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 从 `field_groups.json` 查找 groupUuid | `tiance.resolve_entities(type="field_group", names=[...])` |
| 从 `channel_apps.json` 查找 appCode | `tiance.resolve_entities(type="channel_app", names=[...])` |
| 从 `function_definitions.json` 做平台去重预检 | `tiance.validate_draft()` 含去重检查 |
| 导入后刷新函数库 | MCP 导入后自动返回最新实体 |

Skill 保留部分：DSL 公式语法（`&&`/`||`、`#then`、分号规则）、α 类型前缀系统、Java 脚本模板、编码规则、round-trip 验证。

##### tiance-etl-forge

生成 .etl ETL 处理器文件，含 LLM 生成 Java 代码和 DES 加密。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| ETL 导入到平台 | `tiance.plan_component_change(action="import", category="ETL_HANDLER")` |
| 导入后刷新 etl_handlers.json | MCP 自动维护 |

Skill 保留部分：4 种 ETL 类型的 Java 模板、LLM 代码生成、分页 ETL 运行时模型、Groovy 编译兼容处理、嵌入模式合约。

##### tiance-policy-forge

生成 .pls 策略/决策流导入文件。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 从 `function_definitions.json` 解析函数 UUID | `tiance.resolve_entities(type="function", names=[...])` |
| 从 `ruleset_definitions.json` 解析规则集 UUID | `tiance.resolve_entities(type="ruleset", names=[...])` |
| 从 `deal_types.json` 查找处置类型编码 | `tiance.resolve_entities(type="deal_type", names=[...])` |
| 从 `policy_dict.json` 查找 businessType 映射 | `tiance.get_schema(type="policy_dict")` |
| 校验节点类型白名单（per businessType） | `tiance.validate_draft()` |
| 校验所有引用对象存在性 | `tiance.check_dependencies()` |

Skill 保留部分：20+ 节点类型的属性规格、中间 JSON 格式、Sugiyama 自动布局、`nodeType`/`lineType`/`sourceNodeId` 等关键 schema 规则。

##### tiance-realtime-metric-forge

调度指标生成的总入口，分发到 11 种模板子 skill。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 从 `field_metadata.json` 解析字段 | `tiance.resolve_entities(type="field", ...)` |
| 从 `channel_apps.json` 解析渠道 | `tiance.resolve_entities(type="channel_app", ...)` |
| 从 `metric_catalog.json` 解析指标目录 | `tiance.search_entities(type="metric_catalog")` |
| 指标去重（SHA-256 指纹） | `tiance.validate_draft()` 含去重 |
| 编码分配（10 位 hex） | MCP 可在 `plan_component_change` 时自动分配 |

Skill 保留部分：模板分类决策树（15 优先级）、sceneCondition/fieldCondition 规格、Formula DSL/Groovy 实现、Phase 1/Phase 2 两阶段处理。

##### tiance-service-config-forge

生成接口服务配置 CSV 文件。

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 从 `field_metadata.json` 做字段映射 | `tiance.resolve_entities(type="field", ...)` |
| 从 `serviceconfig_definitions.json` 查找服务类型 | `tiance.search_entities(type="service_config")` |
| 默认字段集合校验 | `tiance.validate_draft()` |

Skill 保留部分：6 列 CSV 格式、ServiceFieldMapping 命名规则、"备注"列解析。

---

### 三、部分可下沉的 Skill

#### 5. tiance-policy-test（策略测试）

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| 策略列表查询 `/noahApi/policy/list` | `tiance.search_entities(type="policy")` |
| 提交测试 `/noahApi/lab/policytest/create` | `tiance.invoke_component(type="policy", code=..., params=...)` |
| 运行数据查询（runData 多层：nodeType=8/1/5） | `tiance.get_invocation_result()` + `tiance.get_execution_logs()` |
| getAllCompontlog 获取完整组件日志 | `tiance.get_execution_logs(traceId, detailLevel="full")` |
| 报告基本信息查询 | `tiance.get_invocation_result(format="report")` |
| 浏览器 JS fetch + CSRF 管理 | MCP OAuth Token 替代 |
| Session 健康检查 | MCP 身份层自动处理 |

Skill 保留部分：六层验证体系的编排逻辑、alias_group/pass_through/fuzzy_alias 等比较框架、Excel 报告 15 列格式生成、策略配置文件的维护。

#### 6. tiance-model-strategy（模型策略全链路）

可下沉到 MCP 的部分：

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| PMML 模型上传和上下线 `/modelApi/...` | `tiance.plan_component_change(action="import", category="MODEL")` |
| 模型入参获取和测试调用 | `tiance.invoke_component(type="model", uuid=...)` |
| 策略导入 check/confirm | `tiance.plan_component_change()` + `tiance.execute_component_change()` |
| 指标发布、规则集发布、策略上线验证和上线 | `tiance.execute_component_change(planId)` 按依赖顺序 |
| 字典查询、模型参数映射 | `tiance.get_schema()` + `tiance.resolve_entities()` |
| 批量测试创建/轮询/结果获取 | `tiance.invoke_component(type="policy", mode="batch_test")` |

Skill 保留部分：26 个已知陷阱/坑点（这些应逐步编码为 MCP 的校验规则）、组件上线顺序编排、PMML 预处理（float→double）、三层测试方法论。

#### 7. tiance-testcase-generator（测试用例生成）

可下沉到 MCP 的部分：很少。此 skill 是纯本地处理，解析 Excel 生成测试用例 JSON。唯一可受益的是通过 MCP 获取策略和规则的完整配置来辅助生成。

| 当前逻辑 | 对应 MCP 工具 |
|----------|--------------|
| （无直接平台调用） | 可选：`tiance.get_entity(type="policy")` 获取完整策略配置辅助用例设计 |

Skill 保留部分：几乎全部。表达式模式识别、AND/OR 条件分解、三方数据 mock 描述生成、跨子策略场景组合、SAFE baseline 生成等均为核心业务逻辑。

#### 8. tiance-report-checker（报告质量检查）

纯本地 Excel 处理，无可下沉部分。完全保留。

#### 9. tiance-agent-loop（自动化闭环编排）

可下沉的部分继承自下游 skill（policy-test 部分），编排逻辑（触发检测、收敛判断、反馈分类）全部保留。

---

### 四、不可下沉的 Skill（基础设施部署类）

以下 4 个 skill 操作的是服务器基础设施（SSH/JumpServer），与天策平台 API 无关，MCP 不覆盖：

| Skill | 原因 |
|-------|------|
| tiance-app-deploy | 通过 SSH 部署 14+ Java 应用，操作 Nacos/JVM/启动脚本 |
| tiance-nginx-frontend | SSH 配置 Nginx 反向代理和前端静态资源 |
| tiance-sql-init | SSH 隧道执行 MySQL 建表脚本和数据完整性验证 |
| tiance-troubleshoot | 35+ 故障案例的诊断指南，涉及 SSH/MySQL/Nacos/Nginx 排查 |

---

### 五、汇总矩阵

| Skill | MCP 替代程度 | 当前端点数/代码行 | MCP 第一期可覆盖 |
|-------|-------------|------------------|-----------------|
| tiance-metadata | **完全替代** | 15 端点 | 是 |
| tiance-metadata-scout | **完全替代** | 42 端点 | 是（核心类别 A-E） |
| tiance-component-lifecycle | **大部分替代** | ~12 端点 + 编排 | 是 |
| tiance-rule-forge | 引用解析+校验下沉 | 0 直接端点 | 是（元数据+校验） |
| tiance-field-forge | 查重+导入下沉 | 通过 lifecycle | 是 |
| tiance-datasource-forge | 导入+引用下沉 | 2 端点 | 是 |
| tiance-function-forge | 引用解析下沉 | 0 直接端点 | 是 |
| tiance-etl-forge | 导入下沉 | 0 直接端点 | 是 |
| tiance-policy-forge | 引用解析+校验下沉 | 0 直接端点 | 是 |
| tiance-realtime-metric-forge | 引用解析下沉 | 0 直接端点 | 是 |
| tiance-service-config-forge | 引用解析下沉 | 0 直接端点 | 是 |
| tiance-policy-test | 调用+日志下沉 | ~6 端点 | 部分（测试环境） |
| tiance-model-strategy | 全链路下沉 | ~15 端点 | 部分 |
| tiance-testcase-generator | 极少 | 0 | 否 |
| tiance-report-checker | 无 | 0 | 否 |
| tiance-agent-loop | 继承下游 | 继承 | 部分 |
| tiance-app-deploy | 不适用 | SSH | 否 |
| tiance-nginx-frontend | 不适用 | SSH | 否 |
| tiance-sql-init | 不适用 | SSH+MySQL | 否 |
| tiance-troubleshoot | 不适用 | SSH 诊断 | 否 |

---

### 六、MCP 第一期落地建议

按需求文档的第一期范围，对应到具体 skill 改造：

**1. 身份层（bifrost 上下文 + capability）**

消除的 skill 复杂度：所有 skill 中的 CSRF 管理、Cookie 处理、`sessionStorage._csrf_` 提取、Gateway Proxy 双嵌套解析、手动模式 data_receiver_server.py、Puppeteer 登录点击。涉及 tiance-metadata、tiance-metadata-scout、tiance-component-lifecycle、tiance-policy-test、tiance-model-strategy 共 5 个 skill。

**2. 元数据查询（搜索、解析、详情、Schema、依赖）**

完全替代：tiance-metadata（15 端点 → 6 个 MCP 工具调用）和 tiance-metadata-scout（42 端点 → 按需 MCP 调用）。关键收益：消除 4 种连接模式的分支逻辑、消除各端点分页协议差异（curPage vs page vs currentPage）、消除 Captain API 的四层嵌套和分页差异。

**3. 配置校验（草稿校验 + 引用解析）**

所有 Forge skill 的 `resolve_entities` 调用统一走 MCP，不再需要本地维护 13 个 JSON 文件。`validate_draft` 可执行平台真实语义校验（而非 Skill 中手工维护的 JSON Schema）。第一期可先支持规则集、字段、函数、指标的校验。

**4. 组件操作（计划+执行模式的导入）**

tiance-component-lifecycle 的 check→confirm 两步直接映射为 plan→execute。批量导入顺序编排可下沉到 MCP 的 `plan_component_change` 批量模式。第一期先支持导入，发布/上线/下线放后续。

**5. 操作状态 + 幂等 + 审计**

消除 skill 中手动的轮询逻辑（如 tiance-model-strategy 的批量测试进度轮询）和重复提交风险。

---

### 七、改造后的 Skill 调用链

```
用户需求（Excel / 自然语言）
  │
  ▼
Forge Skill 理解需求 → 生成配置草稿
  │
  ▼
MCP: tiance.resolve_references(draft)    ← 替代本地 JSON 文件查找
  │
  ▼
MCP: tiance.validate_draft(draft)         ← 替代手工校验逻辑
  │
  ▼
MCP: tiance.plan_component_change(draft)  ← 替代 component-lifecycle check
  │
  ▼
用户确认
  │
  ▼
MCP: tiance.execute_component_change(planId)  ← 替代 component-lifecycle confirm
  │
  ▼
MCP: tiance.get_operation(planId)         ← 替代手动轮询
  │
  ▼
Forge Skill 验收结果、向用户说明
```

这个链路适用于所有 Forge skill（rule/field/datasource/function/etl/policy/metric/service-config），统一的 MCP 调用链消除了每个 skill 中重复的平台交互代码。
