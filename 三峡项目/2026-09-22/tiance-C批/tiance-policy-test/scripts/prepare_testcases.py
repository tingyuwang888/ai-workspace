#!/usr/bin/env python3
"""
Validate and enrich Tiance policy test cases before submission.

The strategy config may declare:

  testExecution.requiredParams
  testExecution.defaults
  testExecution.defaultsByCaseType

Defaults from params.common and params.strategySpecific are also applied.
Required fields from both groups are validated together with requiredParams.
Existing non-empty case values are never overwritten.
"""

import argparse
import copy
from datetime import datetime, timezone
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path


ALLOWED_GROUPS = {
    "规则",
    "函数",
    "决策流分支覆盖",
    "策略预警等级覆盖",
}
RULE_EXPECTATION_RE = re.compile(
    r"(?:命中|未命中)[：:]\s*([A-Za-z][A-Za-z0-9_-]*)\(([^)]+)\)"
)


def _is_missing(value):
    return value is None or value == ""


def collect_constraints(config):
    """Return (required_fields, defaults) derived from a strategy config."""
    required = []
    defaults = {}

    params_config = config.get("params", {})
    if not isinstance(params_config, dict):
        params_config = {}
    for group_name in ("common", "strategySpecific"):
        group = params_config.get(group_name, {})
        if not isinstance(group, dict):
            continue
        for field, spec in group.items():
            if not isinstance(spec, dict):
                continue
            if spec.get("required"):
                required.append(field)
            if "fixed" in spec:
                defaults[field] = spec["fixed"]
            elif "default" in spec:
                defaults[field] = spec["default"]

    execution = config.get("testExecution", {})
    if isinstance(execution, dict):
        execution_defaults = execution.get("defaults", {})
        if isinstance(execution_defaults, dict):
            defaults.update(execution_defaults)

        execution_required = execution.get("requiredParams", [])
        if isinstance(execution_required, list):
            required.extend(
                field for field in execution_required
                if isinstance(field, str) and field
            )

    return list(dict.fromkeys(required)), defaults


def validate_mock_contract(
    config,
    testcase,
    enabled_mock_scenarios,
    mock_readiness=None,
):
    """Return errors when an abnormal case lacks an explicit active mock."""
    execution = config.get("testExecution", {})
    if not isinstance(execution, dict):
        execution = {}

    required_types = execution.get(
        "mockRequiredCaseTypes",
        ["异常案例"],
    )
    if not isinstance(required_types, list):
        required_types = ["异常案例"]

    is_mock_case = (
        testcase.get("caseType") in required_types
        or testcase.get("executionMode") == "mock"
    )
    if not is_mock_case:
        return []

    errors = []
    if testcase.get("executionMode") != "mock":
        errors.append("异常用例必须设置 executionMode=mock")

    scenario = testcase.get("mockScenario")
    if not isinstance(scenario, str) or not scenario.strip():
        errors.append("异常用例必须设置非空 mockScenario")
        return errors

    declared = execution.get("mockScenarios", {})
    if declared and (
        not isinstance(declared, dict)
        or scenario not in declared
    ):
        errors.append(f"mockScenario 未在策略配置中声明: {scenario}")

    enabled = set(enabled_mock_scenarios or [])
    if scenario not in enabled:
        errors.append(
            f"mockScenario 未在本次执行中启用: {scenario}"
        )
    scenario_config = (
        declared.get(scenario, {})
        if isinstance(declared, dict)
        else {}
    )
    if isinstance(scenario_config, dict) and scenario_config.get("probe"):
        readiness = mock_readiness or {}
        scenario_readiness = (
            readiness.get("scenarios", {}).get(scenario, {})
            if isinstance(readiness, dict)
            else {}
        )
        if not scenario_readiness.get("ready"):
            errors.append(f"mockScenario 缺少就绪探针证明: {scenario}")
        else:
            proof_policy = readiness.get("policyCode")
            if proof_policy and str(proof_policy) != str(config.get("policyCode")):
                errors.append(
                    f"mock 就绪证明策略不一致: "
                    f"proof={proof_policy}, config={config.get('policyCode')}"
                )
            captured_at = readiness.get("capturedAt")
            try:
                parsed = datetime.fromisoformat(
                    str(captured_at).replace("Z", "+00:00")
                )
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age = time.time() - parsed.timestamp()
                if age < -60 or age > 600:
                    raise ValueError(f"age={int(age)}s")
            except (TypeError, ValueError, OverflowError):
                errors.append("mock 就绪证明 capturedAt 缺失、无效或已过期")
    return errors


