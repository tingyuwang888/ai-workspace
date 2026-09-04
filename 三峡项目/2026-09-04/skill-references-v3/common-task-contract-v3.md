# 公共任务合同 v3（common-task-contract-v3）

合同版本：`runtime-contract-v3`。任何 Agent 配置 / Skill / GoalSpec 引用本合同时
必须显式声明版本；读取失败或版本不一致即 `blocked`，不得沿用历史规则继续。

## 1 任务身份

| 字段 | 语义 | 规则 |
|---|---|---|
| `taskId` | 一轮 Loop 的唯一标识 | 创建时生成，全轮不变 |
| `attemptId` | 同一 taskId 下的重试序号 | 每次重试递增，不覆盖旧 attempt 产物 |
| `sessionId` | Worker 一次会话标识 | `reuseSession=false`：每个阶段新会话 |
| `expectedAgentId` | 派发目标 Agent 的固定 ID | 四个 Agent ID 全轮一致，不得动态替换 |
| `runId` / `fixtureRunId` | 执行与 Fixture 隔离键 | 每轮新建，禁止复用上一轮 |
| `iteration` | 收敛迭代轮次 | 与 loop_workspace/iteration_N 对应 |

## 2 taskMode 边界

`precheck_only` / `generate` / `execute` / `audit` / `full` 五选一。Worker 只执行
本 mode 声明的阶段；越界动作（如 generate mode 里提交用例）视为违约，主控记
`contract_violation` 并停止派发。

## 3 派发参数合同（主控 → Worker）

Assignment 必须传入：`reportPath`、`reportStageResultPath`、`cleanupResultPath`、
策略身份（policyCode/orgCode/policyVersion/bizType）、`runId`、`iteration`、
`workspaceDir`、`generatedCaseCount`、`passed`、`failed`、`inconclusive`、
`submitted`、`skipped`、`executionFailed`，以及存在的覆盖率摘要路径。
缺任一必需字段，Worker 返回 `blocked: missing_assignment_field`，不得猜测填充。

## 4 回传合同（Worker → 主控）

只回传紧凑摘要 JSON（< 2KB），字段见 artifact-schemas-v3.json 的
`summarySchema`。大块数据（用例、结果、报告）一律落盘 `workspaceDir`，
摘要中只给路径与计数。回传中禁止包含凭据、Cookie、数据库密码。

## 5 输入指纹与消息去重

- `inputFingerprint = sha256(排序后的必需输入字段序列化)`，写入各 Manifest；
  指纹不一致的复用产物视为无效。
- 同一 `(taskId, attemptId, phase)` 的重复完成消息只处理第一次，后续记
  `duplicate_ignored`，不重复计数、不重复落盘。

## 6 阶段状态机

`pending → dispatched → running → completed | failed | blocked | waiting_for_human`。
`completed` 必须附 Manifest 路径与计数；`blocked` 必须附原因码；
`waiting_for_human` 必须附待决问题清单。状态只允许单向推进，回退需新 attempt。
