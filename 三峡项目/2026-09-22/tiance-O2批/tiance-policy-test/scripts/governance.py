"""Offline governance gates. No platform submission or automatic data repair."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs

from jsonschema import Draft202012Validator

from execute_tests import _save_results, parse_component_evidence
from result_evaluator import complete_hit_evidence, select_rule_nodes, validate_evidence_contract


SCHEMA = Path(__file__).resolve().parents[1] / "references" / "governance.schema.json"


def _load_statuses() -> tuple:
    """五态词表单一源：references/governance.schema.json 的 fiveState.enum。"""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return tuple(schema["fiveState"]["enum"])


STATUSES = _load_statuses()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def validate_design(manifest, testcases=None):
    canonical(manifest)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = [f"{list(error.path)}: {error.message}" for error in
              Draft202012Validator(schema).iter_errors(manifest)]
    if errors:
        raise ValueError("Invalid design manifest: " + "; ".join(errors))
    cases = manifest["cases"]
    for name in ("id", "caseKey"):
        if len({case[name] for case in cases}) != len(cases):
            raise ValueError(f"Duplicate {name}")
    by_key = {case["caseKey"]: case for case in cases}
    coverage_ids = set()
    for branch in manifest["coveragePlan"]:
        identity = tuple(branch[name] for name in ("policyCode", "targetRuleSet", "targetRule", "branchId"))
        if identity in coverage_ids:
            raise ValueError(f"Duplicate coverage branch: {identity}")
        coverage_ids.add(identity)
        for key in branch["caseKeys"]:
            case = by_key.get(key)
            if not case or case["assertionKind"] != "rule" or any(
                case.get(name) != branch[name] for name in ("policyCode", "targetRuleSet", "targetRule")
            ) or branch["branchId"] not in case["branchIds"]:
                raise ValueError(f"Coverage identity mismatch: {key}")
    for case in cases:
        target = case["expectedEvidence"].get("targetRuleSet")
        if target and target != case.get("targetRuleSet"):
            raise ValueError("Evidence contract target differs from design target")
        if case["assertionKind"] == "data" and any(
            not any(node.get(field) for field in ("fields", "fieldValues", "absentFields"))
            for node in case["expectedEvidence"]["thirdPartyNodes"]
        ):
            raise ValueError("Data assertions require explicit fields or values, not node presence alone")
        if case["assertionKind"] == "rule":
            for branch in case["branchIds"]:
                identity = tuple(case[name] for name in ("policyCode", "targetRuleSet", "targetRule")) + (branch,)
                if identity not in coverage_ids:
                    raise ValueError(f"Rule branch missing from frozen coverage plan: {identity}")
        rules = case["expectedEvidence"].get("rules", [])
        forbidden = case["expectedEvidence"].get("forbiddenRules", [])
        if set(rules) & set(forbidden):
            raise ValueError("Contradictory required and forbidden rules")
        if case["assertionKind"] == "rule":
            if case["targetRule"] in (forbidden if case["expectedHit"] else rules):
                raise ValueError("Target polarity contradicts evidence contract")
    if testcases is not None:
        items = testcases.get("testCases") if isinstance(testcases, dict) else testcases
        if not isinstance(items, list) or len(items) != len(cases):
            raise ValueError("Prepared cases must exactly match the reviewed manifest")
        seen = set()
        for item in items:
            key = item.get("caseKey")
            if key in seen or key not in by_key:
                raise ValueError(f"Unknown or duplicate prepared case: {key}")
            seen.add(key)
            case = by_key[key]
            if item.get("id") != case["id"] or canonical(item.get("params")) != canonical(case["expectedParams"]):
                raise ValueError(f"Prepared request differs from reviewed design: {key}")
            for name in ("targetRule", "targetRuleSet", "expectedHit", "assertionKind", "expectedEvidence"):
                if name in case and canonical(item.get(name)) != canonical(case[name]):
                    raise ValueError(f"Prepared {name} differs from reviewed design: {key}")
            if item.get("executable") is False:
                raise ValueError(f"Non-executable case cannot pass submission gate: {key}")
    return True


def classify_case(case, record, run_id):
    base = {name: case.get(name) for name in ("id", "caseKey", "assertionKind", "policyCode", "targetRuleSet", "targetRule")}
    base.update(runId=run_id, targetRuleHit=None, targetRuleSetExecuted=None)

    def verdict(status, reason, **evidence):
        return dict(base, status=status, reasonCode=reason, **evidence)

    if record is None:
        return verdict("执行阻塞", "not_submitted")
    if record.get("runId") != run_id or record.get("id") != case["id"]:
        return verdict("无效用例", "archive_identity_mismatch")
    attempts = record.get("submissionAttempts") or []
    if not attempts:
        return verdict("执行阻塞", "not_submitted")
    attempt = attempts[-1]
    response = attempt.get("response") or {}
    data = response.get("data") if isinstance(response, dict) else None
    if (attempt.get("httpStatus") != 200 or not isinstance(data, dict)
            or response.get("success") is not True or str(data.get("runStatus")) != "2"):
        return verdict("执行阻塞", "execution_not_confirmed")
    if (not isinstance(data.get("token"), str) or not data["token"]
            or not isinstance(data.get("uuid"), str) or not data["uuid"]):
        return verdict("执行阻塞", "missing_execution_receipt")
    request = attempt.get("request") or {}
    try:
        body = request["body"]
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != request.get("payloadSha256"):
            return verdict("无效用例", "request_hash_mismatch")
        form = parse_qs(body, keep_blank_values=True, strict_parsing=True)
        if any(len(values) != 1 for values in form.values()):
            return verdict("无效用例", "duplicate_request_field")
        for name in ("policyCode", "policyVersion", "bizType"):
            if form.get(name) != [str(case[name])]:
                return verdict("无效用例", "request_identity_mismatch")
        if canonical(json.loads(form["params"][0])) != canonical(case["expectedParams"]):
            return verdict("无效用例", "request_design_mismatch")
    except (KeyError, ValueError, TypeError, AttributeError):
        return verdict("无效用例", "unverifiable_request")
    if record.get("componentLogHttpStatus") != 200:
        return verdict("执行阻塞", "evidence_retrieval_failed")
    if (record.get("componentLogToken") != data["token"]
            or record.get("token") != data["token"] or record.get("uuid") != data["uuid"]):
        return verdict("执行阻塞", "unbound_component_evidence")
    evidence = parse_component_evidence(record.get("rawComponentLog"))
    if not evidence.get("pathComplete"):
        return verdict("执行阻塞", "incomplete_execution_path")
    # Governed paths contain codes; unverified display names cannot stand in for them.
    for node in evidence.get("rules", []):
        node["nodeName"] = ""
    kind = case["assertionKind"]
    if kind == "rule":
        nodes = select_rule_nodes(evidence, case["targetRuleSet"])
        if not nodes:
            if any(not node.get("nodeCode") for node in evidence.get("rules", [])):
                return verdict("执行阻塞", "unresolved_rule_set_identity")
            base["targetRuleSetExecuted"] = False
            return verdict("编排阻塞", "target_skipped")
        base["targetRuleSetExecuted"] = True
        if not complete_hit_evidence(nodes):
            return verdict("执行阻塞", "incomplete_target_hit_evidence")
        base["targetRuleHit"] = any(hit["ruleCode"] == case["targetRule"] for hit in nodes[0]["hitRules"])
    mismatches = []
    issues = validate_evidence_contract(case["expectedEvidence"], evidence,
                                        target=case.get("targetRuleSet"), mismatches=mismatches)
    missing = [issue for issue in issues if issue not in mismatches]
    if kind == "path":
        route_mismatches = [issue for issue in missing if issue.startswith("执行路径规则集:")]
        if route_mismatches and any(not node.get("nodeCode") for node in evidence.get("rules", [])):
            return verdict("执行阻塞", "unresolved_rule_set_identity")
        mismatches.extend(route_mismatches)
        missing = [issue for issue in missing if issue not in route_mismatches]
    if missing:
        return verdict("执行阻塞", "missing_required_evidence", missingEvidence=missing,
                       mismatchedEvidence=mismatches)
    if mismatches:
        return verdict("失败", "assertion_mismatch", mismatchedEvidence=mismatches)
    if kind == "rule" and base["targetRuleHit"] != case["expectedHit"]:
        return verdict("失败", "target_assertion_mismatch")
    if kind == "decision" and data.get("policyDealType") != case["expectedDecision"]:
        return verdict("失败", "decision_mismatch")
    return verdict("通过", "assertion_satisfied")


def classify(manifest, records):
    validate_design(manifest)
    if not isinstance(records, list):
        raise ValueError("Raw results must be a list")
    keys = {case["caseKey"] for case in manifest["cases"]}
    by_key = {}
    for record in records:
        key = record.get("caseKey") or (record.get("plannedCase") or {}).get("caseKey")
        if key not in keys or key in by_key:
            raise ValueError(f"Unknown/duplicate archive caseKey: {key}")
        by_key[key] = record
    results = [classify_case(case, by_key.get(case["caseKey"]), manifest["runId"])
               for case in manifest["cases"]]
    counts = {status: sum(case["status"] == status for case in results) for status in STATUSES}
    executed = {case["caseKey"] for case in results if case["status"] in {"通过", "失败"}}
    gaps = [copy.deepcopy(branch) for branch in manifest["coveragePlan"]
            if not executed.intersection(branch["caseKeys"])]
    total, passed, failed = len(results), counts["通过"], counts["失败"]
    return {"schemaVersion": "1.0", "runId": manifest["runId"], "cases": results,
            "counts": counts, "planned": total, "coverageGaps": gaps,
            "strictCompletionRate": passed / total if total else None,
            "validExecutionPassRate": passed / (passed + failed) if passed + failed else None,
            "fullSuccess": bool(total) and passed == total and not gaps}


# Acquiring-chain aggregate scoring: translation only, never re-judgement.
# The two execution chains stay mutually exclusive — acquiring archives are
# never fed to classify_case (Noah token/uuid envelope), and platform raw
# results never enter this path. This merges runner evidence into a single
# reasonCode and produces a governed-results-isomorphic report so the same
# validate-rerun front door consumes it.

_ACQ_SINGLE_REASONS = ("preflight_failed", "runner_error", "classifier_error")
_ACQ_STATUS_REASON = {"通过": "assertion_satisfied", "失败": "assertion_mismatch",
                      "编排阻塞": "target_skipped", "无效用例": "preflight_failed",
                      "执行阻塞": "execution_not_confirmed"}


def _merge_acq_reason(record):
    """One reasonCode per case: preflight > runner > classifier > diagnosis head > status default."""
    diagnosis = record.get("diagnosis") or {}
    codes = [code for code in diagnosis.get("reason_codes", []) if code]
    classification = record.get("classification") or {}
    evidence = canonical(classification.get("evidence") or [])
    for single in _ACQ_SINGLE_REASONS:
        if single in codes or single in evidence:
            return single
    if codes:
        return codes[0]
    return _ACQ_STATUS_REASON.get(classification.get("status"), "assertion_satisfied")


def aggregate_acquiring(results, run_id):
    if not isinstance(results, list) or not results:
        raise ValueError("Acquiring results must be a non-empty list")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Acquiring aggregate requires a non-empty runId")
    from acquiring_runner import environment_regression_cases, make_case_key  # lazy: a runner import defect must not break governance itself
    cases, seen = [], set()
    for idx, record in enumerate(results):
        if not isinstance(record, dict):
            raise ValueError(f"Acquiring record #{idx} is not an object")
        classification = record.get("classification") or {}
        status = classification.get("status")
        if status not in STATUSES:
            raise ValueError(f"Unknown acquiring status at row {record.get('row')}: {status}")
        key = make_case_key(record.get("row"), record.get("rule_code"), idx)
        if key in seen:
            raise ValueError(f"Duplicate acquiring caseKey: {key}")
        seen.add(key)
        cases.append({"id": key, "caseKey": key, "assertionKind": "acquiring",
                      "policyCode": record.get("policyCode"),
                      "targetRuleSet": record.get("target_rule_set"),
                      "targetRule": record.get("rule_code"), "runId": run_id,
                      "row": record.get("row"), "namespace": record.get("namespace"),
                      "status": status, "reasonCode": _merge_acq_reason(record),
                      "targetRuleHit": classification.get("target_rule_hit"),
                      "targetRuleSetExecuted": classification.get("target_rule_set_executed"),
                      "metricEvidence": record.get("metric_evidence", []),
                      "diagnosis": record.get("diagnosis") or {}})
    counts = {status: sum(case["status"] == status for case in cases) for status in STATUSES}
    total, passed, failed = len(cases), counts["通过"], counts["失败"]
    regression = environment_regression_cases(
        [dict(r, diagnosis=r.get("diagnosis") or {}) for r in results])
    # coverageGaps stays [] until O2b freezes checkpoint design contracts.
    return {"schemaVersion": "1.0", "runId": run_id, "cases": cases,
            "counts": counts, "planned": total, "coverageGaps": [],
            "strictCompletionRate": passed / total if total else None,
            "validExecutionPassRate": passed / (passed + failed) if passed + failed else None,
            "fullSuccess": bool(total) and passed == total,
            "environmentRegression": regression}


def validate_rerun(plan, report):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    rerun_schema = {"$ref": "#/$defs/rerun", "$defs": schema["$defs"]}
    errors = list(Draft202012Validator(rerun_schema).iter_errors(plan))
    if errors:
        raise ValueError("Invalid rerun plan: " + errors[0].message)
    if (not isinstance(report, dict) or report.get("schemaVersion") != "1.0"
            or not isinstance(report.get("cases"), list)):
        raise ValueError("Invalid governed report")
    rows = report["cases"]
    if any(not isinstance(row, dict) or not row.get("caseKey") or row.get("status") not in STATUSES for row in rows):
        raise ValueError("Invalid governed result identity or status")
    counts = {status: sum(row["status"] == status for row in rows) for status in STATUSES}
    if (len({row["caseKey"] for row in rows}) != len(rows) or report.get("planned") != len(rows)
            or canonical(counts) != canonical(report.get("counts"))):
        raise ValueError("Governed report counts or case identities are inconsistent")
    if plan.get("schemaVersion") != "1.0" or plan.get("previousRunId") != report.get("runId"):
        raise ValueError("Rerun source identity mismatch")
    if not plan.get("runId") or plan["runId"] == report["runId"]:
        raise ValueError("Rerun requires a fresh runId")
    cases = {case["caseKey"]: case for case in report["cases"]}
    seen = set()
    for action in plan.get("actions", []):
        key = action.get("caseKey")
        if key in seen or key not in cases or cases[key]["status"] == "通过":
            raise ValueError(f"Invalid rerun target: {key}")
        if (action.get("approved") is not True or not action.get("evidenceRefs")
                or action.get("reasonKind") not in {"data_fix", "platform_change", "prerequisite_change"}
                or not action.get("preservedIntent") or not action.get("newIsolationRefs")):
            raise ValueError(f"Rerun requires confirmed evidence, preserved intent and fresh isolation: {key}")
        seen.add(key)
    if not seen:
        raise ValueError("Empty rerun plan")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    design = sub.add_parser("validate-design")
    design.add_argument("--manifest", required=True)
    design.add_argument("--testcases")
    evaluate = sub.add_parser("classify")
    evaluate.add_argument("--manifest", required=True)
    evaluate.add_argument("--results", required=True)
    evaluate.add_argument("--output", required=True)
    rerun = sub.add_parser("validate-rerun")
    rerun.add_argument("--plan", required=True)
    rerun.add_argument("--report", required=True)
    aggregate = sub.add_parser("aggregate-acquiring")
    aggregate.add_argument("--run-root", required=True,
                           help="acquiring_runner 本轮归档目录 (读取 row*/result.json)")
    aggregate.add_argument("--output", required=True)
    aggregate.add_argument("--run-id", default=None,
                           help="默认 acq-<run-root 目录名>")
    args = parser.parse_args()
    read = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        if args.command == "validate-design":
            validate_design(read(args.manifest), read(args.testcases) if args.testcases else None)
        elif args.command == "aggregate-acquiring":
            if Path(args.output).exists():
                raise ValueError("Output exists; preserve it and choose a new output")
            root = Path(args.run_root)
            files = sorted(root.glob("row*/result.json"))
            if not files:
                raise ValueError(f"No acquiring result.json under {root} (expected row*/result.json)")
            report = aggregate_acquiring([read(path) for path in files],
                                         args.run_id or f"acq-{root.name}")
            _save_results(report, args.output)
            print(json.dumps({"counts": report["counts"], "fullSuccess": report["fullSuccess"],
                              "validExecutionPassRate": report["validExecutionPassRate"],
                              "environmentRegression": report["environmentRegression"]},
                             ensure_ascii=False))
        elif args.command == "classify":
            if Path(args.output).exists():
                raise ValueError("Output exists; preserve it and choose a new output")
            report = classify(read(args.manifest), read(args.results))
            _save_results(report, args.output)
            print(json.dumps({"counts": report["counts"], "fullSuccess": report["fullSuccess"]}, ensure_ascii=False))
        else:
            validate_rerun(read(args.plan), read(args.report))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Governance gate failed: {exc}\n")


if __name__ == "__main__":
    main()
