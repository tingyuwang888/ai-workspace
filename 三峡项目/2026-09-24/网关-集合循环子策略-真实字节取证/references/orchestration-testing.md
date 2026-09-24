# 复杂编排策略测试（多节点链 / 网关 / 子策略）

本文覆盖**被测策略是"复杂编排"**时的取证与断言要点：一条策略里串了多个决策工具 /
规则集 / 函数节点，或带**网关分支**（排他 / 并行 / 包容）、引用**子策略**（普通子策略 /
集合循环子策略 `runData nodeType=8`）。它是 [SKILL.md](../SKILL.md) 通用流程、
[decision-tool-testing.md](decision-tool-testing.md)（单个决策工具的分支测试）在
"编排级证据 + 逐节点断言"这一层的补充：单工具测试关心"某个工具命中了哪条分支"，
本文关心"整条流按什么顺序走过哪些节点、每个节点各吐出了什么证据"。

前提与通用流程一致：**默认已有落地文档**。本文不从平台导出反推落地文档，也不负责
在画布上搭建策略（那属于 `tiance-policy-forge`），只做三件事：①用 `getAllCompontlog`
把整条流的逐节点证据解出来；②在 `expectedEvidence` 里声明编排级断言并核对；③诚实区分
"已实测的形状"和"仅有文档依据的形状"。

## 何时用本文

- 策略串了多个决策工具 / 规则集 / 函数节点，需要断言**执行路径**（走了哪些节点、按什么顺序），
  而不只看整体决策结果。
- 有**网关**（ExclusiveGateway 等），需要断言实际走了哪条分支 / 路由到哪个下游。
- 引用了**子策略**（普通 / 集合循环），需要下钻子 token 的证据并核对子策略是否执行。
- 需要在 `expectedEvidence` 声明 `decisionTools` / `pathContains` / `nodeVisited` /
  `subPolicies` 四类新断言（对应 `scripts/execute_tests.py` 的取证解析与
  `scripts/result_evaluator.py` 的契约校验）。

## 1. 证据采集通路（与单工具一致，多节点靠"顺序"）

单笔执行通路（`lab/policytest/create` → `baseInfo` 预热 → `getAllCompontlog`）见
[decision-tool-testing.md](decision-tool-testing.md) 第 4 节。多节点编排下要额外记住三条
实测确定的读法：

- `getAllCompontlog` 的 `data` **恰好五个键**：`contextFields`、`fieldMap`、`diagramLine`、
  `flowModelinAndOutputParams`、`token`（实测）。解析器 `parse_component_evidence` 就以这五键为输入。
- **`flowModelinAndOutputParams` 数组序 = 权威执行顺序**。链式多节点策略里，节点在数组中的
  先后就是流经的先后；每个节点带 `ordinal`（解析器补的下标）作为定位锚。
- **`fieldMap.<字段>.nodeIdList` 只表示"哪些节点写过该字段"，其数组顺序不可靠**——实测的
  链式两工具运行里它把**末写者排在前面**。因此**绝不能**用它推执行顺序，执行顺序一律以
  `flowModelinAndOutputParams` 序为准；它只用于"某字段确由某节点产出"的存在性佐证。
- **`diagramLine` = 走过的连线 uuid 数组**：N 个节点 → N-1 条边。解析器原样暴露为 `pathLines`，
  可用来交叉核对路径连通性。

决策工具 `extension.executeDetail` 的骨架**分两支**（2026-09-24 在三峡 `sxdb` 逐字重抓的只读
`getAllCompontlog` 实测）：**决策树 / 决策表**为 `ROOT→CHILD→DECISION`，CHILD 步携带命中
`conditionSet`（只记录命中的那一条分支）；**决策矩阵**只有 `ROOT→DECISION`、**无 CHILD 步**，两步
`nodeId` 均为**空串**，命中只能从 DECISION 出参值反推。三类骨架细节见
[decision-tool-testing.md](decision-tool-testing.md) 第 1、4 节，本文不重复。

## 2. 三类节点在证据里的形状（`parse_component_evidence` 输出键）

`parse_component_evidence` 遍历 `flowModelinAndOutputParams`，按 `nodeType` 分流。返回的关键集合：

