#!/usr/bin/env python3
"""
tiance-agent-loop Orchestrator v1.0.0
多轮自动编排：触发 → 生成 → (暂停执行) → 校验 → 反馈 → 收敛判定

Step 1/2a/3/4 全自动，Step 2b（测试执行）为暂停点。
支持断点续跑（--resume）和直接注入报告（--report）。

用法:
  # 全新循环
  python3 orchestrator.py --strategy strategies/X.json --excel 落地方案.xlsx

  # 断点续跑（自动检测最新未完成的迭代）
  python3 orchestrator.py --resume

  # 跳过执行步骤，直接注入已有报告
  python3 orchestrator.py --strategy strategies/X.json --report 测试报告.xlsx

  # 指定工作目录
  python3 orchestrator.py --strategy strategies/X.json --workspace loop_workspace
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# 路径常量
# ============================================================

SKILLS_DIR = Path.home() / '.qoderwork' / 'skills'

SCRIPTS = {
    'trigger':    SKILLS_DIR / 'tiance-agent-loop' / 'scripts' / 'check_trigger.py',
    'parse':      SKILLS_DIR / 'tiance-testcase-generator' / 'scripts' / 'parse_strategy_excel.py',
    'generate':   SKILLS_DIR / 'tiance-testcase-generator' / 'scripts' / 'generate_testcases.py',
    'check':      SKILLS_DIR / 'tiance-report-checker' / 'scripts' / 'check_report.py',
    'feedback':   SKILLS_DIR / 'tiance-agent-loop' / 'scripts' / 'analyze_feedback.py',
}


# ============================================================
# 工具函数
# ============================================================

def log(msg, level='INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'[{ts}] [{level}] {msg}', flush=True)


def log_step(step, msg):
    log(f'━━━ Step {step} ━━━', 'STEP')
    log(msg)


def run_cmd(cmd, desc=''):
    """执行命令，返回 (success, stdout, stderr)"""
    log(f'执行: {" ".join(str(c) for c in cmd)}')
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            encoding='utf-8',
        )
        if result.returncode != 0:
            log(f'{desc} 失败 (exit {result.returncode})', 'ERROR')
            if result.stderr:
                log(result.stderr.strip()[:500], 'ERROR')
            return False, result.stdout, result.stderr
        return True, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log(f'{desc} 超时 (300s)', 'ERROR')
        return False, '', 'timeout'
    except Exception as e:
        log(f'{desc} 异常: {e}', 'ERROR')
        return False, '', str(e)


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# Step 1: 触发检测
# ============================================================

def step1_trigger(strategy_path, history_path, excel_path=None):
    log_step(1, '触发检测')

    cmd = ['python3', str(SCRIPTS['trigger']),
           '--strategy', str(strategy_path),
           '--history', str(history_path),
           '--json']
    if excel_path:
        cmd.extend(['--excel', str(excel_path)])

    ok, stdout, _ = run_cmd(cmd, '触发检测')
    if not ok:
        return None

    try:
        context = json.loads(stdout)
    except json.JSONDecodeError:
        # 可能 stderr 混入了 stdout，尝试提取 JSON 部分
        for line in stdout.splitlines():
            if line.strip().startswith('{'):
                try:
                    context = json.loads(stdout[stdout.index('{'):])
                    break
                except json.JSONDecodeError:
                    continue
        else:
            log('无法解析触发结果', 'ERROR')
            return None

    if context.get('triggered'):
        log(f'✓ 触发: {context["policyCode"]} — {context["reason"]}')
    else:
        log(f'✗ 未触发: {context["reason"]}')

    return context


# ============================================================
# Step 2a: 用例生成
# ============================================================

def step2a_generate(iter_dir, excel_path, feedback_path=None):
    log_step('2a', '用例生成')

    parsed_path = iter_dir / 'parsed_strategy.json'
    testcases_json = iter_dir / 'testcases.json'
    testcases_xlsx = iter_dir / 'testcases.xlsx'

    # 如果已生成则跳过
    if testcases_json.exists() and testcases_xlsx.exists():
        log(f'用例已存在，跳过: {testcases_json.name}')
        return True, str(testcases_xlsx)

    # 2a-1: 解析落地方案 Excel
    log('2a-1: 解析落地方案 Excel...')
    ok, stdout, stderr = run_cmd(
        ['python3', str(SCRIPTS['parse']), str(excel_path), '-o', str(parsed_path)],
        '解析 Excel',
    )
    if not ok:
        return False, None
    log(f'解析完成: {parsed_path.name}')

    # 2a-2: 生成测试用例
    log('2a-2: 生成测试用例...')
    cmd = ['python3', str(SCRIPTS['generate']), str(parsed_path), str(testcases_json)]
    ok, stdout, stderr = run_cmd(cmd, '生成用例')
    if not ok:
        return False, None

    # generate_testcases.py 自动导出同名 .xlsx
    if not testcases_xlsx.exists():
        log(f'警告: Excel 报告未自动生成，请检查', 'WARN')

    # 统计
    try:
        data = load_json(testcases_json)
        total = data.get('summary', {}).get('total', '?')
        log(f'生成完成: {total} 条用例 → {testcases_json.name}')
    except Exception:
        log('生成完成（无法读取统计）')

    return True, str(testcases_xlsx)


# ============================================================
# Step 2b: 测试执行（暂停点）
# ============================================================

def step2b_execute(iter_dir, testcases_path, report_path=None):
    log_step('2b', '测试执行')

    test_report = iter_dir / 'test_report.xlsx'

    # 如果已有报告则跳过
    if test_report.exists():
        log(f'测试报告已存在，跳过: {test_report.name}')
        return True, str(test_report)

    # 如果通过 --report 注入
    if report_path and os.path.exists(report_path):
        shutil.copy2(report_path, test_report)
        log(f'注入报告: {report_path} → {test_report.name}')
        return True, str(test_report)

    # 暂停等待
    log('')
    log('┌──────────────────────────────────────────────┐', 'PAUSE')
    log('│  Step 2b 需要执行测试（需天策平台环境）       │', 'PAUSE')
    log('│                                              │', 'PAUSE')
    log(f'│  用例文件: {str(testcases_path):<36}│', 'PAUSE')
    log('│                                              │', 'PAUSE')
    log('│  请在另一个终端/会话中运行 tiance-policy-test │', 'PAUSE')
    log('│  完成后输入报告路径继续:                      │', 'PAUSE')
    log('└──────────────────────────────────────────────┘', 'PAUSE')

    try:
        while True:
            path = input('\n  请输入测试报告路径 (或 skip 跳过): ').strip()
            if path.lower() == 'skip':
                log('跳过测试执行步骤', 'WARN')
                return False, None
            if not path:
                continue
            path = os.path.expanduser(path)
            if os.path.exists(path):
                shutil.copy2(path, test_report)
                log(f'报告已复制: {path} → {test_report.name}')
                return True, str(test_report)
            else:
                log(f'文件不存在: {path}，请重试', 'ERROR')
    except (EOFError, KeyboardInterrupt):
        log('\n用户中断', 'WARN')
        return False, None


# ============================================================
# Step 3: 校验
# ============================================================

def step3_check(iter_dir):
    log_step(3, '质量校验')

    test_report = iter_dir / 'test_report.xlsx'
    checked_report = iter_dir / 'checked_report.xlsx'
    check_result = iter_dir / 'check_result.json'

    if check_result.exists() and checked_report.exists():
        log(f'检查结果已存在，跳过')
        return load_json(str(check_result))

    cmd = ['python3', str(SCRIPTS['check']),
           str(test_report),
           '-o', str(checked_report),
           '--json']

    ok, stdout, stderr = run_cmd(cmd, '质量检查')
    if not ok:
        return None

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        # 提取 JSON 部分
        try:
            start = stdout.index('{')
            result = json.loads(stdout[start:])
        except (ValueError, json.JSONDecodeError):
            log('无法解析检查结果', 'ERROR')
            return None

    save_json(result, str(check_result))

    total = result.get('total_cases', 0)
    issues = result.get('total_issues', 0)
    by_level = result.get('by_level', {})
    log(f'校验完成: {total} 用例, {issues} 问题')
    log(f'  严重: {by_level.get("严重", 0)}  '
        f'警告: {by_level.get("警告", 0)}  '
        f'提示: {by_level.get("提示", 0)}')

    return result


# ============================================================
# Step 4: 优化
# ============================================================

def step4_optimize(iter_dir, next_iter_dir, iteration_num):
    log_step(4, '反馈分析')

    check_result = iter_dir / 'check_result.json'
    checked_report = iter_dir / 'checked_report.xlsx'
    feedback_path = next_iter_dir / 'feedback.json'

    if feedback_path.exists():
        log(f'反馈已存在，跳过')
        return load_json(str(feedback_path))

    os.makedirs(str(next_iter_dir), exist_ok=True)

    cmd = ['python3', str(SCRIPTS['feedback']),
           '--check-result', str(check_result),
           '--checked-report', str(checked_report),
           '--output', str(feedback_path),
           '--iteration', str(iteration_num)]

    ok, stdout, stderr = run_cmd(cmd, '反馈分析')
    # stderr 有进度信息，stdout 有摘要
    if stderr:
        for line in stderr.strip().splitlines():
            if line.strip():
                log(f'  {line.strip()}')

    if not feedback_path.exists():
        log('反馈文件未生成', 'ERROR')
        return None

    fb = load_json(str(feedback_path))
    s = fb.get('summary', {})
    log(f'反馈完成: {s.get("totalActions", 0)} 个动作')
    log(f'  可自动修复: {s.get("autoFixable", 0)}  '
        f'需人工确认: {s.get("manualReview", 0)}  '
        f'保留: {s.get("keepAsPair", 0)}  '
        f'待调查: {s.get("investigate", 0)}')

    return fb


# ============================================================
# 收敛判定
# ============================================================

def evaluate_convergence(check_result, feedback, iteration, max_rounds):
    by_level = check_result.get('by_level', {})
    severe = by_level.get('严重', 0)
    warning = by_level.get('警告', 0)
    s = feedback.get('summary', {})

    reasons = []
    converged = False

    if severe > 0:
        reasons.append(f'存在 {severe} 个严重问题，需人工介入')
    elif s.get('estimatedNextIssues', 0) == 0 and s.get('manualReview', 0) == 0:
        converged = True
        reasons.append('所有问题已分类（无待修复、无待人工确认），预估下轮问题数为 0')
    elif iteration >= max_rounds:
        converged = True
        reasons.append(f'达到最大轮次 ({max_rounds})')

    return converged, reasons


# ============================================================
# 收敛追踪
# ============================================================

def update_convergence(workspace, policy_code, policy_version, iteration,
                       check_result, feedback, converged, reasons):
    conv_path = workspace / 'convergence.json'
    conv = load_json(str(conv_path)) if conv_path.exists() else {
        'policyCode': policy_code,
        'policyVersion': policy_version,
        'iterations': [],
    }

    s = feedback.get('summary', {})
    by_level = check_result.get('by_level', {})

    record = {
        'round': iteration,
        'cases': check_result.get('total_cases', 0),
        'issues': check_result.get('total_issues', 0),
        'severe': by_level.get('严重', 0),
        'warning': by_level.get('警告', 0),
        'info': by_level.get('提示', 0),
        'feedback': {
            'autoFixable': s.get('autoFixable', 0),
            'manualReview': s.get('manualReview', 0),
            'keepAsPair': s.get('keepAsPair', 0),
            'investigate': s.get('investigate', 0),
        },
        'estimatedNextIssues': s.get('estimatedNextIssues', 0),
        'converged': converged,
        'convergeReasons': reasons if converged else [],
    }

    # 更新或追加
    existing = [i for i in conv['iterations'] if i['round'] == iteration]
    if existing:
        idx = conv['iterations'].index(existing[0])
        conv['iterations'][idx] = record
    else:
        conv['iterations'].append(record)

    conv['converged'] = converged
    if converged:
        conv['convergeRound'] = iteration
        conv['reason'] = '; '.join(reasons)
        conv['finalReport'] = f'iteration_{iteration}/checked_report.xlsx'

    conv['updatedAt'] = datetime.now().isoformat()
    save_json(conv, str(conv_path))
    return conv


# ============================================================
# 断点续跑：查找最新未完成的迭代
# ============================================================

def find_resume_point(workspace, max_rounds):
    """查找最新未完成的迭代编号"""
    for i in range(max_rounds, 0, -1):
        iter_dir = workspace / f'iteration_{i}'
        if not iter_dir.exists():
            continue
        # 如果缺少 check_result.json，说明这轮没跑完
        if not (iter_dir / 'check_result.json').exists():
            return i
        # 如果 check 完成但 feedback 没完成
        if not (iter_dir / 'feedback.json').exists() and \
           not (workspace / f'iteration_{i+1}' / 'feedback.json').exists():
            return i
    # 所有已存在的迭代都完成了，返回下一轮
    existing = [d for d in workspace.iterdir()
                if d.is_dir() and d.name.startswith('iteration_')]
    if existing:
        nums = [int(d.name.split('_')[1]) for d in existing]
        return max(nums) + 1
    return 1


# ============================================================
# 主循环
# ============================================================

def run_loop(args):
    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    history_dir = workspace / 'history'
    history_dir.mkdir(exist_ok=True)

    # 确定起始轮次
    if args.resume:
        start_round = find_resume_point(workspace, args.max_rounds)
        log(f'断点续跑: 从第 {start_round} 轮开始')
    else:
        start_round = 1

    # 从已有 history 获取 policyCode（resume 场景）
    policy_code = ''
    history_files = list(history_dir.glob('*/history.json'))
    if history_files:
        try:
            h = load_json(str(history_files[0]))
            policy_code = h.get('policyCode', '')
        except Exception:
            pass

    conv = {'converged': False, 'iterations': []}
    conv_path = workspace / 'convergence.json'
    if conv_path.exists():
        try:
            conv = load_json(str(conv_path))
        except Exception:
            pass

    for iteration in range(start_round, args.max_rounds + 1):
        iter_dir = workspace / f'iteration_{iteration}'
        next_dir = workspace / f'iteration_{iteration + 1}'
        iter_dir.mkdir(parents=True, exist_ok=True)

        log('')
        log(f'{"═" * 55}', 'LOOP')
        log(f'  Iteration {iteration} / {args.max_rounds}', 'LOOP')
        log(f'  目录: {iter_dir}', 'LOOP')
        log(f'{"═" * 55}', 'LOOP')

        # ── Step 1: 触发 ──
        if args.strategy:
            strategy_name = Path(args.strategy).stem
            history_path = history_dir / strategy_name / 'history.json'
            history_path.parent.mkdir(parents=True, exist_ok=True)
            context = step1_trigger(args.strategy, history_path, args.excel)
            if context:
                policy_code = context.get('policyCode', strategy_name)
                save_json(context, str(iter_dir / 'trigger_context.json'))
                if not context.get('triggered') and iteration > 1:
                    log('未触发且非首轮，跳过本轮')
                    continue
        elif iteration == 1:
            log('未指定 --strategy，跳过触发检测（直接执行后续步骤）', 'WARN')

        # ── Step 2a: 生成 ──
        if args.excel:
            # 查找反馈文件（来自上一轮）
            prev_feedback = workspace / f'iteration_{iteration - 1}' / 'feedback.json'
            # 注意：当前 generator 不支持 --feedback，预留接口
            ok, testcases_path = step2a_generate(iter_dir, args.excel,
                                                  prev_feedback if prev_feedback.exists() else None)
            if not ok:
                log('用例生成失败，终止循环', 'ERROR')
                break
        else:
            testcases_path = iter_dir / 'testcases.json'
            if not testcases_path.exists():
                log('未指定 --excel 且无已生成用例，跳过生成步骤', 'WARN')

        # ── Step 2b: 执行 ──
        report_arg = args.report if iteration == start_round else None
        ok, report_path = step2b_execute(iter_dir, testcases_path, report_arg)
        if not ok:
            log('测试执行未完成，循环暂停。下次运行加 --resume 继续', 'WARN')
            break

        # ── Step 3: 校验 ──
        check_result = step3_check(iter_dir)
        if not check_result:
            log('校验失败，终止循环', 'ERROR')
            break

        # ── Step 4: 优化 ──
        feedback = step4_optimize(iter_dir, next_dir, iteration)
        if not feedback:
            log('反馈分析失败，终止循环', 'ERROR')
            break

        # ── 收敛判定 ──
        converged, reasons = evaluate_convergence(
            check_result, feedback, iteration, args.max_rounds
        )

        conv = update_convergence(
            workspace, policy_code,
            check_result.get('policyVersion', 0),
            iteration, check_result, feedback, converged, reasons,
        )

        # 输出本轮摘要
        log('')
        log(f'{"─" * 45}', 'SUMMARY')
        log(f'  Iteration {iteration} 完成', 'SUMMARY')
        by_level = check_result.get('by_level', {})
        log(f'  用例: {check_result.get("total_cases", 0)}  '
            f'问题: {check_result.get("total_issues", 0)}  '
            f'(严重:{by_level.get("严重",0)} '
            f'警告:{by_level.get("警告",0)} '
            f'提示:{by_level.get("提示",0)})', 'SUMMARY')
        s = feedback.get('summary', {})
        log(f'  反馈: 自动修复:{s.get("autoFixable",0)} '
            f'人工确认:{s.get("manualReview",0)} '
            f'保留:{s.get("keepAsPair",0)} '
            f'待查:{s.get("investigate",0)}', 'SUMMARY')
        log(f'  预估下轮问题: {s.get("estimatedNextIssues", 0)}', 'SUMMARY')

        if converged:
            log('')
            log(f'  ✓ 收敛！原因: {"; ".join(reasons)}', 'CONVERGE')
            log(f'  最终报告: {conv.get("finalReport", "")}', 'CONVERGE')
            log(f'{"─" * 45}', 'SUMMARY')
            break
        else:
            log(f'  → 未收敛，继续下一轮', 'SUMMARY')
            log(f'{"─" * 45}', 'SUMMARY')

    # 最终输出
    log('')
    log(f'{"═" * 55}', 'DONE')
    if conv.get('converged'):
        log(f'  Agent Loop 完成 — 共 {len(conv["iterations"])} 轮收敛', 'DONE')
    else:
        log(f'  Agent Loop 暂停 — 完成 {len(conv["iterations"])} 轮', 'DONE')
    log(f'  工作目录: {workspace}', 'DONE')
    log(f'  收敛追踪: {workspace / "convergence.json"}', 'DONE')
    log(f'{"═" * 55}', 'DONE')


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='AI 策略测试 Agent Loop 编排器 — 多轮自动循环',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 全新循环
  python3 orchestrator.py --strategy strategies/X.json --excel 落地方案.xlsx

  # 断点续跑
  python3 orchestrator.py --resume

  # 注入已有报告（跳过 Step 2b 暂停）
  python3 orchestrator.py --strategy strategies/X.json --report 测试报告.xlsx

  # 指定工作目录和最大轮次
  python3 orchestrator.py --strategy strategies/X.json --workspace my_loop --max-rounds 3
        """
    )
    parser.add_argument('--strategy', help='策略配置文件路径 (strategies/{policyCode}.json)')
    parser.add_argument('--excel', help='落地方案 Excel 路径')
    parser.add_argument('--workspace', default='loop_workspace', help='工作目录 (默认: loop_workspace)')
    parser.add_argument('--max-rounds', type=int, default=5, help='最大迭代轮次 (默认: 5)')
    parser.add_argument('--resume', action='store_true', help='从上次中断处继续')
    parser.add_argument('--report', help='直接注入测试报告（跳过 Step 2b 暂停）')

    args = parser.parse_args()

    if not args.resume and not args.strategy and not args.report:
        parser.error('请指定 --strategy 或使用 --resume')

    run_loop(args)


if __name__ == '__main__':
    main()
