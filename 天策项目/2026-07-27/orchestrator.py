#!/usr/bin/env python3
"""
tiance-agent-loop Orchestrator v1.3.0
多轮自动编排：触发 → 平台校验 → 生成 → 执行 → 校验 → 反馈 → 收敛判定

v1.3.0: 新增 Step 1.5 平台校验门禁（platform_check.py），比对 policyVersion/
        bizType/status，自动修正本地配置；--skip-platform-check 标志。
v1.2.0: 收敛判定5条件对齐SKILL.md；policyVersion从策略配置读取；
        prev_issues传递支持稳定性判定；step2b调用merge_results回填。
v1.1.0: Step 2b 支持自动执行（需 --host + --cookie），反馈闭环真正生效。
v1.0.0: Step 1/2a/3/4 全自动，Step 2b 为暂停点。

用法:
  # 全新循环（全自动模式，含自动执行）
  python3 orchestrator.py --strategy strategies/X.json --excel 落地方案.xlsx \\
    --host http://10.57.80.231 --cookie "JSESSIONID=xxx; _csrf_=yyy"

  # 半自动模式（执行步骤暂停等待手动注入报告）
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

VERSION = "1.3.0"

# ============================================================
# 路径常量
# ============================================================

SKILLS_DIR = Path.home() / '.qoderwork' / 'skills'

SCRIPTS = {
    'trigger':        SKILLS_DIR / 'tiance-agent-loop' / 'scripts' / 'check_trigger.py',
    'platform_check': SKILLS_DIR / 'tiance-agent-loop' / 'scripts' / 'platform_check.py',
    'parse':          SKILLS_DIR / 'tiance-testcase-generator' / 'scripts' / 'parse_strategy_excel.py',
    'generate':       SKILLS_DIR / 'tiance-testcase-generator' / 'scripts' / 'generate_testcases.py',
    'execute':        SKILLS_DIR / 'tiance-agent-loop' / 'scripts' / 'execute_tests.py',
    'merge':          SKILLS_DIR / 'tiance-agent-loop' / 'scripts' / 'merge_results.py',
    'check':          SKILLS_DIR / 'tiance-report-checker' / 'scripts' / 'check_report.py',
    'feedback':       SKILLS_DIR / 'tiance-agent-loop' / 'scripts' / 'analyze_feedback.py',
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


def run_cmd(cmd, desc='', timeout=300):
    """执行命令，返回 (success, stdout, stderr)"""
    log(f'执行: {" ".join(str(c) for c in cmd)}')
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding='utf-8',
        )
        if result.returncode != 0:
            log(f'{desc} 失败 (exit {result.returncode})', 'ERROR')
            if result.stderr:
                log(result.stderr.strip()[:500], 'ERROR')
            return False, result.stdout, result.stderr
        return True, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log(f'{desc} 超时 ({timeout}s)', 'ERROR')
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
# Step 1.5: 平台校验（强制门禁）
# ============================================================

def step1_5_platform_check(iter_dir, strategy_config, host, cookie,
                            org_code=None):
    """
    调用 platform_check.py 查询平台实际 policyVersion/bizType/status，
    与本地配置比对并自动修正。

    返回 (ok: bool, platform_info: dict|None)。
    """
    log_step('1.5', '平台校验')

    result_path = iter_dir / 'platform_check.json'

    # 如果已有校验结果则跳过
    if result_path.exists():
        try:
            info = load_json(str(result_path))
            if info.get('ok'):
                log(f'平台校验结果已存在，跳过: version={info.get("platformVersion")}, '
                    f'bizType={info.get("platformBizType")}')
                return True, info
            else:
                log('已有校验结果但未通过，重新校验', 'WARN')
        except Exception:
            pass

    cmd = ['python3', str(SCRIPTS['platform_check']),
           '--host', host,
           '--cookie', cookie,
           '--policy-code', _extract_policy_code(strategy_config),
           '--strategy-config', str(strategy_config),
           '-o', str(result_path)]
    if org_code:
        cmd.extend(['--org-code', org_code])

    ok, stdout, stderr = run_cmd(cmd, '平台校验')

    # 读取结果文件（无论 ok 与否，文件可能已生成）
    info = None
    if result_path.exists():
        try:
            info = load_json(str(result_path))
        except Exception:
            pass

    if not ok or not info:
        log('平台校验失败，请检查 host/cookie 是否正确', 'ERROR')
        return False, info

    if info.get('ok'):
        log(f'✓ 平台校验通过: policyVersion={info.get("platformVersion")}, '
            f'bizType={info.get("platformBizType")}({info.get("platformBizTypeName")}), '
            f'status={info.get("status")}({info.get("statusName")})')
        if info.get('configUpdated'):
            for c in info.get('configChanges', []):
                log(f'  ⚠ 已自动修正: {c}', 'WARN')
        if info.get('mismatches'):
            for m in info['mismatches']:
                log(f'  ⚠ {m}', 'WARN')
    else:
        log(f'✗ 平台校验未通过', 'ERROR')
        for w in info.get('warnings', []):
            log(f'  ⚠ {w}', 'WARN')

    # 检查发布状态（status != 4 时发出警告但不阻断）
    status = info.get('status')
    if status is not None:
        try:
            if int(status) != 4:
                log(f'⚠ 策略未发布: status={status}({info.get("statusName")})，'
                    f'测试结果可能不可靠', 'WARN')
        except (ValueError, TypeError):
            pass

    return info.get('ok', False), info


def _extract_policy_code(strategy_config):
    """从策略配置文件中提取 policyCode"""
    try:
        config = load_json(str(strategy_config))
        return config.get('policyCode', config.get('code', ''))
    except Exception:
        return Path(strategy_config).stem


# ============================================================
# Step 2a: 用例生成
# ============================================================

def step2a_generate(iter_dir, excel_path, feedback_path=None):
    log_step('2a', '用例生成')

    parsed_path = iter_dir / 'parsed_strategy.json'
    testcases_json = iter_dir / 'testcases.json'
    testcases_xlsx = iter_dir / 'testcases.xlsx'

    # 如果已生成则检查完整性，不完整则重新生成
    if testcases_json.exists() and testcases_xlsx.exists():
        try:
            tc_data = json.loads(testcases_json.read_text(encoding='utf-8'))
            if isinstance(tc_data, list) and len(tc_data) > 0:
                log(f'用例已存在且完整（{len(tc_data)} 条），跳过: {testcases_json.name}')
                return True, str(testcases_xlsx)
            else:
                log(f'用例 JSON 为空或不完整，重新生成', 'WARN')
        except (json.JSONDecodeError, Exception):
            log(f'用例 JSON 解析失败，重新生成', 'WARN')

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
    # v1.1.0: 传递上轮反馈，让 generator 自动修正用例（需 generate_testcases.py >= v2.4.0）
    if feedback_path and Path(feedback_path).exists():
        cmd.extend(['--feedback', str(feedback_path)])
        log(f'注入反馈: {Path(feedback_path).name}')
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

def step2b_execute(iter_dir, testcases_path, report_path=None,
                    strategy_config=None, host=None, cookie=None):
    log_step('2b', '测试执行')

    test_report = iter_dir / 'test_report.xlsx'
    results_json = iter_dir / 'results.json'

    # 如果已有报告则跳过
    if test_report.exists():
        log(f'测试报告已存在，跳过: {test_report.name}')
        return True, str(test_report)

    # 如果通过 --report 注入
    if report_path and os.path.exists(report_path):
        shutil.copy2(report_path, test_report)
        log(f'注入报告: {report_path} → {test_report.name}')
        return True, str(test_report)

    # v1.1.0: 自动执行模式（需 host + cookie + strategy_config）
    if host and cookie and strategy_config:
        log(f'自动执行模式: 通过 API 提交 {testcases_path.name}')
        cmd = [
            'python3', str(SCRIPTS['execute']),
            '--host', host,
            '--cookie', cookie,
            '--strategy-config', str(strategy_config),
            '--testcases', str(testcases_path),
            '--output', str(results_json),
        ]
        ok, stdout, stderr = run_cmd(cmd, 'API 批量提交', timeout=600)
        if ok and results_json.exists():
            log(f'执行完成，结果: {results_json.name}')
            # 将 results.json 回填到 testcases.xlsx，生成含真实执行数据的报告
            testcases_xlsx = iter_dir / 'testcases.xlsx'
            if testcases_xlsx.exists():
                merge_cmd = [
                    'python3', str(SCRIPTS['merge']),
                    '--excel', str(testcases_xlsx),
                    '--results', str(results_json),
                    '-o', str(test_report),
                ]
                merge_ok, _, merge_err = run_cmd(merge_cmd, '结果回填')
                if merge_ok:
                    log(f'报告已生成: {test_report.name}（含执行结果）')
                    return True, str(test_report)
                else:
                    log(f'结果回填失败，回退为空模板: {merge_err[:200]}', 'WARN')
                    shutil.copy2(str(testcases_xlsx), str(test_report))
            else:
                log('用例 Excel 不存在，无法生成报告', 'ERROR')
            return test_report.exists(), str(test_report) if test_report.exists() else None
        else:
            log('API 执行失败', 'ERROR')
            if stderr:
                log(f'错误: {stderr[:200]}', 'ERROR')
            return False, None

    # 半自动模式：暂停等待
    log('')
    log('┌──────────────────────────────────────────────┐', 'PAUSE')
    log('│  Step 2b 需要执行测试（需天策平台环境）       │', 'PAUSE')
    log('│                                              │', 'PAUSE')
    log(f'│  用例文件: {str(testcases_path):<36}│', 'PAUSE')
    log('│                                              │', 'PAUSE')
    log('│  方式1: 加 --host + --cookie 启用自动执行     │', 'PAUSE')
    log('│  方式2: 手动运行 tiance-policy-test 后输入路径│', 'PAUSE')
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

def step3_check(iter_dir, host=None, cookie=None):
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
    if host and cookie:
        cmd.extend(['--host', host, '--cookie', cookie])
        log(f'维度五系统回查: 已启用 ({host})')

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

def evaluate_convergence(check_result, feedback, iteration, max_rounds,
                          prev_issues=None):
    by_level = check_result.get('by_level', {})
    severe = by_level.get('严重', 0)
    warning = by_level.get('警告', 0)
    current_issues = check_result.get('total_issues', 0)
    s = feedback.get('summary', {})

    reasons = []
    converged = False

    # 1. 严重问题 → 标记需人工介入（不自动收敛）
    if severe > 0:
        reasons.append(f'存在 {severe} 个严重问题，需人工介入')

    # 2. 严重=0 且 警告<10 → 质量达标，可收敛
    elif severe == 0 and warning < 10:
        converged = True
        reasons.append(f'严重问题为 0，警告仅 {warning} 个（<10），质量达标')

    # 3. 连续两轮问题数变化 < 5% → 已趋于稳定
    elif prev_issues is not None and prev_issues > 0:
        change_rate = abs(current_issues - prev_issues) / prev_issues
        if change_rate < 0.05:
            converged = True
            reasons.append(
                f'问题数趋于稳定（{prev_issues}→{current_issues}，'
                f'变化 {change_rate:.1%} < 5%）')

    # 4. 预估下轮问题数为 0 且无需人工确认 → 完全收敛
    elif s.get('estimatedNextIssues', 0) == 0 and s.get('manualReview', 0) == 0:
        converged = True
        reasons.append('所有问题已分类（无待修复、无待人工确认），预估下轮问题数为 0')

    # 5. 达到最大轮次 → 强制停止
    if not converged and iteration >= max_rounds:
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

        # ── Step 1.5: 平台校验（强制门禁）──
        if (args.host and args.cookie and args.strategy
                and not args.skip_platform_check):
            pc_ok, pc_info = step1_5_platform_check(
                iter_dir, args.strategy, args.host, args.cookie,
                org_code=getattr(args, 'org_code', None),
            )
            if not pc_ok:
                log('平台校验未通过，终止循环。'
                    '可用 --skip-platform-check 跳过（不推荐）', 'ERROR')
                break
            # 记录平台校验结果供后续步骤引用
            platform_version = pc_info.get('platformVersion') if pc_info else None
            platform_biz_type = pc_info.get('platformBizType') if pc_info else None
            if platform_version:
                log(f'使用平台值: policyVersion={platform_version}, '
                    f'bizType={platform_biz_type}')
        elif args.skip_platform_check:
            log('跳过平台校验（--skip-platform-check）', 'WARN')
        elif iteration == 1 and args.host:
            log('未提供 --cookie，跳过平台校验', 'WARN')

        # ── Step 2a: 生成 ──
        if args.excel:
            # 查找反馈文件（来自上一轮）
            prev_feedback = workspace / f'iteration_{iteration - 1}' / 'feedback.json'
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
        ok, report_path = step2b_execute(
            iter_dir, testcases_path, report_arg,
            strategy_config=args.strategy,
            host=args.host, cookie=args.cookie,
        )
        if not ok:
            log('测试执行未完成，循环暂停。下次运行加 --resume 继续', 'WARN')
            break

        # ── Step 3: 校验 ──
        check_result = step3_check(iter_dir, host=args.host, cookie=args.cookie)
        if not check_result:
            log('校验失败，终止循环', 'ERROR')
            break

        # ── Step 4: 优化 ──
        feedback = step4_optimize(iter_dir, next_dir, iteration)
        if not feedback:
            log('反馈分析失败，终止循环', 'ERROR')
            break

        # ── 收敛判定 ──
        # 从 convergence.json 获取上一轮问题数（用于稳定性判定）
        prev_issues = None
        if conv.get('iterations'):
            prev_issues = conv['iterations'][-1].get('issues')

        converged, reasons = evaluate_convergence(
            check_result, feedback, iteration, args.max_rounds,
            prev_issues=prev_issues,
        )

        # 从策略配置文件读取 policyVersion（check_result 不含此字段）
        policy_version = 0
        if args.strategy and Path(args.strategy).exists():
            try:
                sc = load_json(args.strategy)
                policy_version = sc.get('policyVersion', sc.get('version', 0))
            except Exception:
                pass

        conv = update_convergence(
            workspace, policy_code, policy_version,
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
    parser.add_argument('--host', help='天策平台地址 (如 http://10.57.80.231)，启用自动执行模式')
    parser.add_argument('--cookie', help='登录 Cookie (含 JSESSIONID + _csrf_)，配合 --host 使用')
    parser.add_argument('--org-code', help='机构编码（多机构场景，传递给平台校验 Step 1.5）')
    parser.add_argument('--skip-platform-check', action='store_true',
                        help='跳过 Step 1.5 平台校验（不推荐，仅在离线/调试时使用）')

    args = parser.parse_args()

    if not args.resume and not args.strategy and not args.report:
        parser.error('请指定 --strategy 或使用 --resume')

    run_loop(args)


if __name__ == '__main__':
    main()
