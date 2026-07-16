#!/usr/bin/env python3
"""
天策策略测试用例 — 批量回归 + 跨策略 pattern 迁移
v2.4.2 Phase 4-4

功能:
  1. 批量模式: 接收多个 parsed_strategy.json，逐一生成测试用例并汇总统计
  2. 跨策略 pattern 迁移: 检测策略类型，推荐可复用的 cases_library 模板
  3. 回归对比: 与历史用例 JSON 比对，输出增量变更摘要

用法:
  python3 batch_generate.py parsed1.json parsed2.json ... [-o output_dir] [--scenarios scenarios.yaml]
  python3 batch_generate.py --dir strategies/ [-o output_dir]  # 自动扫描目录下所有 parsed_strategy.json
  python3 batch_generate.py parsed1.json --compare history/    # 与历史用例对比
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 确保同目录的 generate_testcases 可导入
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from generate_testcases import (
    generate_all,
    _detect_strategy_type,
    _load_cases_library,
    _load_scenarios,
)


def _scan_directory(dir_path):
    """扫描目录下所有 parsed_strategy.json 文件。"""
    results = []
    for p in sorted(Path(dir_path).rglob("parsed_strategy.json")):
        results.append(str(p))
    return results


def _load_history(history_dir):
    """加载历史用例 JSON 文件，返回 {strategy_code: testcases_data}。"""
    history = {}
    if not history_dir or not Path(history_dir).exists():
        return history
    for p in Path(history_dir).rglob("testcases*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            code = data.get("strategyCode", p.stem)
            history[code] = data
        except Exception:
            continue
    return history


def _compare_with_history(new_data, old_data):
    """对比新旧用例集，输出增量变更摘要。"""
    new_cases = {tc["id"]: tc for tc in new_data.get("testCases", [])}
    old_cases = {tc["id"]: tc for tc in old_data.get("testCases", [])}

    added = [cid for cid in new_cases if cid not in old_cases]
    removed = [cid for cid in old_cases if cid not in new_cases]
    modified = []
    for cid in new_cases:
        if cid in old_cases:
            new_params = json.dumps(new_cases[cid].get("params", {}), sort_keys=True)
            old_params = json.dumps(old_cases[cid].get("params", {}), sort_keys=True)
            if new_params != old_params or new_cases[cid].get("expected") != old_cases[cid].get("expected"):
                modified.append(cid)

    return {
        "total_new": len(new_cases),
        "total_old": len(old_cases),
        "added": len(added),
        "removed": len(removed),
        "modified": len(modified),
        "unchanged": len(new_cases) - len(added) - len(modified),
        "added_ids": added[:10],
        "modified_ids": modified[:10],
    }


def _suggest_cross_strategy_patterns(strategy_type, all_detected_types):
    """推荐可跨策略迁移的 pattern。"""
    suggestions = []
    if not strategy_type:
        return suggestions

    lib = _load_cases_library(strategy_type)
    if not lib:
        return suggestions

    rule_pats = list(lib.get("rule_patterns", {}).keys())
    func_pats = list(lib.get("function_patterns", {}).keys())

    for other_type in all_detected_types:
        if other_type == strategy_type:
            continue
        other_lib = _load_cases_library(other_type)
        if not other_lib:
            continue
        other_rules = list(other_lib.get("rule_patterns", {}).keys())
        other_funcs = list(other_lib.get("function_patterns", {}).keys())

        # 检查是否有通用模式可迁移
        common_patterns = []
        for rp in rule_pats:
            if any(rp in orp or orp in rp for orp in other_rules):
                common_patterns.append(f"rule:{rp}")
        for fp in func_pats:
            if any(fp in ofp or ofp in fp for ofp in other_funcs):
                common_patterns.append(f"func:{fp}")

        if common_patterns:
            suggestions.append({
                "from": other_type,
                "to": strategy_type,
                "shared_patterns": common_patterns,
            })

    return suggestions


def batch_generate(input_files, output_dir, scenarios_path=None, compare_dir=None):
    """批量生成测试用例并汇总统计。"""
    if scenarios_path:
        _load_scenarios(scenarios_path)

    history = _load_history(compare_dir) if compare_dir else {}

    results = []
    all_detected_types = set()
    total_cases = 0
    errors = []

    for i, input_file in enumerate(input_files, 1):
        input_path = Path(input_file)
        strategy_dir = input_path.parent
        strategy_name_short = input_path.parent.name

        # 输出路径
        out_path = Path(output_dir) / strategy_name_short / "testcases.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"[{i}/{len(input_files)}] 生成: {strategy_name_short}", file=sys.stderr)

        try:
            # 重置全局缓存（确保每个策略独立加载 scenarios）
            import generate_testcases as gt
            gt._scenarios_config = None
            gt._cases_library_cache = {}

            if scenarios_path:
                _load_scenarios(scenarios_path)

            result = generate_all(input_file, str(out_path))
            if result:
                code = result.get("strategyCode", "unknown")
                name = result.get("strategyName", "unknown")
                case_count = len(result.get("testCases", []))
                total_cases += case_count

                # 检测策略类型
                st_type = _detect_strategy_type(code, name)
                if st_type:
                    all_detected_types.add(st_type)

                entry = {
                    "strategyCode": code,
                    "strategyName": name,
                    "strategyType": st_type,
                    "cases": case_count,
                    "output": str(out_path),
                    "summary": result.get("summary", {}),
                }

                # 历史对比
                if code in history:
                    diff = _compare_with_history(result, history[code])
                    entry["historyDiff"] = diff
                    print(f"  对比历史: +{diff['added']} -{diff['removed']} ~{diff['modified']}",
                          file=sys.stderr)

                results.append(entry)
                print(f"  {code}: {case_count} 条用例 (类型: {st_type or '未识别'})",
                      file=sys.stderr)

        except Exception as e:
            errors.append({"file": input_file, "error": str(e)})
            print(f"  错误: {e}", file=sys.stderr)

    # 跨策略 pattern 迁移建议
    cross_suggestions = []
    for st in all_detected_types:
        suggestions = _suggest_cross_strategy_patterns(st, all_detected_types)
        cross_suggestions.extend(suggestions)

    # 汇总报告
    batch_report = {
        "batchGeneratedAt": datetime.now().isoformat(),
        "totalStrategies": len(input_files),
        "successful": len(results),
        "errors": len(errors),
        "totalCases": total_cases,
        "detectedTypes": list(all_detected_types),
        "strategies": results,
        "crossStrategySuggestions": cross_suggestions,
        "errorDetails": errors,
    }

    # 输出汇总
    report_path = Path(output_dir) / "batch_summary.json"
    report_path.write_text(json.dumps(batch_report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"批量生成完成: {len(results)}/{len(input_files)} 策略, {total_cases} 条用例",
          file=sys.stderr)
    print(f"检测到的策略类型: {', '.join(all_detected_types) or '无'}", file=sys.stderr)
    if cross_suggestions:
        print(f"跨策略迁移建议: {len(cross_suggestions)} 条", file=sys.stderr)
        for s in cross_suggestions:
            print(f"  {s['from']} → {s['to']}: {', '.join(s['shared_patterns'])}",
                  file=sys.stderr)
    print(f"汇总报告: {report_path}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    return batch_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="天策策略测试用例批量生成 + 跨策略 pattern 迁移 (v2.4.2 Phase 4-4)",
        epilog="示例: python3 batch_generate.py p1.json p2.json -o batch_output/",
    )
    parser.add_argument("inputs", nargs="*", help="parsed_strategy.json 文件路径（可多个）")
    parser.add_argument("--dir", default=None,
                        help="扫描目录下所有 parsed_strategy.json")
    parser.add_argument("-o", "--output-dir", default="batch_output",
                        help="输出目录（默认 batch_output/）")
    parser.add_argument("--scenarios", default=None,
                        help="scenarios.yaml 配置路径")
    parser.add_argument("--compare", default=None,
                        help="历史用例目录，用于回归对比")

    args = parser.parse_args()

    input_files = list(args.inputs) if args.inputs else []
    if args.dir:
        input_files.extend(_scan_directory(args.dir))

    if not input_files:
        print("错误：未指定输入文件。使用 --dir 或直接传入 parsed_strategy.json 路径。",
              file=sys.stderr)
        sys.exit(1)

    print(f"发现 {len(input_files)} 个策略文件", file=sys.stderr)
    batch_generate(input_files, args.output_dir, args.scenarios, args.compare)
