#!/usr/bin/env python3
"""
tiance-agent-loop / Step 1.5: 平台校验门禁 v1.0.0

查询天策平台 /noahApi/policy/list，比对 policyVersion / bizType / status，
确保本地策略配置与平台实际值一致。

v1.0.0: 初始版本，HTTP 直连 + publishConfig 解析 + 自动修正本地配置。

用法:
  python3 platform_check.py \\
    --host http://10.57.80.231 \\
    --cookie "JSESSIONID=xxx; _csrf_=yyy" \\
    --policy-code DF_PRE_CONC_001 \\
    --strategy-config strategies/DF_PRE_CONC_001.json

  # 指定 orgCode（多机构场景）
  python3 platform_check.py --host ... --cookie ... --policy-code ... --org-code TD001

  # 输出到文件
  python3 platform_check.py --host ... --cookie ... --policy-code ... -o platform_info.json

退出码:
  0 — 校验通过（或已自动修正配置）
  1 — 参数错误 / 文件不存在
  2 — 会话过期 (401)
  3 — 网络不可达 / 平台未找到该策略
  4 — 策略未发布（status != 4）
"""

import argparse
import json
import os
import re
import sys
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

REQUEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# HTTP 请求封装
# ---------------------------------------------------------------------------

def fetch_policy_list(host, cookie, csrf, org_code=None):
    """
    GET /noahApi/policy/list — 获取全量策略列表。
    返回 (status_code, response_dict)。
    """
    url = f"{host.rstrip('/')}/noahApi/policy/list"
    if org_code:
        url += f"?orgCode={org_code}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-Cf-Random"] = csrf
        headers["_csrf_"] = csrf

    if HAS_REQUESTS:
        resp = requests.get(url, headers=headers,
                            timeout=REQUEST_TIMEOUT, verify=False)
        return resp.status_code, resp.json()
    else:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx)
            body_text = resp.read().decode("utf-8")
            return resp.status, json.loads(body_text)
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            try:
                return e.code, json.loads(body_text)
            except json.JSONDecodeError:
                return e.code, {"code": e.code, "data": [], "errorMsg": body_text[:200]}


# ---------------------------------------------------------------------------
# publishConfig 解析
# ---------------------------------------------------------------------------

