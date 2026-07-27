---
name: tiance-agent-loop
description: "AI 策略测试 Agent Loop 编排器。将 tiance-testcase-generator → tiance-policy-test → tiance-report-checker 串联为自动化闭环，支持触发检测、批量生成执行、质量校验、反馈优化四轮循环。当用户说'跑一轮完整的策略测试循环'、'Agent Loop'、'端到端测试'、'全自动测试循环'、'策略版本变更后重新测试'时触发。"
version: 1.4.0
---

# AI 策略测试 Agent Loop

## 概述

本技能编排三个下游技能形成自动化测试闭环，每轮迭代提升质量、减少人工介入。

**v1.4.0 架构**：采用「主会话编排 + Subagent 执行」分治模式。主会话仅负责触发判断、平台校验、收敛决策；批量执行和报告校验委托给独立 Subagent 完成，Subagent 只回传紧凑摘要（< 2KB），大块数据（用例 JSON、执行结果、Excel 报告）留在磁盘上，不进入主会话上下文。

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                     Agent Loop 循环 (v1.4)                       │
 │                                                                  │
 │  ╔══════════════ 主会话（编排层）══════════════╗                  │
 │  ║                                            ║                  │
 │  ║  ┌──────────┐   ┌──────────┐              ║                  │
 │  ║  │ Step 1   │──▶│ Step 1.5 │              ║                  │
 │  ║  │ 触发     │   │ 平台校验 │              ║                  │
 │  ║  └──────────┘   └────┬─────┘              ║                  │
 │  ║       ▲              │                     ║                  │
 │  ║       │         ┌────▼─────────────────┐   ║                  │
 │  ║  ┌────┴─────┐   │  spawn Subagent A    │   ║                  │
 │  ║  │ Step 4   │◀──│  Step 2: 生成+执行   │   ║                  │
 │  ║  │ 优化     │   │  回传: 摘要 JSON     │   ║                  │
 │  ║  └──────────┘   └────┬─────────────────┘   ║                  │
 │  ║       ▲              │                     ║                  │
 │  ║       │         ┌────▼─────────────────┐   ║                  │
 │  ║       └─────────│  spawn Subagent B    │   ║                  │
 │  ║                 │  Step 3: 报告校验    │   ║                  │
 │  ║                 │  回传: 摘要 JSON     │   ║                  │
 │  ║                 └──────────────────────┘   ║                  │
 │  ╚════════════════════════════════════════════╝                  │
 │                                                                  │
 │  磁盘: loop_workspace/{iteration}/  ← 用例/结果/报告/反馈       │
 └──────────────────────────────────────────────────────────────────┘
```

## 依赖技能

| 技能 | 角色 | 版本要求 |
|------|------|----------|
| `tiance-testcase-generator` | Step 2a: 解析落地方案 Excel → 生成测试用例 JSON+Excel | ≥ v2.3.0 |
| `tiance-policy-test` | Step 2b: 提交用例到天策 API → 生成测试报告 Excel | ≥ v2.1.0（含强制平台校验） |
| `tiance-report-checker` | Step 3: 4 维度质量检查 → 标注报告 + JSON 摘要 | ≥ v1.0.0 |

## 上下文管理与 Subagent 分治

### 问题背景

69 条用例的完整执行+验证+报告生成+质量检查会消耗大量上下文。600+ 条用例的大策略（如 DF_CONC_001）在单会话中几乎不可能跑到收敛。上下文膨胀会导致：指令遵循退化、工具调用参数出错、关键信息被挤出窗口。

### 分治原则

| 层级 | 职责 | 上下文占用 |
|------|------|-----------|
| **主会话** | 触发判断、平台校验、收敛决策、用户交互 | < 20% |
| **Subagent A**（Step 2） | 用例生成、批量提交、结果收集、报告生成 | 独立上下文 |
| **Subagent B**（Step 3） | 质量检查、问题标注、摘要生成 | 独立上下文 |

### 摘要回传契约

Subagent 完成后，**只**向主会话回传紧凑摘要（< 2KB），格式如下：

**Subagent A 回传（Step 2 执行摘要）**：
```json
{
  "status": "completed",
  "totalCases": 69,
  "submitted": 69,
  "passed": 69,
  "failed": 0,
  "errors": [],
  "reportPath": "loop_workspace/iteration_1/test_report.xlsx",
  "executionResultsPath": "loop_workspace/iteration_1/execution_results.json",
  "keyAnomalies": []
}
```

**Subagent B 回传（Step 3 校验摘要）**：
```json
{
  "status": "completed",
  "totalCases": 69,
  "totalIssues": 141,
  "byLevel": {"严重": 0, "警告": 0, "提示": 141},
  "topIssues": ["语义重复: 120", "数据完整性: 21"],
  "checkedReportPath": "loop_workspace/iteration_1/checked_report.xlsx",
  "checkResultPath": "loop_workspace/iteration_1/check_result.json",
  "convergeReady": true
}
```

### 关键规则

- **主会话禁止直接读取** execution_results.json、testcases.json 等大文件。需要了解详情时，通过 spawn 新 subagent 查询
- **Subagent 的 prompt 必须自包含**：包含所有必要参数（policyCode、version、bizType、文件路径），因为 subagent 无法访问主会话上下文
- **磁盘是唯一共享通道**：主会话和 subagent 通过 `loop_workspace/{iteration}/` 目录下的文件交换数据
- **Subagent 失败处理**：如果 subagent 返回 `status: "error"`，主会话应检查错误信息，决定是重试还是请求人工介入

### 何时不用 Subagent

- 用例数 ≤ 20 且无需深度验证时，可在主会话内直接执行（减少 spawn 开销）
- 用户明确要求"在当前会话里跑"时，尊重用户意愿，但提醒上下文风险

## Step 1: 触发 (Trigger)

### 触发方式

**方式 A — 策略版本变更检测（自动）**

读取策略配置文件中记录的 `policyVersion`，与上一次执行记录对比：

```bash
python3 ~/.qoderwork/skills/tiance-agent-loop/scripts/check_trigger.py \
  --strategy strategies/{policyCode}.json \
  --history loop_history/{policyCode}/history.json
