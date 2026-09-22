#!/usr/bin/env python3
"""
天策策略配置自动发现工具

从天策平台API自动发现策略的元数据、参数、决策类型等信息，
生成策略配置文件（JSON），供 tiance-policy-test skill 使用。

用法:
  python3 discover_strategy.py list-policies --host https://tiance.example.invalid --csrf TOKEN
  python3 discover_strategy.py discover --policy-code bhjcpostMainBefore --host https://tiance.example.invalid --csrf TOKEN
  python3 discover_strategy.py get-params --policy-code DF_PRE_CONC_001 --host https://tiance.example.invalid --csrf TOKEN
  python3 discover_strategy.py get-decision-types --host https://tiance.example.invalid --csrf TOKEN
  python3 discover_strategy.py generate-comparison --policy-code MyPolicy --input-json discover_output.json
  python3 discover_strategy.py generate-comparison --policy-code MyPolicy --from-dtypes --host https://tiance.example.invalid --csrf TOKEN

模块结构:
  http_client.py       — HTTP 抽象层（requests / urllib 回退）
  config_generator.py  — API 调用 + 比对规则生成
  discover_strategy.py — 本文件，CLI 入口 + 子命令处理
"""

import argparse
import json
import sys
import os
import traceback
from pathlib import Path
from datetime import datetime

# 从拆分后的模块导入
from http_client import build_session, HAS_REQUESTS
from config_generator import (
    fetch_policy_list,
    fetch_policy_detail,
    fetch_test_input_params,
    fetch_decision_types,
    discover_sub_strategies,
    extract_decision_results_from_raw,
    generate_strategy_config,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _resolve_env(value):
    """解析 $ENV:VAR_NAME 占位符（与 config.json 密码同约定），未设置时明确提示。"""
    if isinstance(value, str) and value.startswith("$ENV:"):
        env_key = value[5:]
        env_val = os.environ.get(env_key)
        if env_val is None:
            print(
                f"config.json 中配置为 '{value}'，但环境变量 {env_key} 未设置。\n"
                f"请设置: export {env_key}=<对应值>",
                file=sys.stderr,
            )
        return env_val
    return value


def _base_url(args):
    """构造基础 URL。优先级：--host > TIANCE_PLATFORM_HOST > config.json（含 $ENV: 解析）。"""
    host = getattr(args, "host", None)
    cfg = _load_config()
    if not host:
        host = os.environ.get("TIANCE_PLATFORM_HOST")
    if not host:
        host = _resolve_env(cfg.get("platform", {}).get("host", "")) if cfg else ""
    host = host or "http://localhost"
    port = getattr(args, "port", None)
    # 去掉尾部斜杠
    host = host.rstrip("/")
    if port and port not in (80, 443) and f":{port}" not in host:
        return f"{host}:{port}"
    return host


def _load_config():
    """
    加载顶层 config.json（位于 skill 根目录）。
    返回 dict 或 None（文件不存在或解析失败时）。
    """
    config_path = Path(__file__).resolve().parent.parent / "config.json"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _safe_json(resp):
    """安全解析 JSON 响应，出错时返回 None"""
    if resp is None:
        return None
    try:
        if hasattr(resp, "json"):
            return resp.json()
        return json.loads(resp.text if hasattr(resp, "text") else str(resp))
    except Exception:
        return None


def _log(msg, level="INFO"):
    """输出日志到 stderr，不干扰 stdout 的 JSON 输出"""
    print(f"[{level}] {msg}", file=sys.stderr)


def _output(data, output_path=None):
    """
    输出 JSON 数据。
    - 如果指定了 output_path，写入文件
    - 否则输出到 stdout（格式化 JSON）
    """
    formatted = json.dumps(data, ensure_ascii=False, indent=2)
    if output_path:
        # 确保目录存在
        dirpath = os.path.dirname(output_path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted)
            f.write("\n")
        _log(f"已写入: {output_path}")
    else:
        print(formatted)


# ---------------------------------------------------------------------------
# 子命令实现
# ---------------------------------------------------------------------------

def cmd_list_policies(args):
    """
    子命令: list-policies
    列出天策平台上所有可用的策略
    """
    session = build_session(args)
    base_url = _base_url(args)

    policies = fetch_policy_list(
        session,
        base_url,
        org_code=getattr(args, "org_code", None),
        biz_type=getattr(args, "biz_type", None),
    )
    if policies is None:
        _log("获取策略列表失败", "ERROR")
        sys.exit(1)

    # 格式化输出
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "host": base_url,
        "total": len(policies),
        "policies": [],
    }
    for p in policies:
        if not isinstance(p, dict):
            continue
        entry = {
            "policyCode": p.get("policyCode") or p.get("code") or "",
            "policyName": p.get("policyName") or p.get("name") or "",
            "bizType": (
                p.get("businessType")
                if p.get("businessType") is not None
                else p.get("bizType", "")
            ),
            "status": p.get("status", p.get("policyStatus", "")),
        }
        # 提取版本号
        pub_config = p.get("publishConfig", {})
        if isinstance(pub_config, dict):
            ord_config = pub_config.get("ordinaryConfig", {})
            if isinstance(ord_config, dict):
                entry["version"] = ord_config.get("version", "")
            elif isinstance(pub_config.get("version"), str):
                entry["version"] = pub_config["version"]
        output_data["policies"].append(entry)

    _output(output_data, getattr(args, "output", None))