def parse_publish_config(raw):
    """
    publishConfig 可能是 JSON 字符串或 dict。
    返回解析后的 dict，失败返回 None。
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def extract_platform_version(publish_config):
    """从 publishConfig 中提取版本号: ordinaryConfig.version"""
    if not publish_config:
        return None
    ordinary = publish_config.get("ordinaryConfig", {})
    if isinstance(ordinary, dict):
        v = ordinary.get("version")
        if v is not None:
            return int(v) if isinstance(v, (int, float)) else v
    return None


# ---------------------------------------------------------------------------
# 策略匹配
# ---------------------------------------------------------------------------

def find_policy_in_list(policy_list, policy_code):
    """
    在策略列表中查找目标策略。
    兼容多种字段名：code / policyCode。
    """
    for item in policy_list:
        if item.get("code") == policy_code or item.get("policyCode") == policy_code:
            return item
    return None


def extract_data_list(resp_data):
    """
    从响应体中提取策略列表。
    兼容多种响应结构：data.contents / data.list / data（直接数组）。
    """
    data = resp_data.get("data", resp_data)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("contents", "list", "records", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # 再剥一层
        inner = data.get("data", {})
        if isinstance(inner, list):
            return inner
        if isinstance(inner, dict):
            for key in ("contents", "list", "records", "items"):
                if key in inner and isinstance(inner[key], list):
                    return inner[key]
    return []


# ---------------------------------------------------------------------------
# 本地配置自动修正
# ---------------------------------------------------------------------------

def update_local_config(config_path, platform_version=None, platform_biz_type=None):
    """
    将平台实际值写回本地策略配置文件。
    返回 (updated: bool, changes: list[str])。
    """
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"警告: 无法读取本地配置: {e}", file=sys.stderr)
        return False, []

    changes = []

    if platform_version is not None:
        old = config.get("policyVersion", config.get("version"))
        if old != platform_version:
            config["policyVersion"] = platform_version
            changes.append(f"policyVersion: {old} → {platform_version}")

    if platform_biz_type is not None:
        old = config.get("bizType")
        if old != platform_biz_type:
            config["bizType"] = platform_biz_type
            changes.append(f"bizType: {old} → {platform_biz_type}")

    if changes:
        Path(config_path).write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"本地配置已更新: {config_path}", file=sys.stderr)
        for c in changes:
            print(f"  {c}", file=sys.stderr)
        return True, changes

    return False, []


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def platform_check(host, cookie, csrf, policy_code, org_code=None,
                   strategy_config=None):
    """
    执行平台校验，返回结果 dict:
    {
      "ok": bool,
      "policyCode": str,
      "platformVersion": int|None,
      "platformBizType": int|None,
      "platformBizTypeName": str|None,
      "status": int|None,
      "statusName": str|None,
      "mismatches": [str],
      "configUpdated": bool,
      "configChanges": [str],
      "warnings": [str],
    }
    """
    result = {
        "ok": False,
        "policyCode": policy_code,
        "platformVersion": None,
        "platformBizType": None,
        "platformBizTypeName": None,
        "status": None,
        "statusName": None,
        "mismatches": [],
        "configUpdated": False,
        "configChanges": [],
        "warnings": [],
    }

    # 1. 查询平台
    print(f"查询平台策略列表: {host}/noahApi/policy/list", file=sys.stderr)
    try:
        status_code, resp_data = fetch_policy_list(host, cookie, csrf, org_code)
    except Exception as e:
        result["warnings"].append(f"平台请求失败: {e}")
        print(f"错误: 平台请求失败: {e}", file=sys.stderr)
        return result

    if status_code == 401:
        result["warnings"].append("会话过期 (401)")
        print("错误: 会话过期 (401)，请更新 cookie", file=sys.stderr)
        return result

    if status_code != 200:
        result["warnings"].append(f"平台返回异常状态码: {status_code}")
        print(f"错误: 平台返回 {status_code}", file=sys.stderr)
        return result

    # 2. 提取策略列表并查找目标策略
    policy_list = extract_data_list(resp_data)
    if not policy_list:
        result["warnings"].append("策略列表为空")
        print("错误: 策略列表为空", file=sys.stderr)
        return result

    print(f"策略列表共 {len(policy_list)} 条", file=sys.stderr)
    policy = find_policy_in_list(policy_list, policy_code)
    if not policy:
        result["warnings"].append(f"平台未找到策略: {policy_code}")
        print(f"错误: 平台未找到策略 {policy_code}", file=sys.stderr)
        return result

    # 3. 提取平台实际值
    pc = parse_publish_config(policy.get("publishConfig"))
    platform_version = extract_platform_version(pc)

    # businessType 兼容多种字段名
    platform_biz_type = (policy.get("businessType")
                         or policy.get("bizType")
                         or policy.get("businessCategory"))
    if platform_biz_type is not None:
        try:
            platform_biz_type = int(platform_biz_type)
        except (ValueError, TypeError):
            pass

    platform_biz_name = (policy.get("businessTypeName")
                         or policy.get("bizTypeName")
                         or policy.get("businessCategoryName"))
    status = policy.get("status")
    status_name = policy.get("statusName")

    result["platformVersion"] = platform_version
    result["platformBizType"] = platform_biz_type
    result["platformBizTypeName"] = platform_biz_name
    result["status"] = status
    result["statusName"] = status_name

    print(f"平台值: policyVersion={platform_version}, "
          f"bizType={platform_biz_type}({platform_biz_name}), "
          f"status={status}({status_name})", file=sys.stderr)

    # 4. 比对
    mismatches = []
    if strategy_config and Path(strategy_config).exists():
        try:
            local = json.loads(Path(strategy_config).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            local = {}

        local_version = local.get("policyVersion", local.get("version"))
        local_biz_type = local.get("bizType")

        if platform_version is not None and local_version != platform_version:
            mismatches.append(
                f"policyVersion: 本地={local_version} vs 平台={platform_version}")

        if (platform_biz_type is not None and local_biz_type is not None
                and int(local_biz_type) != int(platform_biz_type)):
            mismatches.append(
                f"bizType: 本地={local_biz_type} vs 平台={platform_biz_type}")

    result["mismatches"] = mismatches

    # 5. 检查发布状态
    if status is not None:
        try:
            status_int = int(status)
        except (ValueError, TypeError):
            status_int = -1
        if status_int != 4:
            result["warnings"].append(
                f"策略未发布: status={status}({status_name})，"
                f"仅 status=4(已发布) 可执行测试")
            print(f"警告: 策略未发布 status={status}({status_name})", file=sys.stderr)
            # 不直接返回，让调用方决定

    # 6. 自动修正本地配置
    if mismatches and strategy_config and Path(strategy_config).exists():
        updated, changes = update_local_config(
            strategy_config, platform_version, platform_biz_type)
        result["configUpdated"] = updated
        result["configChanges"] = changes
        if updated:
            for c in changes:
                result["warnings"].append(f"已自动修正: {c}")

    # 7. 判定通过
    # 通过条件：找到策略 + 无致命错误
    # 未发布状态仅警告不阻断（某些测试环境策略可能 status!=4）
    if not any("会话过期" in w for w in result["warnings"]):
        result["ok"] = True

    if mismatches:
        print(f"比对结果: {len(mismatches)} 项不一致", file=sys.stderr)
        for m in mismatches:
            print(f"  ⚠ {m}", file=sys.stderr)
    else:
        print("比对结果: 一致 ✓", file=sys.stderr)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="天策平台校验门禁 v1.0.0 — Step 1.5 平台值比对",
    )
    parser.add_argument("--host", required=True,
                        help="天策平台地址 (如 http://10.57.80.231)")
    parser.add_argument("--cookie", required=True,
                        help="登录 Cookie 字符串 (如 JSESSIONID=xxx; _csrf_=yyy)")
    parser.add_argument("--csrf", default=None,
                        help="CSRF token（如果不传则从 cookie 中提取 _csrf_ 值）")
    parser.add_argument("--policy-code", required=True,
                        help="策略编码 (如 DF_PRE_CONC_001)")
    parser.add_argument("--org-code", default=None,
                        help="机构编码（多机构场景，可选）")
    parser.add_argument("--strategy-config", default=None,
                        help="本地策略配置文件路径，用于比对和自动修正")
    parser.add_argument("--output", "-o", default=None,
                        help="输出结果 JSON 路径（不指定则输出到 stdout）")

    args = parser.parse_args()

    # CSRF 处理：如果未显式传入，尝试从 cookie 提取
    csrf = args.csrf
    if not csrf and args.cookie:
        m = re.search(r'_csrf_=([^;]+)', args.cookie)
        if m:
            csrf = m.group(1)

    print(f"平台校验: {args.policy_code} @ {args.host}", file=sys.stderr)
    print(f"CSRF: {'已配置' if csrf else '未配置'}", file=sys.stderr)

    result = platform_check(
        host=args.host,
        cookie=args.cookie,
        csrf=csrf,
        policy_code=args.policy_code,
        org_code=args.org_code,
        strategy_config=args.strategy_config,
    )

    # 输出
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"结果已保存: {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # 摘要
    if result["ok"]:
        print(f"✓ 平台校验通过: {args.policy_code}", file=sys.stderr)
        if result["mismatches"]:
            print(f"  ⚠ {len(result['mismatches'])} 项不一致"
                  + ("（已自动修正）" if result["configUpdated"] else "（需手动修正）"),
                  file=sys.stderr)
    else:
        print(f"✗ 平台校验失败: {args.policy_code}", file=sys.stderr)
        for w in result["warnings"]:
            print(f"  ⚠ {w}", file=sys.stderr)

    # 退出码
    if not result["ok"]:
        if any("会话过期" in w for w in result["warnings"]):
            sys.exit(2)
        sys.exit(3)
    if any("未发布" in w for w in result["warnings"]):
        sys.exit(4)
    sys.exit(0)


if __name__ == "__main__":
    # 抑制 InsecureRequestWarning（内网自签证书）
    if HAS_REQUESTS:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    main()
