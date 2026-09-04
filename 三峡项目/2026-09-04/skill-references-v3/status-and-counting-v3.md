# 五状态与计数合同 v3（status-and-counting-v3）

## 1 五种用例状态

| 状态 | 定义 | 来源 |
|---|---|---|
| `passed` | 提交成功且断言与证据均支持预期 | 执行+证据比对 |
| `failed` | 提交成功但断言或证据与预期矛盾 | 执行+证据比对 |
| `inconclusive` | 提交成功但证据缺失/不可判定 | 证据比对 |
| `skipped` | 未提交（mock 不支持、设计排除等） | 生成/执行前置 |
| `execution_failed` | 提交或执行环节错误（含 401、超时、接口异常） | 执行器 |

## 2 计数公式（硬合同）

```text
passed + failed + inconclusive + skipped + execution_failed = generatedCaseCount
submitted = 报告中具有有效 UUID 的用例数量
submitted = passed + failed + inconclusive + execution_failed
```

- 任何 Manifest / 摘要 / 报告不满足上述等式即 `counting_inconsistent`，
  主控停止收敛判定并要求重出报告；
- 禁止用三状态公式（submitted+skipped+execution_failed）代替五状态之和；
- `generatedCaseCount` 以 generation Manifest 为准，执行侧不得改写。

## 3 判定硬规则

- `runStatus=2` 只代表执行完成，**不等于通过**，不得直接计入 passed；
- `assertionStatus=inconclusive` 必须单独统计，不得并入 passed/failed；
- 401 响应计入 `execution_failed` 并触发会话健康检查，禁止静默重试超过 1 次；
- UUID 重复的用例只计一次，重复项记 `duplicate_ignored`；
- 证据比对只认平台返回与组件日志，不得从 expected 反推实际结果。

## 4 覆盖率摘要

覆盖率摘要（规则/函数/决策流/预警等级四模块覆盖矩阵）为可选产物；存在时
Assignment 与 audit Manifest 必须携带其路径；不存在时显式写
`coverageSummaryPath: null`，不得留空字段。