def cmd_get_params(args):
    """
    子命令: get-params
    获取指定策略的输入参数
    """
    session = build_session(args)
    base_url = _base_url(args)
    policy_code = args.policy_code

    params = fetch_test_input_params(session, base_url, policy_code)

    output_data = {
        "timestamp": datetime.now().isoformat(),
        "host": base_url,
        "policyCode": policy_code,
        "params": params if params else [],
        "paramCount": len(params) if params else 0,
    }

    if not params:
        _log(f"未能发现 policyCode='{policy_code}' 的输入参数", "WARN")

    _output(output_data, getattr(args, "output", None))


def cmd_get_decision_types(args):
    """
    子命令: get-decision-types
    获取平台可用的决策结果类型（dealType）
    """
    session = build_session(args)
    base_url = _base_url(args)

    types = fetch_decision_types(session, base_url)

    output_data = {
        "timestamp": datetime.now().isoformat(),
        "host": base_url,
        "decisionTypes": types if types else [],
        "count": len(types) if types else 0,
    }

    if not types:
        _log("未能获取决策结果类型列表", "WARN")

    _output(output_data, getattr(args, "output", None))


def cmd_discover(args):
    """
    子命令: discover
    完整发现指定策略的配置信息，包括：
    - 策略基本信息（policyCode, policyName, version, bizType）
    - 输入参数列表
    - 决策结果类型
    - 子策略/决策流节点
    输出一份完整的策略配置 JSON
    """
    session = build_session(args)
    base_url = _base_url(args)
    policy_code = args.policy_code

    _log(f"开始发现策略配置: {policy_code}")
    _log(f"目标平台: {base_url}")

    result = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "host": base_url,
            "discoveredBy": "discover_strategy.py",
        },
        "policy": {
            "policyCode": policy_code,
            "policyName": "",
            "version": "",
            "bizType": "",
            "status": "",
        },
        "inputParams": [],
        "decisionTypes": [],
        "subStrategies": [],
        "raw": {},
        "discoveryNotes": [],
    }

    # ---- 步骤 1: 获取策略基本信息 ----
    _log("步骤 1/4: 获取策略基本信息...")
    policy_detail = fetch_policy_detail(
        session,
        base_url,
        policy_code,
        org_code=getattr(args, "org_code", None),
        biz_type=getattr(args, "biz_type", None),
    )
    if policy_detail:
        result["policy"]["policyName"] = (
            policy_detail.get("policyName")
            or policy_detail.get("name")
            or ""
        )
        result["policy"]["bizType"] = (
            policy_detail.get("businessType")
            if policy_detail.get("businessType") is not None
            else policy_detail.get("bizType", "")
        )
        result["policy"]["status"] = policy_detail.get("status", policy_detail.get("policyStatus", ""))
        # 提取版本
        pub_config = policy_detail.get("publishConfig", {})
        if isinstance(pub_config, dict):
            ord_config = pub_config.get("ordinaryConfig", {})
            if isinstance(ord_config, dict):
                result["policy"]["version"] = ord_config.get("version", "")
        # 保存原始数据（去掉过大的字段）
        safe_detail = {k: v for k, v in policy_detail.items()
                       if k not in ("publishConfig",) or isinstance(v, (str, int, float, bool))}
        result["raw"]["policyDetail"] = safe_detail
        result["discoveryNotes"].append(f"策略基本信息获取成功: {result['policy']['policyName']}")
        _log(f"  策略名称: {result['policy']['policyName']}")
        _log(f"  业务类型: {result['policy']['bizType']}")
        _log(f"  版本: {result['policy']['version']}")
    else:
        result["discoveryNotes"].append("未能获取策略基本信息（可能策略不存在或无权限）")
        _log("未能获取策略基本信息", "WARN")

    # ---- 步骤 2: 获取输入参数 ----
    _log("步骤 2/4: 发现输入参数...")
    params = fetch_test_input_params(session, base_url, policy_code)
    if params:
        result["inputParams"] = params
        result["discoveryNotes"].append(f"发现 {len(params)} 个输入参数")
        _log(f"  发现 {len(params)} 个输入参数")
    else:
        result["discoveryNotes"].append("未能自动发现输入参数（需要手动补充）")
        _log("  未能自动发现输入参数", "WARN")

    # ---- 步骤 3: 获取决策结果类型 ----
    _log("步骤 3/4: 获取决策结果类型...")
    dtypes = fetch_decision_types(session, base_url)
    if dtypes:
        result["decisionTypes"] = dtypes
        result["discoveryNotes"].append(f"获取到 {len(dtypes)} 个决策结果类型")
        _log(f"  获取到 {len(dtypes)} 个决策结果类型")
    else:
        result["discoveryNotes"].append("未能获取决策结果类型（需要手动补充）")
        _log("  未能获取决策结果类型", "WARN")

    # ---- 步骤 4: 发现子策略 ----
    _log("步骤 4/4: 发现子策略/决策流节点...")
    subs = discover_sub_strategies(session, base_url, policy_code, policy_detail)
    if subs:
        result["subStrategies"] = subs
        result["discoveryNotes"].append(f"发现 {len(subs)} 个子策略/节点")
        _log(f"  发现 {len(subs)} 个子策略/节点")
    else:
        result["discoveryNotes"].append("未发现子策略（可能策略无子流程，或无法解析决策流）")
        _log("  未发现子策略", "INFO")

    # ---- 输出结果 ----
    output_path = getattr(args, "output", None)
    if not output_path and getattr(args, "auto_output", False):
        # 自动生成输出路径
        output_path = f"strategies/{policy_code}.json"
    _output(result, output_path)

    # 汇总
    _log("=" * 60)
    _log("发现结果汇总:")
    for note in result["discoveryNotes"]:
        _log(f"  - {note}")
    _log("=" * 60)


