#!/usr/bin/env python3
"""
tiance-agent-loop / Step 1: 触发检测
检查策略配置版本是否变更，决定是否启动新一轮测试循环。
"""

import argparse
import json
import os
import sys
from datetime import datetime


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_trigger(strategy_path, history_path, excel_path=None):
    """
    对比策略配置版本与历史记录，返回触发上下文。

    Returns:
        dict: {
            triggered: bool,
            policyCode: str,
            oldVersion: int|None,
            newVersion: int,
            excelPath: str|None,
            reason: str,
            timestamp: str
        }
    """
    # 读取当前策略配置
    strategy = load_json(strategy_path)
    policy_code = strategy.get('policyCode', os.path.basename(strategy_path).replace('.json', ''))
    new_version = strategy.get('policyVersion', strategy.get('version', 0))

    # 读取历史记录
    history = {}
    if os.path.exists(history_path):
        history = load_json(history_path)

    old_version = history.get('lastVersion', None)
    last_run = history.get('lastRun', None)

    # 判断是否触发
    triggered = False
    reason = ''

    if old_version is None:
        triggered = True
        reason = f'首次执行（无历史记录）'
    elif new_version != old_version:
        triggered = True
        if new_version > old_version:
            reason = f'策略版本升级: v{old_version} → v{new_version}'
        else:
            reason = f'策略版本回退: v{old_version} → v{new_version}（需人工确认）'
    else:
        reason = f'版本未变更（当前 v{new_version}，上次执行 {last_run or "未知"}）'

    context = {
        'triggered': triggered,
        'policyCode': policy_code,
        'oldVersion': old_version,
        'newVersion': new_version,
        'excelPath': excel_path or history.get('excelPath', None),
        'reason': reason,
        'timestamp': datetime.now().isoformat(),
    }

    # 更新历史记录
    if triggered:
        history['lastVersion'] = new_version
        history['lastRun'] = context['timestamp']
        history['lastExcel'] = context['excelPath']
        # 追加迭代记录
        history.setdefault('iterations', [])
        history['iterations'].append({
            'version': new_version,
            'timestamp': context['timestamp'],
            'reason': reason,
        })
        save_json(history, history_path)

    return context


def main():
    parser = argparse.ArgumentParser(description='Agent Loop Step 1: 触发检测')
    parser.add_argument('--strategy', required=True, help='策略配置文件路径 (strategies/{policyCode}.json)')
    parser.add_argument('--history', required=True, help='历史记录文件路径 (loop_history/{policyCode}/history.json)')
    parser.add_argument('--excel', help='落地方案 Excel 路径（首次执行时需提供）')
    parser.add_argument('--json', action='store_true', help='JSON 格式输出')

    args = parser.parse_args()

    if not os.path.exists(args.strategy):
        print(f'错误: 策略配置文件不存在: {args.strategy}', file=sys.stderr)
        sys.exit(1)

    context = check_trigger(args.strategy, args.history, args.excel)

    if args.json:
        print(json.dumps(context, ensure_ascii=False, indent=2))
    else:
        status = '✓ 触发' if context['triggered'] else '✗ 不触发'
        print(f'[{status}] {context["policyCode"]}')
        print(f'  原因: {context["reason"]}')
        if context['excelPath']:
            print(f'  落地方案: {context["excelPath"]}')


if __name__ == '__main__':
    main()
