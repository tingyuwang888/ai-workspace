#!/usr/bin/env python3
"""Validate local strategy identity against current platform metadata."""

import argparse
from datetime import datetime, timezone
import json
import time
from pathlib import Path

import requests


def _as_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _walk_policy_candidates(payload):
    """Yield policy-like objects from common API response envelopes."""
    if isinstance(payload, list):
        for item in payload:
            yield from _walk_policy_candidates(item)
        return
    if not isinstance(payload, dict):
        return

    if payload.get("policyCode") or payload.get("code"):
        yield payload

    for key in (
        "data",
        "contents",
        "rows",
        "list",
        "records",
        "items",
        "policies",
        "payload",
    ):
        child = payload.get(key)
        if isinstance(child, (dict, list)):
            yield from _walk_policy_candidates(child)


def normalize_policy(candidate):
    """Normalize field variants returned by different Tiance releases."""
    publish_config = _as_dict(candidate.get("publishConfig"))
    ordinary_config = _as_dict(publish_config.get("ordinaryConfig"))

    version = (
        ordinary_config.get("version")
        if ordinary_config.get("version") is not None
        else candidate.get("policyVersion", candidate.get("version"))
    )
    return {
        "policyCode": candidate.get("policyCode") or candidate.get("code"),
        "policyName": candidate.get("policyName") or candidate.get("name"),
        "policyVersion": version,
        "bizType": (
            candidate.get("businessType")
            if candidate.get("businessType") is not None
            else candidate.get("bizType")
        ),
        "status": candidate.get("status"),
        "statusName": candidate.get("statusName"),
    }


def find_policy(payload, policy_code):
    for candidate in _walk_policy_candidates(payload):
        normalized = normalize_policy(candidate)
        if str(normalized.get("policyCode") or "") == str(policy_code):
            return normalized
    return None


def _same_scalar(left, right):
    return str(left).strip() == str(right).strip()


def _is_published(policy):
    status_name = str(policy.get("statusName") or "").strip()
    status = str(policy.get("status") or "").strip()
    if status_name:
        return "已发布" in status_name
    return status == "4"


def validate_snapshot_freshness(snapshot, max_age_seconds=600):
    """Reject browser snapshots without a recent capture timestamp."""
    if not isinstance(snapshot, dict):
        raise RuntimeError("平台快照根节点必须是对象")
    captured_at = snapshot.get("capturedAt", snapshot.get("_capturedAt"))
    if captured_at in (None, ""):
        raise RuntimeError(
            "平台快照缺少 capturedAt，无法证明元数据是本次执行前获取"
        )

    try:
        if isinstance(captured_at, (int, float)):
            timestamp = float(captured_at)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
        else:
            normalized = str(captured_at).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            timestamp = parsed.timestamp()
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError(f"平台快照 capturedAt 无效: {captured_at!r}") from exc

    age = time.time() - timestamp
    if age < -60:
        raise RuntimeError("平台快照 capturedAt 位于未来")
    if age > max_age_seconds:
        raise RuntimeError(
            f"平台快照已过期: age={int(age)}s, max={max_age_seconds}s"
        )
    return True


def validate_platform_config(local_config, snapshot):
    """Return a strict validation report for a platform snapshot."""
    policy_code = local_config.get("policyCode")
    platform = find_policy(snapshot, policy_code)
    if not platform:
        return {
            "ok": False,
            "errors": [f"平台快照中未找到策略 {policy_code}"],
            "platform": None,
        }

    errors = []
    platform_name = platform.get("policyName")
    if not isinstance(platform_name, str) or not platform_name.strip():
        errors.append("平台快照缺少有效 policyName，禁止回退到本地名称")
    if not _is_published(platform):
        errors.append(
            "策略不是已发布状态: "
            f"status={platform.get('status')!r}, "
            f"statusName={platform.get('statusName')!r}"
        )

    platform_version = platform.get("policyVersion")
    if platform_version in (None, ""):
        errors.append("平台快照缺少 policyVersion")
    elif not _same_scalar(local_config.get("policyVersion"), platform_version):
        errors.append(
            "策略版本不一致: "
            f"local={local_config.get('policyVersion')!r}, "
            f"platform={platform_version!r}"
        )

    platform_biz_type = platform.get("bizType")
    if platform_biz_type in (None, ""):
        errors.append("平台快照缺少 bizType/businessType")
    elif not _same_scalar(local_config.get("bizType"), platform_biz_type):
        errors.append(
            "业务类型不一致: "
            f"local={local_config.get('bizType')!r}, "
            f"platform={platform_biz_type!r}"
        )

    return {
        "ok": not errors,
        "errors": errors,
        "platform": platform,
        "policyNameResolution": {
            "local": local_config.get("policyName"),
            "platform": platform_name,
            "submitted": platform_name if not errors else None,
            "source": "platform",
            "changed": local_config.get("policyName") != platform_name,
        },
    }


