---
name: tiance-agent-loop
description: "天策策略测试分阶段闭环编排器（v2.0，runtime-contract-v3）。定义 A-H 八阶段闭环与四角色合同，QoderWork 主会话编排与 TdAlly 四 Agent 平台编排共用同一合同；串联 tiance-testcase-generator → tiance-policy-test → tiance-report-checker。当用户说'跑一轮完整的策略测试循环'、'Agent Loop'、'端到端测试'、'全自动测试循环'、'策略版本变更后重新测试'时触发。"
version: 2.0.0
---

# 天策策略测试分阶段闭环（v2.0）

## 概述

v1.4 的"生成+执行合并 Subagent"已废弃。v2.0 与总控 V3 对齐：生成（B）与
执行（D）拆为独立阶段，各阶段有独立 Manifest、独立会话（reuseSession=false）
与硬门禁；四角色（总控/用例助手/执行助手/审计助手）在 QoderWork 本地表现为
主会话+Subagent，在 TdAlly 平台表现为四个固定 Agent，合同完全一致。

## 强制读取与版本钉

执行任何阶段前必须完整读取以下 reference；声明版本非 `runtime-contract-v3`
或读取失败即 `blocked`，不得沿用历史规则继续：

| 文件 | 内容 |
|---|---|
| references/common-task-contract-v3.md | 任务身份、taskMode、派发/回传合同、指纹与去重 |
| references/artifact-schemas-v3.json | 各 Manifest 与摘要 Schema、计数等式 |
| references/status-and-counting-v3.md | 五状态定义与计数硬合同 |
| references/security-contract-v3.md | 凭据、环境边界、行为禁令、安全审计 |
| references/orchestration-events-v3.md | 事件驱动等待、超时/无进展、迭代上限、verify_commands 省略 |

## 阶段闭环总览

| 阶段 | 名称 | _owner（本地/平台） | 输出 Manifest | 硬门禁 |
|---|---|---|---|---|
| A | 平台门禁 | 总控 | precheck_result + platform_snapshot | 快照 ≤10 分钟；status=4 |
| B | 用例生成 | 用例助手 | generationManifest | 四模块覆盖矩阵；excluded 显式列明 |
| C | Fixture 准备 | 执行助手 | fixtureManifest | 新 fixtureRunId；连接与清理范围确认 |
| D | 执行与证据 | 执行助手 | executionManifest | 每 10 条分段；401 停；runStatus=2≠通过 |
| E | 报告生成 | 执行助手 | reportPath + 计数 | 五状态等式成立 |
| F | 报告审计 | 审计助手 | auditManifest | 安全违约非空即停 |
| G | 收敛决策 | 总控 | convergence.json | 严重>0 暂停 |
| H | 清理收尾 | 执行助手 | cleanupResultPath | 未清理不得 completed |

## 阶段合同

### A 平台门禁
- 每次进入 B 之前必做；查询平台元数据核对 policyVersion/bizType/status；
- 接口不可用时从已登录浏览器导出完整响应生成快照，快照超 10 分钟阻断；
- 禁止凭记忆填版本号；禁止复用上一轮快照；无跳过参数。

### B 用例生成
- 消费落地方案 Excel（首轮）或 feedback.json（后续轮）；
- 产出 testcases.json/xlsx 与 generationManifest；`generatedCaseCount` 以此为准；
- 不生成超时/错误码/字段类型等 Mock 异常用例；排除项写入 `excluded` 及原因。

### C Fixture 准备
- 每轮新 `fixtureRunId`，禁止复用上一轮隔离键；
- 首轮需人工确认数据库连接、隔离键与清理范围（见安全合同）。

### D 执行与证据
- 按 `execute_tests.py` 分段执行，默认每 10 条一段，段状态入 Manifest `segments`；
- 对需要规则/函数/三方证据的用例查询组件日志，只认平台返回与日志；
- 401 计入 execution_failed 并触发会话健康检查；`--resume` 仅复用同版本同隔离态结果。

### E 报告生成
- 合并执行结果生成 15 列 Excel 报告；只回填平台证据，不从 expected 反推；
- 报告计数必须满足五状态等式，不满足即 `counting_inconsistent` 重出。