| 节点 `nodeType` | 证据形状是否实测 | 输出键 | 身份定位方式 |
|---|---|---|---|
| `DecisionToolServiceNode` | **已实测**（三峡 `sxdb` 2026-09-24 逐字重抓：树 / 矩阵 / 表，fixture 为真实字节） | `decisionTools` | `nodeName` / `nodeId` / `toolCode`（`extension.code`） |
| `ExclusiveGateway`（并行 / 包容网关仅文档） | **已实测**（`sxdb` 2026-09-24 `crossScoreFlow` 真实字节，fixture 落地；`nodeOutputList` **恒空**，分支选择落在 `extension.conditions`，见第 2.1 节） | `gateways` | `nodeName` / `nodeId` |
| `ChildFlowNode`（集合循环 / 普通子策略，`runData nodeType=8`；文档旧名 `SubPolicyNode`/`CollectionSubPolicyNode` 见第 2.2 节纠正） | **已实测**（`sxdb` 2026-09-24 `bhjcpostMainBefore` 集合循环真实字节，子 token 落在 `extension.tokenIds[]`） | `subPolicies`（`.children`） | 子 `policyCode`（`extension.code`）/ `token`（`tokenIds[]`） |
| 全部类型（路径顺序 / 连线） | 已实测 | `flowOrder`、`pathLines` | `ordinal` |

两个必须刻意的坑（已实测，写进了解析器与用例）：

- **同工具复用无判别力**：一个策略里两次调用同一决策工具时 `nodeName` **完全相同**，只有
  `nodeId` / 数组 `ordinal` 能区分。断言与去歧义一律优先用 `nodeId` / `toolCode`。
- **值类型字符串 / 数字混用**：决策工具出参既可能是数字也可能是字符串，比对前先经
  `_contract_values_match` 用 Decimal / String 归一；`"001"` 与 `"1"` 这类编码串**不做**数字归一。

### 2.1 排他网关真实形状（`crossScoreFlow`，2026-09-24 `sxdb` 真实字节）

真实 `ExclusiveGateway` 节点在 `flowModelinAndOutputParams` 里长得和文档假设有出入，务必按实盘写断言：

- **`nodeOutputList` 恒为空数组**——网关不"产出"字段，因此人读渲染里**只有一行判定、没有路由目标行**。
- **分支选择落在 `extension`**：`extension.conditions` 是一个**下标数组**（如 `[2]` 表示命中第 3 条出边），
  并带 `extension.conditionRuleUuid`（32 位小写 hex）与 `extension.type`（实测为 `"start"`）。
  解析器把它们暴露为 `selectedBranch`（下标字符串数组）、`conditionRuleUuid`、`gatewayType`。
- **被判定的字段在 `nodeInputList`**（实测 `C_F_APPLYSCORE=62`），解析器归入 `inputs`；
  `routeFields` 在实盘**恒为 `[]`**（网关不往输出侧吐路由标签）。
- 早期合成 fixture 里的 `routeTarget` / `routeCondition` 字段名是**编造的**，平台上并不存在——
  断言与渲染一律改用 `selectedBranch` + `inputs`，不再断言任何"路由目标"文本。

### 2.2 集合循环 / 普通子策略真实形状（`bhjcpostMainBefore`，2026-09-24 `sxdb` 真实字节）

- **运行时 `nodeType` 是 `ChildFlowNode`**，不是文档旧名 `SubPolicyNode` / `CollectionSubPolicyNode`；
  解析器的 `SUB_POLICY_NODE_TYPES` 已补入 `ChildFlowNode`。早前只认文档旧名会导致真实
  `ChildFlowNode` **整条被跳过**、`subPolicies` 恒为 0——这正是"唯真实抓包能证伪"的又一例。
- **子 token 落在 `extension.tokenIds`（数组）**，不是 `nodeOutputList` 里的 JSON、也不是假设的
  `subPolicyResultList`；`extension.code` 是子策略编码，解析器关联为子项 `policyCode`，
  并记下 `sourceKey == "tokenIds"`。逐元素的子结果另镜像在 `nodeOutputList` 的 `C_O_*` 数组字段里。
- 集合循环会产出**多个**子项（实测一次运行 3 个：企业 / 个人 / 关联企业子策略），每个各带一个子 token。
- **降级不失败语义不变**：子项本身不带平台侧 `evidenceStatus`，解析器仍赋默认 `unavailable`，
  因此 `subPolicies` 断言命中"子策略证据不可用"时只进 `missing`、**不**进 `mismatch`（见第 4 节）。

