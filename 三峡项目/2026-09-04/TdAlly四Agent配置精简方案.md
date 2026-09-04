# TdAlly 四 Agent 配置精简方案（合同迁移版）

日期：2026-09-04　状态：待执行（方案源自 09-01 会话分析，本文补全现状与验收）

## 一、现状与问题

| 项 | 数值 | 说明 |
|---|---|---|
| 四份运行配置合计 | 5,383 行 | 总控 V3 1345 / 执行 V2 1694 / 用例 V2 1142 / 审计 V2 1202 |
| Leader 单次唤醒 prompt | 44,000～47,000 tokens | 三次成功唤醒实测合计 137,809 |
| 最近一轮 Loop 墙钟 | 3 小时 34 分 | 其中等待占 84.8%，Agent 实际仅 32 分 40 秒 |
| 桌面"优化版" | 3 份（缺执行助手） | 1047/830/767 行，仍远高于目标，且未做合同外置 |

结论：运行版过长是额度消耗与响应变慢的主因之一；精简须做，但必须"迁移式压缩"，不得直接删约束。

## 二、精简目标

| Agent | 现状 | 目标 | 主要外置内容 |
|---|---:|---:|---|
| 总控 | 1345 | 300～450 | 编排事件表、GoalSpec 模板、历史踩坑 |
| 用例助手 | 1142 | 200～300 | 用例 JSON 示例、字段解释 |
| 执行助手 | 1694 | 400～600 | API/脚本细节、证据比对逻辑、错误码全表 |
| 审计助手 | 1202 | 200～300 | Manifest 完整 Schema、计数公式推导 |
| 合计 | 5,383 | 1,100～1,650 | Leader 上下文降至约 10,000～20,000 tokens |

## 三、分层结构（压缩≠删除）

```text
Agent 配置（精简运行版）        Skill（操作流程）           references/（公共合同）
├── 身份、职责、禁止事项        ├── 实际执行步骤            ├── common-task-contract-v3.md
├── taskMode 边界              ├── 脚本与 API 用法         ├── artifact-schemas-v3.json
├── 输入摘要与必需字段          ├── 证据比对逻辑            ├── status-and-counting-v3.md
├── 硬门禁清单                 └── 错误处理                ├── security-contract-v3.md
├── 停止条件                                              └── orchestration-events-v3.md
└── 回传合同（摘要级）
```

配置中必须写明："执行前完整读取 Skill 与指定 runtime-contract-v3；版本不一致即 blocked，不得沿用历史规则。"

### 不得删除的硬约束（16 项）

身份与禁止事项；taskMode 边界；taskId/attemptId/sessionId；expectedAgentId 与
reuseSession=false；输入必需字段；阶段状态与五状态；completed 硬门禁；401 判定；
Fixture cleanup 责任；runStatus=2 不等于通过；waiting_for_human；事件驱动等待；
超时与晚到结果处理；Manifest/输入指纹/消息去重；Worker 完成即退出；安全与凭据限制。

### 应外置到 Skill/references 的内容（9 类）

大段背景解释；重复 JSON 示例；错误码全表；Manifest 完整 Schema；状态字段解释；
API 与脚本命令细节；历史踩坑记录；各 Agent 重复的安全条款；重复的 Fixture/UUID/计数说明。

## 四、安全执行顺序（8 步）

1. 保留四份"可直接复制"版为规范基线，禁止覆盖；
2. 先升级 tiance-agent-loop skill（旧 v1.4 仍是生成+执行合并 Subagent 模式，
   不升级就精简总控会退回旧架构）；
3. 提取五份公共合同与 JSON Schema 到 references/；
4. 生成四份精简运行版（按第二节目标行数）；
5. 硬门禁自检脚本：16 项逐条 grep 校验，缺一项即失败；
6. precheck-only 空跑，验证任务派发与读取合同路径；
7. ≤10 条用例小批量验证分段、报告与 cleanup；
8. 跑一轮完整 Loop 对比耗时与额度。

## 五、验收标准

- 16 项硬门禁在精简版中 100% 存在（自检脚本输出全绿）；
- 跨 Agent 合同七项一致：Agent ID、taskId/attemptId/sessionId、execute 分段、
  五状态与 UUID 计数、三份 Manifest、总控→审计五状态传参、Markdown 结构；
- Leader 唤醒 prompt ≤20,000 tokens（平台按需用 reference 计）；
- 创建 Loop 到派发阶段 A ≤5 分钟；
- 单轮 GoalSpec max_iterations=1（持续模式 ≤3）；verify_commands 完全省略；
- 确认后禁止重复 loop_set_goalspec，状态查询走只读接口。

## 六、风险与回滚

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| 门禁被删 | 直接删减而非迁移 | 第 5 步自检脚本强制拦截 |
| 架构回退 | Skill 未升级先精简总控 | 第 2 步前置 |
| 合同漂移 | 三处版本不一致 | 配置内版本声明 + blocked 规则 |
| 示例缺失致产物错误 | JSON 示例外置后未读 | 配置声明必读 reference |
| 硬限制变建议 | 401/cleanup/重试语气弱化 | 精简版保留祈使句硬门禁 |

回滚：桌面基线四份不动，任何异常直接切回"可直接复制"版粘贴即可。

## 七、边界说明

GoalSpec 状态同步、只读状态接口、verify_commands 平台侧移除、单轮迭代上限四项
属 TdAlly 平台修改，随既有平台反馈清单走开发排期，不在本精简执行范围内；
平台未修复前，精简收益只体现在额度与响应速度，不体现在启动成功率。
