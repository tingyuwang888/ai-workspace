---
name: tiance-policy-test
description: >
  天策(Tiance/Noah)决策平台策略测试执行。以通用规则测试设计、五态分类和证据分析为约束，
  复用API单笔/区间执行、隔离Fixture和UI备用提交。
  覆盖 策略发现 → 语义预检 → 隔离数据 → 单笔提交 → 结构化证据 → Excel报告 全流程。
  适用于天策平台上任意策略的回归测试和验证，通过策略配置文件支持新策略快速接入。
  当用户提到"策略测试"、"跑用例"、"天策测试"、"policytest"、"规则集测试"、
  "Noah测试"、"批量提交测试用例"时使用。
---

# 天策策略测试自动化（通用框架）

## 执行域路由

本 skill 内含两条互斥的执行链，先按被测接口选域，再进入治理合同：

| 执行域 | 适用对象 | 执行工具 | 五态判定 |
|---|---|---|---|
| 平台链 | 天策/Noah `/noah/policyTest`（需登录 session、平台快照、componentLog 证据） | `scripts/execute_tests.py` | `scripts/governance.py classify` |
| 收单链 | `acqAuthorization/acqDecline` 等收单风控 HTTP 直连接口（JSON 提交，响应含 `mingFields`） | `scripts/acquiring_runner.py`（checkpoint 合同 → 隔离命名空间登记 → 时间 rebase → 历史先于当前 → 窗口物化等待 → 指标证据与根因诊断） | `scripts/classify-execution-result.js` |

两链不得混用：`governance.py classify` 只认 Noah 平台证据封套（token/uuid/rawComponentLog），
对收单直连响应会一律判为阻塞；收单链的隔离登记与指标物化诊断也不适用于平台链。

## 治理入口与职责

根据本次意图选择步骤：执行请求连续完成适用门禁、提交、证据采集和报告；仅发现、
只读诊断、续查日志或报告展示修订不触发新的提交及 Fixture 写入。缺少登录或 DB
权限时先完成可做的本地预检，阻断受影响步骤并给出具体缺口，不要求用户手工代查
已有授权工具能够查询的内容。

可执行门禁和版本化清单见 [治理 CLI](references/governance-cli.md)。命令行提交必须
传 `--design-manifest`；`governance.py` 提供设计绑定、五态分类与重跑计划校验。

每次执行先读 [共享治理合同](references/risk-governance.md) 和
[通用执行规范](references/metric-execute.md)。本 skill 负责
天策平台能力；设计、五态业务结论、根因分析与完成门禁由治理层执行。
不套用通用套的 HLB 端点/枚举，也不把天策 policyTest 提交当成历史事件入库接口。

执行前必须具备 `design-manifest.json`、`design-review.json` 和门禁通过的
`testcases.governed.json`。旧 JSON 没有这些产物时先补设计复核，不直接提交。
参数预检后再次比较设计清单与实际 params；发现语义变化停止对应用例。
历史事件、当前笔计入、名单/标签和聚合维度按合同验证，不支持的数据能力记阻塞。

`executionOk/assertionStatus/evidenceStatus/pass` 保留为原生输出。权威结论另写
`governed-results.json`，使用 `通过/失败/执行阻塞/编排阻塞/无效用例`。平台链经
`governance.py classify`、收单链经 `governance.py aggregate-acquiring`（仅翻译
runner 归档，不重判）生成同构 `governed-results.json`。
`runStatus=2`、原生 passed 或报告无警告均不能替代治理门禁。
治理层检查目标规则集执行证据和该节点的目标规则；日志缺失不能当成规则未命中。

现有执行器归档 `plannedCase`（预检后的输入）、逐次 `submissionAttempts` 和原始
`rawComponentLog`。共享合同定义其证据边界及到通用分析模型的映射。
原始设计、历史事件和 Fixture 回查另行归档；不能事后从预期值反推实际请求。

默认使用新运行目录，修改既有结果/工作簿前备份。提交前和响应后原子保存，默认
`--max-retry 0`；超时不自动重试。`--resume --run-id` 校验 host、策略身份、runId
及包含 params/目标/断言/Fixture 合同的完整 case 摘要，已接收请求仅补查证据。
旧或损坏的 checkpoint 阻断恢复。外部 Fixture 状态变化必须使用新 runId。

## 概述

对天策决策平台的任意策略进行自动化测试的通用框架。两种提交方式：