## 3. 四类 `expectedEvidence` 编排断言

在 `strategies/*.json` 或单条用例的 `expectedEvidence` 下声明。执行器逐项消费，语义与
"值不符=失败、证据缺失=不确定"的铁律见第 4 节。

### 3.1 `decisionTools` —— 逐工具命中分支 / 出参

```json
{
  "expectedEvidence": {
    "decisionTools": [
      {
        "nodeName": "决策树测试gf3",
        "fieldValues": {"C_F_LEVEL": "1"},
        "hitConditions": [
          {"field": "C_F_SALARY909", "operator": "<=", "expected": "100", "actual": "90"}
        ]
      }
    ]
  }
}
```

契约项按 **`nodeName` / `nodeId` / `code`** 三个别名键与工具侧 `{nodeName, nodeId, toolCode}` 求交集来定位
命中的决策工具节点（工具编码走 `code` 键，命中工具侧的 `toolCode`；单独写 `toolCode` 键**不参与匹配**，只被
用于下一步的去歧义）。再校验出参字段值（`fieldValues`，字符串 / 数字归一）与命中条件（`hitConditions` 的
field / operator / expected / actual）。工具被复用而只给 `nodeName` 时记为"决策工具身份不唯一"（补 `nodeId`
或 `toolCode` 键可抑制该歧义报错），**不**当成通过或不通过。`executeDetail` 缺失或解析失败 →
"决策工具证据不可用"，只进 `missing`、**不**进 `mismatch`（证据不足不等于分支被跳过）。

### 3.2 `pathContains` —— 路径必须出现的节点（可含严格顺序）

```json
{
  "expectedEvidence": { "pathContains": ["开始", "还款决策树", "额度矩阵", "结束"] },
  "executionPath": { "order": "strict" }
}
```

声明执行路径必须出现的节点名，对照 `flowOrder` 里的 `nodeName`。默认只校验"都出现过"；
带 `executionPath.order == "strict"` 时按流顺序严格校验，顺序不符报"路径顺序与契约不符"。
`pathContains` 也可写在 `executionPath.pathContains` 下（两种位置等价）。目标节点不在
**已捕获的**流里 → "路径节点:名称" 记为不符；**完全没采到组件日志**时只记缺失、不判不符。

### 3.3 `nodeVisited` —— 节点被访问（重名场景按 `nodeId` 去歧义）

```json
{
  "expectedEvidence": { "nodeVisited": [{"nodeId": "t2"}] }
}
```

只断言某节点被走到。重名时按 `nodeName` 定位会有歧义，用 `nodeId` 精确命中；无法唯一定位
时报"路径节点身份不唯一"。

### 3.4 `subPolicies` —— 集合循环 / 普通子策略下钻

```json
{
  "expectedEvidence": { "subPolicies": [{"policyCode": "SUB_POLICY_X", "evidenceStatus": "ok"}] }
}
```

对照 `subPolicies[*].children`（由 `_extract_child_tokens` 从 `extension.tokenIds[]` 挖出的子 token，
真实形状见第 2.2 节），按 `policyCode`（`extension.code`）/ `token` / `nodeName` / `nodeId` 匹配。子项状态键是
`evidenceStatus`（缺省视为 `ok`）。**子策略载荷已在 `sxdb` 真实采集（见第 2.2 节）**，但子项本身不带平台侧
`evidenceStatus`，解析器赋的默认值是 `unavailable`；因此子项实际状态与显式预期不符（含该默认 `unavailable`）
一律降级为"子策略证据不可用"（`missing` / `inconclusive`），**永不**判为断言失败；完全没有子策略节点时也只记
"子策略:名称"缺失、不判失败。

## 4. 降级不失败原则（degrade-don't-fail）

编排证据不完整是常态（子项不带平台侧 `evidenceStatus`、可选分支本轮未命中、组件日志偶发未采集等），
断言必须区分"值不符"与"没证据"（注意：这里的"没证据"是**运行时缺失**，不是形状未测——网关 / 子策略形状已实测，见第 2.1 / 2.2 节）：

