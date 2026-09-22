# 策略配置与测试用例示例

## 策略配置文件示例

### 简单策略（五级分类）

以 `automated_5_tier_rating_strategy.json` 为例，展示最简策略配置结构：

```json
{
  "policyCode": "automated_5_tier_rating_strategy",
  "policyName": "五级分类自动评级策略",
  "policyVersion": 3,
  "bizType": 4,

  // ① 决策结果枚举：列出策略可能输出的所有结果
  "decisionResults": [
    {"name": "绿灯", "code": "greenalert", "priority": 0,
     "aliases": ["绿灯", "greenalert"]},
    {"name": "黄灯", "code": "yellowalert", "priority": 1,
     "aliases": ["黄灯", "yellowalert"]}
  ],

  // ② 比对规则：声明式比对逻辑，替代硬编码函数
  "comparisonRules": [
    {"type": "alias_group", "groups": [
      ["绿灯", "greenalert"],
      ["黄灯", "yellowalert"]
    ]},
    {"type": "invalid_expectation", "triggers": ["次级", "可疑", "损失"],
     "note": "策略不支持这些输出，预期不合理直接判未通过"}
  ],

  // ③ 参数定义：common（通用） + strategySpecific（策略专属）
  "params": {
    "common": {
      "S_E_APIMODEL": {"type": "string", "fixed": "30"},
      "S_S_BIZID": {"type": "string", "required": true},
      "S_S_CUSTNO": {"type": "string", "required": true},
      "S_S_ORGCODE": {"type": "string", "fixed": "sxdb"},
      "S_E_CUSTTYPE": {"type": "string", "fixed": "1"},
      "S_S_CUSTMANAGER": {"type": "string", "default": "wty"},
      "S_F_LOANBALANCE": {"type": "number", "required": true}
    },
    "strategySpecific": {
      "C_N_COMPENSATEDAYS": {"type": "number",
        "description": "代偿天数（不影响决策结果）"},
      "C_S_MANUALCHECKITEMSJSON": {"type": "string", "format": "json_array",
        "description": "人工检查项，前缀M"},
      "C_S_SYSTEMCHECKITEMSJSON": {"type": "string", "format": "json_array",
        "description": "系统检查项，前缀S"},
      "C_S_REVIEWCHECKITEMSJSON": {"type": "string", "format": "json_array",
        "description": "复核检查项，前缀R"}
    }
  },

  "decisionLogic": "三类检查项(M/S/R)全部空数组→绿灯，任一非空→黄灯。",
  "notes": "策略只输出绿灯/黄灯，不存在次级/可疑/损失等五级分类。"
}
```

**关键要点**：
- `decisionResults` 的 `aliases` 字段用于 alias_group 比对
- `comparisonRules` 按数组顺序执行，先匹配先返回
- `params.common` 定义所有策略共享的必填字段
- `params.strategySpecific` 定义该策略独有的参数

---

### 带子策略的复杂策略（保后检查）

以 `bhjcpostMainBefore.json` 为例，展示含子策略和路由字段的配置：

```json
{
  "policyCode": "bhjcpostMainBefore",
  "policyName": "保后检查贷前主策略",
  "policyVersion": 6,
  "bizType": 1,

  // ① 子策略声明：列出所有子策略及其角色
  "subStrategies": [
    {"policyCode": "bhjcpostSubentBefore",
     "policyName": "保后检查贷前企业子策略", "role": "enterprise"},
    {"policyCode": "bhjcpostSubperBefore",
     "policyName": "保后检查贷前个人子策略", "role": "personal"},
    {"policyCode": "bhjcpostSubrelateentBefore",
     "policyName": "保后检查贷前关联企业子策略", "role": "related_enterprise"}
  ],

  // ② 路由字段：决定走哪条决策流分支
  "routingFields": {
    "S_S_ENTERPRISETYPE": {
      "enum": ["国企", "民营"],
      "description": "企业类型，决定走哪套规则集"
    },
    "C_S_BIZSCENARIO": {
      "enum": ["借款类", "债券委贷投资类", "非融类"],
      "description": "业务场景，决定走哪条规则路线"
    }
  },

  // ③ 5级预警结果 + pass_through比对
  "decisionResults": [
    {"name": "红色预警", "code": "redwarnbh", "priority": 150},
    {"name": "黄色预警", "code": "yellowwarnbh", "priority": 130},
    {"name": "蓝色预警", "code": "bluewarnbh", "priority": 120},
    {"name": "绿色预警", "code": "greenwarnbh", "priority": 110},
    {"name": "通过", "code": "Accept", "priority": 0}
  ],
  "comparisonRules": [
    {"type": "pass_through", "triggers": ["通过", "Accept", "无风险"],
     "matchActual": ["Accept", "通过"]},
    {"type": "alias_group", "groups": [
      ["红色预警", "redwarnbh"],
      ["黄色预警", "yellowwarnbh"],
      ["蓝色预警", "bluewarnbh"],
      ["绿色预警", "greenwarnbh"]
    ]},
    {"type": "fuzzy_alias", "pattern": "中风险预警",
     "matches": ["黄色预警", "蓝色预警"],
     "note": "中风险=黄色或蓝色预警"}
  ]
}
```