- **Python API执行器**（推荐）：强制平台门禁、参数预检、断点续跑和证据比对
- **浏览器/API或UI交互**（仅备用）：用于直接认证不可用或诊断单条用例

```
会话检查 → 平台门禁 → 语义/mock预检 → Fixture → 单笔执行
→ 结构化证据比对 → 15列Excel报告 → Fixture清理
```

**平台地址**: `http://{HOST}/noah/policyTest` | **API前缀**: `/noahApi/` (form-encoded, 需session认证) | **DB**: MySQL `{DB_HOST}:3306`, 库`tiance`, 用户`tongdun`

## 前置条件

1. 用户已登录天策平台
2. 已取得有效 Cookie/CSRF；需要浏览器备用流程时加载浏览器控制技能
3. 策略配置文件存在于 `strategies/` 目录（或通过 `discover_strategy.py` 自动发现）
4. 环境地址与密码通过环境变量提供（config.json 使用 `$ENV:` 占位符）：`export TIANCE_PLATFORM_HOST=<天策平台地址>`、`export TIANCE_DB_HOST=<DB地址>`、`export TIANCE_DB_PASS=<密码>`；未设置时脚本会明确报错提示

## 核心流程

### Step 0: 会话健康检查（每次提交前必做）

执行器自动处理 CSRF 和 401。浏览器备用流程先运行
[api-reference.md](api-reference.md) 的会话健康检查；失败时停止，不提交用例。

### Step 1: 加载并校验策略配置（强制平台校验）

**这是通用化的关键步骤。** 所有策略特有信息均从配置文件加载，SKILL.md 不含任何策略特定内容。

> **⚠️ 强制校验规则：无论本地配置文件是否存在，每次测试前必须查询平台 API 核对 `policyVersion` 和 `businessType`。** 本地缓存可能过期（策略发布了新版本、业务类型配置变更），使用错误值会导致测试结果无效。

`scripts/execute_tests.py` 在提交前自动查询平台元数据，并严格比对：

| 字段 | 平台字段 | 本地字段 | 不一致时 |
|------|----------|----------|----------|
| 版本号 | `platformVersion` | `policyVersion` | 阻断，确认来源后显式更新配置 |
| 业务类型 | `businessType` | `bizType` | 阻断，确认来源后显式更新配置 |
| 策略名 | `policyName` / `name` | `policyName` | 采用本次平台名称提交，打印并归档差异；平台名称缺失则阻断 |

策略不存在、状态非已发布、版本或业务类型不一致时阻断提交。不要自动修改本地
配置；先确认差异来源，再显式更新配置并重新运行。

名称只是展示字段，不能覆盖编码/版本/业务类型的身份门禁。身份通过后，执行器必须
使用门禁返回的 `platform.policyName`，不得继续提交配置中的旧名称。每条新提交记录
保留 `policyName` 和 `policyNameResolution`（local/platform/submitted/source/changed）。
名称同步只作用于本次新请求，不自动改配置或历史结果，不因改名重跑已完成用例。
直接调用 Python 批量函数时传入本次 `platform_validation`，不能把历史快照当作本次校验。
浏览器备用模板的名称同样来自本次门禁结果，不能手填旧配置或按名称选择执行目标。

元数据接口不可用时，从已登录浏览器导出完整 API JSON 响应，再使用：

```json
{
  "capturedAt": "2026-07-29T12:00:00+08:00",
  "payload": {"success": true, "data": []}
}
```

```bash
python3 scripts/platform_guard.py \
  --config strategies/{policyCode}.json \
  --raw-payload browser_response.json \
  --output platform_snapshot.json
```

批量执行时追加 `--platform-snapshot platform_snapshot.json`。快照必须在十分钟内生成；
缺少时间、版本、业务类型或发布状态都会被阻断。

**配置文件不存在时**——执行完整自动发现：
```bash
python3 scripts/discover_strategy.py \
  --host {host} --cookie "{cookie}" --org-code {orgCode} --biz-type {bizType} \
  --output strategies/{policyCode}.json \
  discover --policy-code {policyCode}
```
然后执行平台门禁。

自动发现后必须补充 `routingFields`、`subStrategies`、`comparisonRules`、
`params.strategySpecific` 和数据源执行约束。

**配置文件关键字段**：