def cmd_generate_comparison(args):
    """
    子命令: generate-comparison
    从策略的决策结果自动生成 comparisonRules 比对规则。

    数据来源（三选一，按优先级）：
    1. --input-json: 读取 discover 子命令的输出JSON
    2. --from-dtypes: 从平台 dealType API 获取决策类型并生成
    3. API 模式: 从策略详情中提取 decisionResults 并生成
    """
    policy_code = args.policy_code
    decision_results = []
    policy_detail = None
    raw_dtypes = None

    # ── 方式1: 从 discover 输出文件中读取 ──
    input_json = getattr(args, "input_json", None)
    if input_json:
        _log(f"从文件读取策略信息: {input_json}")
        with open(input_json, 'r', encoding='utf-8') as f:
            discover_data = json.load(f)
        policy_info = discover_data.get("policy", {})
        decision_results = discover_data.get("decisionResults", [])
        # 兼容: 部分 discover 输出将结果放在 raw 或其他位置
        if not decision_results:
            raw = discover_data.get("raw", {})
            if isinstance(raw, dict):
                detail = raw.get("policyDetail", {})
                if isinstance(detail, dict):
                    decision_results = detail.get("decisionResults", [])
        if not decision_results:
            # 最后尝试从 decisionTypes 转换
            dtypes = discover_data.get("decisionTypes", [])
            if dtypes:
                decision_results = extract_decision_results_from_raw(dtypes)
                raw_dtypes = dtypes
        policy_detail = {
            "policyName": policy_info.get("policyName", ""),
            "bizType": policy_info.get("bizType", ""),
            "publishConfig": {
                "ordinaryConfig": {"version": policy_info.get("version", "")}
            },
        }

    # ── 方式2: 从平台 dealType API 获取 ──
    elif getattr(args, "from_dtypes", False):
        _log("从平台 dealType API 获取决策类型...")
        session = build_session(args)
        base_url = _base_url(args)
        raw_dtypes = fetch_decision_types(session, base_url)
        if raw_dtypes:
            decision_results = extract_decision_results_from_raw(raw_dtypes)
            _log(f"从 {len(raw_dtypes)} 个决策类型中提取 {len(decision_results)} 个结果")
        # 也尝试获取策略详情
        policy_detail = fetch_policy_detail(
            session,
            base_url,
            policy_code,
            org_code=getattr(args, "org_code", None),
            biz_type=getattr(args, "biz_type", None),
        )

    # ── 方式3: 从策略详情 API 获取 ──
    else:
        session = build_session(args)
        base_url = _base_url(args)
        _log(f"从平台获取策略详情: {policy_code}")
        policy_detail = fetch_policy_detail(
            session,
            base_url,
            policy_code,
            org_code=getattr(args, "org_code", None),
            biz_type=getattr(args, "biz_type", None),
        )
        if policy_detail:
            decision_results = policy_detail.get("decisionResults", [])
            if not decision_results:
                _log("策略详情中无 decisionResults，尝试获取平台 dealType...", "WARN")
                raw_dtypes = fetch_decision_types(session, base_url)
                if raw_dtypes:
                    decision_results = extract_decision_results_from_raw(raw_dtypes)

    if not decision_results:
        _log("无法获取决策结果，无法生成比对规则", "ERROR")
        _log("请确保: (1) 策略详情包含 decisionResults 字段，"
             "或 (2) 使用 --input-json 提供 discover 输出，"
             "或 (3) 使用 --from-dtypes 从平台 dealType 生成", "ERROR")
        sys.exit(1)

    # ── 发现子策略（如果需要且未提供） ──
    sub_strategies = None
    if policy_detail and not input_json:
        base_url = _base_url(args) if not getattr(args, "input_json", None) else ""
        session_obj = build_session(args) if not getattr(args, "input_json", None) else None
        if session_obj and base_url:
            subs = discover_sub_strategies(session_obj, base_url, policy_code, policy_detail)
            if subs:
                sub_strategies = subs

    # ── 生成策略配置 ──
    config = generate_strategy_config(
        policy_code=policy_code,
        policy_detail=policy_detail,
        decision_results=decision_results,
        raw_dtypes=raw_dtypes,
        sub_strategies=sub_strategies,
    )

    # ── 输出 ──
    output_path = getattr(args, "output", None)
    if not output_path and getattr(args, "auto_output", False):
        output_path = f"strategies/{policy_code}.json"
    _output(config, output_path)

    # ── 汇总 ──
    _log("=" * 60)
    _log("生成结果汇总:")
    _log(f"  策略: {config['policyCode']} ({config['policyName']})")
    _log(f"  决策结果: {len(decision_results)} 个")
    _log(f"  比对规则: {len(config['comparisonRules'])} 条")
    for i, r in enumerate(config['comparisonRules']):
        _log(f"    [{i}] {r['type']}: {r.get('description', '')}")
    if sub_strategies:
        _log(f"  子策略: {len(sub_strategies)} 个")
    _log(f"  参数模板: common={len(config['params']['common'])} 个, "
         f"strategySpecific={len(config['params']['strategySpecific'])} 个")
    _log("  提示: comparisonRules 为自动生成骨架，请根据实际测试需要手动调整")
    _log("=" * 60)


