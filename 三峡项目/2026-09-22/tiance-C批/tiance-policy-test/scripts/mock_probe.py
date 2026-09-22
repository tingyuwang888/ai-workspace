#!/usr/bin/env python3
"""Probe declared mock scenarios and emit a fresh readiness proof."""

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests


def _lookup(payload, dotted_path):
    current = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def probe_scenario(host, scenario, config, headers=None, session=None):
    probe = config.get("probe", {}) if isinstance(config, dict) else {}
    if not isinstance(probe, dict) or not probe:
        return {
            "ready": False,
            "error": "场景未配置 probe",
        }
    url = probe.get("url") or urljoin(
        host.rstrip("/") + "/",
        str(probe.get("path", "")).lstrip("/"),
    )
    method = str(probe.get("method", "GET")).upper()
    expected_status = int(probe.get("expectedStatus", 200))
    timeout = float(probe.get("timeoutSeconds", 10))
    requester = session or requests.Session()
    try:
        response = requester.request(
            method,
            url,
            headers=headers or {},
            timeout=timeout,
            json=probe.get("json"),
        )
        ready = response.status_code == expected_status
        error = ""
        body_contains = probe.get("bodyContains")
        if ready and body_contains is not None:
            ready = str(body_contains) in response.text
            if not ready:
                error = f"响应不包含 {body_contains!r}"
        json_equals = probe.get("jsonEquals", {})
        if ready and isinstance(json_equals, dict) and json_equals:
            payload = response.json()
            mismatches = [
                f"{path}={_lookup(payload, path)!r}"
                for path, expected in json_equals.items()
                if _lookup(payload, path) != expected
            ]
            if mismatches:
                ready = False
                error = "JSON 不匹配: " + ", ".join(mismatches)
        if not ready and not error:
            error = (
                f"HTTP {response.status_code}, expected {expected_status}"
            )
        return {
            "ready": ready,
            "url": url,
            "status": response.status_code,
            "error": error,
        }
    except Exception as exc:
        return {
            "ready": False,
            "url": url,
            "error": str(exc),
        }


def run_probes(config, host, scenarios=None, cookie=None, csrf=None, session=None):
    execution = config.get("testExecution", {})
    declared = (
        execution.get("mockScenarios", {})
        if isinstance(execution, dict)
        else {}
    )
    requested = set(scenarios or declared)
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Cf-Random"] = csrf
        headers["_csrf_"] = csrf
    results = {}
    for scenario in sorted(requested):
        scenario_config = (
            declared.get(scenario)
            if isinstance(declared, dict)
            else None
        )
        if not isinstance(scenario_config, dict):
            results[scenario] = {
                "ready": False,
                "error": "场景未在策略配置中声明",
            }
            continue
        results[scenario] = probe_scenario(
            host,
            scenario,
            scenario_config,
            headers=headers,
            session=session,
        )
    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "policyCode": config.get("policyCode"),
        "scenarios": results,
    }


def main():
    parser = argparse.ArgumentParser(description="天策异常用例 mock 就绪探针")
    parser.add_argument("--config", required=True, help="策略配置 JSON")
    parser.add_argument("--host", required=True, help="mock 所在环境根地址")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--cookie")
    parser.add_argument("--csrf")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    proof = run_probes(
        config,
        args.host,
        scenarios=args.scenario,
        cookie=args.cookie,
        csrf=args.csrf,
    )
    Path(args.output).write_text(
        json.dumps(proof, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ready = all(
        result.get("ready")
        for result in proof["scenarios"].values()
    ) and bool(proof["scenarios"])
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    return 0 if ready else 2


if __name__ == "__main__":
    sys.exit(main())
