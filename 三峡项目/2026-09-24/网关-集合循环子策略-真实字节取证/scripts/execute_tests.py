#!/usr/bin/env python3
"""
天策策略测试 — Python 批量执行器 v2.1.0

替代 submit_batch.js 的浏览器执行方式，直接通过 HTTP API 提交测试用例。
v2.1.0: executable=false 用例直接归档为 skipped；支持 executionPath 规则集证据。
v2.0.0: 增加强制平台门禁、mock 契约和证据驱动的断言状态。
v1.5.0: 提交前应用策略配置中的默认参数并校验必填参数。
v1.4.0: 改用 getAllCompontlog API（token）获取规则级执行详情，含 hitRules 解析。
v1.3.0: 引入 getAllCompontlog 替代 baseInfo。
v1.1.0: 增量保存（每10条/遇失败时写入）、--resume 断点续跑、周期进度统计。
v1.0.0: 初始版本，HTTP API 批量提交。

API 端点：POST /noahApi/lab/policytest/create (form-urlencoded)
CSRF 处理：X-Cf-Random + _csrf_ 双 header

用法:
  python3 execute_tests.py \\
    --host https://tiance.example.invalid \\
    --cookie "JSESSIONID=xxx; _csrf_=yyy" \\
    --strategy-config strategies/bhjcpostMainBefore.json \\
    --testcases testcases.json \\
    --output results.json

  # 断点续跑（从中途崩溃处继续，跳过已完成的用例）
  python3 execute_tests.py --host ... --cookie ... --resume ...

  # 也可单独传 CSRF token（如果不包含在 cookie 中）
  python3 execute_tests.py --host ... --cookie ... --csrf yyy ...

输出 results.json 格式（与 update_report.py 兼容）:
  [
    {
      "id": "TC_001",
      "expected": "黄色预警",
      "batch": 1,
      "rs": "2",
      "dt": "黄色预警",
      "dtCode": "yellowwarnbh",
      "uuid": "xxx",
      "token": "xxx",
      "err": "",
      "executionOk": true,
      "assertionStatus": "passed",
      "evidenceStatus": "complete",
      "pass": true
    }
  ]

退出码:
  0 — 全部用例提交完成（不代表全部通过）
  1 — 参数、平台门禁、预检或文件错误
  2 — 会话过期 (401)
"""

import argparse
import copy
import fcntl
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# HTTP 抽象层：优先 requests，回退 urllib
# ---------------------------------------------------------------------------
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error
    import urllib.parse
    import ssl


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
MAX_RETRY = 0          # Mutating requests are not retried by default.
BATCH_DELAY = 0.8      # 用例间等待秒数
RETRY_DELAY = 2.0      # 重试间等待秒数
REQUEST_TIMEOUT = 60   # 单次请求超时秒数
CHECKPOINT_INTERVAL = 10  # 每 N 条增量保存一次结果
_RESULT_EVALUATOR_MODULE = None
_PLATFORM_GUARD_MODULE = None


