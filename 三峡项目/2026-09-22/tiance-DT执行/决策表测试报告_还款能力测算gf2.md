# 决策表测试报告 — 还款能力测算gf2

- 决策工具：还款能力测算gf2（决策表 D_TABLE）
- 标识 / 版本：`TABLE26062310321945640` / V1（uuid `be0d9140d50a41a0a22876fcac0fff9d`）
- 所属机构 / 渠道：sxdb / 初始应用（orgCode=sxdb）
- 执行方式：Noah 运行区「决策工具测试」debug 入口，`POST /noahApi/decisiontool/test`（引擎真实执行）
- 执行时间：2026-09-22

## 一、模型（导出解码反推）

输入 `C_F_GEXX0043`（评分卡评分，double）→ 输出 `C_F_OUTLENDINGRATE`（贷款利率，double）。

| 行 | 条件 | 赋值 |
|----|------|------|
| R1 | C_F_GEXX0043 ≤ 6 | C_F_OUTLENDINGRATE = 7 |
| R2 | C_F_GEXX0043 > 6 | C_F_OUTLENDINGRATE = 4 |
| R3 | C_F_GEXX0043 isnull | C_F_OUTLENDINGRATE = 0.3 |
| 默认 | 以上均不命中 | C_F_OUTLENDINGRATE = 0.25 |

## 二、用例设计与执行结果（五态）

| 用例 | 输入 | 期望命中 | 期望输出 | 实际输出 | 证据 | 五态 |
|------|------|----------|----------|----------|------|------|
| TC1 | 6.00（≤边界） | R1 | 7 | **7** | code:200, decisions.C_F_OUTLENDINGRATE="7" | 通过 |
| TC2 | 6.50（>边界） | R2 | 4 | **4** | code:200, decisions.C_F_OUTLENDINGRATE="4" | 通过 |
| TC3 | 3.00（≤区间内） | R1 | 7 | **7** | code:200, decisions.C_F_OUTLENDINGRATE="7" | 通过 |
| TC4 | 空值 | R3 | 0.3 | **0.3** | code:200, decisions.C_F_OUTLENDINGRATE="0.3" | 通过 |
| TC5 | 默认分支 | 默认 | 0.25 | 不可达 | — | 无效用例 |

结论：R1/R2/R3 三条命中路径均按边界正确赋值，执行成功、命中路径与决策值与落地文档一致。

## 三、关键发现

1. **默认决策 0.25 不可达**：输入域为 double，`≤6`、`>6`、`isnull` 三个条件已穷尽「任意实数 + 空值」，
   没有任何合法输入会落到默认分支。默认值 0.25 属死代码。若业务上默认值有意义，需复核是否漏配某段
   取值区间（例如负分、超上限）；若默认值仅为兜底占位，可维持现状但应知悉其永不触发。
2. **无引用策略**：correlation（`relationReference/relationAnalysis/decisionToolTree`）返回 `data: []`，
   当前没有任何策略引用本决策表。因此"经引用策略的 policyTest 全链路"暂无落地目标，本次改用决策工具
   自带 debug 入口对决策逻辑做端到端真实执行（等价验证决策表行/边界/赋值，不涉及策略编排层）。

## 四、边界与说明

- 本次为决策工具单点执行，未创建/上线/删除任何策略或组件，POC 平台状态零改动。
- 未覆盖：决策矩阵、决策树两类（本批样例仅决策表有可执行实例）；决策树字节级 schema 仍待补。
- 客户真实数据（评分卡评分/贷款利率字段、机构 sxdb）仅留存本地报告与私有归档，不进发布子集。