**关键要点**：
- `subStrategies` 声明子策略列表，baseInfo API返回时需按 policyCode 匹配（顺序不固定）
- `routingFields` 标注路由字段，测试用例中必须正确设置以走到目标分支
- `pass_through` 规则放在最前面，优先处理"通过/Accept"类预期
- `fuzzy_alias` 处理一对多的模糊匹配场景

---

### 带三方数据覆盖的策略（集中度）

以 `DF_PRE_CONC_001.json` 为例，展示三方数据覆盖声明和可用城市配置：

```json
{
  "policyCode": "DF_PRE_CONC_001",
  "policyName": "保前集中度判断策略",
  "policyVersion": 2,
  "bizType": 1,

  "comparisonRules": [
    {"type": "keyword_absent",
     "triggers": ["不触发", "通过", "Accept", "全部通过"],
     "target": "超限",
     "note": "预期不触发时，实际不应含超限"},
    {"type": "keyword_present",
     "triggers": ["触发", "超限"],
     "target": "超限"}
  ],

  // ① 三方数据覆盖声明：哪些入参会被运行时三方查询覆盖
  "thirdPartyOverrides": [
    {"field": "C_F_PREAREAMERGEDUSEDQUOTA",
     "source": "ads_icr_area_conc_realtime",
     "sourceField": "C_F_DISTRICTUSEDQUOTA",
     "note": "区域合并已用额度被三方数据覆盖"}
  ],

  "testExecution": {
    "requiredParams": [
      "S_S_CUSTNAME",
      "C_S_AREACITYCODE",
      "C_S_AREADISTRICTCODE"
    ],
    "defaults": {
      "C_S_AREACITYCODE": "340100",
      "C_S_AREADISTRICTCODE": "340000"
    },
    "defaultsByCaseType": {
      "正案例": {"S_S_CUSTNAME": "命中数据客户"},
      "反案例": {"S_S_CUSTNAME": "安全数据客户"}
    },
    "mockRequiredCaseTypes": ["异常案例"],
    "mockScenarios": {
      "third_party_timeout": {
        "description": "隔离环境中的三方超时场景"
      }
    }
  },

  // ② 可用城市列表：三方数据表中有记录的城市
  "availableCities": [
    {"code": "340100", "name": "合肥", "area_used_quota": 5000000},
    {"code": "500100", "name": "重庆", "area_used_quota": 52000000},
    {"code": "510100", "name": "成都", "area_used_quota": 60000000}
    // ... 完整列表见配置文件
  ],

  // ③ 踩坑记录
  "pitfalls": [
    "不在表中的城市查询返回空数组但策略仍判区域集中度超限",
    "测试区域不超限时选合肥340100(area_used_quota仅5M)，CONCLIMITSTANDARDOFF设为80000000"
  ]
}
```

**关键要点**：
- `thirdPartyOverrides` 声明会被三方数据覆盖的入参字段，用例设计时必须考虑
- `availableCities` 列出有数据的城市，测试"不超限"场景应选低额度城市
- `pitfalls` 记录已知的陷阱，避免重复踩坑
- 异常用例必须引用已声明且本次真实启用的 `mockScenario`

---

## 测试用例示例

### 异常用例

```json
{
  "id": "TC_MOCK_001",
  "caseType": "异常案例",
  "executionMode": "mock",
  "mockScenario": "third_party_timeout",
  "expected": "三方接口超时后走降级逻辑",
  "params": {
    "S_S_BIZID": "MOCK_TIMEOUT_001",
    "S_S_CUSTNO": "MOCK_CUSTOMER_001"
  }
}
```

只有隔离环境确实启用 `third_party_timeout` 后，执行命令才可传
`--enabled-mock-scenario third_party_timeout`。

### 规则级用例

验证单条规则是否正确触发。入参通过 searchKey 控制 mock 返回值。

```json
{
  "id": "TC_001",
  "desc": "企业近3个月法定代表人变更>0 → 命中EBGS01低风险",
  "group": "规则",
  "caseType": "正案例",
  "scenario": "国企+借款类，2003返回法定代表人变更1次",
  "expected": "命中：EBGS01(企业近3个月法定代表人存在变更记录企查查)[低风险预警]",
  "params": {
    "S_E_APIMODEL": "30",
    "S_S_BIZID": "TC_001",
    "S_S_CUSTNO": "BHJC_RUN_01",
    "S_S_ORGCODE": "sxdb",
    "S_S_ENTERPRISETYPE": "国企",
    "C_S_BIZSCENARIO": "借款类",
    "S_S_COMPANYNAME": "RULE_EBGS01_TC_001",
    "S_S_UNIFSOCLCRCOD": "RULE_EBGS01_TC_001",
    "S_F_LOANBALANCE": 5000000
  }
}
```

**验证方式**：通过 `runData?nodeType=1` 查询规则集命中详情，确认 hitRuleList 中包含目标规则。