```

输出 `trigger_context.json`：
```json
{
  "triggered": true,
  "policyCode": "DF_PRE_CONC_001",
  "oldVersion": 3,
  "newVersion": 4,
  "excelPath": "落地方案_v4.xlsx",
  "timestamp": "2026-07-09T15:00:00"
}
```

**方式 B — 手动触发**

用户直接提供策略编码和落地方案 Excel 路径，跳过版本检测。

### 人工介入点

- 首次触发需人工确认落地方案 Excel 文件路径
- 版本回退（newVersion < oldVersion）需人工确认是否继续

## Step 1.5: 平台校验（强制门禁）

> **无论本地配置文件是否存在、无论是否首次测试，每次进入 Step 2 之前必须执行此步骤。**

### 校验内容

通过浏览器执行 JS 查询天策平台 `/noahApi/policy/list?orgCode={orgCode}`，获取策略的实际状态：

```javascript
// 在已登录的天策平台页面执行
(async function(){
  var csrf = sessionStorage.getItem('_csrf_') || '';
  var resp = await fetch('/noahApi/policy/list?orgCode=' + orgCode, {
    headers: {'X-Cf-Random': csrf, '_csrf_': csrf}
  });
  var d = await resp.json();
  var p = (d.data || []).find(function(x){ return x.code === policyCode; });
  var pc = p ? (typeof p.publishConfig === 'string' ? JSON.parse(p.publishConfig) : p.publishConfig) : null;
  return JSON.stringify({
    policyCode: p ? p.code : 'NOT_FOUND',
    businessType: p ? p.businessType : null,       // 1=贷前 3=交易 4=贷中
    businessTypeName: p ? p.businessTypeName : null,
    status: p ? p.status : null,                    // 4=已发布
    statusName: p ? p.statusName : null,
    platformVersion: pc ? pc.ordinaryConfig.version : null
  });
})()
```

### 比对规则

| 比对项 | 本地配置值 | 平台实际值 | 不一致时处理 |
|--------|-----------|-----------|-------------|
| policyVersion | 配置文件中的 version | `publishConfig.ordinaryConfig.version` | **自动更新配置文件**，警告用户，使用平台值 |
| bizType | 配置文件中的 bizType | `businessType` | **自动更新配置文件**，警告用户，使用平台值 |
| status | — | `status` | 若非 4（已发布），暂停并警告用户 |

### 版本号规则

- 始终使用平台最新发布版本（`publishConfig.ordinaryConfig.version`），除非用户明确指定其他版本
- **禁止凭记忆或历史值填写版本号**
- 每次迭代循环开始前（包括从 Step 4 回到 Step 2 时）均需重新校验

### 踩坑记录

DF_PRE_CONC_001 实测中，本地配置文件 `policyVersion=1`（平台实际=2）、`bizType=4`（平台实际=1 贷前），导致首轮测试全部使用错误版本和业务类型，69条用例中7条失败、其余用例的判定结论也不可信。加入此门禁后，V2+贷前重测 69/69 全部通过。

## Step 2: 生成 + 执行 (Generate & Execute) — Subagent A

> **主会话不直接执行此步骤**。主会话负责准备参数、spawn Subagent A、接收摘要。

### 主会话操作

1. 确认 Step 1.5 平台校验已通过，记录 `policyVersion`、`bizType`、`orgCode`
2. 确认落地方案 Excel 路径（首轮）或 feedback.json 路径（后续轮次）
3. 使用 Agent 工具 spawn Subagent A，传入下方 prompt 模板
4. 等待 Subagent A 完成，解析回传摘要
5. 如果 `status === "error"`，检查错误并决定重试或人工介入

### Subagent A Prompt 模板

```
你是天策策略测试执行代理。请完成以下任务，最终只回传一个紧凑的 JSON 摘要。

