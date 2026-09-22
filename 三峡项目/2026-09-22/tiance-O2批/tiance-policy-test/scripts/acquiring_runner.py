#!/usr/bin/env python3
"""Acquiring-domain metric test-case runner (收单 HTTP 域执行器).

Executes HLB-style checkpoint contracts against direct acquiring risk-decision
endpoints (no Noah cookie/CSRF). Implements the metric-execute workflow:

  checkpoint design -> fresh isolated namespace -> structural preflight
  -> history submitted before current -> metric-window settle -> current
  -> five-state classification (classify-execution-result.js)
  -> metric evidence with root-cause diagnosis.

Isolation registry prevents cross-run contamination: every run allocates an
unused token and per-case row-number salts, persisted so later runs never
reuse a namespace that may still sit inside a long metric window.

Diagnosis rules (offline, evidence-preserving):
  - metric value null/absent for an expected indicator -> reasonCode
    ``metric_null_env`` (indicator backend suspected down; do not retry);
  - numeric-but-below-plan after settle -> reasonCode ``suspected_ingest_lag``
    (safe to rerun the case in a freshly allocated namespace);
  - same indicator family null across >=2 cases -> summary flag
    ``environment_regression`` (platform issue, not per-case failures).

No automatic retries are performed against the platform.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request

SCHEMA = pathlib.Path(__file__).resolve().parents[1] / "references" / "governance.schema.json"


def _load_statuses() -> tuple:
    """五态词表单一源：references/governance.schema.json 的 fiveState.enum（与 governance.py 同源）。"""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return tuple(schema["fiveState"]["enum"])


STATUSES = _load_statuses()
NULL_TOKENS = {None, "null", "NULL", ""}


# ---------------------------------------------------------------- namespace

def _now() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)


def load_registry(path: pathlib.Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"used_tokens": [], "used_salts": []}


def save_registry(path: pathlib.Path, registry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def dump_json(path, obj) -> None:
    pathlib.Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def allocate_namespace(prefix: str, registry: dict, today: datetime.date | None = None) -> str:
    """Return PREFIX_MMDD (then _2, _3 ... for the same day) and record it."""
    day = (today or _now().date()).strftime("%m%d")
    base = f"{prefix}_{day}"
    candidate, n = base, 2
    used = set(registry["used_tokens"])
    while candidate in used:
        candidate = f"{base}_{n}"
        n += 1
    registry["used_tokens"].append(candidate)
    return candidate


ROW_SALT_POOL = range(900, 1000)


def allocate_salt(registry: dict) -> str:
    used = set(registry["used_salts"])
    for value in ROW_SALT_POOL:
        tag = f"{value:03d}"
        if tag not in used:
            registry["used_salts"].append(tag)
            return tag
    raise RuntimeError("row-salt pool 900-999 exhausted; prune registry")


def case_digit_map(row: int, salt: str) -> dict:
    """Digit remap for cases whose IDs embed a zero-padded row number.

    Cases whose identity fields already carry the run token are isolated by
    the token remap itself; migrating the padded row number to an unused
    9xx salt covers the numeric-ID style as well.
    """
    return {f"{row:03d}": salt}


# ---------------------------------------------------------------- remapping

def strip_tokens(value: str, old_tokens: list[str], new_token: str) -> str:
    for old in old_tokens:
        value = value.replace(old, new_token)
    return value


def remap_str(value, old_tokens, new_token, digit_map):
    if not isinstance(value, str):
        return value
    value = strip_tokens(value, old_tokens, new_token)
    if digit_map:
        for old, new in digit_map.items():
            value = value.replace(old, new)
    return value


def remap_req(req: dict, old_tokens, new_token, digit_map) -> dict:
    out = {}
    for key, val in req.items():
        if isinstance(val, str):
            out[key] = remap_str(val, old_tokens, new_token, digit_map)
        elif isinstance(val, list):
            out[key] = [remap_str(x, old_tokens, new_token, digit_map) if isinstance(x, str) else x
                        for x in val]
        elif isinstance(val, dict):
            out[key] = {k: remap_str(v, old_tokens, new_token, digit_map) if isinstance(v, str) else v
                        for k, v in val.items()}
        else:
            out[key] = val
    return out


def rebase_time(req: dict, offset: datetime.timedelta) -> dict:
    r = dict(req)
    if "biztime" in r:
        dt = datetime.datetime.strptime(r["biztime"], "%Y-%m-%d %H:%M:%S") + offset
        r["biztime"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        r["transactiondate"] = dt.strftime("%Y-%m-%d")
        r["transactiontime"] = dt.strftime("%H:%M:%S")
    return r


# ---------------------------------------------------------------- identity

def make_case_key(row, rule_code, idx=0) -> str:
    """收单用例稳定身份，与 governance.aggregate_acquiring 共用同一公式。

    行号+规则码可用时取 acq-<row:03d>-<ruleCode>；身份不可用（runner_error
    兜底记录缺 row/rule）时退化为按枚举序的 acq-misc<idx:03d>，保证唯一。
    """
    if isinstance(row, int) and not isinstance(row, bool) and row >= 0 and rule_code:
        return f"acq-{row:03d}-{rule_code}"
    return f"acq-misc{idx:03d}"


# ---------------------------------------------------------------- preflight

def preflight(history_requests, current_request, expected_fields, old_tokens, new_token, digit_map):
    issues = []
    all_biz = [r["bizid"] for r in history_requests] + [current_request.get("bizid")]
    if len(set(all_biz)) != len(all_biz):
        issues.append("bizid 不唯一")
    mismatches = {}
    for field, want in (expected_fields or {}).items():
        got = current_request.get(field)
        if str(remap_str(str(want), old_tokens, new_token, digit_map)) != str(got):
            mismatches[field] = (want, got)
    if mismatches:
        issues.append(f"当前笔字段不符预期: {mismatches}")
    return {"bizid_unique": len(set(all_biz)) == len(all_biz),
            "current_field_match": not mismatches, "issues": issues, "mismatches": mismatches}


# ---------------------------------------------------------------- metrics

def walk_metrics(obj, bag):
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(key, str) and key.startswith("salaxyzb_"):
                bag.setdefault(key, val)
            walk_metrics(val, bag)
    elif isinstance(obj, list):
        for item in obj:
            walk_metrics(item, bag)


def find_metric(response: dict, name: str):
    bag = {}
    walk_metrics(response, bag)
    if name in bag:
        return bag[name]
    match = re.search(r'"' + re.escape(name) + r'"\s*:\s*"?([0-9.eE+-]+|null)"?',
                      json.dumps(response, ensure_ascii=False))
    if not match:
        return None
    raw = match.group(1)
    if raw == "null":
        return "null"
    try:
        return float(raw) if "." in raw or "e" in raw.lower() else int(raw)
    except ValueError:
        return raw


def is_null(value) -> bool:
    return value in NULL_TOKENS


def cmp_op(actual, op, threshold) -> bool:
    if is_null(actual):
        return False
    try:
        a = float(actual)
        v = float(threshold)
    except (TypeError, ValueError):
        return False
    return {">=": a >= v, ">": a > v, "<=": a <= v, "<": a < v,
            "==": a == v, "=": a == v}.get(op, False)


def metric_evidence(expected_metrics, response):
    evidence = []
    for metric in expected_metrics or []:
        actual = find_metric(response, metric["name"])
        evidence.append({"name": metric["name"], "operator": metric["operator"],
                         "value": metric["value"], "actual": actual,
                         "satisfied": cmp_op(actual, metric["operator"], metric["value"])})
    return evidence


def diagnose_metrics(evidence):
    """Return (reason_codes, details). metric_null_env beats ingest lag."""
    nulls = [e["name"] for e in evidence if is_null(e["actual"]) and not e["satisfied"]]
    below = [e["name"] for e in evidence
             if not is_null(e["actual"]) and not e["satisfied"]]
    codes = []
    if nulls:
        codes.append("metric_null_env")
    if below:
        codes.append("suspected_ingest_lag")
    return codes, {"null_metrics": nulls, "below_plan_metrics": below}


def metric_kind(name: str) -> str:
    lowered = name.lower()
    if "amt" in lowered or "sum" in lowered:
        return "amount"
    if "distinct" in lowered:
        return "distinct"
    if "cnt" in lowered or "count" in lowered:
        return "count"
    if "ratio" in lowered:
        return "ratio"
    return "other"


def environment_regression_cases(results):
    """Same aggregation-kind family null across >=2 cases -> platform issue."""
    kind_index: dict[str, list[int]] = {}
    for item in results:
        kinds = {metric_kind(name) for name in item.get("diagnosis", {}).get("null_metrics", [])}
        for kind in kinds:
            kind_index.setdefault(kind, []).append(item["row"])
    return {kind: rows for kind, rows in kind_index.items() if len(rows) >= 2}


# ---------------------------------------------------------------- transport

def post(endpoint: str, payload: dict, timeout: int = 30) -> dict:
    request = urllib.request.Request(
        endpoint, data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def classify(classifier_js: str, archive: dict) -> dict:
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(archive, fh, ensure_ascii=False)
        path = fh.name
    try:
        return json.loads(subprocess.check_output(
            ["node", classifier_js, path], timeout=60).decode())
    except Exception as exc:  # noqa: BLE001 - classifier is best-effort evidence
        return {"status": "执行阻塞", "target_rule_hit": None,
                "target_rule_set_executed": None, "executed_rule_sets": [],
                "evidence": [f"classifier_error: {exc}"]}
    finally:
        os.unlink(path)


def preflight_node(classifier_js: str, allow_missing: bool = False) -> None:
    """Fail fast when the node runtime required by the js classifier is absent.

    Without this probe a missing/broken node surfaces as per-case
    ``执行阻塞/classifier_error`` floods — an environment defect misrecorded as
    governance verdicts. ``allow_missing`` restores that legacy behavior.
    """
    problem = None
    if not shutil.which("node"):
        problem = "node runtime not found on PATH"
    else:
        try:
            subprocess.check_output(["node", "--version"], timeout=30)
        except Exception as exc:  # noqa: BLE001 - broken node is same class as missing
            problem = f"node runtime broken ({exc})"
    if problem is None:
        return
    if allow_missing:
        print(f"warn: {problem}; --allow-missing-node set, per-case results will be "
              f"执行阻塞/classifier_error", file=sys.stderr)
        return
    raise SystemExit(
        f"env-missing: {problem}; acquiring chain classifier ({classifier_js}) cannot run. "
        f"Install node, or pass --allow-missing-node to accept per-case 执行阻塞/classifier_error.")


# ---------------------------------------------------------------- orchestration

def run_checkpoint(ck_path: str, args, registry: dict, run_root: pathlib.Path) -> dict:
    with open(ck_path, encoding="utf-8") as fh:
        data = json.load(fh)
    manifest = data["planned_manifest"]
    row = int(data["row"])
    old_tokens = [t for t in {data.get("runId"), "SKR2_0820", "SKR4_0821_R53", "SKR3_0821_R53"} if t]
    case_dir = run_root / f"row{row:03d}"
    (case_dir / "responses").mkdir(parents=True, exist_ok=True)
    done_file = case_dir / "result.json"
    if done_file.exists() and not args.force:
        cached = json.loads(done_file.read_text(encoding="utf-8"))
        if cached.get("complete"):
            cached["skipped"] = True
            return cached

    new_token = allocate_namespace(args.namespace_prefix, registry)
    digit_map = case_digit_map(row, allocate_salt(registry)) if args.salt_rows else None

    history = data["actual_history_requests"]
    old_current_dt = datetime.datetime.strptime(
        data["actual_current_request"]["biztime"], "%Y-%m-%d %H:%M:%S")
    offset = _now() - old_current_dt  # uniform shift: current -> now, relative intervals preserved
    requests = [rebase_time(remap_req(item["request"], old_tokens, new_token, digit_map), offset)
                for item in history]
    current = rebase_time(remap_req(data["actual_current_request"], old_tokens, new_token, digit_map), offset)
    pairs = sorted(((item["endpoint"], req) for item, req in zip(history, requests)),
                   key=lambda pair: pair[1]["biztime"])
    check = preflight([r for _, r in pairs], current, manifest.get("预期当前笔字段"),
                      old_tokens, new_token, digit_map)
    dump_json(case_dir / "preflight.json",
              {"namespace": new_token, "digit_map": digit_map, "preflight": check})

    base = {"row": row, "rule_code": data["rule_code"], "case_type": data["case_type"],
            "target_rule_set": data["target_rule_set_code"], "namespace": new_token,
            "source_checkpoint": str(ck_path), "preflight": check}

    if check["issues"]:
        result = dict(base, complete=True, classification={"status": "无效用例", "evidence": check["issues"]},
                      metric_evidence=[], diagnosis={"reason_codes": ["preflight_failed"], "null_metrics": [],
                                                      "below_plan_metrics": []})
        dump_json(done_file, result)
        return result

    if args.dry_run:
        result = dict(base, complete=False, dry_run=True)
        dump_json(case_dir / "planned_requests.json",
                  {"requests": [r for _, r in pairs] + [current]})
        return result

    hist_ok = 0
    for idx, (endpoint, req) in enumerate(pairs, 1):
        try:
            resp = post(endpoint, req)
            hist_ok += resp.get("success") is True
            (case_dir / "responses" / f"hist_{idx:03d}.json").write_text(
                json.dumps(resp, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            (case_dir / "responses" / f"hist_{idx:03d}.error").write_text(str(exc), encoding="utf-8")
        time.sleep(args.spacing)
    time.sleep(args.settle)

    cur_endpoint = history[0]["endpoint"]
    try:
        current_resp = post(cur_endpoint, current)
    except Exception as exc:  # noqa: BLE001
        current_resp = {"success": False, "error": str(exc)}
    (case_dir / "responses" / "current.json").write_text(
        json.dumps(current_resp, ensure_ascii=False), encoding="utf-8")

    archive = {"rule_code": data["rule_code"], "target_rule_set_code": data["target_rule_set_code"],
               "case_type": data["case_type"], "current_response": current_resp,
               "http_status": 200 if current_resp.get("success") is True else 599}
    classification = classify(args.classifier, archive)
    evidence = metric_evidence(manifest.get("预期指标"), current_resp)
    codes, details = diagnose_metrics(evidence)
    if classification.get("status") == "失败" and codes:
        classification["diagnosisHint"] = codes

    result = dict(base, complete=True, history_sent=len(pairs), history_success=hist_ok,
                  current_success=current_resp.get("success"), current_biztime=current["biztime"],
                  classification=classification, metric_evidence=evidence,
                  diagnosis={"reason_codes": codes, **details},
                  finishedAt=datetime.datetime.now().isoformat())
    dump_json(done_file, result)
    return result


def expand_inputs(patterns: list[str]) -> list[str]:
    files = []
    for pattern in patterns:
        hits = sorted(glob.glob(pattern)) if any(ch in pattern for ch in "*?[") else [pattern]
        files.extend(h for h in hits if os.path.isfile(h))
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", action="append", required=True,
                        help="checkpoint JSON 文件或 glob，可重复")
    parser.add_argument("--output", required=True, help="本轮归档目录")
    parser.add_argument("--registry", default=None,
                        help="隔离命名空间登记表 (默认 <output>/../isolation_registry.json)")
    parser.add_argument("--classifier", default=str(pathlib.Path(__file__).with_name("classify-execution-result.js")))
    parser.add_argument("--namespace-prefix", default="QW")
    parser.add_argument("--settle", type=float, default=30,
                        help="历史全部受理后、当前笔提交前的窗口物化等待秒数")
    parser.add_argument("--spacing", type=float, default=0.3, help="历史笔间隔秒数")
    parser.add_argument("--salt-rows", dest="salt_rows", action="store_true", default=True,
                        help="对行号段做未占用 9xx salt 迁移 (默认开)")
    parser.add_argument("--no-salt-rows", dest="salt_rows", action="store_false")
    parser.add_argument("--dry-run", action="store_true", help="只做重映射+预检，不落平台")
    parser.add_argument("--force", action="store_true", help="忽略已完成 result.json 重跑")
    parser.add_argument("--allow-missing-node", dest="allow_missing_node", action="store_true",
                        help="node 缺失/损坏时不 abort，接受逐例 classifier_error 阻塞（旧行为）")
    args = parser.parse_args(argv)

    if not args.dry_run:
        preflight_node(args.classifier, args.allow_missing_node)

    files = expand_inputs(args.checkpoint)
    if not files:
        print("no checkpoint matched", file=sys.stderr)
        return 2
    run_root = pathlib.Path(args.output).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    registry_path = pathlib.Path(args.registry) if args.registry \
        else run_root.parent / "isolation_registry.json"
    registry = load_registry(registry_path)

    results = []
    for ck in files:
        try:
            results.append(run_checkpoint(ck, args, registry, run_root))
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the batch
            row = re.search(r"_(\d+)_", ck)
            results.append({"row": int(row.group(1)) if row else -1,
                            "source_checkpoint": ck, "complete": True,
                            "classification": {"status": "执行阻塞", "evidence": [f"runner_error: {exc}"]},
                            "diagnosis": {"reason_codes": ["runner_error"], "null_metrics": [],
                                          "below_plan_metrics": []}})
        save_registry(registry_path, registry)

    counts = {s: sum(1 for r in results if r.get("classification", {}).get("status") == s)
              for s in STATUSES}
    summary = {"schemaVersion": "1.0", "runId": f"acq-{run_root.name}",
               "namespace_tokens": registry["used_tokens"][-len(files):] if files else [],
               "planned": len(results), "counts": counts,
               "environment_regression": environment_regression_cases(results),
               "cases": [{"caseKey": make_case_key(r.get("row"), r.get("rule_code"), i),
                          "row": r.get("row"), "rule": r.get("rule_code"),
                          "case_type": r.get("case_type"), "status": r.get("classification", {}).get("status"),
                          "reason_codes": r.get("diagnosis", {}).get("reason_codes", []),
                          "namespace": r.get("namespace")} for i, r in enumerate(results)]}
    (run_root / "runner_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