---

### 函数级用例

验证函数计算逻辑是否正确。

```json
{
  "id": "TC_310",
  "desc": "股东公司数据合并(S000007): 首次迭代累加(0+2=2)",
  "group": "函数",
  "caseType": "正案例",
  "expected": "函数输出：股东公司数据合并(S000007)+C_N_SHAREHOLDERCOUNT=2",
  "params": {
    "S_E_APIMODEL": "30",
    "S_S_BIZID": "TC_310",
    "S_S_CUSTNO": "BHJC_FUNC_RUN",
    "S_S_ORGCODE": "sxdb",
    "S_S_ENTERPRISETYPE": "国企",
    "C_S_BIZSCENARIO": "借款类",
    "S_S_COMPANYNAME": "FUNC_S000007_TC_310",
    "S_S_UNIFSOCLCRCOD": "FUNC_S000007_TC_310"
  }
}
```

**验证方式**：通过 `runData?nodeType=5` 查询函数执行详情，确认输出变量值。

---

### 策略预警等级用例

验证端到端的预警等级输出。

```json
{
  "id": "TC_200",
  "desc": "高风险规则命中≥4条 → 红色预警",
  "group": "策略预警等级覆盖",
  "caseType": "正案例",
  "expected": "红色预警",
  "params": {
    "S_E_APIMODEL": "30",
    "S_S_BIZID": "TC_200",
    "S_S_CUSTNO": "BHJC_RED_RUN",
    "S_S_ORGCODE": "sxdb",
    "S_S_ENTERPRISETYPE": "国企",
    "C_S_BIZSCENARIO": "借款类",
    "S_S_COMPANYNAME": "RED_ALERT_TC_200",
    "S_S_UNIFSOCLCRCOD": "RED_ALERT_TC_200"
  }
}
```

**验证方式**：直接比对 `policyDealTypeName` 与 `expected`，通过 `comparisonRules` 中的 `alias_group` 规则匹配。

---

### 决策流分支覆盖用例

验证决策流中的排他网关路由是否正确。

```json
{
  "id": "TC_050",
  "desc": "民营企业+债券委贷投资类 → 走民营规则集分支",
  "group": "决策流分支覆盖",
  "caseType": "正案例",
  "scenario": "路由字段设为民营+债券委贷投资类，验证走正确分支",
  "expected": "通过",
  "params": {
    "S_E_APIMODEL": "30",
    "S_S_BIZID": "TC_050",
    "S_S_CUSTNO": "BHJC_BRANCH_RUN",
    "S_S_ORGCODE": "sxdb",
    "S_S_ENTERPRISETYPE": "民营",
    "C_S_BIZSCENARIO": "债券委贷投资类",
    "S_S_COMPANYNAME": "BRANCH_TC_050",
    "S_S_UNIFSOCLCRCOD": "BRANCH_TC_050",
    "S_F_LOANBALANCE": 10000000
  }
}
```

**验证方式**：通过 `getAllCompontlog` 查询 `diagramLine`（决策流执行路径），确认经过了预期的网关节点。

---

## 用例设计原则

1. **边界值覆盖**：每个关键参数至少测边界值、边界±1、典型值
2. **正/反案例**：正案例验证规则触发，反案例验证规则不触发
3. **组合测试**：多个参数同时变化时的交叉组合
4. **决策流端到端**：不仅测单个函数，还要测完整决策流
5. **预期结果明确**：每个用例必须有明确的 `expected` 值

---

## searchKey 前缀约定

通过 `S_S_COMPANYNAME` / `S_S_UNIFSOCLCRCOD` 字段传入不同的 searchKey，mock 服务器根据前缀返回不同的三方数据：

| 前缀 | 用途 | mock返回特征 |
|------|------|-------------|
| `RULE_*` | 普通规则测试 | 黄色/可能国企数据 |
| `RED_ALERT_*` | 高风险/红色预警测试 | 红色/民营数据 |
| `FUNC_*` | 函数测试 | 函数测试专用数据 |

---

## 批量提交格式

将用例分批，每批10~11个：

> **完整提交脚本见 SKILL.md Step 3**（含重试和会话过期检测）。
>
> 此处仅说明结果字段映射差异：SKILL.md 模板返回 `rs`(runStatus)、`dt`(dealTypeName)、`dtCode`(policyDealTypeCode)，
> 旧版示例使用 `runStatus`/`dealType`。统一使用 SKILL.md 模板的缩写字段名。

```javascript
// 单条结果字段说明（完整循环见 SKILL.md Step 3）
{
  id: "CASE_001",
  expected: "绿灯",
  rs: d.data && d.data.runStatus,          // 执行状态: "1"=成功
  dt: d.data && d.data.policyDealTypeName,  // 决策结果: "绿灯"/"黄灯"
  dtCode: d.data && d.data.policyDealTypeCode,
  uuid: d.data && d.data.uuid,
  token: d.data && d.data.token,
  err: ""
}
```

批次间无需等待，批内间隔800ms。完整提交脚本模板见 SKILL.md Step 3。
