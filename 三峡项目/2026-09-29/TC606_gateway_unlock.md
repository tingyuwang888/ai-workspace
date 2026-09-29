# TC_606 编排阻塞根因纠正与分支解锁验证

日期：2026-09-29　环境：test03（保后检查决策服务_副本03，strategy=bhjcpostMainBefore v10）

## 结论先行

A 类 10 条编排阻塞（TC_606~TC_615）此前被判定为"ExclusiveGateway 互斥导致 basic/lawsuit 分支不可达"，该判断**是错误的**。企业子策略 `bhjcpostSubentBefore` v19（uuid `de0c19b678484ef6880798861c132da6`）的真实拓扑是**串行**：

```
[18个企查查/征信/预警通特征] → bhjcEntCreditAll
  → Gateway[211169] by C_S_BIZSCENARIO
      ├ 借款类 → bhjcEntNegativeLoan
      └ 债券/委贷/投资/非融 → 758或958特征 → bhjcEntNegativeBelni
  → Gateway[223686/226341/229969/221634/222069] by S_S_ENTERPRISETYPE
      ├ =="国企" → bhjcEntBasicFinancing*Soe
      ├ =="民营" → bhjcEntBasicFinancing*Priv
      └ 默认     → End   ★此前全部落到这里
  → bhjcEntLawsuit*（串行）→ [若民营] bhjcPrivateCounterGuarantee → End
```

Gateway 分支条件（实测 flowLine.attributes.condition）：

```json
{"property":"S_S_ENTERPRISETYPE","op":"==","value":"国企"}   // priority 1 → Soe
{"property":"S_S_ENTERPRISETYPE","op":"==","value":"民营"}   // priority 2 → Priv
{"isDefault":true}                                            // → End
```

## 真正根因

`S_S_ENTERPRISETYPE` 是脚本字段（S_ 前缀），由企业子策略里的 FunctionServiceNode `[脚本]企业信息对象取值`（functionUuid=S000010）赋值。该脚本对查询主体对象 `getFirstElement(C_O_ENTERPRISEINFO)`，**仅当对象含 `S_enterpriseType` 属性时才输出** `S_S_ENTERPRISETYPE`。

serviceConfigTest 调试器预置的 `C_O_ENTERPRISEINFO` 默认数组元素只有 `{S_enterpriseName, S_uscc}`，**没有 `S_enterpriseType`** → 脚本恒不输出 → `S_S_ENTERPRISETYPE` 为空 → Gateway 两条件都不满足 → 落 default → End，跳过整段 basic/lawsuit 分支。顶层"企业类型"标量与脚本读取的对象属性是两条不同路径，前者设了也传不到 Gateway。

## 修复方式（输入数据级，不碰平台配置，可完全回滚）

提交 serviceConfigTest 时给 `C_O_ENTERPRISEINFO` 数组元素补 `"S_enterpriseType":"国企"`，同时业务场景=借款类、企业类型标量=国企、唯一业务流水号。

## 验证证据（TC_606 借款类+国企，bizId=TC606_GW_1790676766281）

修复前 executedRuleSets：
`bhjcEntCreditAll, bhjcEntNegativeLoan, bhjcPerNegativeAll, bhjcPerLawsuitBni, bhjcRelatedRiskFinancingPriv, alertLevelJudgment`
unreached：`bhjcEntBasicFinancingSoe, bhjcEntLawsuitLoanSoe, bhjcRelatedRiskFinancingSoe`

修复后 executedRuleSets：
`bhjcEntCreditAll, bhjcEntNegativeLoan, `**`bhjcEntBasicFinancingSoe, bhjcEntLawsuitLoanSoe,`**` bhjcPerNegativeAll, bhjcPerLawsuitBni, bhjcRelatedRiskFinancingPriv`

→ **Basic 与 Lawsuit 分支均已到达**。finalDecisionCode=绿色（greenwarnbh），符合预期：分支到达≠规则命中，Soe 分支内规则因企查查 mock 对基础/诉讼特征仍返回空而未命中。

剩余 unreached：`bhjcRelatedRiskFinancingSoe`（属关联企业子策略 Soe 分支，需在关联主体对象里同样注入企业类型，独立问题）。

## 对 A 类解锁的意义

单点修复（补齐查询主体对象的 `S_enterpriseType`）即可把 A 类 10 条从"编排阻塞"一次性推进到"分支已到达、可测"。要翻红仍需按 V27-P2/P4 已跑通的 fixture 模式，给 `bhjcEntBasicFinancing*`（企业征信基础融资特征）与 `bhjcEntLawsuit*`（887裁判文书+741被执行人）注入负面命中数据。

## 证据文件

- `TC606_gateway_unlock_evidence.json`（serviceConfigTest/system 完整响应 150209 字节，sha256=20d105ff…299ca2）