## 任务参数
- policyCode: {policyCode}
- orgCode: {orgCode}
- policyVersion: {policyVersion}（已经过平台校验，直接使用）
- bizType: {bizType}（已经过平台校验，直接使用）
- 落地方案 Excel: {excelPath}（首轮）
- 反馈文件: {feedbackPath}（后续轮次，可选）
- 工作目录: {workspaceDir}
- 迭代轮次: {iteration}

## 执行步骤

### 2a: 用例生成
1. 读取 tiance-testcase-generator 技能（~/.qoderwork/skills/tiance-testcase-generator/SKILL.md）
2. 解析落地方案 Excel → parsed_strategy.json
3. 生成测试用例 → testcases.json + testcases.xlsx
4. 如有 feedback.json，通过 --feedback 参数注入

### 2b: 批量执行
1. 读取 tiance-policy-test 技能（~/.qoderwork/skills/tiance-policy-test/SKILL.md）
2. 按技能要求执行平台校验（双重保险）
3. 生成批量提交 JS，每批 ≤ 10 条，间隔 800ms
4. 通过浏览器 MCP javascript_tool 逐批提交
5. 收集执行结果 → execution_results.json
6. 对关键用例执行 getAllCompontlog 深度验证
7. 生成 Excel 测试报告 → test_report.xlsx

### 批量提交注意事项
- 每批 ≤ 10 条用例，避免 MCP 超时
- 如果 javascript_tool 超时，检查 window.__v3b.length 确认是否实际完成
- 超时不是失败，是 MCP 层面的限制

## 回传要求
完成后，你的最终回复必须且只包含以下 JSON（不要附加其他文字）：
{
  "status": "completed" | "error",
  "totalCases": <number>,
  "submitted": <number>,
  "passed": <number>,
  "failed": <number>,
  "errors": ["<error description>", ...],
  "reportPath": "{workspaceDir}/test_report.xlsx",
  "executionResultsPath": "{workspaceDir}/execution_results.json",
  "keyAnomalies": ["<anomaly description>", ...]
}
```

### 人工介入点

- 第一轮需人工确认 mock 配置是否正确（Subagent A 会在摘要中标注）
- 后续轮次自动复用上一轮 mock 配置
- 仅当新增规则需要新 mock 数据时才需介入

## Step 3: 校验 (Verify) — Subagent B

> **主会话不直接执行此步骤**。主会话负责 spawn Subagent B、接收摘要、做收敛决策。

### 主会话操作

1. 从 Subagent A 摘要中获取 `reportPath`
2. 使用 Agent 工具 spawn Subagent B，传入下方 prompt 模板
3. 等待 Subagent B 完成，解析回传摘要
4. 根据摘要中的 `byLevel` 做收敛判定（见下方表格）

### Subagent B Prompt 模板

```
你是天策策略测试报告质量检查代理。请完成以下任务，最终只回传一个紧凑的 JSON 摘要。

## 任务参数
- 测试报告路径: {reportPath}
- 工作目录: {workspaceDir}
- 迭代轮次: {iteration}

## 执行步骤
1. 读取 tiance-report-checker 技能（~/.qoderwork/skills/tiance-report-checker/SKILL.md）
2. 执行质量检查：
   python3 ~/.qoderwork/skills/tiance-report-checker/scripts/check_report.py \
     {reportPath} \
     -o {workspaceDir}/checked_report.xlsx \
     --json > {workspaceDir}/check_result.json
3. 解析 check_result.json，提取关键指标
4. 判断是否可以收敛（严重=0 且 警告<10 → convergeReady=true）

