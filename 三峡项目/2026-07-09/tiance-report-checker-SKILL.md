---
name: tiance-report-checker
description: >
  天策策略测试报告自动化质量检查工具。
  对已生成的测试报告 Excel 进行多维度质量体检，自动检测判定矛盾、数据缺失、
  语义重复、实际结果异常等问题，在原 Excel 上新增"质量检查"Sheet 并标注每行问题。
  支持独立运行（用户说"检查一下这个报告"）和嵌入 tiance-policy-test 流水线自动调用。
  当用户提到"检查测试报告"、"报告质量检查"、"测试报告有什么问题"、"报告体检"、
  "检查一下这个Excel"、"质量检查"、"报告审查"时触发。
version: 1.0.0
---

# 天策策略测试报告质量检查器 v1.0.0

对天策策略测试报告 Excel 执行四维度自动化质量检查，输出带标注的 Excel 文件。

## 检查维度

### 维度一：判定一致性
- 目标规则预期命中但实际未命中，状态却标为"通过"
- 实际结果含异常/错误关键词（报异常、执行失败等）但标为"通过"
- 通过/未通过但实际结果列为空

### 维度二：数据完整性
- 关键列空值（用例编号、用例名称、预期结果、测试状态）
- TC编号连续性（检测缺号）和重复编号
- policyVersion 与文件名版本号一致性
- 测试时间格式统一性
- 用例编号含人工批注/备注
- 规则类用例三方数据列空值

### 维度三：语义重复检测
- 同模块内预期结果完全相同的用例组（可能是边界用例与正常用例重复）
- 名称相似度 >85% 的用例对（通常是跨子策略对应规则，如 EBGS/EBGP）

### 维度四：实际结果质量
- 函数类用例：实际结果中记录的函数与预期目标函数不匹配（高频问题）
- 规则类用例：目标规则未命中但有伴随命中（可能mock数据问题）
- 预期与实际风险等级不一致（且目标规则未命中时）
- 实际结果含错误/异常关键词

## 使用方式

### 方式一：独立运行（用户主动调用）

```bash
python3 ~/.qoderwork/skills/tiance-report-checker/scripts/check_report.py <报告.xlsx> [-o 输出.xlsx]
```

**CLI参数：**
- `input`（必选）：输入的 Excel 测试报告路径
- `-o / --output`：输出文件路径，默认 `原文件名_checked.xlsx`
- `--json`：以 JSON 格式输出检查摘要（供流水线消费）

### 方式二：嵌入流水线（tiance-policy-test 自动调用）

在 tiance-policy-test 的 Excel 报告生成步骤后，自动调用：

```python
import sys
sys.path.insert(0, os.path.expanduser('~/.qoderwork/skills/tiance-report-checker/scripts'))
from check_report import check_report

result = check_report(report_path)
# result['total_issues'] — 问题总数
# result['by_level'] — 按严重级别统计
# result['output_path'] — 标注后的文件路径
```

### 方式三：Agent 内调用

当用户说"检查一下这个测试报告"时，Agent 执行：

```bash
python3 ~/.qoderwork/skills/tiance-report-checker/scripts/check_report.py "<报告路径>" -o "<输出路径>"
```

然后读取终端输出的摘要信息向用户汇报。

## 输出格式

在原 Excel 上增加：

1. **每个原始 Sheet**：最后一列新增"质量问题"列，行级标注该行发现的问题，按严重程度着色（红=严重、黄=警告、绿=提示）
2. **"质量检查"汇总 Sheet**（插入首位）：
   - 统计摘要（用例总数、问题数、各级别/维度分布）
   - 问题明细表（按严重级别排序：严重 > 警告 > 提示）

## 报告格式支持

自动检测两种列格式：
- **15列格式**：tiance-testcase-generator 生成 + tiance-policy-test 回填
- **自定义格式**：通过关键列名（用例编号/预期结果/实际结果/测试状态）自动映射

## 严重级别定义

| 级别 | 含义 | 典型场景 |
|------|------|----------|
| 严重 | 数据错误，影响报告可信度 | 通过判定矛盾、编号重复、函数输出错误 |
| 警告 | 数据可疑，需人工确认 | 版本不一致、伴随命中、风险等级差异 |
| 提示 | 规范性问题，不影响正确性 | 编号不连续、时间格式不统一、批注残留 |

## 与现有 Skill 的关系

```
tiance-testcase-generator → 生成用例 JSON+Excel
        ↓
tiance-policy-test → 批量提交执行 → 回填结果到 Excel 报告
        ↓
tiance-report-checker → 对报告做质量体检 → 输出标注后的 Excel（本 Skill）
```

建议将 tiance-report-checker 作为 tiance-policy-test 流水线的最后一步自动调用。