def prepare_cases_for_submission(
    test_cases,
    config,
    enabled_mock_scenarios=None,
    strategy_model=None,
    mock_readiness=None,
):
    """Apply the shared policy-test preflight before any remote submission."""
    preparer_path = (
        Path(__file__).resolve().parents[2]
        / "tiance-policy-test"
        / "scripts"
        / "prepare_testcases.py"
    )
    if not preparer_path.exists():
        raise RuntimeError(f"参数预检脚本不存在: {preparer_path}")

    spec = importlib.util.spec_from_file_location(
        "tiance_policy_test_prepare_testcases",
        preparer_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载参数预检脚本: {preparer_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare_testcases(
        test_cases,
        config,
        enabled_mock_scenarios=enabled_mock_scenarios,
        strategy_model=strategy_model,
        mock_readiness=mock_readiness,
    )


def select_test_cases(test_cases, case_ids=None, case_range=None):
    """Select explicit cases while preserving source order."""
    selected_ids = set(case_ids or [])
    if case_range:
        if ":" not in case_range:
            raise ValueError("--case-range 必须使用 START:END 格式")
        start_id, end_id = case_range.split(":", 1)
        ordered_ids = [str(case.get("id", "")) for case in test_cases]
        if start_id not in ordered_ids or end_id not in ordered_ids:
            raise ValueError(
                f"--case-range 找不到边界: {start_id}:{end_id}"
            )
        start_index = ordered_ids.index(start_id)
        end_index = ordered_ids.index(end_id)
        if start_index > end_index:
            raise ValueError("--case-range 起始用例位于结束用例之后")
        selected_ids.update(ordered_ids[start_index:end_index + 1])
    if not selected_ids:
        return list(test_cases)
    selected = [
        case for case in test_cases
        if str(case.get("id", "")) in selected_ids
    ]
    missing = selected_ids - {
        str(case.get("id", "")) for case in selected
    }
    if missing:
        raise ValueError(f"找不到用例: {', '.join(sorted(missing))}")
    return selected


def load_mock_readiness(path, max_age_seconds=600):
    """Load a recent mock readiness proof."""
    proof = json.loads(Path(path).read_text(encoding="utf-8"))
    captured_at = proof.get("capturedAt") if isinstance(proof, dict) else None
    if not captured_at:
        raise ValueError("mock 就绪证明缺少 capturedAt")
    parsed = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = time.time() - parsed.timestamp()
    if age < -60 or age > max_age_seconds:
        raise ValueError(
            f"mock 就绪证明已过期或时间无效: age={int(age)}s"
        )
    return proof


def evaluate_submission_result(expected, result, comparison_rules):
    """Evaluate a completed execution using platform evidence."""
    global _RESULT_EVALUATOR_MODULE
    if _RESULT_EVALUATOR_MODULE is not None:
        return _RESULT_EVALUATOR_MODULE.evaluate_result(
            expected,
            result,
            comparison_rules,
        )

    evaluator_path = (
        Path(__file__).resolve().parents[2]
        / "tiance-policy-test"
        / "scripts"
        / "result_evaluator.py"
    )
    if not evaluator_path.exists():
        raise RuntimeError(f"结果评估脚本不存在: {evaluator_path}")

    spec = importlib.util.spec_from_file_location(
        "tiance_policy_test_result_evaluator",
        evaluator_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载结果评估脚本: {evaluator_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _RESULT_EVALUATOR_MODULE = module
    return module.evaluate_result(expected, result, comparison_rules)


def validate_platform_guard(
    config,
    host,
    cookie,
    csrf,
    org_code,
    snapshot_path=None,
):
    """Require current published platform metadata before submission."""
    global _PLATFORM_GUARD_MODULE
    guard_path = (
        Path(__file__).resolve().parents[2]
        / "tiance-policy-test"
        / "scripts"
        / "platform_guard.py"
    )
    if not guard_path.exists():
        raise RuntimeError(f"平台门禁脚本不存在: {guard_path}")

    if _PLATFORM_GUARD_MODULE is None:
        spec = importlib.util.spec_from_file_location(
            "tiance_policy_test_platform_guard",
            guard_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法加载平台门禁脚本: {guard_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PLATFORM_GUARD_MODULE = module
    module = _PLATFORM_GUARD_MODULE

    if snapshot_path:
        snapshot = module.load_snapshot(snapshot_path)
        module.validate_snapshot_freshness(snapshot)
    else:
        if not org_code:
            raise RuntimeError(
                "缺少 orgCode，无法查询平台策略元数据；"
                "请传 --org-code 或 --platform-snapshot"
            )
        snapshot = module.fetch_platform_snapshot(
            host=host,
            cookie=cookie,
            csrf=csrf,
            org_code=org_code,
            policy_code=config["policyCode"],
            biz_type=config.get("bizType"),
        )

    report = module.validate_platform_config(config, snapshot)
    if not report["ok"]:
        raise RuntimeError("; ".join(report["errors"]))
    return report


# ---------------------------------------------------------------------------
# HTTP 请求封装
# ---------------------------------------------------------------------------

def _url_quote(val):
    """URL-encode a form value"""
    from urllib.parse import quote
    return quote(str(val), safe="")


def serialize_form_data(body):
    """Share the exact serialization between submission and evidence capture."""
    return "&".join(f"{k}={_url_quote(v)}" for k, v in body.items())


def make_submission_attempt(host, body, attempt):
    payload = serialize_form_data(body)
    return {
        "attempt": attempt,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "request": {
            "method": "POST",
            "url": f"{host.rstrip('/')}/noahApi/lab/policytest/create",
            "contentType": "application/x-www-form-urlencoded;charset=UTF-8",
            "body": payload,
            "payloadSha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        },
    }


def post_test_case(host, body, cookie, csrf):
    """
    提交单条测试用例到 /noahApi/lab/policytest/create
    返回 (status_code, response_dict)
    """
    url = f"{host.rstrip('/')}/noahApi/lab/policytest/create"
    form_data = serialize_form_data(body)

    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Accept": "application/json",
    }
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Cf-Random"] = csrf
        headers["_csrf_"] = csrf

    if HAS_REQUESTS:
        resp = requests.post(url, data=form_data, headers=headers,
                             timeout=REQUEST_TIMEOUT, verify=False)
        return resp.status_code, resp.json()
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            url, data=form_data.encode("utf-8"),
            headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx)
            body_text = resp.read().decode("utf-8")
            return resp.status, json.loads(body_text)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(body_text)
            except json.JSONDecodeError:
                return e.code, {"success": False, "errorMsg": body_text[:200]}


def retryable_submission_error(status, response):
    """Return a retry reason for transport, API, or execution failures."""
    if status == 0 or status == 429 or status >= 500:
        return f"HTTP_{status}"
    if not isinstance(response, dict):
        return "INVALID_RESPONSE"
    if not response.get("success", False):
        return (
            "API_FAILED: "
            + str(
                response.get("message")
                or response.get("msg")
                or response.get("errorMsg")
                or "unknown"
            )
        )
    data = response.get("data", {})
    if isinstance(data, dict) and str(data.get("runStatus", "")) == "-2":
        return "RUN_FAILED: " + str(
            data.get("errorMsg") or "runStatus=-2"
        )
    return ""


def query_base_info(host, uuid, cookie, csrf):
    """查询 baseInfo API 获取真实执行决策路径。
    返回 (status_code, response_dict)。
    """
    url = (f"{host.rstrip('/')}/noahApi/policy/report/test/baseInfo"
           f"?id={uuid}&token={uuid}&tokenId={uuid}&type=1")
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Cf-Random"] = csrf
        headers["_csrf_"] = csrf

    if HAS_REQUESTS:
        resp = requests.get(url, headers=headers, timeout=30, verify=False)
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {}
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=30, context=ctx)
            body_text = resp.read().decode("utf-8")
            return resp.status, json.loads(body_text)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(body_text)
            except json.JSONDecodeError:
                return e.code, {}
        except Exception:
            return 0, {}


def _report_get(host, path, params, cookie, csrf):
    """Shared GET helper for /noahApi/policy/report/* evidence endpoints.

    Returns (status_code, response_dict); response_dict is {} on any failure.
    """
    query = "&".join(f"{key}={value}" for key, value in params.items())
    url = f"{host.rstrip('/')}{path}?{query}"
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Cf-Random"] = csrf
        headers["_csrf_"] = csrf

    if HAS_REQUESTS:
        try:
            resp = requests.get(url, headers=headers, timeout=30, verify=False)
        except Exception:
            return 0, {}
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, {}

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body_text)
        except json.JSONDecodeError:
            return e.code, {}
    except Exception:
        return 0, {}
    body_text = resp.read().decode("utf-8", errors="replace")
    try:
        return resp.status, json.loads(body_text)
    except json.JSONDecodeError:
        return resp.status, {}


def query_component_log(host, token, cookie, csrf):
    """查询 getAllCompontlog API 获取规则级执行详情。

    注意：此接口使用 token（执行流水号）而非 uuid 调用。
    返回 (status_code, response_dict)。
    """
    return _report_get(
        host,
        "/noahApi/policy/report/getAllCompontlog",
        {"id": token, "reportAuth": "false", "tokenId": token, "type": "1"},
        cookie,
        csrf,
    )


def query_run_data(host, token, node_type, cookie, csrf):
    """查询 runData 分层取证 API（按 nodeType 取某一层执行详情）。

    nodeType 语义（平台文档，未全部真实验证）：
      8 = 子策略 token 与决策结果；1 = 规则集命中详情；5 = 函数执行详情。
    与 query_component_log 同样使用 token（执行流水号）而非 uuid。
    返回 (status_code, response_dict)。
    """
    return _report_get(
        host,
        "/noahApi/policy/report/runData",
        {"nodeType": node_type, "reportAuth": "false", "tokenId": token, "type": "1"},
        cookie,
        csrf,
    )


def _normalize_rule_catalog(rule_catalog):
    """Return valid rule catalog entries without trusting opaque platform ids."""
    if not isinstance(rule_catalog, list):
        return []
    return [
        {"code": str(item["code"]), "name": str(item["name"])}
        for item in rule_catalog
        if isinstance(item, dict) and item.get("code") and item.get("name")
    ]


def _infer_area_route(third_party_results):
    """Infer the executed area branch from the actual feature-service nodes."""
    names = " ".join(
        str(item.get("nodeName", ""))
        for item in third_party_results
        if isinstance(item, dict)
    )
    if any(marker in names for marker in ("区县", "区级", "县级", "district")):
        return "district"
    if any(marker in names for marker in ("市级", "地市", "city")):
        return "city"
    return ""


def _resolve_rule_identity(rule_name, rule_code, node_name, catalog, route):
    """Map platform rule names to stable catalog codes and canonical names."""
    by_code = {item["code"]: item for item in catalog}
    if rule_code and rule_code in by_code:
        item = by_code[rule_code]
        return item["code"], item["name"]

    name = str(rule_name or "").strip()
    exact = [item for item in catalog if item["name"] == name]
    if len(exact) == 1:
        return exact[0]["code"], exact[0]["name"]

    candidates = [
        item for item in catalog
        if name and (item["name"].startswith(name) or name.startswith(item["name"]))
    ]
    context = f"{name} {node_name}"
    if len(candidates) > 1:
        if route == "district" or "区县" in context or "县级" in context:
            routed = [
                item for item in candidates
                if "区县" in item["name"] or "县级" in item["name"]
            ]
            if len(routed) == 1:
                candidates = routed
        elif route == "city" or "地市" in context or "市级" in context:
            routed = [
                item for item in candidates
                if "地市" in item["name"] or "市级" in item["name"]
            ]
            if len(routed) == 1:
                candidates = routed
    if len(candidates) == 1:
        return candidates[0]["code"], candidates[0]["name"]
    return str(rule_code or ""), name


def _parse_field_entries(entries):
    """Normalize a platform nodeInputList/nodeOutputList into field entries."""
    items = []
    for item in entries or []:
        if not isinstance(item, dict):
            continue
        name = (
            item.get("name")
            or item.get("fieldName")
            or item.get("field")
            or item.get("serviceParam")
            or ""
        )
        if not str(name).strip():
            continue
        items.append({
            "field": str(name),
            "displayName": str(item.get("displayName") or item.get("bizExplain") or ""),
            "value": item.get("value"),
        })
    return items


def _loads_maybe_json(value):
    """Parse a JSON-encoded platform string, returning None when it is not one."""
    if not isinstance(value, str) or not value.strip():
        return None
    if value.strip()[:1] not in "{[":
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_decision_tool_conditions(condition_set):
    """Flatten a decision tool conditionSet into comparable condition entries.

    ``isHit`` is the platform's own verdict, so assertions read it instead of
    re-evaluating thresholds. Values arrive as numbers or strings depending on
    the tool type; they are kept raw here and stringified by comparators.
    """
    conditions = []
    if not isinstance(condition_set, dict):
        return conditions
    for group in condition_set.get("conditionGroup") or []:
        if not isinstance(group, dict):
            continue
        for condition in group.get("conditions") or []:
            if not isinstance(condition, dict):
                continue
            conditions.append({
                "field": str(condition.get("leftFieldName") or ""),
                "fieldDesc": str(condition.get("leftFieldDesc") or ""),
                "operator": str(condition.get("operator") or ""),
                "expected": condition.get("rightValue"),
                "actual": condition.get("leftValue"),
                "hit": condition.get("isHit"),
            })
    return conditions


def _parse_decision_tool_trace(execute_detail):
    """Parse DecisionToolServiceNode.extension.executeDetail into a branch trace.

    Verified against three byte-exact read-only 三峡 (org ``sxdb``) runs captured
    2026-09-24 covering D_TREE / D_MATRIX / D_TABLE. The payload is a JSON *string*
    holding an array of ``{nodeType: "ROOT"|"CHILD"|"DECISION", nodeId, nodeDesc,
    conditionSet?, decisionResult?}``. Only the hit row / branch / leaf is recorded,
    so evidence can prove which branch fired but never which rows were skipped.
    Two skeletons exist and they differ:
    - D_TREE / D_TABLE: ``ROOT -> CHILD -> DECISION``. ``CHILD.nodeId`` is a hash for
      trees and null for tables; ``CHILD.nodeDesc`` is the field name, not the edge
      label. So steps must be identified by conditionSet content or ordinal, never
      by nodeId.
    - D_MATRIX: ``ROOT -> DECISION`` ONLY -- there is NO CHILD step, and both
      ``nodeId`` values are the empty string "". A matrix hit is therefore provable
      only from the DECISION output value, never from a condition step.
    Node types in the flow are ``StartFlowNode``/``EndFlowNode`` (nodeName
    "开始节点"/"结束节点"), not StartEvent/EndEvent. Value types mix: ``leftValue`` is a
    float while the boundary ``rightValue`` stays a string.
    """
    parsed = execute_detail
    if isinstance(parsed, str):
        parsed = _loads_maybe_json(parsed)
        if parsed is None:
            return {"available": False, "parseError": True, "steps": [],
                    "hitConditions": [], "assigned": {}}
    if not isinstance(parsed, list):
        return {"available": False, "parseError": False, "steps": [],
                "hitConditions": [], "assigned": {}}

    steps = []
    assigned = {}
    for ordinal, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            continue
        step = {
            "ordinal": ordinal,
            "stepType": str(entry.get("nodeType") or ""),
            "desc": str(entry.get("nodeDesc") or ""),
            "platformNodeId": entry.get("nodeId"),
            "conditions": _parse_decision_tool_conditions(entry.get("conditionSet")),
        }
        decision = entry.get("decisionResult")
        if isinstance(decision, dict):
            step["assigned"] = {str(key): value for key, value in decision.items()}
            assigned.update(step["assigned"])
        steps.append(step)

    hit_conditions = [
        condition
        for step in steps
        for condition in step["conditions"]
        if condition.get("hit") is True
    ]
    return {
        "available": bool(steps),
        "parseError": False,
        "steps": steps,
        "hitConditions": hit_conditions,
        "assigned": assigned,
    }


_CHILD_TOKEN_KEYS = ("token", "tokenId", "childToken", "subToken", "tokenIds")


def _walk_child_tokens(value):
    """Recursively collect child/sub-policy tokens from any platform payload."""
    tokens = []
    seen = set()

    def policy_code_of(container):
        for key in ("policyCode", "code"):
            found = container.get(key)
            if isinstance(found, str) and found.strip():
                return found.strip()
        nested = container.get("policyVersionDTO")
        if isinstance(nested, dict):
            return policy_code_of(nested)
        return ""

    def walk(node):
        if isinstance(node, dict):
            matched_token_key = False
            for key in _CHILD_TOKEN_KEYS:
                candidate = node.get(key)
                if isinstance(candidate, str) and candidate.strip() and candidate not in seen:
                    seen.add(candidate)
                    tokens.append({
                        "token": candidate.strip(),
                        "sourceKey": key,
                        "policyCode": policy_code_of(node),
                    })
                    matched_token_key = True
                    break
                if isinstance(candidate, list):
                    # Real ChildFlowNode carries child execution tokens as
                    # ``extension.tokenIds = [<str>, ...]`` (array-valued).
                    added = False
                    for item in candidate:
                        if (isinstance(item, str) and item.strip()
                                and item not in seen):
                            seen.add(item)
                            tokens.append({
                                "token": item.strip(),
                                "sourceKey": key,
                                "policyCode": policy_code_of(node),
                            })
                            added = True
                    if added:
                        matched_token_key = True
                        break
            if matched_token_key:
                # A node that itself declares child tokens (e.g. the extension
                # dict) is fully handled here; do not descend into its token
                # strings and risk re-walking them under a different identity.
                pass
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        else:
            decoded = _loads_maybe_json(node)
            if decoded is not None:
                walk(decoded)

    walk(value)
    return tokens


def _extract_child_tokens(node):
    """Best-effort child token extraction for sub-policy nodes.

    Verified against a real read-only 三峡 (``sxdb``) run (2026-09-24,
    ``bhjcpostMainBefore`` collection sub-policy): the runtime node type is
    ``ChildFlowNode`` whose child execution tokens arrive as
    ``extension.tokenIds`` (an array), with per-element results mirrored in the
    ``nodeOutputList`` ``C_O_*`` array fields. Extraction still walks both the
    ``extension`` and ``nodeOutputList`` containers so the older documented
    shapes stay covered. Callers must treat an empty result as
    "evidence unavailable", never as "no sub-policies ran".
    """
    if not isinstance(node, dict):
        return []
    tokens = []
    seen = set()
    for container in (node.get("extension"), node.get("nodeOutputList")):
        for item in _walk_child_tokens(container):
            if item["token"] in seen:
                continue
            seen.add(item["token"])
            tokens.append(item)
    return tokens


def _parse_gateway_node(node):
    """Record a gateway's routing evidence.

    Verified against a real read-only 三峡 (``sxdb``) run (2026-09-24,
    ``crossScoreFlow`` ``ExclusiveGateway``): the gateway's evaluated field(s)
    arrive in ``nodeInputList`` (e.g. ``C_F_APPLYSCORE=62``), ``nodeOutputList``
    is ALWAYS empty, and the actual branch selection lives in ``extension``:
    ``conditions`` is the list of taken branch indices (e.g. ``[2]``),
    ``conditionRuleUuid`` identifies the condition rule set that drove the
    choice, and ``type`` marks the gateway position (``start``). Therefore
    ``selectedBranch`` (from ``extension.conditions``) is the authoritative
    routing evidence; ``routeFields`` is retained only for back-compat and is
    empty in the captured payload. ``extension`` is still passed through so
    reviewers can read any fields the parser does not yet model.
    """
    extension = node.get("extension")
    if isinstance(extension, str):
        decoded = _loads_maybe_json(extension)
        extension = decoded if decoded is not None else {"raw": extension[:500]}
    extension = extension if isinstance(extension, dict) else {}
    selected_branch = extension.get("conditions")
    if not isinstance(selected_branch, list):
        selected_branch = []
    return {
        "nodeName": str(node.get("nodeName") or ""),
        "nodeId": str(node.get("nodeId") or ""),
        "inputs": _parse_field_entries(node.get("nodeInputList")),
        "routeFields": _parse_field_entries(node.get("nodeOutputList")),
        "selectedBranch": [str(item) for item in selected_branch],
        "conditionRuleUuid": str(extension.get("conditionRuleUuid") or ""),
        "gatewayType": str(extension.get("type") or ""),
        "extension": extension,
    }


# flowModelinAndOutputParams nodeType vocabulary.
# DecisionToolServiceNode is verified against three read-only 三峡 (org ``sxdb``)
# runs. Gateways and sub-policies were subsequently captured from real read-only
# 三峡 (``sxdb``) runs (2026-09-24: ExclusiveGateway via ``crossScoreFlow`` and
# the collection sub-policy via ``bhjcpostMainBefore``). The real runtime
# sub-policy node type is ``ChildFlowNode`` — NOT the api-reference-documented
# ``SubPolicyNode`` / ``CollectionSubPolicyNode``, which are retained only for
# permissive back-compat. Parsing stays permissive: callers must still treat a
# missing entry as "evidence unavailable" rather than "node did not run".
DECISION_TOOL_NODE_TYPES = ("DecisionToolServiceNode",)
SUB_POLICY_NODE_TYPES = ("ChildFlowNode", "SubPolicyNode", "CollectionSubPolicyNode")
GATEWAY_NODE_TYPES = ("ExclusiveGateway", "ParallelGateway", "InclusiveGateway")


def _extension_of(node):
    extension = node.get("extension")
    if isinstance(extension, str):
        decoded = _loads_maybe_json(extension)
        extension = decoded if decoded is not None else {}
    return extension if isinstance(extension, dict) else {}


def _parse_field_map(field_map):
    """Normalize getAllCompontlog ``fieldMap`` into {field: value + writer ids}.

    ``nodeIdList`` holds the flow node ``nodeId`` values that wrote the field.
    Verified caveat: the array order is NOT execution order (the chained
    two-tool run listed the last writer first), so it is exposed as a set of
    writer ids and ordering must come from ``flowOrder`` instead.
    """
    fields = {}
    if not isinstance(field_map, dict):
        return fields
    for name, entry in field_map.items():
        if not isinstance(entry, dict):
            continue
        node_ids = entry.get("nodeIdList")
        if not isinstance(node_ids, list):
            node_ids = []
        fields[str(name)] = {
            "field": str(name),
            "displayName": str(entry.get("displayName") or entry.get("bizExplain") or ""),
            "value": entry.get("value"),
            "dataType": entry.get("dataType"),
            "writerNodeIds": [str(item) for item in node_ids if item is not None],
        }
    return fields


def parse_component_evidence(comp_log_resp, rule_catalog=None):
    """Extract structured evidence for rules, functions, tools, paths and nodes."""
    if not isinstance(comp_log_resp, dict) or comp_log_resp.get('success') is not True:
        return {}

    data = comp_log_resp.get('data', {})
    if not isinstance(data, dict):
        return {}

    flow = data.get('flowModelinAndOutputParams')
    if not isinstance(flow, list):
        return {}

    rule_results = []
    function_results = []
    third_party_results = []
    decision_tool_results = []
    sub_policy_results = []
    gateway_results = []
    flow_order = []
    overall_result = ''
    for node in flow:
        if not isinstance(node, dict):
            continue
        node_type = node.get('nodeType', '')
        node_name = node.get('nodeName', '')
        node_name = node_name if isinstance(node_name, str) else ""
        node_id = str(node.get("nodeId") or "")
        outputs = node.get('nodeOutputList', []) or []
        flow_order.append({
            "ordinal": len(flow_order),
            "nodeType": str(node_type or ""),
            "nodeName": node_name,
            "nodeId": node_id,
        })

        if node_type == 'RuleSetServiceNode':
            rule_node = {
                "nodeName": node_name,
                "nodeCode": (
                    node.get("nodeCode")
                    or node.get("ruleSetCode")
                    or node.get("serviceCode")
                    or ""
                ),
                "outputs": [],
                "hitRules": [],
                "hitEvidenceComplete": False,
                "input": copy.deepcopy(node.get("nodeInputList", []) or []),
                "rawExecutionDetail": copy.deepcopy(
                    (node.get("extension") or {}).get("executeDetail")
                    if isinstance(node.get("extension"), dict) else None
                ),
            }
            if not isinstance(rule_node["nodeCode"], str):
                rule_node["nodeCode"] = ""
            for out in outputs:
                if isinstance(out, dict):
                    val = out.get('value', '')
                    rule_node["outputs"].append({
                        "field": (
                            out.get('fieldName')
                            or out.get('name')
                            or out.get('field')
                            or out.get('serviceParam')
                            or "value"
                        ),
                        "value": val,
                    })

            # 从 extension.executeDetail 提取命中规则详情
            ext = node.get('extension', {})
            detail_str = ext.get('executeDetail', '') if isinstance(ext, dict) else ''
            if detail_str:
                try:
                    detail = json.loads(detail_str) if isinstance(detail_str, str) else detail_str
                    hit_rules = detail.get('hitRules') if isinstance(detail, dict) else None
                    rule_node["hitEvidenceComplete"] = isinstance(hit_rules, list) and all(
                        isinstance(hit, dict) and isinstance(hit.get("ruleCode"), str)
                        and bool(hit["ruleCode"].strip()) for hit in hit_rules
                    )
                    if hit_rules:
                        for hr in hit_rules:
                            if isinstance(hr, dict):
                                rc = hr.get('ruleCode', '')
                                rn = hr.get('ruleName', '') or hr.get('name', '')
                                rl = hr.get('riskLevelName', '') or hr.get('riskLevel', '')
                                rule_node["hitRules"].append({
                                    "ruleCode": rc,
                                    "ruleName": rn,
                                    "riskLevel": rl,
                                    "platformRuleId": hr.get('id', ''),
                                })
                except (json.JSONDecodeError, TypeError):
                    pass
            rule_results.append(rule_node)

        if node_type == 'FunctionServiceNode':
            for out in outputs:
                if isinstance(out, dict) and 'value' in out:
                    field = (
                        out.get('fieldName')
                        or out.get('name')
                        or out.get('field')
                        or out.get('serviceParam')
                        or "value"
                    )
                    value = out.get('value', '')
                    function_results.append({
                        "nodeName": node_name,
                        "field": field,
                        "value": value,
                    })
                    if '综合' in node_name:
                        overall_result = value

        if node_type == 'FeatureServiceNode':
            fields = {}
            for out in outputs:
                if not isinstance(out, dict) or 'value' not in out:
                    continue
                field = (
                    out.get('fieldName')
                    or out.get('name')
                    or out.get('field')
                    or out.get('serviceParam')
                    or "value"
                )
                fields[str(field)] = out.get('value', '')
            third_party_results.append({
                "nodeName": node_name,
                "fields": fields,
                "input": node.get("nodeInputList", []) or [],
            })

        if node_type in DECISION_TOOL_NODE_TYPES:
            extension = _extension_of(node)
            detail = extension.get("executeDetail")
            trace = _parse_decision_tool_trace(detail)
            decision_tool_results.append({
                "nodeName": node_name,
                "nodeId": node_id,
                "ordinal": flow_order[-1]["ordinal"],
                "toolCode": str(extension.get("code") or ""),
                "toolVersion": str(extension.get("version") or ""),
                "inputs": _parse_field_entries(node.get("nodeInputList")),
                "outputs": _parse_field_entries(outputs),
                "available": trace["available"],
                "parseError": trace["parseError"],
                "steps": trace["steps"],
                "hitConditions": trace["hitConditions"],
                "assigned": trace["assigned"],
                "rawExecutionDetail": copy.deepcopy(detail),
            })

        if node_type in SUB_POLICY_NODE_TYPES:
            sub_policy_results.append({
                "nodeName": node_name,
                "nodeId": node_id,
                "ordinal": flow_order[-1]["ordinal"],
                "children": _extract_child_tokens(node),
            })

        if node_type in GATEWAY_NODE_TYPES:
            gateway = _parse_gateway_node(node)
            gateway["ordinal"] = flow_order[-1]["ordinal"]
            gateway["nodeType"] = str(node_type or "")
            gateway_results.append(gateway)

    catalog = _normalize_rule_catalog(rule_catalog)
    route = _infer_area_route(third_party_results)
    for node in rule_results:
        for hit_rule in node.get("hitRules", []):
            code, name = _resolve_rule_identity(
                hit_rule.get("ruleName"),
                hit_rule.get("ruleCode"),
                node.get("nodeName", ""),
                catalog,
                route,
            )
            hit_rule["ruleCode"] = code
            hit_rule["ruleName"] = name

    return {
        "pathComplete": bool(flow) and all(isinstance(node, dict)
            and isinstance(node.get("nodeType"), str) and bool(node["nodeType"].strip()) for node in flow),
        "rules": rule_results,
        "functions": function_results,
        "thirdPartyNodes": third_party_results,
        "decisionTools": decision_tool_results,
        "subPolicies": sub_policy_results,
        "gateways": gateway_results,
        "flowOrder": flow_order,
        "pathLines": [str(item) for item in data.get("diagramLine") or [] if item is not None]
                     if isinstance(data.get("diagramLine"), list) else [],
        "fields": _parse_field_map(data.get("fieldMap")),
        "overallResult": overall_result,
    }


def _fmt_value(value):
    """Render a platform value compactly for the evidence column."""
    if value is None:
        return "null"
    if isinstance(value, str):
        text = value.strip()
        return text if text else "''"
    return str(value)


def _node_label(node):
    """Best available human identity for a flow node."""
    return str(node.get("nodeName") or "").strip() or str(node.get("nodeId") or "").strip() or "?"


def _render_decision_tool_entry(tool):
    """Render one DecisionToolServiceNode branch trace.

    Only the hit row / branch / leaf is recorded by the platform (verified), so
    the trace proves which branch fired and never which rows were skipped.
    """
    label = str(tool.get("nodeName") or "").strip() or str(tool.get("nodeId") or "")
    header = f"决策工具: {label}"
    if tool.get("toolCode"):
        header += f"({tool['toolCode']})"
    header += f" #{tool.get('ordinal', '')}"
    lines = [header]
    if tool.get("parseError"):
        lines.append("  执行详情解析失败(证据不可用)")
        return lines
    if not tool.get("available"):
        lines.append("  证据不可用(无执行详情)")
        return lines
    for step in tool.get("steps", []) or []:
        desc = str(step.get("desc") or "").strip()
        line = f"  [{step.get('stepType', '')}]"
        if desc:
            line += f" {desc}"
        lines.append(line)
    for condition in tool.get("hitConditions", []) or []:
        lines.append(
            f"  命中 {condition.get('field', '')}"
            f" 运算 {condition.get('operator', '')}"
            f" 期望 {_fmt_value(condition.get('expected'))}"
            f" 实际 {_fmt_value(condition.get('actual'))}"
        )
    for field, value in (tool.get("assigned") or {}).items():
        lines.append(f"  赋值 {field}={_fmt_value(value)}")
    return lines


def _render_path_entry(structured):
    """Render the traversed flow path (node order plus walked line count)."""
    names = [
        _node_label(item)
        for item in structured.get("flowOrder", []) or []
        if isinstance(item, dict)
    ]
    if not names:
        return []
    lines = [" → ".join(names)]
    path_lines = structured.get("pathLines") or []
    if path_lines:
        lines.append(f"  走过连线 {len(path_lines)} 条")
    return lines


def _render_gateway_entry(gateway):
    """Render a gateway's evaluated inputs and routed outputs.

    CAVEAT: gateway payload shape is documented only, not captured from a real
    run; anything the parser could not interpret stays visible as ``extension``.
    """
    label = str(gateway.get("nodeName") or "").strip() or str(gateway.get("nodeId") or "")
    line = f"网关: {label}({gateway.get('nodeType', '')})"
    inputs = "; ".join(
        f"{item.get('field')}={_fmt_value(item.get('value'))}"
        for item in gateway.get("inputs", []) or []
    )
    routes = "; ".join(
        f"{item.get('field')}={_fmt_value(item.get('value'))}"
        for item in gateway.get("routeFields", []) or []
    )
    if inputs:
        line += f" 判定 {inputs}"
    if routes:
        line += f" 路由 {routes}"
    extension = gateway.get("extension") or {}
    if not inputs and not routes and extension:
        line += f" 扩展 {json.dumps(extension, ensure_ascii=False)[:200]}"
    return line


def _render_subpolicy_entries(node):
    """Render a sub-policy node plus per-child drill evidence status.

    CAVEAT: sub-policy payload shape comes from api-reference.md only. A child
    without evidence is reported as an explicit status string, never as a
    pass/fail conclusion.
    """
    label = str(node.get("nodeName") or "").strip() or str(node.get("nodeId") or "")
    lines = [f"子策略: {label} 下钻={node.get('drillStatus', '未执行')}"]
    children = node.get("children", []) or []
    if not children:
        lines.append(f"  子项证据不可用({node.get('evidenceStatus', 'no-children')})")
        return lines
    for child in children:
        if not isinstance(child, dict):
            continue
        identity = str(child.get("policyCode") or "").strip() or str(child.get("token") or "")[:12]
        lines.append(f"  子项 {identity} status={child.get('evidenceStatus', 'unavailable')}")
    return lines


def render_component_evidence(structured):
    """Render structured component evidence for the Excel report."""
    if not isinstance(structured, dict):
        return ""
    evidence = []
    rendered_rules = []
    for node in structured.get("rules", []) or []:
        outputs = ", ".join(
            f"{item.get('field')}={item.get('value')}"
            for item in node.get("outputs", [])
        )
        rendered_rules.append(
            f"{node.get('nodeName', '')}"
            + (f" → {outputs}" if outputs else "")
        )
        for hit_rule in node.get("hitRules", []):
            rendered_rules.append(
                "  命中: "
                f"{hit_rule.get('ruleCode', '')}"
                f"({hit_rule.get('ruleName', '')})"
                f"[{hit_rule.get('riskLevel', '')}]"
            )
    if rendered_rules:
        evidence.append("规则集执行:\n" + "\n".join(rendered_rules))

    for item in structured.get("functions", []) or []:
        evidence.append(
            f"函数输出: {item.get('nodeName', '')} "
            f"{item.get('field', 'value')}={item.get('value', '')}"
        )
    for item in structured.get("thirdPartyNodes", []) or []:
        rendered = "; ".join(
            f"{field}={value}"
            for field, value in (item.get("fields", {}) or {}).items()
        )
        evidence.append(
            f"三方节点: {item.get('nodeName', '')}"
            + (f" {rendered}" if rendered else "")
        )
    decision_tools = [
        item for item in (structured.get("decisionTools", []) or []) if isinstance(item, dict)
    ]
    gateways = [
        item for item in (structured.get("gateways", []) or []) if isinstance(item, dict)
    ]
    sub_policies = [
        item for item in (structured.get("subPolicies", []) or []) if isinstance(item, dict)
    ]
    for tool in decision_tools:
        evidence.append("\n".join(_render_decision_tool_entry(tool)))
    for gateway in gateways:
        evidence.append(_render_gateway_entry(gateway))
    for node in sub_policies:
        evidence.append("\n".join(_render_subpolicy_entries(node)))
    if decision_tools or gateways or sub_policies:
        path_lines = _render_path_entry(structured)
        if path_lines:
            evidence.append("路径:\n" + "\n".join(path_lines))
    overall_result = structured.get("overallResult", "")
    if overall_result:
        evidence.append(f"综合结果: {overall_result}")
    return "\n".join(evidence)


def parse_component_log(comp_log_resp, expected='', rule_catalog=None):
    """Backward-compatible text rendering of structured component evidence."""
    structured = parse_component_evidence(comp_log_resp, rule_catalog=rule_catalog)
    rendered = render_component_evidence(structured)
    if rendered:
        return rendered

    # 回退：使用 contextFields 中的决策结果
    data = comp_log_resp.get('data', {}) if isinstance(comp_log_resp, dict) else {}
    ctx = data.get('contextFields', {})
    final = ctx.get('S_S_FINALDEALTYPE', '') or ctx.get('finalDealTypeName', '')
    return final


def parse_decision_path(base_info_resp, expected=''):
    """从 baseInfo API 响应中提取 V5 风格决策路径。

    返回格式示例：
      "规则命中\\n保前单户集中度判断(R001) → 单户集中度超限"
      "规则未命中\\n保前单户集中度判断(R001) → 不触发"
    """
    if not base_info_resp or not base_info_resp.get('success'):
        return ''

    records = base_info_resp.get('data', [])
    if isinstance(records, dict):
        records = [records]
    if not records:
        return ''

    # 从记录中提取决策信息
    # baseInfo 返回主策略+子策略，取主策略（第一条）的决策结果
    main_rec = records[0] if records else {}
    policy_deal_type_name = main_rec.get('policyDealTypeName', '') or ''
    policy_deal_type = main_rec.get('policyDealType', '') or ''
    run_status = str(main_rec.get('runStatus', ''))

    # 尝试提取子策略/规则集级别的命中详情
    rule_hits = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        # 检查是否有规则命中详情字段
        rule_details = rec.get('ruleDetails', []) or rec.get('rules', [])
        if isinstance(rule_details, list):
            for rule in rule_details:
                if isinstance(rule, dict):
                    rule_name = rule.get('ruleName', '') or ''
                    rule_code = rule.get('ruleCode', '') or ''
                    hit = rule.get('hit', False) or rule.get('result', '')
                    if rule_name:
                        rule_hits.append({
                            'name': rule_name,
                            'code': rule_code,
                            'hit': hit,
                        })

    # 如果有规则级详情，构造详细决策路径
    if rule_hits:
        hit_rules = [r for r in rule_hits if r['hit']]
        if hit_rules:
            parts = [f"{r['name']}({r['code']})" for r in hit_rules[:3]]
            return f"规则命中\n{', '.join(parts)}"
        else:
            return f"规则未命中\n无规则触发"

    # 回退：使用 policyDealTypeName（策略级决策结果）
    if policy_deal_type_name:
        if policy_deal_type and policy_deal_type not in policy_deal_type_name:
            return f"{policy_deal_type_name}({policy_deal_type})"
        return policy_deal_type_name

    return ''


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def checkpoint_identity(testcase, host, policy_code, policy_version, biz_type, run_id):
    canonical = json.dumps(testcase, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "host": host.rstrip("/"), "policyCode": policy_code,
        "policyVersion": str(policy_version), "bizType": str(biz_type), "runId": run_id,
        "caseKey": testcase.get("caseKey") or testcase.get("id"),
        "caseDigest": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _locked_run(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        bound = inspect.signature(function).bind(*args, **kwargs)
        bound.apply_defaults()
        output = Path(bound.arguments["output_path"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        # Keep the lock inode: unlinking it would let a new caller bypass waiters.
        with output.with_suffix(output.suffix + ".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("This output is already being executed") from exc
            try:
                previous = bound.arguments.get("existing_results")
                if previous is not None:
                    if not output.exists():
                        raise ValueError("Resume requires the durable archive, not an in-memory snapshot")
                    current = json.loads(output.read_text(encoding="utf-8"))
                    if json.dumps(current, sort_keys=True) != json.dumps(previous, sort_keys=True):
                        raise ValueError("Stale resume snapshot; reload the latest archive")
                return function(*args, **kwargs)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    return wrapped


@_locked_run
def execute_tests(host, cookie, csrf, policy_code, policy_name,
                  policy_version, biz_type, test_cases, output_path,
                  batch_delay=BATCH_DELAY, max_retry=MAX_RETRY,
                  existing_results=None, completed_ids=None,
                  comparison_rules=None, evidence_delay=0.3,
                  evidence_workers=1, rule_catalog=None, run_id=None,
                  subpolicy_drill_depth=1,
                  platform_validation=None):
    """批量提交测试用例，返回结果列表。支持断点续跑。"""
    if existing_results is not None and not run_id:
        raise ValueError("Resume requires the original run_id")
    run_id = run_id or uuid.uuid4().hex
    ids = [tc.get("id") for tc in test_cases]
    if any(not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("Test case IDs must be present and unique")
    identities = {tc["id"]: checkpoint_identity(
        tc, host, policy_code, policy_version, biz_type, run_id
    ) for tc in test_cases}
    if existing_results is not None:
        if not resume_identity_matches(existing_results, policy_version, biz_type, identities):
            raise ValueError("Checkpoint identity mismatch; refusing to reuse or overwrite results")
    elif Path(output_path).exists() or completed_ids:
        raise ValueError("Existing output or skipped IDs require verified resume")
    if max_retry < 0:
        raise ValueError("max_retry must be non-negative")
    name_resolution = None
    if platform_validation is not None:
        platform = platform_validation.get("platform", {})
        if platform_validation.get("ok") is not True or any(
            str(platform.get(key)) != str(value) for key, value in (
                ("policyCode", policy_code), ("policyVersion", policy_version), ("bizType", biz_type)
            )
        ):
            raise ValueError("Platform validation does not match submission identity")
        verified_name = platform.get("policyName")
        if not isinstance(verified_name, str) or not verified_name.strip():
            raise ValueError("Platform policyName is missing; refusing local-name fallback")
        name_resolution = copy.deepcopy(platform_validation.get("policyNameResolution") or {
            "local": policy_name, "platform": verified_name,
            "submitted": verified_name, "source": "platform", "changed": policy_name != verified_name,
        })
        if name_resolution.get("submitted") != verified_name or name_resolution.get("platform") != verified_name:
            raise ValueError("Platform name resolution is inconsistent")
        policy_name = verified_name
    results = copy.deepcopy(existing_results or [])
    by_id = {result["id"]: result for result in results}
    total = len(test_cases)
    consecutive_failures = 0
    CIRCUIT_BREAKER_THRESHOLD = 10
    skipped = 0
    pending_evidence = []
    run_started = time.perf_counter()

    for i, tc in enumerate(test_cases):
        tc_id = tc.get("id", f"TC_{i+1:03d}")

        if tc_id in by_id:
            previous = by_id[tc_id]
            if previous.get("checkpointState") == "complete":
                continue
            if previous.get("executionOk") and previous.get("token"):
                _collect_and_evaluate_evidence(
                    previous, tc.get("expected", ""), host, cookie, csrf,
                    comparison_rules or [], evidence_delay, rule_catalog or [],
                    subpolicy_drill_depth,
                )
                previous["checkpointState"] = (
                    "complete" if previous.get("assertionStatus") in {"passed", "failed"}
                    else "evidence_pending"
                )
                _save_results(results, output_path)
                continue
            raise ValueError(f"{tc_id}: submission outcome unresolved; do not resubmit automatically")

        if tc.get("executable") is False:
            skip_reason = tc.get("skipReason") or "not_executable"
            results.append({
                "id": tc_id,
                "expected": tc.get("expected", ""),
                "batch": 1,
                "rs": "",
                "dt": "",
                "dtCode": "",
                "uuid": "",
                "token": "",
                "err": "",
                "policyVersion": policy_version,
                "bizType": biz_type,
                "executionOk": False,
                "assertionStatus": "skipped",
                "evidenceStatus": "not_applicable",
                "pass": False,
                "skipReason": skip_reason,
                "expectedEvidence": tc.get("expectedEvidence", {}),
                "plannedCase": copy.deepcopy(tc),
                "submissionAttempts": [],
                "policyCode": policy_code, "runId": run_id,
                "checkpoint": identities[tc_id], "checkpointState": "complete",
            })
            skipped += 1
            print(
                f"[{i+1}/{total}] {tc_id}: 跳过（{skip_reason}）",
                file=sys.stderr,
            )
            if len(results) % CHECKPOINT_INTERVAL == 0:
                _save_results(results, output_path)
            continue

        tc_expected = tc.get("expected", "")
        tc_params = tc.get("params", {})

        body = {
            "policyCode": policy_code,
            "policyName": policy_name,
            "policyVersion": str(policy_version),
            "bizType": str(biz_type),
            "testcase": "1",
            "customParams": "{}",
            "params": json.dumps(tc_params, ensure_ascii=False),
        }

        success = False
        submission_attempts = []
        result = {
            "id": tc_id, "caseKey": tc.get("caseKey"), "expected": tc_expected,
            "policyCode": policy_code, "policyVersion": policy_version, "bizType": biz_type,
            "runId": run_id, "checkpoint": identities[tc_id], "checkpointState": "prepared",
            "plannedCase": copy.deepcopy(tc), "submissionAttempts": submission_attempts,
            "executionOk": False, "assertionStatus": "inconclusive", "pass": False,
            "expectedEvidence": copy.deepcopy(tc.get("expectedEvidence", {})),
        }
        result["policyName"] = policy_name
        if name_resolution is not None:
            result["policyNameResolution"] = copy.deepcopy(name_resolution)
        results.append(result)
        submit_started = time.perf_counter()
        for retry in range(max_retry + 1):
            attempt = make_submission_attempt(host, body, retry + 1)
            submission_attempts.append(attempt)
            result["checkpointState"] = "submitting"
            _save_results(results, output_path)
            response_received = False
            try:
                status, resp_data = post_test_case(host, body, cookie, csrf)
                response_received = True
                attempt.update({
                    "completedAt": datetime.now(timezone.utc).isoformat(),
                    "httpStatus": status,
                    "response": copy.deepcopy(resp_data),
                })
                received_data = resp_data.get("data") if isinstance(resp_data, dict) else None
                received_data = received_data if isinstance(received_data, dict) else {}
                result.update(
                    token=received_data.get("token", ""), uuid=received_data.get("uuid", ""),
                    rs=str(received_data.get("runStatus", "")),
                    dt=received_data.get("policyDealTypeName", ""),
                    dtCode=received_data.get("policyDealType", ""),
                    executionOk=(status == 200 and isinstance(resp_data, dict)
                                 and resp_data.get("success") is True
                                 and str(received_data.get("runStatus", "")) == "2"),
                )

                if status == 401:
                    print(f"[{i+1}/{total}] {tc_id}: 会话过期 (401)", file=sys.stderr)
                    result.update({
                        "id": tc_id, "expected": tc_expected,
                        "batch": 1, "rs": "", "dt": "", "dtCode": "",
                        "uuid": "", "token": "", "err": "SESSION_EXPIRED",
                        "plannedCase": copy.deepcopy(tc),
                        "submissionAttempts": submission_attempts,
                        "policyVersion": policy_version,
                        "bizType": biz_type,
                        "executionOk": False,
                        "assertionStatus": "failed",
                        "evidenceStatus": "execution_failed",
                        "pass": False,
                        "checkpointState": "rejected",
                    })
                    _save_results(results, output_path)
                    print(f"会话过期，已保存 {len(results)} 条结果。请更新 cookie 后重试。",
                          file=sys.stderr)
                    sys.exit(2)

                result["checkpointState"] = "response_received"
                _save_results(results, output_path)
                retry_reason = retryable_submission_error(
                    status,
                    resp_data,
                )
                if retry_reason:
                    result.update(err=retry_reason, executionOk=False, assertionStatus="failed",
                                  evidenceStatus="execution_failed", checkpointState="rejected")
                    _save_results(results, output_path)
                    data = resp_data.get("data") or {}
                    if (retry < max_retry and status >= 500 and resp_data.get("success") is False
                            and not data.get("uuid") and not data.get("token")):
                        time.sleep(RETRY_DELAY)
                        continue
                    consecutive_failures += 1
                    break

                dd = resp_data.get("data", {})
                run_status = str(dd.get("runStatus", ""))
                is_success = resp_data.get("success", False)

                result.update({
                    "id": tc_id,
                    "expected": tc_expected,
                    "plannedCase": copy.deepcopy(tc),
                    "submissionAttempts": submission_attempts,
                    "batch": 1,
                    "rs": run_status,
                    "dt": dd.get("policyDealTypeName", ""),
                    "dtCode": dd.get("policyDealType", ""),
                    "uuid": dd.get("uuid", ""),
                    "token": dd.get("token", ""),
                    "err": dd.get("errorMsg", ""),
                    "policyVersion": policy_version,
                    "bizType": biz_type,
                    "executionOk": is_success and run_status == "2",
                    "assertionStatus": "inconclusive",
                    "evidenceStatus": "missing_evidence",
                    "pass": False,
                    "actual_decision": "",
                    "evidence": {},
                    "expectedEvidence": tc.get("expectedEvidence", {}),
                    "timingsMs": {
                        "submit": round(
                            (time.perf_counter() - submit_started) * 1000,
                            1,
                        ),
                    },
                })
                _save_results(results, output_path)

                tc_token = result["token"]
                deferred_evidence = False
                if evidence_workers > 1 and tc_token and run_status == "2":
                    pending_evidence.append((result, tc_expected))
                    deferred_evidence = True
                else:
                    _collect_and_evaluate_evidence(
                        result=result,
                        expected=tc_expected,
                        host=host,
                        cookie=cookie,
                        csrf=csrf,
                        comparison_rules=comparison_rules or [],
                        evidence_delay=evidence_delay,
                        rule_catalog=rule_catalog or [],
                        subpolicy_drill_depth=subpolicy_drill_depth,
                    )
                result["checkpointState"] = (
                    "complete" if result.get("assertionStatus") in {"passed", "failed"}
                    else "evidence_pending"
                )
                _save_results(results, output_path)

                status_str = (
                    "SUBMITTED"
                    if deferred_evidence
                    else result["assertionStatus"].upper()
                )
                print(f"[{i+1}/{total}] {tc_id}: {status_str} → {result['dt']}",
                      file=sys.stderr)
                success = True
                if result["executionOk"]:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                # 增量保存：每 CHECKPOINT_INTERVAL 条或遇失败时写入磁盘
                executed_count = len(results) - len(existing_results or [])
                if executed_count % CHECKPOINT_INTERVAL == 0 or not result["pass"]:
                    _save_results(results, output_path)

                # 周期进度统计
                if executed_count % 10 == 0 or i == total - 1:
                    _passed = sum(1 for r in results if r.get("pass"))
                    _failed = sum(
                        1 for r in results
                        if r.get("assertionStatus") == "failed"
                    )
                    _inconclusive = sum(
                        1 for r in results
                        if r.get("assertionStatus") == "inconclusive"
                    )
                    print(
                        f"progress: {i+1}/{total} passed={_passed} "
                        f"failed={_failed} inconclusive={_inconclusive}",
                          file=sys.stderr)
                break

            except Exception as e:
                if response_received:
                    # Submission already returned; local/evidence failures must not retry it.
                    raise
                attempt["error"] = str(e)
                attempt.setdefault("completedAt", datetime.now(timezone.utc).isoformat())
                result.update(err=str(e), checkpointState="submission_unknown",
                              executionOk=False, assertionStatus="inconclusive",
                              evidenceStatus="execution_failed")
                _save_results(results, output_path)
                consecutive_failures += 1
                break

        # 熔断：连续失败超过阈值则停止
        if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            print(f"\n熔断触发：连续 {consecutive_failures} 条失败，停止提交。"
                  f"已执行 {len(results)}/{total}", file=sys.stderr)
            break

        # 用例间延迟
        if i < total - 1:
            time.sleep(batch_delay)

    if pending_evidence:
        _collect_evidence_parallel(
            pending_evidence,
            host=host,
            cookie=cookie,
            csrf=csrf,
            comparison_rules=comparison_rules or [],
            evidence_delay=evidence_delay,
            workers=evidence_workers,
            rule_catalog=rule_catalog or [],
            subpolicy_drill_depth=subpolicy_drill_depth,
        )
        for record, _ in pending_evidence:
            record["checkpointState"] = (
                "complete" if record.get("assertionStatus") in {"passed", "failed"}
                else "evidence_pending"
            )

    _save_results(results, output_path)
    _save_timing_summary(
        results,
        output_path,
        total_ms=(time.perf_counter() - run_started) * 1000,
    )

    passed = sum(1 for r in results if r.get("pass"))
    failed = sum(
        1 for r in results
        if r.get("assertionStatus") == "failed"
    )
    inconclusive = sum(
        1 for r in results
        if r.get("assertionStatus") == "inconclusive"
    )
    print(
        f"\n执行完成: passed={passed} failed={failed} "
        f"inconclusive={inconclusive} total={total}",
        file=sys.stderr,
    )
    print(f"结果保存到: {output_path}", file=sys.stderr)

    return results


SUBPOLICY_RUN_DATA_NODE_TYPE = 8


def _child_tokens_via_run_data(host, token, cookie, csrf):
    """Fetch child strategy tokens through ``runData?nodeType=8``.

    Documented behaviour only: the response shape has not been captured from a
    real 集合循环子策略 run, so extraction is a permissive walk and an empty
    result means "evidence unavailable", not "no sub-policy executed".
    """
    try:
        status, resp = query_run_data(
            host, token, SUBPOLICY_RUN_DATA_NODE_TYPE, cookie, csrf
        )
    except Exception:
        return []
    if status != 200 or not isinstance(resp, dict) or resp.get("success") is not True:
        return []
    return _walk_child_tokens(resp.get("data"))


def drill_subpolicy_evidence(
    evidence,
    host,
    cookie,
    csrf,
    token,
    rule_catalog=None,
    max_depth=1,
    visited=None,
    fetch_delay=0.0,
):
    """Attach child-strategy evidence to SubPolicyNode entries, in place.

    Children are matched by ``policyCode`` where available and never by array
    position, because the documented contract warns that sub-policy order is
    not stable. ``visited`` breaks reference cycles (a sub-policy that calls
    back into an ancestor token) and ``max_depth`` bounds nesting cost.
    """
    if not isinstance(evidence, dict):
        return evidence
    nodes = evidence.get("subPolicies")
    if not isinstance(nodes, list) or not nodes:
        return evidence
    if max_depth < 1:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node["drillStatus"] = "budget-exhausted"
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    child["evidenceStatus"] = "not-drilled"
        return evidence
    visited = visited if visited is not None else set()
    if token:
        visited.add(str(token))
    for node in nodes:
        if not isinstance(node, dict):
            continue
        children = node.get("children")
        if not children:
            children = _child_tokens_via_run_data(host, token, cookie, csrf)
            node["children"] = children
            node["childrenSource"] = "runData-nodeType-8" if children else "unavailable"
        else:
            node.setdefault("childrenSource", "subPolicyNode")
        node["drillStatus"] = "drilled" if children else "no-children"
        for child in children:
            if not isinstance(child, dict):
                continue
            child_token = str(child.get("token") or "")
            if not child_token:
                child["evidenceStatus"] = "unavailable"
                continue
            if child_token in visited:
                child["evidenceStatus"] = "cycle-skipped"
                continue
            visited.add(child_token)
            try:
                if fetch_delay:
                    time.sleep(fetch_delay)
                status, resp = query_component_log(host, child_token, cookie, csrf)
            except Exception as exc:
                child["evidenceStatus"] = "fetch-failed"
                child["error"] = str(exc)
                continue
            child["httpStatus"] = status
            if status != 200 or not isinstance(resp, dict):
                child["evidenceStatus"] = "fetch-failed"
                continue
            child_evidence = parse_component_evidence(resp, rule_catalog=rule_catalog)
            child["evidenceStatus"] = "ok" if child_evidence else "unavailable"
            if child_evidence:
                drill_subpolicy_evidence(
                    child_evidence, host, cookie, csrf, child_token,
                    rule_catalog=rule_catalog, max_depth=max_depth - 1,
                    visited=visited, fetch_delay=fetch_delay,
                )
            child["evidence"] = child_evidence
    return evidence


def _collect_and_evaluate_evidence(
    result,
    expected,
    host,
    cookie,
    csrf,
    comparison_rules,
    evidence_delay=0.3,
    rule_catalog=None,
    subpolicy_drill_depth=1,
):
    """Collect component evidence and update one result in place."""
    evidence_started = time.perf_counter()
    if "rawComponentLog" in result:
        result.setdefault("componentLogHistory", []).append({
            key: copy.deepcopy(result.get(key)) for key in (
                "rawComponentLog", "componentLogHttpStatus", "componentLogFetchedAt", "componentLogToken"
            )
        })
    result["evidence"] = {}
    result["actual_decision"] = ""
    for key in ("evidenceError", "rawComponentLog", "componentLogHttpStatus", "componentLogFetchedAt", "componentLogToken"):
        result.pop(key, None)
    tc_token = result.get("token")
    query = {"token": tc_token, "startedAt": datetime.now(timezone.utc).isoformat()}
    result.setdefault("evidenceAttempts", []).append(query)
    if tc_token and str(result.get("rs", "")) == "2":
        try:
            if evidence_delay:
                time.sleep(evidence_delay)
            cl_status, cl_resp = query_component_log(
                host, tc_token, cookie, csrf
            )
            result["componentLogHttpStatus"] = cl_status
            result["componentLogToken"] = tc_token
            result["componentLogFetchedAt"] = datetime.now(timezone.utc).isoformat()
            result["rawComponentLog"] = copy.deepcopy(cl_resp)
            query.update(httpStatus=cl_status, completedAt=datetime.now(timezone.utc).isoformat())
            if cl_status == 200:
                evidence = parse_component_evidence(
                    cl_resp,
                    rule_catalog=rule_catalog,
                )
                if evidence.get("subPolicies"):
                    # Always invoked when sub-policy nodes exist: depth 0 means
                    # "detect but do not descend", and the drill itself stamps
                    # drillStatus="budget-exhausted" / evidenceStatus="not-drilled"
                    # so the absence of child evidence is reported explicitly
                    # rather than silently.
                    drill_subpolicy_evidence(
                        evidence,
                        host,
                        cookie,
                        csrf,
                        tc_token,
                        rule_catalog=rule_catalog,
                        max_depth=subpolicy_drill_depth,
                        fetch_delay=evidence_delay,
                    )
                result["evidence"] = evidence
                result["actual_decision"] = (
                    render_component_evidence(evidence)
                    or parse_component_log(
                        cl_resp,
                        expected=expected,
                        rule_catalog=rule_catalog,
                    )
                )
        except Exception as cl_err:
            query.update(error=str(cl_err), completedAt=datetime.now(timezone.utc).isoformat())
            result["evidenceError"] = str(cl_err)
            print(
                f"  componentLog 查询失败({tc_token[:12]}...): {cl_err}",
                file=sys.stderr,
            )
    result.setdefault("timingsMs", {})["evidence"] = round(
        (time.perf_counter() - evidence_started) * 1000,
        1,
    )
    result.update(
        evaluate_submission_result(
            expected,
            result,
            comparison_rules,
        )
    )
    return result


def _collect_evidence_parallel(
    pending,
    host,
    cookie,
    csrf,
    comparison_rules,
    evidence_delay,
    workers,
    rule_catalog=None,
    subpolicy_drill_depth=1,
):
    """Collect evidence for completed single submissions with bounded workers."""
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                _collect_and_evaluate_evidence,
                result,
                expected,
                host,
                cookie,
                csrf,
                comparison_rules,
                evidence_delay,
                rule_catalog,
                subpolicy_drill_depth,
            ): result
            for result, expected in pending
        }
        for future in as_completed(futures):
            result = futures[future]
            try:
                future.result()
            except Exception as exc:
                result["evidenceError"] = str(exc)
                result.update({
                    "assertionStatus": "inconclusive",
                    "evidenceStatus": "evidence_collection_failed",
                    "pass": False,
                })


def _save_timing_summary(results, output_path, total_ms):
    """Write phase metrics next to results without changing the result schema."""
    timings = {
        "totalMs": round(total_ms, 1),
        "caseCount": len(results),
        "submitMs": round(sum(
            result.get("timingsMs", {}).get("submit", 0)
            for result in results
        ), 1),
        "evidenceMs": round(sum(
            result.get("timingsMs", {}).get("evidence", 0)
            for result in results
        ), 1),
    }
    timing_path = Path(output_path).with_suffix(".timings.json")
    timing_path.write_text(
        json.dumps(timings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _update_timing_summary_file(output_path, **phase_ms):
    timing_path = Path(output_path).with_suffix(".timings.json")
    summary = {}
    if timing_path.exists():
        summary = json.loads(timing_path.read_text(encoding="utf-8"))
    summary.update({
        name: round(value, 1)
        for name, value in phase_ms.items()
    })
    timing_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_results(results, output_path):
    """Atomically persist a checkpoint without truncating the previous archive."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=target.name + ".", delete=False) as stream:
            name = stream.name
            json.dump(results, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def resume_identity_matches(results, policy_version, biz_type, identities=None):
    """Only reuse results produced for the same strategy identity."""
    return isinstance(results, list) and bool(identities) and len({
        result.get("id") for result in results if isinstance(result, dict)
    }) == len(results) and all(
        isinstance(result, dict)
        and str(result.get("policyVersion")) == str(policy_version)
        and str(result.get("bizType")) == str(biz_type)
        and result.get("checkpoint") == identities.get(result.get("id"))
        and result.get("id") in identities
        for result in results
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    workflow_started = time.perf_counter()
    parser = argparse.ArgumentParser(
        description="天策策略测试批量执行器 v2.0.0",
    )
    parser.add_argument("--host", required=True,
                        help="天策平台地址 (如 https://tiance.example.invalid)")
    parser.add_argument("--cookie", required=True,
                        help="登录 Cookie 字符串 (如 JSESSIONID=xxx; _csrf_=yyy)")
    parser.add_argument("--csrf", default=None,
                        help="CSRF token（如果不传则从 cookie 中提取 _csrf_ 值）")
    parser.add_argument("--org-code",
                        help="机构编码；未提供时从策略配置 S_S_ORGCODE 默认值读取")
    parser.add_argument(
        "--platform-snapshot",
        help="浏览器导出的平台策略元数据 JSON；提供时不调用元数据 API",
    )
    parser.add_argument("--strategy-config", required=True,
                        help="策略配置文件路径 (strategies/xxx.json)")
    parser.add_argument("--testcases", required=True,
                        help="测试用例 JSON 文件路径")
    parser.add_argument("--design-manifest", required=True,
                        help="经过语义复核的 governance 1.0 设计清单")
    parser.add_argument(
        "--strategy-model",
        help="parsed_strategy.json，用于提交前校验规则编号和名称",
    )
    parser.add_argument("--output", required=True,
                        help="输出结果 JSON 文件路径")
    parser.add_argument("--batch-delay", type=float, default=BATCH_DELAY,
                        help=f"用例间等待秒数 (默认: {BATCH_DELAY})")
    parser.add_argument("--max-retry", type=int, default=MAX_RETRY,
                        help=f"单条用例最大重试次数 (默认: {MAX_RETRY})")
    parser.add_argument("--resume", action="store_true",
                        help="断点续跑：加载已有结果文件，跳过已完成的用例")
    parser.add_argument("--run-id", help="本轮隔离身份；--resume 必须提供原始值")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="只执行指定用例 ID；可重复传入",
    )
    parser.add_argument(
        "--case-range",
        help="按源文件顺序执行闭区间，例如 TC_005:TC_008",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="单笔快速模式：取消固定等待，使用4个证据查询线程",
    )
    parser.add_argument(
        "--evidence-workers",
        type=int,
        default=1,
        help="已完成单笔请求的证据查询并发数（默认: 1）",
    )
    parser.add_argument(
        "--subpolicy-depth",
        type=int,
        default=None,
        help="子策略证据下钻层数（0=只识别子策略节点、不拉取子策略证据；默认: 1）。子策略结构来自接口文档、尚未在真实运行中采集，取不到时按“证据不可用”处理",
    )
    parser.add_argument(
        "--enabled-mock-scenario",
        action="append",
        default=[],
        help="已在隔离环境真实启用的 mock 场景；可重复传入",
    )
    parser.add_argument(
        "--mock-readiness",
        help="mock_probe.py 在十分钟内生成的就绪证明",
    )

    args = parser.parse_args()
    if args.resume and not args.run_id:
        parser.error("--resume requires the original --run-id")
    if args.resume and not Path(args.output).exists():
        parser.error("--resume output does not exist; refusing to submit a new run")
    run_id = args.run_id

    # 加载策略配置
    config_path = Path(args.strategy_config)
    if not config_path.exists():
        print(f"策略配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    policy_code = config["policyCode"]
    policy_name = config.get("policyName")
    policy_version = config.get("policyVersion", 1)
    biz_type = config.get("bizType", 1)

    # 加载测试用例
    tc_path = Path(args.testcases)
    if not tc_path.exists():
        print(f"测试用例文件不存在: {tc_path}", file=sys.stderr)
        sys.exit(1)
    tc_data = json.loads(tc_path.read_text(encoding="utf-8"))
    test_cases = tc_data.get("testCases", tc_data) if isinstance(tc_data, dict) else tc_data

    if not isinstance(test_cases, list):
        print("测试用例格式错误：需要 JSON 数组或 {testCases: [...]}", file=sys.stderr)
        sys.exit(1)

    preflight_started = time.perf_counter()
    try:
        test_cases = select_test_cases(
            test_cases,
            case_ids=args.case_id,
            case_range=args.case_range,
        )
    except ValueError as exc:
        print(f"用例选择失败: {exc}", file=sys.stderr)
        sys.exit(1)

    strategy_model = None
    strategy_model_path = args.strategy_model
    if not strategy_model_path:
        auto_model_path = tc_path.with_name("parsed_strategy.json")
        if auto_model_path.exists():
            strategy_model_path = str(auto_model_path)
    if strategy_model_path:
        try:
            strategy_model = json.loads(
                Path(strategy_model_path).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            print(f"策略解析结果读取失败: {exc}", file=sys.stderr)
            sys.exit(1)

    mock_readiness = None
    enabled_mock_scenarios = list(args.enabled_mock_scenario)
    if args.mock_readiness:
        try:
            mock_readiness = load_mock_readiness(args.mock_readiness)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"mock 就绪证明无效: {exc}", file=sys.stderr)
            sys.exit(1)
        enabled_mock_scenarios.extend(
            scenario
            for scenario, result in mock_readiness.get("scenarios", {}).items()
            if isinstance(result, dict) and result.get("ready")
        )

    try:
        test_cases, preflight_errors, preflight_summary = (
            prepare_cases_for_submission(
                test_cases,
                config,
                enabled_mock_scenarios=enabled_mock_scenarios,
                strategy_model=strategy_model,
                mock_readiness=mock_readiness,
            )
        )
    except Exception as exc:
        print(f"参数预检失败: {exc}", file=sys.stderr)
        sys.exit(1)

    if preflight_errors:
        print("参数预检未通过，已阻止提交：", file=sys.stderr)
        for error in preflight_errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from governance import validate_design
        manifest = json.loads(Path(args.design_manifest).read_text(encoding="utf-8"))
        # Full manifests cannot silently become partial runs via --case-id.
        validate_design(manifest, test_cases)
        if run_id and run_id != manifest["runId"]:
            raise ValueError("--run-id differs from reviewed manifest")
        run_id = manifest["runId"]
        for case in manifest["cases"]:
            if any(str(case[field]) != str(value) for field, value in (
                ("policyCode", policy_code), ("policyVersion", policy_version), ("bizType", biz_type)
            )):
                raise ValueError("Manifest policy identity differs from platform configuration")
    except (OSError, ValueError) as exc:
        print(f"治理设计门禁未通过，已阻止提交: {exc}", file=sys.stderr)
        sys.exit(1)
    preflight_ms = (time.perf_counter() - preflight_started) * 1000

    if preflight_summary["changedCases"]:
        filled = ", ".join(
            f"{field}={count}"
            for field, count in preflight_summary["filledFields"].items()
        )
        print(
            f"参数预检已补全 {preflight_summary['changedCases']} 条用例"
            f"（{filled}）",
            file=sys.stderr,
        )

    # CSRF 处理：如果未显式传入，尝试从 cookie 提取
    csrf = args.csrf
    if not csrf and args.cookie:
        import re
        m = re.search(r'_csrf_=([^;]+)', args.cookie)
        if m:
            csrf = m.group(1)

    common_params = config.get("params", {}).get("common", {})
    org_spec = (
        common_params.get("S_S_ORGCODE", {})
        if isinstance(common_params, dict)
        else {}
    )
    org_code = args.org_code
    if not org_code and isinstance(org_spec, dict):
        org_code = org_spec.get("fixed", org_spec.get("default"))

    platform_guard_started = time.perf_counter()
    try:
        guard_report = validate_platform_guard(
            config=config,
            host=args.host,
            cookie=args.cookie,
            csrf=csrf,
            org_code=org_code,
            snapshot_path=args.platform_snapshot,
        )
    except Exception as exc:
        print(f"平台配置门禁未通过，已阻止提交: {exc}", file=sys.stderr)
        sys.exit(1)
    platform_guard_ms = (
        time.perf_counter() - platform_guard_started
    ) * 1000
    platform = guard_report["platform"]
    policy_name = platform.get("policyName")
    if not isinstance(policy_name, str) or not policy_name.strip():
        print("平台缺少有效策略名称，已阻止提交", file=sys.stderr)
        sys.exit(1)
    if config.get("policyName") != policy_name:
        print(
            f"策略名称不同，采用平台名称提交: local={config.get('policyName')!r}, "
            f"platform={policy_name!r}（不自动改写配置或历史记录）",
            file=sys.stderr,
        )
    print(
        "平台配置门禁通过: "
        f"{platform['policyCode']} v{platform['policyVersion']} "
        f"bizType={platform['bizType']}",
        file=sys.stderr,
    )

    # 断点续跑：加载已有结果
    existing_results = None
    completed_ids = set()
    if args.resume and Path(args.output).exists():
        try:
            existing_results = json.loads(Path(args.output).read_text(encoding="utf-8"))
            if isinstance(existing_results, list):
                same_identity = resume_identity_matches(
                    existing_results,
                    policy_version,
                    biz_type,
                    identities={tc["id"]: checkpoint_identity(
                        tc, args.host, policy_code, policy_version, biz_type, run_id
                    ) for tc in test_cases},
                )
                if same_identity:
                    completed_ids = {
                        r["id"] for r in existing_results
                        if "id" in r
                    }
                    print(
                        f"[resume] 加载已有结果: {len(existing_results)} 条, "
                        f"跳过已完成: {len(completed_ids)} 条",
                        file=sys.stderr,
                    )
                else:
                    print("[resume] 执行身份不一致，拒绝覆盖或重新提交", file=sys.stderr)
                    sys.exit(1)
            else:
                print("[resume] 结果不是列表，拒绝重新提交", file=sys.stderr)
                sys.exit(1)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[resume] 结果损坏，拒绝重新提交: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"策略: {policy_name} ({policy_code}) v{policy_version}", file=sys.stderr)
    print(f"用例数: {len(test_cases)}", file=sys.stderr)
    print(f"平台: {args.host}", file=sys.stderr)
    print(f"CSRF: {'已配置' if csrf else '未配置'}", file=sys.stderr)
    print("", file=sys.stderr)

    batch_delay = 0 if args.fast else args.batch_delay
    evidence_delay = 0 if args.fast else 0.3
    evidence_workers = 4 if args.fast else args.evidence_workers
    if evidence_workers < 1 or evidence_workers > 8:
        print("--evidence-workers 必须在 1 到 8 之间", file=sys.stderr)
        sys.exit(1)

    test_execution = config.get("testExecution", {}) or {}
    if args.subpolicy_depth is not None:
        subpolicy_depth = args.subpolicy_depth
    else:
        subpolicy_depth = test_execution.get("subpolicyDrillDepth", 1)
    if not isinstance(subpolicy_depth, int) or isinstance(subpolicy_depth, bool) \
            or subpolicy_depth < 0 or subpolicy_depth > 3:
        print("--subpolicy-depth 必须是 0 到 3 之间的整数", file=sys.stderr)
        sys.exit(1)

    execute_tests(
        host=args.host,
        cookie=args.cookie,
        csrf=csrf,
        policy_code=policy_code,
        policy_name=policy_name,
        policy_version=policy_version,
        biz_type=biz_type,
        test_cases=test_cases,
        output_path=args.output,
        batch_delay=batch_delay,
        max_retry=args.max_retry,
        existing_results=existing_results,
        completed_ids=completed_ids,
        comparison_rules=config.get("comparisonRules", []),
        evidence_delay=evidence_delay,
        evidence_workers=evidence_workers,
        rule_catalog=test_execution.get("ruleCatalog", []),
        subpolicy_drill_depth=subpolicy_depth,
        run_id=run_id,
        platform_validation=guard_report,
    )
    _update_timing_summary_file(
        args.output,
        preflightMs=preflight_ms,
        platformGuardMs=platform_guard_ms,
        workflowTotalMs=(time.perf_counter() - workflow_started) * 1000,
    )


if __name__ == "__main__":
    # 抑制 InsecureRequestWarning（内网自签证书）
    if HAS_REQUESTS:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    main()