### F 报告审计
- 执行 `check_report.py` 产出 checked_report 与 check_result；
- 按 security-contract 检查全部落盘产物凭据泄漏；`securityViolations` 非空即暂停；
- 收敛建议 `convergeReady`：严重=0 且警告<10。

### G 收敛决策与反馈
- 总控依 auditManifest 判定：严重=0 且警告<10 → 继续/收敛；严重>0 → 暂停人工；
- 连续两轮 totalIssues 变化 <5% → 收敛，输出最终报告；
- 反馈分类映射：未命中→fixParams/重建 Fixture；判定矛盾→adjustExpected/manualReview；
  函数不匹配→adjustExpected；语义重复→keepAsPair；版本不一致→reSubmit；
  数据缺失→investigate。

### H 清理收尾
- Fixture 清理并回传 cleanupResultPath；未清理该阶段不得 completed；
- 数据源若本轮切换过，按九步流程恢复并复核后才允许收尾完成。

## 五状态与计数（硬合同摘要）

passed/failed/inconclusive/skipped/execution_failed 五状态之和 =
generatedCaseCount；submitted = 报告有效 UUID 数 = passed+failed+inconclusive+
execution_failed。细则与判定规则见 status-and-counting-v3.md。

## 摘要回传合同

Worker 只回传 <2KB 摘要 JSON（schema 见 artifact-schemas-v3.json summarySchema）：
status/phase/counts/artifactPaths/errors。大块数据一律落盘 workspaceDir，
摘要只给路径与计数；回传禁止含凭据。

## 迭代控制

- 单轮 max_iterations=1；持续优化 ≤3；目录 loop_workspace/iteration_N/；
- 收敛追踪 convergence.json（round/cases/issues/severe/warning/info）；
- 终止：收敛 / 达最大轮次输出当前最优 / 严重问题无法自动修复暂停。

## 硬门禁清单（16 项，自检脚本逐条校验）

身份与禁止事项；taskMode 边界；taskId/attemptId/sessionId；expectedAgentId 与
reuseSession=false；输入必需字段；阶段状态与五状态；completed 硬门禁；401 判定；
Fixture cleanup 责任；runStatus=2 不等于通过；waiting_for_human；事件驱动等待；
超时与晚到结果处理；Manifest/输入指纹/消息去重；Worker 完成即退出；安全与凭据限制。

## 人工介入点

首轮 Fixture 确认；版本回退确认；严重质量问题定性；凭据/会话失效；门禁阻断后的
配置更新；收敛争议；数据源切换与恢复（用户操作）。

## QoderWork 本地编排模式

- 主会话=总控：触发、A 门禁、G 收敛、H 确认；B/D/F 分别 spawn Subagent；
- Subagent prompt 必须自包含（policyCode/orgCode/version/bizType/路径/iteration）；
- 磁盘 loop_workspace 是唯一共享通道；主会话禁止直读大文件，详情另 spawn 查询；
- 用例数 ≤20 且用户要求时可在主会话直跑，但须提醒上下文风险。

## 快速启动

- 完整循环："跑一轮完整的策略测试循环，策略 DF_PRE_CONC_001，落地方案 <path>"
- 单阶段："只跑校验，报告 <path>" / "只做平台门禁预检"
- 从反馈继续："上一轮反馈已确认，继续下一轮"

## 脚本版本要求

| 脚本 | 最低版本 | 关键特性 |
|---|---|---|
| tiance-policy-test/scripts/execute_tests.py | v2.0.0 | 门禁、预检、Fixture、证据断言、断点续跑 |
| analyze_feedback.py | v1.1.0 | JSON 损坏保护、空 issues 早退出 |
| platform_guard.py | 当前 | 统一门禁解析，快照校验 |
| merge_results.py | v2.1.0 | 只回填平台证据 |
| check_trigger.py | v1.0.0 | 版本变更触发检测 |

## 已知限制

- 平台门禁需已登录浏览器会话或有效 Cookie，离线不可执行；
- analyze_feedback 分类器基于关键词，新类型问题落 investigate 兜底；
- TdAlly 平台侧（GoalSpec 状态同步、只读查询接口）未修复前，启动成功率不受本
  技能版本影响；verify_commands 已按合同省略，收尾校验由 F/H 承担。
