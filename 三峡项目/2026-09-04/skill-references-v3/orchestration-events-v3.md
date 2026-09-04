# 编排事件合同 v3（orchestration-events-v3）

## 1 事件驱动等待

- 主控与 Worker 之间只通过平台事件/完成通知推进，禁止轮询循环刷状态；
- Worker 完成即退出会话，不挂起等待下一指令；
- 晚到结果（阶段已关闭后到达的完成消息）记入 Manifest `lateArrivals`，
  不重开阶段、不改变计数，留待下一 attempt 参考。

## 2 超时与无进展

- 单阶段超时上限由平台配置；超时记 `failed: timeout` 并释放 Worker；
- `no_progress` 判定：连续工具调用无产物落盘变化达到阈值（默认 48 次）即
  `blocked: no_progress`，记录调用次数与最后产物时间戳；
- 超时/无进展后禁止原地无限重试：同一 attempt 最多重试 1 次，再失败转人工。

## 3 迭代与目标

- 单轮模式 `max_iterations=1`；持续优化模式 ≤3；禁止默认 20；
- GoalSpec 只描述目标、输入、输出、停止条件与核心验收，不重复 Agent 规则；
- GoalSpec 确认后禁止再次 `loop_set_goalspec`；状态查询走只读接口；
  确认状态矛盾时记录一次并停止，等待人工，不反复生成/发布。

## 4 verify_commands

- 完全省略 `verify_commands` 字段（磁盘与 GoalSpec 均不得出现）；
- 收尾校验改由 audit 阶段 Manifest 与自检脚本承担。

## 5 waiting_for_human

- 触发条件：门禁阻断、严重质量问题、凭据/会话失效、合同违约、收敛争议；
- 必须附：待决问题清单、可选动作、影响范围；挂起期间不消耗 Worker 会话。
