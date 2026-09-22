# 决策工具类组件测试（决策表 / 决策矩阵 / 决策树）

本文覆盖**决策工具（decision tool）类组件**从平台导出文件到测试用例与报告的链路，
是对 [SKILL.md](../SKILL.md) 通用流程在"被测策略引用了决策工具"场景下的补充。规则/决策流类
策略仍走通用链路；评分卡类走 [scorecard-pls-testing.md](scorecard-pls-testing.md)。只有当被测
策略的某个节点调用了一个**决策工具**（决策表 / 决策矩阵 / 决策树），或输入是一份决策工具导出
文件时，按本文执行。

## 何时用本文

- 被测策略里存在"调用决策工具"的节点，需要针对该工具的每一行 / 每个单元格 / 每条路径设计用例。
- 用户给的是一份决策工具导出文件（`decisionToolExportData` 顶层键），想知道"结构是什么 / 转成落地方案 / 生成用例"。
- 需要判断某策略引用了哪些决策工具、这些工具是否已上线（用运行区的 correlation 引用关系）。

## 决策工具是什么

天策/Noah「策略中心」下与 策略管理 / 规则集 / 函数库 / 评分卡 **并列的独立组件**，共三类：

| 类型 | modelType | 标识前缀 | 编辑器 |
|---|---|---|---|
| 决策表 | `D_TABLE` | `TABLE…` | 基础信息(含默认决策) + 决策表设计(节点式) |
| 决策矩阵 | `D_MATRIX` | `METRIC…` | 基础信息(含默认决策) + 矩阵设计(X轴/Y轴/单元格) |
| 决策树 | `D_TREE`(待字节级确认) | 路由 `decisionTree` | 基础信息(含默认决策) + 画布式 DAG(节点=条件、决策=赋值、连线) |

生命周期分**运行区**(已发布)与**编辑区**。运行区每行操作图标含：上/下线、`debug`(平台自带单条调试)、
`profile`(查看)、`export`(导出)、`correlation`(查引用它的策略)。**未上线**(如"导入待提交")的工具没有
`export` 图标——此时改用 `profile` 打开只读查看态（URL 形如
`http://<NOAH_HOST>/noah/bodyguard/modelTool/decisionMatrix?decisionToolCode=<code>&type=view`）零改动读模型，
不要为拿 schema 去发布生产。

## 1. 解码决策工具导出

导出走 UI：点运行区某已上线工具的 `export` 图标，触发
`GET http://<NOAH_HOST>/noahApi/component/export/DECISION_TOOL?componentCategory=DECISION_TOOL&componentIdentifys=<code>&componentShowType=dste&fileName=<name>`。
该接口由 SPA 带 header token 调用，直接 `fetch` 会 401；浏览器已把响应完整落盘（Chrome 可能显示为
"未确认 .crdownload"，字节其实齐全），内容是 **base64(gzip(JSON))**——与 `.pls` 同封装。

用仓库内解码器的通用 loader 还原（`load_pls()` 已兼容 base64+gzip / base64+json / 纯 gzip / 纯 JSON）：

```bash
python3 scripts/decode_pls.py <导出文件> -o decoded.json   # 全量解码（决策工具走这条）
```

> 注：`decode_pls.py` 的 `--summary`/默认摘要目前只识别评分卡的 `policyCombineExportData`/
> `scorecardExportDataList`，不解析 `decisionToolExportData`。决策工具请用 `-o` 取全量 JSON 后按下述结构读取。

导出 JSON 顶层键：`decisionToolExportData[]`、`systemFieldExportData[]`、`exportDataMap`、
`ruleSetBindCommonRuleMap`、`version`。每条工具信封字段：

```
modelType, decisionCode, uuid, name, orgCode, appName, source, version, enabled,
inputData[]   # 条件入参：{name,displayName,dataType,bizType,dName}
outputData[]  # 输出决策字段：{name,displayName,dataType,systemField,selectType,sourceName}
defaultDecisions[]  # 兜底赋值：{fieldName,value,valueType,fieldType,operatorType}
content       # 嵌套 JSON 字符串，需二次 json.loads —— 见下
```

`systemFieldExportData[]` 是所有被引用字段的定义（`name/displayName/dataType/funcType/groupName/uuid`），
即落地文档"字段映射"的来源。