def collect_case_defaults(config, testcase):
    """Return defaults selected by the test case's ``caseType``."""
    execution = config.get("testExecution", {})
    if not isinstance(execution, dict):
        return {}

    defaults_by_type = execution.get("defaultsByCaseType", {})
    if not isinstance(defaults_by_type, dict):
        return {}

    case_type = testcase.get("caseType")
    selected = defaults_by_type.get(case_type, {})
    return selected if isinstance(selected, dict) else {}


def collect_parameter_specs(config):
    """Return all declared request parameter specifications."""
    specs = {}
    params_config = config.get("params", {})
    if not isinstance(params_config, dict):
        return specs
    for group_name in ("common", "strategySpecific"):
        group = params_config.get(group_name, {})
        if isinstance(group, dict):
            specs.update(
                (field, spec)
                for field, spec in group.items()
                if isinstance(field, str) and isinstance(spec, dict)
            )
    return specs


def collect_rule_catalog(config, strategy_model=None):
    """Return ``ruleCode -> rule`` from config or parsed strategy metadata."""
    catalog = {}
    candidates = []
    if isinstance(strategy_model, dict):
        candidates.extend(strategy_model.get("rules", []) or [])
    execution = config.get("testExecution", {})
    if isinstance(execution, dict):
        candidates.extend(execution.get("ruleCatalog", []) or [])
    candidates.extend(config.get("rules", []) or [])
    for rule in candidates:
        if not isinstance(rule, dict):
            continue
        code = rule.get("code") or rule.get("ruleCode")
        if code:
            catalog[str(code)] = rule
    return catalog


def _routing_specs(config):
    routing = config.get("routingFields", [])
    if isinstance(routing, dict):
        routing = [
            dict(spec, field=field) if isinstance(spec, dict) else {"field": field}
            for field, spec in routing.items()
        ]
    if not isinstance(routing, list):
        return []
    return [spec for spec in routing if isinstance(spec, dict)]


def collect_strategy_model_parameter_specs(strategy_model):
    """Return parameter specs declared by parsed strategy field metadata."""
    specs = {}
    if not isinstance(strategy_model, dict):
        return specs
    fields = strategy_model.get("fields", {})
    if isinstance(fields, dict):
        candidates = fields.values()
    elif isinstance(fields, list):
        candidates = fields
    else:
        return specs
    for field in candidates:
        if not isinstance(field, dict):
            continue
        code = field.get("code") or field.get("fieldCode") or field.get("name")
        if code:
            specs[str(code)] = field
            if not str(code).startswith(("C_", "S_")):
                field_type = str(field.get("type") or "")
                prefix = "C_F_" if any(
                    token in field_type for token in ("小数", "整数", "数值", "金额")
                ) else "C_S_"
                specs[f"{prefix}{str(code).upper()}"] = field
    return specs