| 字段 | 用途 |
|------|------|
| `policyCode`/`policyName`/`policyVersion`/`bizType` | 提交API必需的策略标识（**必须从平台校验获取**） |
| `params.common` | 通用公共参数定义 |
| `params.strategySpecific` | 策略特有参数定义 |
| `decisionResults` | 决策结果列表（含别名） |
| `comparisonRules` | 比对规则 |
| `subStrategies` | 子策略列表（policyCode + 角色） |
| `routingFields` | 路由字段（决策分支条件） |
| `testExecution.requiredParams` | 提交前必须存在的数据源/执行参数 |
| `testExecution.defaults` | 仅在用例缺失字段时补入的安全测试默认值 |
| `testExecution.defaultsByCaseType` | 按正/反案例选择命中或安全数据，且不覆盖用例显式值 |

配置格式详见 [comparison-framework.md](comparison-framework.md) 和 [examples.md — 策略配置文件示例](examples.md#策略配置文件示例)。

**版本规则**：始终使用平台最新发布版本（`publishConfig.ordinaryConfig.version`），除非用户明确指定其他版本。**禁止凭记忆或历史值填写版本号。**

### Step 2: 准备测试用例

测试用例以JSON数组定义：

```json
{
  "id": "TC_001", "desc": "用例描述", "group": "分组名",
  "caseType": "正案例", "scenario": "测试场景", "expected": "预期结果",
  "params": { /* API params 键值对 */ }
}
```

#### 模块分组（4大类）

| 模块 | 说明 | 覆盖目标 |
|------|------|---------|
| 规则 | 验证单条规则命中/未命中及阈值边界 | 每条规则至少1正1反 |
| 函数 | 验证函数输出值/评分及边界条件 | 函数分支覆盖 |
| 决策流分支覆盖 | 验证决策流路由 | 各分支路径 |
| 策略预警等级覆盖 | 验证最终预警等级 | 各级别覆盖 |

> Excel报告中Col2"模块"列只填4大类名称。

#### 预期结果格式

- **规则级**：`命中：规则编号(规则中文名)[风险等级]` / `未命中：未命中规则编号(规则中文名)`
- **函数级**：`函数输出：函数中文名(函数编码)+字段名=值`
- **策略级**：`预警等级名称`（如红色预警、黄色预警、通过）

> 规则编号后**必须附中文名**，不能只写编号。

#### 参数组装

`params` 必须包含策略所需全部入参：
1. **公共参数**（从配置 `params.common` 获取）
2. **策略特有参数**（从配置 `params.strategySpecific` 获取）
3. **数据源查询参数**（从配置 `testExecution.requiredParams` 获取）

> **S_S_BIZID 必填**：缺失时 API 返回 `success:true` 但 `data` 为空，不报错，极难排查。

#### 提交前参数预检（强制）

生成用例后、提交前运行：

```bash
python3 scripts/prepare_testcases.py \
  --config strategies/{policyCode}.json \
  --testcases testcases.governed.json \
  --output testcases.prepared.json
```

后续提交必须使用 `testcases.prepared.json`。脚本会：

- 补入 `params.common` 中的 `fixed/default` 值
- 补入 `testExecution.defaults`，但不覆盖用例显式值
- 按 `testExecution.defaultsByCaseType` 选择正/反例数据，不覆盖用例显式值
- 校验 `params.common.required` 和 `testExecution.requiredParams`
- 任一用例缺少必需参数时以退出码 `2` 阻断提交
- 将模块限制为“规则/函数/决策流分支覆盖/策略预警等级覆盖”
- 使用 `parsed_strategy.json` 校验目标规则编号和中文名
- 在严格模式下拦截策略未声明参数、无效枚举和路由值
- 按 `testExecution.ruleDependencies` 校验三方节点证据契约
- 对 `executable=false` 且具有 `skipReason` 的候选用例跳过提交参数约束，保留给执行阶段归档

`params.strategySpecific.required/fixed/default` 与 `params.common` 使用同一套预检。

策略配置启用：

```json
{
  "testExecution": {
    "semanticValidation": {
      "requireMetadata": true,
      "strictParams": true
    },
    "ruleCatalog": [{"code": "R001", "name": "规则中文名"}],
    "ruleDependencies": {
      "R001": ["third_party_realtime", "third_party_offline"]
    }
  }
}
```

规则用例声明必须核对的证据：

```json
{
  "targetRule": "R001",
  "expectedEvidence": {
    "rules": ["R001"],
    "thirdPartyNodes": [
      {"nodeName": "third_party_realtime", "fields": ["amount"]},
      "third_party_offline"
    ]
  }
}
```

#### 异常用例和 mock

异常用例必须声明真实 mock 契约：

```json
{
  "caseType": "异常案例",
  "executionMode": "mock",
  "mockScenario": "third_party_timeout"
}
```

策略配置在 `testExecution.mockScenarios` 声明场景。只有隔离环境确实启用后，提交命令
才可追加 `--enabled-mock-scenario third_party_timeout`。未声明、未启用或普通请求伪装
成异常用例都会被预检阻断。

存在 `probe` 的场景必须先生成十分钟内有效的就绪证明：

```bash
python3 scripts/mock_probe.py \
  --config strategies/{policyCode}.json \
  --host {host} \
  --scenario third_party_timeout \
  --output mock_readiness.json
```

执行时传 `--mock-readiness mock_readiness.json`。探针失败时禁止执行异常用例。

配置了 MySQL 数据源时，必须把 SQL 中每个 `#{变量}` 对应的系统字段加入
`testExecution.requiredParams`。否则三方节点可能返回 `10907`
（`解析sql不完整，存在未替换变量`），且后续函数会以 `0/null` 继续执行，
造成“策略运行成功但规则结果错误”的假象。

#### 路由字段校验

配置文件有 `routingFields` 时，提交前必须确认这些字段已正确设置——设错会导致走错误分支。

#### searchKey 唯一性

每条规则命中用例使用唯一 searchKey（如 `RULE_{规则码}_TC_{编号}`），避免数据源缓存干扰。

用例设计原则见 [examples.md — 测试用例示例](examples.md#测试用例示例)，三方数据覆盖见 [api-reference.md](api-reference.md)。

### Step 3: 提交测试

优先使用 Python API 执行器，API 不可用时才切换浏览器或 UI。

---

#### 方式A: Python API执行器（推荐）

```bash
python3 scripts/execute_tests.py \
  --host {host} \
  --cookie "{cookie}" \
  --org-code {orgCode} \
  --strategy-config strategies/{policyCode}.json \
  --testcases testcases.prepared.json \
  --design-manifest design-manifest.json \
  --output results.json --max-retry 0
```

执行器会依次完成平台门禁、参数/mock 预检、组件日志采集和原生预期比对。
治理运行禁用自动提交重试；断点续跑先验证完整执行身份，只选择未完成 ID。
续跑还必须提供与清单一致的原始 `--run-id`，不匹配会阻断，不覆盖旧输出。

执行器不得提交 `executable=false` 的用例。这类用例必须直接归档为：

```json
{
  "assertionStatus": "skipped",
  "evidenceStatus": "not_applicable",
  "skipReason": "生成阶段声明的原因",
  "uuid": ""
}
```

优先按单笔或小区间执行，不使用平台批量导入：

```bash
# 单条
python3 scripts/execute_tests.py ... --case-id TC_005 --fast

# 多条仍逐笔提交，证据查询最多4并发
python3 scripts/execute_tests.py ... \
  --case-range TC_005:TC_008 --fast
```

`--fast` 只取消固定等待并并行采集已完成流水的证据，不会把多条用例合并为一个请求。
结果旁生成 `results.timings.json`，记录预检、平台门禁、提交、证据和总耗时。

结果字段必须按以下语义使用：

| 字段 | 含义 |
|------|------|
| `executionOk` | 平台调用和策略执行是否完成 |
| `assertionStatus` | `passed` / `failed` / `inconclusive` / `skipped` |
| `evidenceStatus` | 规则、函数或三方证据是否完整 |
| `pass` | 原生断言布尔值；不能直接作为治理通过结论 |

禁止把 `runStatus=2` 单独解释成测试通过；证据不足必须保持 `inconclusive`。
存在 `expectedEvidence` 时必须逐项满足；缺少可核验的函数、三方节点或字段证据时保持
`inconclusive`。完整命中列表证明目标未命中，或已观测的函数/三方值与预期不符时，
判定为断言失败，不再混入“证据缺失”。禁止仅凭出现一次“三方节点”判定完整。

路由用例使用 `expectedEvidence.executionPath.requiredRuleSets`。每个目标规则集可同时声明
`code` 和 `name`；执行器从平台组件日志中的规则集编码或名称精确匹配。全部目标规则集
出现后才可判定 `passed`，缺少任一目标时保持 `inconclusive`。

#### 方式B: 浏览器批量API（备用）

替换 `submit_batch.js` 的 `{{PLATFORM_GUARD}}` 时使用本次门禁的完整 JSON 报告，
其中 `ok=true`、平台身份和有效名称必须已验证；不要手造报告或沿用历史报告。
模板从该报告取名称，身份不匹配、名称为空或名称解析记录矛盾时在请求前返回错误。

使用 `scripts/submit_batch.js` 时必须对所有 `{{...}}` 占位符做全局替换，而不是只替换
第一次出现的位置。模板只负责底层提交，不能替代 Python 执行器的证据比对。使用前
检查模板的重试行为；治理流程必须禁用自动提交重试。无法关闭时不采用该模板；
结果不确定时先查回执，不得切换 UI 重复提交同一用例。

---

#### 方式C: UI交互提交（备用）

详见 [ant-design-tips.md](ant-design-tips.md)。流程：打开新增 → 选类型/策略/版本 → 生成测试数据 → 修改参数（用 `fill`，禁止 eval 改DOM）→ 提交。

关键：下拉菜单DOM挂在 `document.body` 下，用 `:not(.ant-select-dropdown-hidden)` 过滤；`fill` 自动触发 React onChange。

---

#### 方式D: 浏览器内 fetch 提交（httpOnly cookie 回退）

当 `JSESSIONID` 为 httpOnly、`document.cookie` 只能看到 `lang=cn`、无法把 cookie 交给
Python 执行器时，在**已登录平台的浏览器标签页上下文**内用 `fetch(..., {credentials:'include'})`
自动携带 httpOnly cookie 完成提交与取证据。CSRF 取 `sessionStorage.getItem('_csrf_')`，请求头
**同时**带 `X-Cf-Random` 与 `_csrf_` 且都等于该 CSRF（只带一个或用 `x-csrf-token` 会 401）。
提交端点、`params` 必填字段、批量脚本模板与评分证据（`C_F_APPLYSCORE`）提取详见
[scorecard-pls-testing.md](references/scorecard-pls-testing.md) 第 5~6 节。该回退不改变 Step 1
平台门禁与预期算分，只替换传输方式；治理五态仍按证据比对判定，证据取不到记 `执行阻塞` 不得伪造为 0。

### Step 4: 验证测试结果

> **自主验证闭环**：自己通过API或浏览器验证，不让用户手动查看。

#### 验证层级（先轻后重）

| 层级 | 方式 | 验证内容 |
|------|------|---------|
| 1 | create API响应 | `policyDealTypeName`（整体决策） |
| 2 | runData `nodeType=8` | 各子策略 `finalDecision` |
| 3 | runData `nodeType=1` | `hitRuleList`（规则命中）、`inputFieldList`（ETL字段） |
| 4 | runData `nodeType=5` | 函数输出值、评分 |
| 5 | getAllCompontlog | 完整执行路径、三方数据、分支走向 |
| 6 | 浏览器导航 | 可视化确认 |

> 按 assertionKind 和 expectedEvidence 获取完整目标证据；规则用例不能仅验证整体决策。
> 已归档证据足够证明目标断言与路径后停止补查，不为每条用例无差别执行六层验证。
> 新失败、证据缺失或矛盾才扩大到相关函数、ETL、DB 或浏览器；不能省略声明的必查证据。

#### 验证API

runData（分层查询）和 getAllCompontlog（全组件日志）的详细用法、JS调用模板、nodeType类型表均见 [api-reference.md](api-reference.md) "结果验证API" 节。

关键原则：
- **常规验证**用 runData 分层查（nodeType=8→子策略token → nodeType=1→规则命中 / nodeType=5→函数输出）
- **排查问题**用 getAllCompontlog（完整执行路径+三方数据+分支走向）
- **不要依赖 `getHitRuleList` API**——可能返回0条，用 runData nodeType=8+1 组合

#### 浏览器导航验证

报告URL：`http://{HOST}/noah/policyTest/report?token={uuid}&type=1`（uuid 是 `data.uuid`，不是 token）

#### DB验证

连接信息读取 `config.json` 的 `db` 配置，或通过环境变量 `TIANCE_DB_HOST`/`TIANCE_DB_PORT`/`TIANCE_DB_USER`/`TIANCE_DB_PASS`/`TIANCE_DB_NAME` 覆盖。DB表结构详见 [api-reference.md](api-reference.md) "DB验证" 节。

```bash
python3 scripts/verify_result.py --last 5
python3 scripts/verify_result.py --uuid "xxx" --json
```

需要创建三方测试数据时使用 Fixture 清单，不手写临时 SQL：

```bash
python3 scripts/fixture_manager.py validate \
  --manifest fixtures/{policyCode}.json --run-id {uniqueRunId}
python3 scripts/fixture_manager.py setup \
  --manifest fixtures/{policyCode}.json --run-id {uniqueRunId}
python3 scripts/fixture_manager.py verify \
  --manifest fixtures/{policyCode}.json --run-id {uniqueRunId}
# 报告完成后
python3 scripts/fixture_manager.py cleanup \
  --manifest fixtures/{policyCode}.json --run-id {uniqueRunId}
```

Fixture 的 `keyColumns` 至少一个值必须包含 `${RUN_ID}`。插入前如发现同键存量数据，
脚本直接回滚；清理只按本次渲染后的隔离键执行。

#### 结果比对

**不能只用字符串匹配。** 使用配置文件的 `comparisonRules` 比对：

| 类型 | 说明 |
|------|------|
| `alias_group` | 别名组（"红色预警"="redwarnbh"） |
| `pass_through` | 直通（"通过"="Accept"） |
| `fuzzy_alias` | 模糊别名（"中风险"→黄色或蓝色） |
| `numeric_tolerance` | 数值容差（±1.0） |
| `invalid_expectation` | 无效预期标记 |

详见 [comparison-framework.md](comparison-framework.md)。

### Step 5: 生成测试报告

> 增量更新，不全量重建。先读 [报告交付合同](references/report-delivery.md)，
> 确定历史模板、新建报告或仅展示修订模式，并记录 `report-contract.json`。

先保留原生 `results.json` 并按 [共享治理合同](references/risk-governance.md) 生成
使用 `governance.py classify` 输出五态 `governed-results.json`，Agent 结合证据补充
`analysis.json`；两者都不是下面 update_report.py 的隐含功能。报告检查委托
[tiance-report-checker](../tiance-report-checker/SKILL.md)，按通用分析规范检查后
无指定模板的新报告可增加治理结果、根因分析及覆盖缺口 sheet；指定模板时保留原有
Sheet/列/样式，并将完整治理明细留在 sidecar，必要结论填入兼容的汇总位置。旧列保持原生格式，
最终统计使用治理五态，不强塞不兼容枚举，也不丢弃未执行的计划用例。

**策略主Sheet**：未指定模板时使用标准15列（见 `excel_formatter.py` 的 `COL_NAMES`）。
已有模板的17列等合法扩展应保留，不强行压缩。固定模板用 spreadsheet skill 完成写入，
不要用只支持标准列的旧写入器重建。测试场景必须包含具体数据、算术/路由与目标预期。

> **Col13 必须填 `data.uuid`**（32位小写hex），不能填 `data.token`。uuid 用于报告URL，token 是执行流水号。

**Col8 格式**：`提交策略测试API\npolicyCode=...\npolicyVersion=...\nbizType=...\n\n【关键入参】\n参数=值`

**Col10 格式**：
- 规则命中：`命中：规则编号(中文名)[风险等级] ✓`
- 规则未命中：`未命中规则编号(中文名)`
- 函数输出：`函数输出：函数名(编码)+字段=值`
- 禁止添加子策略汇总文字；决策流分支只确认路由

**样式**：表头蓝底白字 | 数据行微软雅黑9号 | 仅Col11着色（绿/红）| 全部细边框+顶部对齐+自动换行

```bash
python3 scripts/update_report.py results.json report.xlsx --config strategies/{policyCode}.json
python3 scripts/update_report.py --validate-report report.xlsx
```

上述旧命令仅用于标准列报告，不作为固定历史模板的默认入口。
报告采用临时文件保存并在结构校验通过后原子替换；标准列模式要求前15列表头符合标准、
状态枚举有效且 Col13 为32位小写 UUID。工作簿标记为打开时完整重算公式；只在所有
结果完成后写入和渲染一次。

### Step 6: 获取真实三方数据（可选）

```
GET /noahApi/policy/report/test/baseInfo?id={uuid}&token={uuid}&tokenId={uuid}&type=1
```

查询参数用 **UUID**（`data.uuid`），不是 token。baseInfo 详细用法和返回结构见 [api-reference.md](api-reference.md) "baseInfo 报告详情" 节。

UUID/Token/childToken 三者的区别和获取方式见 [api-reference.md](api-reference.md) "UUID vs Token vs childToken" 节。核心要点：

- **UUID**（32位小写hex）：报告URL、baseInfo查询、Col13
- **Token**（35位混合大小写）：runData nodeType=8 查子策略
- **childToken**：从 nodeType=8 获取，用于 nodeType=1 查规则命中

> 流程：`create token` → `nodeType=8(token)` → `childToken` → `nodeType=1(childToken)` → 规则命中详情

## 新策略接入流程

1. **获取 policyCode**：用户提供或从平台确认
2. **自动发现**：`python3 scripts/discover_strategy.py discover --policy-code {code} --host {host} --csrf {token} --output strategies/{code}.json`
3. **补充配置**：检查并补充 `routingFields`、`subStrategies`、`comparisonRules`、`params.strategySpecific`
4. **编写用例**：按 Step 2 格式，参数参考配置文件的 `params` 定义
5. **执行测试**：按 Step 3~5 流程

> **评分卡类策略**（核心产出是连续分值而非命中/决策枚举，或输入是 `.pls` 导出文件）：
> 改走 [scorecard-pls-testing.md](references/scorecard-pls-testing.md) 全链路——`decode_pls.py`
> 解码取身份与分箱 → 按分箱边界+缺省设计最小充分用例 → cookie 不可导出时用方式D 浏览器 fetch
> 真实执行 → 从 `getAllCompontlog` 取 `C_F_APPLYSCORE` 作实际评分 → 五态报告。

## 常见问题（通用）

### FUNC_002 决策流调用失败
平台侧间歇性故障，`runStatus=-2`，`errorMsg="决策流调用失败"`。不是用例问题，记录为平台故障。

### 登录失效
创建新tab → 导航确认登录状态 → 提示用户重新登录 → Step 0 检查CSRF。

### 参数格式差异
数值型（`91`）、JSON数组字符串（`"[{...}]"`）、金额型、区域级别等，提交前确认配置文件中的参数类型。

### UI表单验证错误
"该项必填"=必填为空 | "请选择测试数据"=DOM修改未更新React状态，需用 `fill` 重填 | 提交无API请求=必须用 `fill` 不用 eval。

### searchKey 路由与缓存
引擎传给数据源的 searchKey **不一定等于用例参数**。多用例同名称时可能用缓存数据。**最佳实践**：每条用例用唯一企业名称。

### 规则预期值必须与平台配置一致
预期结果必须与平台规则定义的"命中结果"一致，否则判为未通过。从配置文件或落地方案校准。

### 外部数据源覆盖
某些入参会被三方数据源覆盖。检查配置文件的 `thirdPartyOverrides` 或 `notes`。

### 三方数据源返回 10907

先查数据源 `inputConfig`，确认 SQL 占位符与 `sqlParam` 映射；再查执行日志中的
`FeatureServiceNode.nodeInputList`。如果映射正确但 `nodeInputList` 为空，问题在测试
请求缺少系统字段，不要修改 SQL。把对应字段加入 `testExecution.requiredParams`，
配置可命中的测试默认值，并用 `prepare_testcases.py` 重新生成后再提交。

## 浏览器操作注意事项

- `tabId` 必须是 number 类型，不能是 string
- IIFE 语法：`(async function(){...})()`
- 注意 null 检查避免 `Cannot read properties of undefined`
- 超时设置 `timeout: 120` 秒

## 补充参考

- [api-reference.md](api-reference.md) — 通用API文档、三方数据覆盖详解
- [comparison-framework.md](comparison-framework.md) — 通用比对框架与配置文件格式说明
- [examples.md](examples.md) — 策略配置文件示例与测试用例示例
- [ant-design-tips.md](ant-design-tips.md) — Ant Design组件交互技巧
- [scorecard-pls-testing.md](references/scorecard-pls-testing.md) — 评分卡类策略：`.pls` 解码 → 落地方案 → 分箱边界用例 → httpOnly 浏览器 fetch 真实执行 → `C_F_APPLYSCORE` 证据 → 五态报告；配套解码器 `scripts/decode_pls.py`
