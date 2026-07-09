---
name: tiance-agent-loop
description: "AI 策略测试 Agent Loop 编排器。将 tiance-testcase-generator → tiance-policy-test → tiance-report-checker 串联为自动化闭环，支持触发检测、批量生成执行、质量校验、反馈优化四轮循环。当用户说'跑一轮完整的策略测试循环'、'Agent Loop'、'端到端测试'、'全自动测试循环'、'策略版本变更后重新测试'时触发。"
version: 1.0.0
---

# AI 策略测试 Agent Loop

## 概述

本技能编排三个下游技能形成自动化测试闭环，每轮迭代提升质量、减少人工介入。

```
 ┌─────────────────────────────────────────────────────────┐
 │                   Agent Loop 循环                        │
 │                                                         │
 │  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
 │  │ Step 1   │───▶│ Step 2   │───▶│ Step 3   │          │
 │  │ 触发     │    │ 生成+执行 │    │ 校验     │          │
 │  └──────────┘    └──────────┘    └────┬─────┘          │
 │       ▲                               │                 │
 │       │          ┌──────────┐         │                 │
 │       └──────────│ Step 4   │◀────────┘                 │
 │                  │ 优化     │                            │
 │                  └──────────┘                            │
 └─────────────────────────────────────────────────────────┘
```

## 依赖技能

| 技能 | 角色 | 版本要求 |
|------|------|----------|
| `tiance-testcase-generator` | Step 2a: 解析落地方案 Excel → 生成测试用例 JSON+Excel | ≥ v2.3.0 |
| `tiance-policy-test` | Step 2b: 提交用例到天策 API → 生成测试报告 Excel | ≥ v2.0.0 |
| `tiance-report-checker` | Step 3: 4 维度质量检查 → 标注报告 + JSON 摘要 | ≥ v1.0.0 |

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

## Step 2: 生成 + 执行 (Generate & Execute)

### 2a: 用例生成（调用 tiance-testcase-generator）

1. 解析落地方案 Excel：
   ```bash
   python3 ~/.qoderwork/skills/tiance-testcase-generator/scripts/parse_strategy_excel.py \
     "{excelPath}" -o loop_workspace/{iteration}/parsed_strategy.json
   ```

2. 确认解析结果摘要（人工或自动）

3. 生成测试用例（如有反馈配置则传入）：
   ```bash
   python3 ~/.qoderwork/skills/tiance-testcase-generator/scripts/generate_testcases.py \
     loop_workspace/{iteration}/parsed_strategy.json \
     --output loop_workspace/{iteration}/testcases.json \
     --excel-output loop_workspace/{iteration}/testcases.xlsx \
     --feedback loop_workspace/{iteration}/feedback.json  # 来自上一轮
   ```

4. **反馈注入点**：`--feedback` 参数接收上一轮的分析结果，影响生成逻辑：
   - `fixParams`: 修正特定用例的入参值
   - `addBoundary`: 为指定规则增加边界用例
   - `removeCases`: 移除持续失败的无效用例
   - `adjustExpected`: 调整预期结果模板

### 2b: 测试执行（调用 tiance-policy-test）

1. 加载策略配置 → 获取当前 `policyVersion`
2. 通过 `submit_batch.js` 批量提交用例
3. 多层验证（6 级）
4. 增量更新 Excel 报告

```
输出: loop_workspace/{iteration}/test_report.xlsx
```

### 人工介入点

- 第一轮需人工确认 mock 配置是否正确
- 后续轮次自动复用上一轮 mock 配置
- 仅当新增规则需要新 mock 数据时才需介入

## Step 3: 校验 (Verify)

### 调用 tiance-report-checker

```bash
python3 ~/.qoderwork/skills/tiance-report-checker/scripts/check_report.py \
  loop_workspace/{iteration}/test_report.xlsx \
  -o loop_workspace/{iteration}/checked_report.xlsx \
  --json > loop_workspace/{iteration}/check_result.json
```

### 输出结构

```json
{
  "total_cases": 652,
  "total_issues": 524,
  "by_level": {"严重": 0, "警告": 15, "提示": 509},
  "by_category": {"语义重复": 480, "版本不一致": 15, ...},
  "affected_rows": 520,
  "check_time": "2026-07-09 15:30:00"
}
```

### 收敛判定

| 条件 | 结果 |
|------|------|
| `严重` = 0 且 `警告` < 10 | **自动继续** → Step 4 |
| `严重` > 0 | **暂停** → 人工介入修复后继续 |
| 连续两轮 `total_issues` 变化 < 5% | **收敛** → 输出最终报告 |

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
3. Step 2: 依次调用 generator → policy-test
4. Step 3: 调用 report-checker
5. Step 4: 分析反馈 → 生成 feedback.json
6. 判断是否收敛 → 不收敛则回到 Step 2

### 单步执行

```
用户: "只跑校验这一步，报告在 ~/Downloads/测试报告.xlsx"
```

### 从反馈继续

```
用户: "上一轮的反馈已经确认了，继续跑下一轮"
```

## 注意事项

- 每轮迭代的 API 提交会覆盖上一轮的测试记录（同 policyCode+version），DB 中保留最新结果
- mock 配置在轮次间复用，除非反馈明确要求修改
- 语义重复类问题（跨子策略对应规则）是设计意图，不会被自动消除
- 人工核查标注（TC ID 带括号批注）在后续轮次中会被保留，直到问题修复后清除
- `--feedback` 参数是 generator v2.3.0+ 的可选扩展，不传则按默认逻辑生成
