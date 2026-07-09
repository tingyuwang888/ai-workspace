#!/usr/bin/env python3
"""
天策策略测试 — Python 批量执行器 v1.0.0

替代 submit_batch.js 的浏览器执行方式，直接通过 HTTP API 提交测试用例。
可被 orchestrator.py 自动调用，消除 Step 2b 暂停点。

API 端点：POST /noahApi/lab/policytest/create (form-urlencoded)
CSRF 处理：X-Cf-Random + _csrf_ 双 header

用法:
  python3 execute_tests.py \\
    --host http://10.57.80.231 \\
    --cookie "JSESSIONID=xxx; _csrf_=yyy" \\
    --strategy-config strategies/bhjcpostMainBefore.json \\
    --testcases testcases.json \\
    --output results.json

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
      "pass": true
    }
  ]

退出码:
  0 — 全部用例提交完成（不代表全部通过）
  1 — 参数错误 / 文件不存在
  2 — 会话过期 (401)
  3 — 网络不可达
"""

import argparse
import json
import sys
import time
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
MAX_RETRY = 2          # 单条用例最大重试次数
BATCH_DELAY = 0.8      # 用例间等待秒数
RETRY_DELAY = 2.0      # 重试间等待秒数
REQUEST_TIMEOUT = 60   # 单次请求超时秒数


# ---------------------------------------------------------------------------
# HTTP 请求封装
# ---------------------------------------------------------------------------

def _url_quote(val):
    """URL-encode a form value"""
    from urllib.parse import quote
    return quote(str(val), safe="")


def post_test_case(host, body, cookie, csrf):
    """
    提交单条测试用例到 /noahApi/lab/policytest/create
    返回 (status_code, response_dict)
    """
    url = f"{host.rstrip('/')}/noahApi/lab/policytest/create"
    form_data = "&".join(f"{k}={_url_quote(v)}" for k, v in body.items())

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


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def execute_tests(host, cookie, csrf, policy_code, policy_name,
                  policy_version, biz_type, test_cases, output_path,
                  batch_delay=BATCH_DELAY, max_retry=MAX_RETRY):
    """批量提交测试用例，返回结果列表"""
    results = []
    total = len(test_cases)

    for i, tc in enumerate(test_cases):
        tc_id = tc.get("id", f"TC_{i+1:03d}")
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
        for retry in range(max_retry + 1):
            try:
                status, resp_data = post_test_case(host, body, cookie, csrf)

                if status == 401:
                    print(f"[{i+1}/{total}] {tc_id}: 会话过期 (401)", file=sys.stderr)
                    results.append({
                        "id": tc_id, "expected": tc_expected,
                        "batch": 1, "rs": "", "dt": "", "dtCode": "",
                        "uuid": "", "token": "", "err": "SESSION_EXPIRED",
                        "pass": False
                    })
                    _save_results(results, output_path)
                    print(f"会话过期，已保存 {len(results)} 条结果。请更新 cookie 后重试。",
                          file=sys.stderr)
                    sys.exit(2)

                dd = resp_data.get("data", {})
                run_status = str(dd.get("runStatus", ""))
                is_success = resp_data.get("success", False)

                result = {
                    "id": tc_id,
                    "expected": tc_expected,
                    "batch": 1,
                    "rs": run_status,
                    "dt": dd.get("policyDealTypeName", ""),
                    "dtCode": dd.get("policyDealType", ""),
                    "uuid": dd.get("uuid", ""),
                    "token": dd.get("token", ""),
                    "err": dd.get("errorMsg", ""),
                    "pass": is_success and run_status == "2",
                }
                results.append(result)

                status_str = "OK" if result["pass"] else f"rs={run_status}"
                print(f"[{i+1}/{total}] {tc_id}: {status_str} → {result['dt']}",
                      file=sys.stderr)
                success = True
                break

            except Exception as e:
                if retry < max_retry:
                    print(f"[{i+1}/{total}] {tc_id}: 重试 {retry+1}/{max_retry} ({e})",
                          file=sys.stderr)
                    time.sleep(RETRY_DELAY)
                else:
                    err_msg = f"RETRY_EXHAUSTED: {e}"
                    print(f"[{i+1}/{total}] {tc_id}: {err_msg}", file=sys.stderr)
                    results.append({
                        "id": tc_id, "expected": tc_expected,
                        "batch": 1, "rs": "", "dt": "", "dtCode": "",
                        "uuid": "", "token": "", "err": err_msg,
                        "pass": False
                    })

        # 用例间延迟
        if i < total - 1:
            time.sleep(batch_delay)

    _save_results(results, output_path)

    passed = sum(1 for r in results if r["pass"])
    print(f"\n执行完成: {passed}/{total} 通过", file=sys.stderr)
    print(f"结果保存到: {output_path}", file=sys.stderr)

    return results


def _save_results(results, output_path):
    """保存结果 JSON"""
    Path(output_path).write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="天策策略测试批量执行器 v1.0.0 — 替代 submit_batch.js 的 Python 实现",
    )
    parser.add_argument("--host", required=True,
                        help="天策平台地址 (如 http://10.57.80.231)")
    parser.add_argument("--cookie", required=True,
                        help="登录 Cookie 字符串 (如 JSESSIONID=xxx; _csrf_=yyy)")
    parser.add_argument("--csrf", default=None,
                        help="CSRF token（如果不传则从 cookie 中提取 _csrf_ 值）")
    parser.add_argument("--strategy-config", required=True,
                        help="策略配置文件路径 (strategies/xxx.json)")
    parser.add_argument("--testcases", required=True,
                        help="测试用例 JSON 文件路径")
    parser.add_argument("--output", required=True,
                        help="输出结果 JSON 文件路径")
    parser.add_argument("--batch-delay", type=float, default=BATCH_DELAY,
                        help=f"用例间等待秒数 (默认: {BATCH_DELAY})")
    parser.add_argument("--max-retry", type=int, default=MAX_RETRY,
                        help=f"单条用例最大重试次数 (默认: {MAX_RETRY})")

    args = parser.parse_args()

    # 加载策略配置
    config_path = Path(args.strategy_config)
    if not config_path.exists():
        print(f"策略配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    policy_code = config["policyCode"]
    policy_name = config["policyName"]
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

    # CSRF 处理：如果未显式传入，尝试从 cookie 提取
    csrf = args.csrf
    if not csrf and args.cookie:
        import re
        m = re.search(r'_csrf_=([^;]+)', args.cookie)
        if m:
            csrf = m.group(1)

    print(f"策略: {policy_name} ({policy_code}) v{policy_version}", file=sys.stderr)
    print(f"用例数: {len(test_cases)}", file=sys.stderr)
    print(f"平台: {args.host}", file=sys.stderr)
    print(f"CSRF: {'已配置' if csrf else '未配置'}", file=sys.stderr)
    print("", file=sys.stderr)

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
        batch_delay=args.batch_delay,
        max_retry=args.max_retry,
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