## 回传要求
完成后，你的最终回复必须且只包含以下 JSON（不要附加其他文字）：
{
  "status": "completed" | "error",
  "totalCases": <number>,
  "totalIssues": <number>,
  "byLevel": {"严重": <n>, "警告": <n>, "提示": <n>},
  "topIssues": ["<category>: <count>", ...],
  "checkedReportPath": "{workspaceDir}/checked_report.xlsx",
  "checkResultPath": "{workspaceDir}/check_result.json",
  "convergeReady": true | false
}
```

### 收敛判定（主会话执行）

| 条件 | 结果 |
|------|------|
| `严重` = 0 且 `警告` < 10 | **自动继续** → Step 4 |
| `严重` > 0 | **暂停** → 人工介入修复后继续 |
| 连续两轮 `totalIssues` 变化 < 5% | **收敛** → 输出最终报告 |

### 人工介入点

- 严重问题需人工判断是工具缺陷还是策略缺陷
- 人工核查标注（TC ID 中带括号批注）需人工确认处理方案

## Step 4: 优化 (Optimize)

### 反馈分析

```bash
python3 ~/.qoderwork/skills/tiance-agent-loop/scripts/analyze_feedback.py \
  --check-result loop_workspace/{iteration}/check_result.json \
  --checked-report loop_workspace/{iteration}/checked_report.xlsx \
  --test-report loop_workspace/{iteration}/test_report.xlsx \
  --output loop_workspace/{iteration+1}/feedback.json