# ---------------------------------------------------------------------------
# 命令行参数解析
# ---------------------------------------------------------------------------

def build_parser():
    """构建 argparse 命令行解析器"""
    parser = argparse.ArgumentParser(
        prog="discover_strategy.py",
        description="天策策略配置自动发现工具 - 从天策平台API发现策略元数据并生成配置文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出所有策略
  %(prog)s list-policies --host https://tiance.example.invalid --csrf YOUR_TOKEN

  # 发现指定策略的完整配置
  %(prog)s discover --policy-code bhjcpostMainBefore --host https://tiance.example.invalid --csrf TOKEN

  # 发现并保存到文件
  %(prog)s discover --policy-code DF_PRE_CONC_001 --output strategies/DF_PRE_CONC_001.json

  # 获取策略输入参数
  %(prog)s get-params --policy-code DF_PRE_CONC_001 --host https://tiance.example.invalid --csrf TOKEN

  # 获取决策结果类型
  %(prog)s get-decision-types --host https://tiance.example.invalid --csrf TOKEN

  # 使用浏览器 cookie 认证
  %(prog)s list-policies --cookie "JSESSIONID=xxx; XSRF-TOKEN=yyy"

  # 使用从浏览器复制的 CSRF token
  %(prog)s discover --policy-code test --from-browser YOUR_CSRF_TOKEN
        """,
    )

    # 全局参数
    parser.add_argument(
        "--host",
        default=None,
        help="天策平台地址 (默认从 config.json 读取)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="天策平台端口（如不指定则使用 host 中的端口或默认）",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        help="完整的 Cookie 字符串，用于认证",
    )
    parser.add_argument(
        "--csrf", "--csrf-token",
        dest="csrf",
        default=None,
        help="CSRF/XSRF Token，用于认证",
    )
    parser.add_argument(
        "--from-browser",
        dest="csrf",
        default=None,
        help="从浏览器会话复制的 CSRF Token（等同于 --csrf）",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出文件路径（不指定则输出到 stdout）",
    )
    parser.add_argument(
        "--org-code",
        default=None,
        help="机构编码；策略列表接口通常必须提供",
    )
    parser.add_argument(
        "--biz-type",
        type=int,
        default=None,
        help="业务类型编号（1=贷前、3=交易、4=贷中）",
    )
    parser.add_argument(
        "--auto-output",
        action="store_true",
        default=False,
        help="自动根据 policyCode 生成输出文件路径 (strategies/{policyCode}.json)",
    )

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # list-policies
    sub_list = subparsers.add_parser(
        "list-policies",
        help="列出所有可用策略",
        description="从天策平台获取所有已发布的策略列表",
    )
    sub_list.set_defaults(func=cmd_list_policies)

    # discover
    sub_discover = subparsers.add_parser(
        "discover",
        help="发现指定策略的完整配置",
        description="自动发现策略的元数据、参数、决策类型、子策略等信息",
    )
    sub_discover.add_argument(
        "--policy-code", "-p",
        required=True,
        help="策略编码 (policyCode)",
    )
    sub_discover.set_defaults(func=cmd_discover)

    # get-params
    sub_params = subparsers.add_parser(
        "get-params",
        help="获取策略的输入参数",
        description="发现指定策略的测试输入参数列表",
    )
    sub_params.add_argument(
        "--policy-code", "-p",
        required=True,
        help="策略编码 (policyCode)",
    )
    sub_params.set_defaults(func=cmd_get_params)

    # get-decision-types
    sub_dtypes = subparsers.add_parser(
        "get-decision-types",
        help="获取可用的决策结果类型",
        description="获取天策平台上配置的所有决策结果类型（dealType）",
    )
    sub_dtypes.set_defaults(func=cmd_get_decision_types)

    # generate-comparison
    sub_gencomp = subparsers.add_parser(
        "generate-comparison",
        help="从决策结果自动生成比对规则配置",
        description=(
            "从策略的 decisionResults 自动生成 comparisonRules 比对规则，"
            "输出完整的策略配置 JSON 文件骨架。"
            "数据来源: discover输出文件 / 平台dealType API / 策略详情API"
        ),
    )
    sub_gencomp.add_argument(
        "--policy-code", "-p",
        required=True,
        help="策略编码 (policyCode)",
    )
    sub_gencomp.add_argument(
        "--input-json",
        default=None,
        help="discover 子命令的输出 JSON 文件路径（优先使用此来源）",
    )
    sub_gencomp.add_argument(
        "--from-dtypes",
        action="store_true",
        default=False,
        help="从平台 dealType API 获取决策类型并生成（当策略详情无 decisionResults 时使用）",
    )
    sub_gencomp.set_defaults(func=cmd_generate_comparison)

    return parser


def main():
    """主入口"""
    # 禁用 SSL 警告（内网自签证书场景）
    if HAS_REQUESTS:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # 调用对应的子命令处理函数
    func = getattr(args, "func", None)
    if func:
        try:
            func(args)
        except KeyboardInterrupt:
            _log("用户中断", "WARN")
            sys.exit(130)
        except Exception as e:
            _log(f"执行失败: {e}", "ERROR")
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