def validate_semantics(config, testcase, rule_catalog=None, parameter_specs=None):
    """Validate testcase meaning against the strategy metadata."""
    errors = []
    testcase_id = testcase.get("id") or "<missing-id>"
    execution = config.get("testExecution", {})
    semantic_config = (
        execution.get("semanticValidation", {})
        if isinstance(execution, dict)
        else {}
    )
    group = testcase.get("group")
    if group is not None and group not in ALLOWED_GROUPS:
        errors.append(
            f"{testcase_id}: group 必须是标准模块之一: "
            f"{', '.join(sorted(ALLOWED_GROUPS))}"
        )

    if (
        isinstance(semantic_config, dict)
        and semantic_config.get("requireMetadata", False)
    ):
        for field in ("id", "group", "caseType", "scenario", "expected"):
            if _is_missing(testcase.get(field)):
                errors.append(f"{testcase_id}: 缺少用例字段 {field}")

    params = testcase.get("params")
    if not isinstance(params, dict):
        return errors

    parameter_specs = parameter_specs or collect_parameter_specs(config)
    strict_params = (
        isinstance(semantic_config, dict)
        and semantic_config.get("strictParams", False)
    )
    if strict_params and parameter_specs:
        unknown = sorted(set(params) - set(parameter_specs))
        if unknown:
            errors.append(
                f"{testcase_id}: 包含策略未声明参数 {', '.join(unknown)}"
            )

    for field, spec in parameter_specs.items():
        if field not in params or not isinstance(spec, dict):
            continue
        value = params[field]
        enum_values = spec.get("enum")
        if isinstance(enum_values, list) and enum_values and value not in enum_values:
            errors.append(
                f"{testcase_id}: 参数 {field}={value!r} 不在枚举 "
                f"{enum_values!r} 中"
            )

    for routing_spec in _routing_specs(config):
        field = routing_spec.get("field") or routing_spec.get("name")
        if not field:
            continue
        required = routing_spec.get("required", True)
        if required and _is_missing(params.get(field)):
            errors.append(f"{testcase_id}: 缺少路由字段 {field}")
            continue
        allowed = (
            routing_spec.get("enum")
            or routing_spec.get("values")
            or routing_spec.get("allowedValues")
        )
        if (
            isinstance(allowed, list)
            and field in params
            and params[field] not in allowed
        ):
            errors.append(
                f"{testcase_id}: 路由字段 {field}={params[field]!r} "
                f"不在 {allowed!r} 中"
            )

    catalog = rule_catalog or {}
    target_rule = testcase.get("targetRule")
    expected_match = RULE_EXPECTATION_RE.search(str(testcase.get("expected") or ""))
    expected_code = expected_match.group(1) if expected_match else None
    expected_name = expected_match.group(2) if expected_match else None
    code = target_rule or expected_code
    if target_rule and expected_code and str(target_rule) != expected_code:
        errors.append(
            f"{testcase_id}: targetRule={target_rule} 与预期规则 "
            f"{expected_code} 不一致"
        )
    if code and catalog:
        rule = catalog.get(str(code))
        if not rule:
            errors.append(f"{testcase_id}: 策略中不存在规则 {code}")
        elif expected_name:
            actual_name = rule.get("name") or rule.get("ruleName")
            if actual_name and str(actual_name) != expected_name:
                errors.append(
                    f"{testcase_id}: 规则 {code} 中文名不一致，"
                    f"预期={expected_name!r}，策略={actual_name!r}"
                )

    dependencies = (
        execution.get("ruleDependencies", {})
        if isinstance(execution, dict)
        else {}
    )
    required_nodes = dependencies.get(str(code), []) if code else []
    if isinstance(required_nodes, dict):
        required_nodes = required_nodes.get("thirdPartyNodes", [])
    expected_evidence = testcase.get("expectedEvidence", {})
    declared_nodes = (
        expected_evidence.get("thirdPartyNodes", [])
        if isinstance(expected_evidence, dict)
        else []
    )
    if required_nodes:
        def node_names(items):
            if not isinstance(items, list):
                errors.append(f"{testcase_id}: 三方节点契约必须是列表")
                return set()
            names = set()
            for item in items:
                name = item if isinstance(item, str) else (
                    (item.get("nodeName") or item.get("name"))
                    if isinstance(item, dict) else None
                )
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"{testcase_id}: 无效三方节点契约 {item!r}")
                else:
                    names.add(name)
            return names

        missing_nodes = sorted(node_names(required_nodes) - node_names(declared_nodes or []))
        if missing_nodes:
            errors.append(
                f"{testcase_id}: expectedEvidence 缺少三方节点 "
                f"{', '.join(missing_nodes)}"
            )

    return errors


def prepare_testcases(
    testcases,
    config,
    fill_defaults=True,
    enabled_mock_scenarios=None,
    strategy_model=None,
    mock_readiness=None,
):
    """
    Enrich and validate test cases.

    Returns (prepared_cases, errors, summary).
    """
    if not isinstance(testcases, list):
        return [], ["测试用例根节点必须是 JSON 数组"], {
            "totalCases": 0,
            "changedCases": 0,
            "filledFields": {},
            "errorCount": 1,
        }

    required, defaults = collect_constraints(config)
    prepared = copy.deepcopy(testcases)
    errors = []
    changed_cases = 0
    filled_fields = Counter()
    mock_cases = 0
    excluded_cases = 0
    seen_ids = set()
    rule_catalog = collect_rule_catalog(config, strategy_model)
    parameter_specs = collect_parameter_specs(config)
    parameter_specs.update(collect_strategy_model_parameter_specs(strategy_model))

    for index, testcase in enumerate(prepared):
        if not isinstance(testcase, dict):
            errors.append(f"第 {index + 1} 条用例必须是对象")
            continue

        testcase_id = testcase.get("id") or f"index:{index + 1}"
        if testcase.get("id") in seen_ids:
            errors.append(f"{testcase_id}: 用例 ID 重复")
        elif testcase.get("id"):
            seen_ids.add(testcase["id"])

        if testcase.get("executable") is False:
            excluded_cases += 1
            if _is_missing(testcase.get("skipReason")):
                errors.append(f"{testcase_id}: executable=false 时必须提供 skipReason")
            if not isinstance(testcase.get("params"), dict):
                errors.append(f"{testcase_id}: params 必须是对象")
            continue

        errors.extend(validate_semantics(
            config,
            testcase,
            rule_catalog,
            parameter_specs=parameter_specs,
        ))
        mock_errors = validate_mock_contract(
            config,
            testcase,
            enabled_mock_scenarios,
            mock_readiness=mock_readiness,
        )
        if (
            testcase.get("caseType") == "异常案例"
            or testcase.get("executionMode") == "mock"
        ):
            mock_cases += 1
        errors.extend(f"{testcase_id}: {error}" for error in mock_errors)

        params = testcase.get("params")
        if not isinstance(params, dict):
            errors.append(f"{testcase_id}: params 必须是对象")
            continue

        explicit_fields = {
            field for field, value in params.items()
            if not _is_missing(value)
        }
        changed = False
        if fill_defaults:
            selected_defaults = copy.deepcopy(defaults)
            selected_defaults.update(collect_case_defaults(config, testcase))
            for field, default_value in selected_defaults.items():
                if field not in explicit_fields:
                    params[field] = copy.deepcopy(default_value)
                    filled_fields[field] += 1
                    changed = True

        missing = [
            field for field in required
            if field not in params or _is_missing(params[field])
        ]
        if missing:
            errors.append(
                f"{testcase_id}: 缺少必需参数 {', '.join(missing)}"
            )

        if changed:
            changed_cases += 1

    summary = {
        "totalCases": len(prepared),
        "changedCases": changed_cases,
        "filledFields": dict(sorted(filled_fields.items())),
        "requiredParams": required,
        "mockCases": mock_cases,
        "excludedCases": excluded_cases,
        "errorCount": len(errors),
    }
    return prepared, errors, summary