## 2. 三类型结构

### 2.1 决策表 D_TABLE —— content 是 root→child(条件)→decision(赋值) 树

真实样例（机构 `sxdb` 决策表 `TABLE26062310321945640` "还款能力测算gf2"）：

- 入参 `C_F_GEXX0043`（评分卡评分, double），出参 `C_F_OUTLENDINGRATE`（贷款利率, double）。
- content 解析后：

```
root
 ├─ child key=C_F_GEXX0043 conditionsGroup{connector:"all", conditions:[{compareKey:"<=",compareValue:"6"}]}  → decision: C_F_OUTLENDINGRATE = 7
 ├─ child key=C_F_GEXX0043 conditions:[{compareKey:">", compareValue:"6"}]                                     → decision: C_F_OUTLENDINGRATE = 4
 └─ child key=C_F_GEXX0043 conditions:[{compareKey:"isnull"}]                                                  → decision: C_F_OUTLENDINGRATE = 0.3
默认决策 defaultDecisions: C_F_OUTLENDINGRATE = 0.25
```

每个 `child` = 一行规则，`conditionsGroup.conditions[]` 以 `connector`(all/any) 组合，比较符实测有
`<=`、`>`、`isnull`（其余词表以真实导出为准）；叶子 `decisions[].{fieldName,value,valueType}` 是命中后赋值；
按顺序 + `defaultDecisions` 决定最终结果（首个命中即出，否则默认）。

### 2.2 决策矩阵 D_MATRIX —— X轴变量分桶 × Y轴枚举 → 单元格决策

真实样例（`METRIC26061715321945626` "g4"，只读查看态读取）：

- 默认决策：赋值 系统字段 `个人月收入919` = 0。
- X 轴（列）变量 `个人月收入909` 分桶：`≥ 10000` / `< 100` / `≥ 100 && < 10000`；叠加 `个人月收入908` 条件 `不为空`。
- Y 轴（行）变量 `业务代理人反洗钱评级` 枚举：`= 通过` / `= 拒绝`。
- 单元格（输出决策，赋 `个人月收入919`）：通过行 = 10000 / 100 / 1000；拒绝行 = 20000 / 100 / 2000。

结构要点：X 轴可**多变量叠加**且每变量是**复合区间**（`≥100 && <10000`），Y 轴是变量枚举值，
单元格是 (行值 × 列桶) 的决策输出，表级 `defaultDecisions` 兜底。

### 2.3 决策树 D_TREE —— 画布式 DAG（字节级 content 待补）

编辑器 `decisionTree` 的设计态是画布：组件面板两类——`节点`(拖到画布→配置条件)、`决策`(拖到画布→
配置赋值)，用连线连成 DAG，另有表级默认决策。可确认它与决策表**共用同一套节点 DSL**（root/child/decision +
`conditionsGroup` + `decisions`），差异在于树允许**逐层多分支**（一个节点按不同条件挂多个子树），并可能额外携带
画布坐标。

> TODO（未验证）：D_TREE 的 `content` 是否用 `nodes[]/edges[]`+坐标，还是复用 `childNodes` 嵌套。需一棵
> "建好并发布"的决策树导出后锁定；在此之前，树类用例可按"根→叶每条路径展开成一条规则"近似处理。

## 3. 反推成策略落地文档

落地文档由
[tiance-testcase-generator](../../tiance-testcase-generator/scripts/parse_strategy_excel.py)
消费，其 sheet 与列为：规则集(规则集标识/名称/执行模式/规则数)、规则(规则编号/规则名称/所属规则集/
规则集标识/**规则表达式**/规则描述/**命中结果**/**命中后赋值**/**规则入参**/规则类型)、函数、
**字段映射**(字段显示名→系统编码)、**风险决策类型**、**三方数据接口**、决策流。决策工具映射如下：