```

### 反馈分类与动作映射

| 问题模式 | 根因 | 自动动作 |
|----------|------|----------|
| 目标规则未命中 | mock 数据不匹配 or ETL 覆盖 | 生成 `fixParams` 修正入参 |
| 判定矛盾（通过但实际未命中） | 验证标准宽松 or 预期结果错误 | 生成 `adjustExpected` 或标记 `manualReview` |
| 函数输出不匹配 | 预期值模板错误 | 生成 `adjustExpected` 修正函数预期 |
| 语义重复（同规则跨子策略） | 设计意图（正常） | 标记 `keepAsPair`，不重复生成 |
| 版本号不一致 | 策略版本更新后未重新提交 | 触发 `reSubmit` 用最新版本 |
| 策略报异常 | 入参格式错误 | 生成 `fixParams` 修正 JSON 格式 |
| 数据完整性缺失 | 列值为空 | 标记 `investigate`，人工检查 |

### 输出: feedback.json

```json
{
  "iteration": 2,
  "previousIssues": 524,
  "actions": [
    {
      "type": "fixParams",
      "target": "TC_188",
      "field": "C_F_REGCAP",
      "oldValue": 49990000,
      "newValue": 50000000,
      "reason": "EBGS11 未命中: 注册资本需 >= 5000万(元)而非万元"
    },
    {
      "type": "adjustExpected",
      "target": "TC_235",
      "field": "expected",
      "newValue": "C_N_HIGHRISKHITCOUNT=0, C_N_MEDIUMRISKHITCOUNT=0",
      "reason": "S000002 空字符串输入预期应为所有计数=0"
    },
    {
      "type": "manualReview",
      "target": "TC_307",
      "reason": "函数输出值异常，需人工确认持股公司循环函数的正确返回值"
    }
  ],
  "summary": {
    "autoFixable": 15,
    "manualReview": 8,
    "keepAsPair": 480,
    "estimatedNextIssues": 30
  }
}
```

## 迭代控制

### 工作目录结构

```
loop_workspace/
├── iteration_1/
│   ├── parsed_strategy.json
│   ├── testcases.json
│   ├── testcases.xlsx
│   ├── test_report.xlsx
│   ├── checked_report.xlsx
│   ├── check_result.json
│   └── feedback.json          → 传递给 iteration_2
├── iteration_2/
│   ├── feedback.json          ← 来自 iteration_1
│   ├── testcases.json         ← 含反馈修正
│   ├── test_report.xlsx
│   ├── checked_report.xlsx
│   ├── check_result.json
│   └── feedback.json          → 传递给 iteration_3
└── convergence.json           ← 收敛追踪
```

### 收敛追踪: convergence.json

```json
{
  "policyCode": "DF_PRE_CONC_001",
  "iterations": [
    {"round": 1, "cases": 652, "issues": 524, "severe": 0, "warning": 15, "info": 509},
    {"round": 2, "cases": 645, "issues": 30, "severe": 0, "warning": 5, "info": 25},
    {"round": 3, "cases": 645, "issues": 28, "severe": 0, "warning": 3, "info": 25}
  ],
  "converged": true,
  "convergeRound": 3,
  "finalReport": "iteration_3/checked_report.xlsx"
}
```

### 终止条件

| 条件 | 行为 |
|------|------|
| 连续两轮 issues 变化 < 5% | 收敛，输出最终报告 |
| 达到最大轮次（默认 5） | 停止，输出当前最优报告 |
| 严重问题无法自动修复 | 暂停，等待人工介入 |

### 人工介入递减预期

| 轮次 | 预期人工介入量 | 说明 |
|------|----------------|------|
| 第 1 轮 | 高 | 初始 mock 配置、策略理解、异常处理 |
| 第 2 轮 | 中 | 修复反馈标记的 manualReview 项 |
| 第 3 轮 | 低 | 仅剩边界场景确认 |
| 第 4+ 轮 | 极低 | 基本全自动 |

## 快速启动

### 完整循环（推荐）

```
用户: "跑一轮完整的策略测试循环，策略编码 DF_PRE_CONC_001，落地方案在 ~/Downloads/落地方案_v4.xlsx"
```

Agent 执行流程：
1. 读取 `tiance-agent-loop` 技能
2. Step 1: 检查触发条件（或直接开始）
3. Step 1.5: 平台校验（强制门禁）
4. spawn Subagent A → Step 2: 生成用例 + 批量执行 → 回传摘要
5. spawn Subagent B → Step 3: 报告质量检查 → 回传摘要
6. Step 4: 主会话分析摘要 → 生成 feedback.json
7. 判断是否收敛 → 不收敛则重新 spawn Subagent A（带 feedback）

### 单步执行

```
用户: "只跑校验这一步，报告在 ~/Downloads/测试报告.xlsx"
```

### 从反馈继续

```
用户: "上一轮的反馈已经确认了，继续跑下一轮"
```

## 脚本版本要求

| 脚本 | 最低版本 | 关键特性 |
|------|---------|---------|
| `execute_tests.py` | v1.1.0 | 增量保存、断点续跑（`--resume`） |
| `analyze_feedback.py` | v1.1.0 | JSON 损坏保护、空 issues 早退出、`--test-report` 参数 |
| `platform_check.py` | v1.0.0 | Step 1.5 平台校验门禁 |
| `orchestrator.py` | v1.3.0 | Step 1.5 集成、`--skip-platform-check` 标志 |
| `merge_results.py` | v1.0.0 | 结果回填 Excel |
| `check_trigger.py` | v1.0.0 | 触发检测 |

## 已知限制

- platform_check.py 依赖 requests 库；若未安装则回退到 urllib（功能等价但无连接池）
- execute_tests.py 的 `--resume` 仅跳过已完成的用例 ID，不验证已有结果的时效性（如策略版本变更后旧结果可能失效）
- analyze_feedback.py 的分类器基于关键词匹配，对新类型的问题可能落入 `investigate` 兜底
- SKILL.md 中描述的 Subagent 架构需要 Agent 工具（QoderWork 的 Task tool），纯 orchestrator.py 脚本模式不支持 Subagent 分治
- 平台校验（Step 1.5）需要已登录的浏览器会话或有效 Cookie，离线环境无法执行

## 注意事项

- **平台校验是最高优先级门禁**：Step 1.5 和 tiance-policy-test Step 1 形成双重校验，确保 policyVersion 和 bizType 始终与平台一致。任何情况下都不允许跳过此步骤
- **Subagent 是上下文管理的核心手段**：Step 2 和 Step 3 必须通过 subagent 执行（用例数 > 20 时），主会话只接收 < 2KB 的摘要 JSON。这确保 600+ 条用例的大策略也能在单会话中完成多轮迭代
- **Subagent prompt 必须自包含**：subagent 无法访问主会话的上下文，所有必要参数（policyCode、version、bizType、文件路径）必须在 prompt 中显式传入
- 每轮迭代的 API 提交会覆盖上一轮的测试记录（同 policyCode+version），DB 中保留最新结果
- mock 配置在轮次间复用，除非反馈明确要求修改
- 语义重复类问题（跨子策略对应规则）是设计意图，不会被自动消除
- 人工核查标注（TC ID 带括号批注）在后续轮次中会被保留，直到问题修复后清除
- `--feedback` 参数是 generator v2.3.0+ 的可选扩展，不传则按默认逻辑生成
- 本地策略配置文件中的 policyVersion 和 bizType 仅作为缓存参考，每次测试前必须以平台 `/noahApi/policy/list` 返回值为准