| 情形 | `missing`（不确定） | `mismatch`（失败） |
|---|---|---|
| 完全没采到组件日志（`flowOrder` 为空） | 是 | 否 |
| 路径节点缺失但流**已**捕获 | 是 | 是 |
| 决策工具出参值与预期不符 | 是 | 是 |
| 决策工具 `executeDetail` 缺失 / 解析失败 | 是 | 否 |
| 子策略子项不可用 / status 不符 | 是 | 否（子项不带平台 `evidenceStatus`，解析器默认 `unavailable`，据此只降级） |

判据由 `flow_captured = bool(flow_entries)` 驱动：**能证明"节点没在这条已执行的流里"才判不符，
否则只记缺失**。对应五态：证据缺失→`inconclusive`，值不符→`failed`。

## 5. verified vs documented 边界（免责）

- **已实测**（三峡 `sxdb` 2026-09-24 逐字重抓的只读 `getAllCompontlog`，fixture 存真实字节）：决策工具
  `executeDetail` 骨架**分两支**——树 / 表为 `ROOT→CHILD→DECISION`（CHILD 带命中 `conditionSet`，只记录命中
  分支；树 `CHILD.nodeId` 为 hash、表为 `null`），矩阵为 `ROOT→DECISION`（**无 CHILD**，两步 `nodeId` 均为
  空串，命中只能从 DECISION 出参反推）；流节点名为 `StartFlowNode`/"开始节点" 与 `EndFlowNode`/"结束节点"；
  值类型混用（`leftValue`/actual 为 float、边界 `rightValue`/expected 为 string）。另实测
  `flowModelinAndOutputParams` 顺序权威性、`fieldMap.nodeIdList` 顺序不可靠、`diagramLine` = N-1 连线、
  复用工具 `nodeName` 相同。第 3.1 / 3.2 / 3.3 的断言语义建立在这些事实之上。
- **已实测（本批新增）**（`sxdb` 2026-09-24，`crossScoreFlow` 排他网关 + `bhjcpostMainBefore` 集合循环子策略，
  fixture 落地真实字节）：**排他网关** `nodeOutputList` **恒空**，分支选择落在 `extension.conditions`（下标数组，
  如 `[2]`）+ `extension.conditionRuleUuid`（32 hex）+ `extension.type`（`"start"`），被判定字段在 `nodeInputList`；
  **集合循环子策略**运行时 `nodeType` 是 **`ChildFlowNode`**（非文档旧名 `SubPolicyNode`/`CollectionSubPolicyNode`），
  子 token 落在 `extension.tokenIds[]`、子策略编码在 `extension.code`、逐元素子结果镜像在 `nodeOutputList` 的
  `C_O_*` 数组。早前合成 fixture 里的 `routeTarget` / `routeCondition` / `subPolicyResultList` 等字段名**均为编造**、
  被真实抓包证伪；只认文档旧名 `SubPolicyNode` 会使真实 `ChildFlowNode` 整条被跳过（`subPolicies` 恒 0）。
  第 2.1 / 2.2 / 3.4 的形状纠正与断言语义建立在这些事实之上。
- **仅文档级**（`api-reference.md`，本批仍未采集真实载荷）：`ParallelGateway` / `InclusiveGateway` 的载荷形状
  （只实测了排他网关），以及**非集合循环的普通子策略**载荷（只实测了集合循环 `ChildFlowNode`）。解析按宽容实现、
  可被 fixture 测试，但**不能**据此断言平台一定如此吐数；命中这些未测形状时一律走第 4 节的降级不失败路径。

## 交叉引用

- 单个决策工具的分支 / 边界 / 画布核对 → [decision-tool-testing.md](decision-tool-testing.md)。
- 编排断言的用例样例 → [../examples.md](../examples.md)。
- 输出比对规则层（`comparisonRules`）→ [../comparison-framework.md](../comparison-framework.md)。
- 平台接口契约（含 `runData nodeType=8`）→ [../api-reference.md](../api-reference.md)。
- 解析 / 校验实现 → `scripts/execute_tests.py`（`parse_component_evidence` 及渲染）、
  `scripts/result_evaluator.py`（`validate_orchestration_contracts`）；回归用例 →
  `scripts/test_orchestration_evidence.py`。

## 合规与注意

- 本文引用真实机构 `sxdb` 与工具编码，**只进 live 与私有归档，不进通用发布子集（staging）**。
- 任何文档 / 脚本中 Noah 主机一律写占位符 `<NOAH_HOST>`，禁止出现内网 IP 字面量与客户标签，
  避免触发 `scripts/test_desensitized.py` 全树扫描。