def prepare_testcase_document(
    document,
    config,
    fill_defaults=True,
    enabled_mock_scenarios=None,
    strategy_model=None,
    mock_readiness=None,
):
    """Prepare either a raw case array or a ``{"testCases": [...]}`` document."""
    if isinstance(document, list):
        prepared, errors, summary = prepare_testcases(
            document,
            config,
            fill_defaults=fill_defaults,
            enabled_mock_scenarios=enabled_mock_scenarios,
            strategy_model=strategy_model,
            mock_readiness=mock_readiness,
        )
        return prepared, errors, summary

    if isinstance(document, dict) and isinstance(document.get("testCases"), list):
        prepared, errors, summary = prepare_testcases(
            document["testCases"],
            config,
            fill_defaults=fill_defaults,
            enabled_mock_scenarios=enabled_mock_scenarios,
            strategy_model=strategy_model,
            mock_readiness=mock_readiness,
        )
        prepared_document = copy.deepcopy(document)
        prepared_document["testCases"] = prepared
        return prepared_document, errors, summary

    return document, [
        '测试用例根节点必须是 JSON 数组或包含 "testCases" 数组的对象'
    ], {
        "totalCases": 0,
        "changedCases": 0,
        "filledFields": {},
        "errorCount": 1,
    }


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="提交前补全并校验天策策略测试用例参数"
    )
    parser.add_argument("--config", required=True, help="策略配置 JSON")
    parser.add_argument("--testcases", required=True, help="测试用例 JSON")
    parser.add_argument("--output", help="补全后的输出 JSON")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只校验，不写输出文件",
    )
    parser.add_argument(
        "--no-fill",
        action="store_true",
        help="不应用默认值，只校验原始用例",
    )
    parser.add_argument(
        "--enabled-mock-scenario",
        action="append",
        default=[],
        help="本次已真实启用的 mock 场景；可重复传入",
    )
    parser.add_argument(
        "--strategy-model",
        help="discover_strategy 生成的 parsed_strategy.json，用于规则语义校验",
    )
    parser.add_argument(
        "--mock-readiness",
        help="mock_probe.py 生成的就绪证明 JSON",
    )
    args = parser.parse_args()

    if not args.check_only and not args.output:
        parser.error("非 --check-only 模式必须提供 --output")

    try:
        config = _load_json(args.config)
        testcases = _load_json(args.testcases)
        strategy_model = (
            _load_json(args.strategy_model)
            if args.strategy_model
            else None
        )
        mock_readiness = (
            _load_json(args.mock_readiness)
            if args.mock_readiness
            else None
        )
    except (OSError, json.JSONDecodeError) as exc:
        print(f"读取 JSON 失败: {exc}", file=sys.stderr)
        return 1

    prepared, errors, summary = prepare_testcase_document(
        testcases,
        config,
        fill_defaults=not args.no_fill,
        enabled_mock_scenarios=args.enabled_mock_scenario,
        strategy_model=strategy_model,
        mock_readiness=mock_readiness,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if not args.check_only:
        Path(args.output).write_text(
            json.dumps(prepared, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已写入: {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