| 决策工具要素 | → 落地文档 |
|---|---|
| 决策表节点 | 一条**规则**：`规则表达式`=conditionsGroup 拼接（all→AND / any→OR）；`命中后赋值`=`fieldName=value`；`规则入参`=inputData 字段；`所属规则集`=decisionCode/工具名 |
| 决策矩阵单元格 | 按 (Y值 × X分桶) **笛卡尔积展开**为多条规则；`规则表达式`=X条件 AND Y条件；`命中后赋值`=单元格决策 |
| 默认决策 `defaultDecisions` | 一条 else **兜底规则**（表达式="以上均不满足"） |
| inputData / outputData / systemFieldExportData | **字段映射** sheet（中文名→`C_/S_` 系统编码 + dataType） |
| 条件里的三方派生字段（如企查查类外数） | **三方数据接口** sheet |
| outputData 字段 + 各 `decision.value` 枚举 | **风险决策类型** sheet |

字段编码遵循天策格式 `{C|S}_{S|F|E|D|N|O}_{名}`（首段类型 + 次段 String/Float/Enum/Date/Number/Object）。

## 4. 用例设计（对齐五态与边界）

- 决策表：每个 `child` 行至少一条命中用例；对每个数值条件取**阈值 / 阈值±ε / 越界**三点；对 `isnull` 单独造空值用例；再加一条**全不命中→默认决策**用例。
- 决策矩阵：每个单元格一条用例（令 X 落对应桶、Y 取对应枚举值）；对每个 X 轴分桶边界取 ±ε；Y 轴每个枚举值各覆盖一次；加"某轴值越出所有桶→默认决策"用例。
- 决策树：每条根→叶路径一条用例（TODO：待 D_TREE schema 锁定后细化）。
- 命中判定以工具输出字段（如本例 `C_F_OUTLENDINGRATE` / `个人月收入919`）的**实际赋值**为准，纳入 通过/失败/执行阻塞/编排阻塞/无效用例 五态。

## 5. 执行与证据

1. 用运行区 `correlation` 查出**引用该决策工具的策略**，确认工具已上线（未上线时策略调用会编排阻塞）。
2. 编排顺序：**先导入/上线决策工具 → 再测引用它的策略**（工具是策略节点的依赖）。
3. 提交与取证据沿用通用链路（API 单笔/区间执行、httpOnly 场景走方式D 浏览器 fetch）；从平台
   `executeDetail`/节点结果中抽取"命中了哪个节点/单元格 + 写回字段值"作为决策链证据。
4. 三方派生字段（如外数/企查查）命中不稳定时，按 `testExecution.thirdPartyCapabilities` 标注
   `live_uncontrolled`，不自动提升为可执行。

## 6. decisionTool 契约键（策略配置内嵌）

在被测策略的 `strategies/*.json` 里，用 `decisionTool` 段声明所依赖的决策工具，语义复用现有
`testExecution.*`：

```json
"decisionTool": {
  "decisionCode": "TABLE…/METRIC…",
  "modelType": "D_TABLE | D_MATRIX | D_TREE",
  "inputs":  [{"name": "C_F_GEXX0043", "dataType": "double"}],
  "outputs": [{"name": "C_F_OUTLENDINGRATE", "dataType": "double"}],
  "rows":    [{"expr": "C_F_GEXX0043 <= 6", "assign": {"C_F_OUTLENDINGRATE": "7"}}],
  "axes":    {"x": [{"var": "个人月收入909", "buckets": [">=10000", "<100", ">=100 && <10000"]}],
               "y": [{"var": "业务代理人反洗钱评级", "values": ["通过", "拒绝"]}],
               "cells": {"通过": ["10000", "100", "1000"], "拒绝": ["20000", "100", "2000"]}},
  "defaultDecision": {"C_F_OUTLENDINGRATE": "0.25"},
  "requiredParams": ["C_F_GEXX0043"],
  "defaults": {"C_F_GEXX0043": 5}
}
```

`rows` 用于决策表、`axes/cells` 用于决策矩阵、`defaultDecision` 通用；`requiredParams`/`defaults` 与
`testExecution` 同义（提交前必备字段、用例缺字段时补的安全默认值）。

## 合规与注意

- 本文含真实客户数据（机构 `sxdb`/三峡担保、字段与工具编码），**只进 live 与私有归档，不进通用发布子集（staging）**。
- 任何文档/脚本中 Noah 主机一律写占位符 `<NOAH_HOST>`，禁止出现内网 IP 字面量与客户标签，避免触发
  `scripts/test_desensitized.py` 全树扫描。