def fetch_platform_snapshot(
    host,
    cookie,
    csrf,
    org_code,
    policy_code,
    biz_type,
    timeout=30,
):
    """Query known metadata endpoints and return the first matching payload."""
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Cf-Random"] = csrf
        headers["_csrf_"] = csrf

    base = host.rstrip("/")
    now_ms = int(time.time() * 1000)
    attempts = [
        (
            "GET",
            f"{base}/noahApi/policy/list",
            {
                "params": {
                    "orgCode": org_code,
                    "bizType": biz_type,
                    "startTime": 0,
                    "endTime": now_ms,
                }
            },
        ),
        (
            "POST",
            f"{base}/noahApi/policy/listByPage",
            {
                "json": {
                    "orgCode": org_code,
                    "bizType": biz_type,
                    "pageNo": 1,
                    "pageSize": 1000,
                }
            },
        ),
    ]

    diagnostics = []
    session = requests.Session()
    session.verify = False
    session.headers.update(headers)
    for method, url, kwargs in attempts:
        try:
            response = session.request(
                method,
                url,
                timeout=timeout,
                **kwargs,
            )
            payload = response.json()
            if response.status_code == 401:
                raise RuntimeError("平台会话已失效 (401)")
            if find_policy(payload, policy_code):
                return payload
            diagnostics.append(
                f"{method} {url}: HTTP {response.status_code}, 未找到策略"
            )
        except (requests.RequestException, ValueError) as exc:
            diagnostics.append(f"{method} {url}: {exc}")

    raise RuntimeError(
        "无法从平台元数据接口确认策略。"
        "可在已登录浏览器中导出 API 响应并使用 --platform-snapshot。"
        f" 尝试结果: {'; '.join(diagnostics)}"
    )


def load_snapshot(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def make_snapshot(payload, source="browser-network"):
    """Wrap a raw platform response in a fresh auditable snapshot."""
    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload": payload,
    }


def main():
    parser = argparse.ArgumentParser(description="天策策略平台配置强制校验")
    parser.add_argument("--config", required=True, help="本地策略配置 JSON")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--snapshot", help="带 capturedAt 的平台快照 JSON")
    source.add_argument("--raw-payload", help="浏览器网络面板导出的原始响应 JSON")
    source.add_argument("--host", help="直接请求平台元数据并生成快照")
    parser.add_argument("--cookie")
    parser.add_argument("--csrf")
    parser.add_argument("--org-code")
    parser.add_argument("--output", help="保存规范化平台快照")
    args = parser.parse_args()

    local_config = load_snapshot(args.config)
    if args.snapshot:
        snapshot = load_snapshot(args.snapshot)
    elif args.raw_payload:
        snapshot = make_snapshot(
            load_snapshot(args.raw_payload),
            source="browser-network",
        )
    else:
        if not args.org_code:
            parser.error("--host 模式必须提供 --org-code")
        payload = fetch_platform_snapshot(
            host=args.host,
            cookie=args.cookie,
            csrf=args.csrf,
            org_code=args.org_code,
            policy_code=local_config["policyCode"],
            biz_type=local_config.get("bizType"),
        )
        snapshot = make_snapshot(payload, source="platform-api")
    validate_snapshot_freshness(snapshot)
    report = validate_platform_config(local_config, snapshot)
    if args.output:
        Path(args.output).write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
