#!/usr/bin/env python3
"""
天策策略配置生成器

负责：
1. 从天策平台API获取策略元数据（策略列表、详情、参数、决策类型、子策略）
2. 从 decisionResults 自动生成 comparisonRules 比对规则
3. 组装完整的策略配置 JSON

Public API:
    fetch_policy_list()         — 获取策略列表
    fetch_policy_detail()       — 获取策略详情
    fetch_test_input_params()   — 获取策略输入参数
    fetch_decision_types()      — 获取决策结果类型
    discover_sub_strategies()   — 发现子策略/决策流节点
    generate_comparison_rules() — 生成比对规则
    generate_strategy_config()  — 组装完整策略配置
    extract_decision_results_from_raw() — 转换原始 dealType 数据
"""

import json
import sys
import time
import traceback
from datetime import datetime


# ---------------------------------------------------------------------------
# 私有辅助函数（避免与 discover_strategy.py 循环导入）
# ---------------------------------------------------------------------------

def _log(msg, level="INFO"):
    """输出日志到 stderr"""
    print(f"[{level}] {msg}", file=sys.stderr)


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


# ---------------------------------------------------------------------------
# 核心 API 调用函数
# ---------------------------------------------------------------------------

def fetch_policy_list(session, base_url, org_code=None, biz_type=None):
    """
    获取天策平台上所有策略列表。
    API: GET /noahApi/policy/list
    返回: data.contents[] 数组，每项含 policyCode, policyName, publishConfig 等
    """
    url = f"{base_url}/noahApi/policy/list"
    _log(f"获取策略列表: {url}")
    try:
        params = {}
        if org_code:
            params["orgCode"] = org_code
        if biz_type is not None:
            params["bizType"] = biz_type
        if params:
            params["startTime"] = 0
            params["endTime"] = int(time.time() * 1000)
        resp = session.get(url, params=params or None, timeout=30)
        data = _safe_json(resp)
        if data is None:
            _log(f"无法解析响应 (HTTP {resp.status_code}): {resp.text[:500]}", "WARN")
            return None
        # 天策返回格式通常是 { "code": 200, "data": { "contents": [...] } }
        if isinstance(data, dict):
            inner = data.get("data", data)
            if isinstance(inner, dict):
                contents = inner.get("contents", inner.get("list", inner.get("records", [])))
                return contents if isinstance(contents, list) else []
            elif isinstance(inner, list):
                return inner
        return []
    except Exception as e:
        _log(f"获取策略列表失败: {e}", "ERROR")
        traceback.print_exc(file=sys.stderr)
        return None


def fetch_policy_detail(
    session,
    base_url,
    policy_code,
    org_code=None,
    biz_type=None,
):
    """
    从策略列表中查找指定 policyCode 的详细信息。
    返回: 策略详情 dict 或 None
    """
    policies = fetch_policy_list(
        session,
        base_url,
        org_code=org_code,
        biz_type=biz_type,
    )
    if policies is None:
        _log("无法获取策略列表，无法查找详情", "ERROR")
        return None
    for p in policies:
        if isinstance(p, dict) and (
            p.get("policyCode") or p.get("code")
        ) == policy_code:
            return p
    # 尝试模糊匹配
    for p in policies:
        if isinstance(p, dict):
            code = p.get("policyCode") or p.get("code") or ""
            if policy_code.lower() in code.lower():
                _log(f"未精确匹配 '{policy_code}'，模糊匹配到: {code}", "WARN")
                return p
    _log(f"未找到 policyCode='{policy_code}'，共 {len(policies)} 条策略", "WARN")
    return None


def fetch_test_input_params(session, base_url, policy_code):
    """
    获取策略的测试输入参数。
    方法1: 通过提交测试请求，从错误/成功响应中提取参数信息。
    方法2: 通过 getTestInputParams 接口（如果存在）。
    返回: 参数列表 [{name, type, required, ...}] 或 None
    """
    params = []

    # 方法1: 尝试调用实验室测试接口，从响应中提取参数信息
    # POST /noahApi/lab/policytest/create
    test_url = f"{base_url}/noahApi/lab/policytest/create"
    test_payload = {
        "policyCode": policy_code,
        "testcase": "1",
        "customParams": "{}",
        "params": "{}",
    }
    _log(f"尝试通过测试接口发现参数: {test_url}")
    try:
        resp = session.post(test_url, data=test_payload, timeout=30)
        data = _safe_json(resp)
        if data:
            # 从错误信息中提取缺失参数列表
            msg = data.get("message", data.get("msg", ""))
            err_data = data.get("data", {})
            # 有些版本返回 data.missingParams 或 data.requiredParams
            if isinstance(err_data, dict):
                for key in ("missingParams", "requiredParams", "params",
                            "inputParams", "fields", "inputFields"):
                    if key in err_data and isinstance(err_data[key], list):
                        params.extend(err_data[key])
                        _log(f"从测试响应中发现 {len(err_data[key])} 个参数 (via {key})")
                        break
                # 也检查 data.paramList
                if not params and "paramList" in err_data:
                    pl = err_data["paramList"]
                    if isinstance(pl, list):
                        params.extend(pl)
                        _log(f"从 paramList 中发现 {len(pl)} 个参数")
            # 尝试从 data.testToken / data.id 获取测试执行记录
            test_token = None
            if isinstance(err_data, dict):
                test_token = err_data.get("testToken") or err_data.get("id") or err_data.get("tokenId")
            elif isinstance(err_data, str):
                test_token = err_data
            if test_token:
                _log(f"获取到测试 token: {test_token}")
                # 尝试从执行日志中提取更多信息
                log_params = _fetch_execution_log_params(session, base_url, test_token)
                if log_params:
                    params.extend(log_params)
    except Exception as e:
        _log(f"测试接口调用失败: {e}", "WARN")

    # 方法2: 尝试直接获取参数的 API（部分版本支持）
    param_apis = [
        f"{base_url}/noahApi/policy/getTestInputParams?policyCode={policy_code}",
        f"{base_url}/noahApi/policy/inputParams?policyCode={policy_code}",
        f"{base_url}/noahApi/policy/params?policyCode={policy_code}",
    ]
    for api_url in param_apis:
        try:
            resp = session.get(api_url, timeout=15)
            data = _safe_json(resp)
            if data and resp.ok:
                inner = data.get("data", data)
                if isinstance(inner, list) and len(inner) > 0:
                    _log(f"从 {api_url.split('/noahApi/')[-1]} 获取到 {len(inner)} 个参数")
                    params.extend(inner)
                    break
                elif isinstance(inner, dict):
                    # 可能返回 { "params": [...] } 形式
                    for key in ("params", "fields", "inputParams", "inputFields"):
                        if key in inner and isinstance(inner[key], list):
                            params.extend(inner[key])
                            _log(f"从响应 .{key} 获取到 {len(inner[key])} 个参数")
                            break
        except Exception:
            continue

    # 去重
    seen = set()
    unique_params = []
    for p in params:
        if isinstance(p, dict):
            key = p.get("name") or p.get("code") or p.get("fieldName") or str(p)
        else:
            key = str(p)
        if key not in seen:
            seen.add(key)
            unique_params.append(p)

    return unique_params if unique_params else None


def _fetch_execution_log_params(session, base_url, token):
    """
    从测试执行日志中提取参数信息。
    API: GET /noahApi/policy/report/getAllCompontlog?id={token}&reportAuth=false&tokenId={token}&type=1
    """
    url = f"{base_url}/noahApi/policy/report/getAllCompontlog"
    params_dict = {
        "id": token,
        "reportAuth": "false",
        "tokenId": token,
        "type": "1",
    }
    _log(f"获取执行日志: {url}")
    try:
        resp = session.get(url, params=params_dict, timeout=30)
        data = _safe_json(resp)
        if not data:
            return []
        # 从执行日志中提取输入参数
        result_params = []
        inner = data.get("data", data)
        if isinstance(inner, list):
            for node in inner:
                if isinstance(node, dict):
                    # 每个节点可能包含 inputParams / input 等
                    for key in ("inputParams", "input", "inputs", "paramMap"):
                        val = node.get(key)
                        if isinstance(val, dict):
                            for pname, pval in val.items():
                                result_params.append({
                                    "name": pname,
                                    "value": pval,
                                    "source": "execution_log",
                                    "node": node.get("nodeName", node.get("compontName", "")),
                                })
                        elif isinstance(val, list):
                            for item in val:
                                if isinstance(item, dict):
                                    result_params.append({
                                        "name": item.get("name", item.get("key", "")),
                                        "value": item.get("value", ""),
                                        "source": "execution_log",
                                        "node": node.get("nodeName", node.get("compontName", "")),
                                    })
        elif isinstance(inner, dict):
            # 某些版本直接返回参数 map
            for key in ("inputParams", "input", "inputs", "paramMap", "params"):
                val = inner.get(key)
                if isinstance(val, dict):
                    for pname, pval in val.items():
                        result_params.append({
                            "name": pname,
                            "value": pval,
                            "source": "execution_log",
                        })
        if result_params:
            _log(f"从执行日志中提取到 {len(result_params)} 个参数")
        return result_params
    except Exception as e:
        _log(f"获取执行日志失败: {e}", "WARN")
        return []


def fetch_decision_types(session, base_url):
    """
    获取天策平台的决策结果类型（dealType）列表。
    尝试多个已知 API 端点。
    返回: 决策类型列表 或 None
    """
    # 已知可能的 API 端点
    endpoints = [
        "/noahApi/common/dealType/list",
        "/noahApi/dealType/list",
        "/noahApi/policy/dealType/list",
        "/noahApi/common/getDealTypes",
        "/noahApi/config/dealType/list",
        "/noahApi/riskDecisionType/list",
        "/noahApi/common/riskDecisionType/list",
    ]
    for ep in endpoints:
        url = f"{base_url}{ep}"
        try:
            resp = session.get(url, timeout=15)
            if resp.ok:
                data = _safe_json(resp)
                if data:
                    inner = data.get("data", data)
                    if isinstance(inner, list) and len(inner) > 0:
                        _log(f"从 {ep} 获取到 {len(inner)} 个决策类型")
                        return inner
                    elif isinstance(inner, dict):
                        for key in ("list", "contents", "records", "items"):
                            if key in inner and isinstance(inner[key], list):
                                _log(f"从 {ep} (.data.{key}) 获取到 {len(inner[key])} 个决策类型")
                                return inner[key]
        except Exception:
            continue
    _log("未能从已知端点获取决策类型列表", "WARN")
    return None


def discover_sub_strategies(session, base_url, policy_code, policy_detail):
    """
    尝试发现策略的子策略（决策流中的子节点）。
    通过分析策略的 publishConfig 和决策流配置来识别。
    返回: 子策略列表 [{code, name, type}] 或空列表
    """
    sub_strategies = []

    if not policy_detail:
        return sub_strategies

    # 从 publishConfig 中提取决策流节点信息
    publish_config = policy_detail.get("publishConfig", {})
    if isinstance(publish_config, str):
        try:
            publish_config = json.loads(publish_config)
        except Exception:
            publish_config = {}

    # 检查 ordinaryConfig 中的流程定义
    ordinary_config = publish_config.get("ordinaryConfig", {})
    if isinstance(ordinary_config, str):
        try:
            ordinary_config = json.loads(ordinary_config)
        except Exception:
            ordinary_config = {}

    # 从多个可能的位置提取子策略/节点信息
    flow_keys = [
        "flowNodes", "nodes", "decisionFlow", "subPolicies",
        "policyNodes", "components", "componts", "stages",
        "ruleSets", "ruleSetList",
    ]
    for key in flow_keys:
        nodes = ordinary_config.get(key) or publish_config.get(key)
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, dict):
                    sub = {
                        "code": node.get("policyCode", node.get("code", node.get("nodeCode", ""))),
                        "name": node.get("policyName", node.get("name", node.get("nodeName", ""))),
                        "type": node.get("nodeType", node.get("type", node.get("compontType", ""))),
                    }
                    if sub["code"] or sub["name"]:
                        sub_strategies.append(sub)
            if sub_strategies:
                _log(f"从 publishConfig.{key} 中发现 {len(sub_strategies)} 个子节点")
                break

    # 尝试通过 API 获取策略的决策流配置
    flow_apis = [
        f"/noahApi/policy/flow?policyCode={policy_code}",
        f"/noahApi/policy/detail?policyCode={policy_code}",
        f"/noahApi/policy/config?policyCode={policy_code}",
    ]
    if not sub_strategies:
        for api_path in flow_apis:
            url = f"{base_url}{api_path}"
            try:
                resp = session.get(url, timeout=15)
                if resp.ok:
                    data = _safe_json(resp)
                    if data:
                        inner = data.get("data", data)
                        if isinstance(inner, dict):
                            for key in flow_keys:
                                nodes = inner.get(key)
                                if isinstance(nodes, list):
                                    for node in nodes:
                                        if isinstance(node, dict):
                                            sub = {
                                                "code": node.get("policyCode", node.get("code", "")),
                                                "name": node.get("policyName", node.get("name", "")),
                                                "type": node.get("nodeType", node.get("type", "")),
                                            }
                                            if sub["code"] or sub["name"]:
                                                sub_strategies.append(sub)
                                    if sub_strategies:
                                        _log(f"从 {api_path} 中发现 {len(sub_strategies)} 个子节点")
                                        break
                        if sub_strategies:
                            break
            except Exception:
                continue

    return sub_strategies


# ---------------------------------------------------------------------------
# 比对规则自动生成
# ---------------------------------------------------------------------------

# 通过/Accept 的关键词集合
_PASS_KEYWORDS = {'通过', 'Accept', 'pass', '通过审批', '正常', '无风险',
                  '不触发', '全部通过', 'accept'}

# 表示"级别/等级"的关键字，用于检测 level-based 决策体系
_LEVEL_HINTS = ('风险', '等级', '级别', '预警', 'risk', 'level', 'warn')


def _is_pass_type(name, aliases):
    """判断一个决策结果是否为'通过'类型"""
    if any(kw in name for kw in _PASS_KEYWORDS):
        return True
    return any(any(kw in a for kw in _PASS_KEYWORDS) for a in aliases)


def _is_level_based(decision_results):
    """检测决策结果是否为等级体系（大部分结果含风险/等级/预警关键字）"""
    if len(decision_results) < 2:
        return False
    level_count = sum(
        1 for dr in decision_results
        if any(h in dr['name'] for h in _LEVEL_HINTS)
    )
    return level_count >= len(decision_results) * 0.5


def generate_comparison_rules(decision_results):
    """
    从 decisionResults 列表自动生成 comparisonRules。

    生成策略：
    1. 等级体系（含风险/等级/预警关键字）→ alias_group + exploratory
    2. 含"通过"类型结果 → keyword_absent (预期通过时不应含失败关键字)
    3. 含具体失败类型 → keyword_present (预期某失败时实际应包含)
    4. 含"待探索" → exploratory
    5. 含"待验证"/"待确认" → invalid_expectation
    6. 兜底 → 报错/异常检测

    参数:
        decision_results: [{"name": str, "code": str, "aliases": [str], "priority": int}]

    返回:
        comparisonRules 列表
    """
    rules = []
    if not decision_results:
        return rules

    # ── 检测等级体系 → 生成 alias_group ──
    is_level = _is_level_based(decision_results)

    if is_level:
        groups = []
        for dr in decision_results:
            # 跳过占位类结果（它们有专用的 exploratory / invalid_expectation 规则）
            if dr['name'] in ('待探索', '待验证', '待确认'):
                continue
            group_aliases = [dr['name']]
            if dr.get('code') and dr['code'] != dr['name']:
                group_aliases.append(dr['code'])
            for a in dr.get('aliases', []):
                if a not in group_aliases:
                    group_aliases.append(a)
            groups.append(group_aliases)
        rules.append({
            "type": "alias_group",
            "groups": groups,
            "description": "等级别名组匹配（自动生成）",
        })

    # ── 收集所有失败结果名（非通过类型） ──
    fail_names = [dr['name'] for dr in decision_results
                  if not _is_pass_type(dr['name'], dr.get('aliases', []))]

    # ── 通过类型 → keyword_absent ──
    pass_results = [dr for dr in decision_results
                    if _is_pass_type(dr['name'], dr.get('aliases', []))]
    if pass_results:
        pass_triggers = []
        for dr in pass_results:
            pass_triggers.append(dr['name'])
            for a in dr.get('aliases', []):
                if a not in pass_triggers:
                    pass_triggers.append(a)
        rules.append({
            "type": "keyword_absent",
            "triggers": pass_triggers,
            "target": fail_names if len(fail_names) <= 5 else fail_names[:5],
            "description": "预期通过时，实际不应含失败/预警关键字（自动生成）",
        })

    # ── 非等级体系 → 为每个失败结果生成 keyword_present ──
    if not is_level:
        for dr in decision_results:
            if _is_pass_type(dr['name'], dr.get('aliases', [])):
                continue
            if dr['name'] in ('待探索', '待验证', '待确认'):
                continue
            triggers = [dr['name']]
            for a in dr.get('aliases', []):
                if a not in triggers:
                    triggers.append(a)
            rules.append({
                "type": "keyword_present",
                "triggers": triggers,
                "target": dr['name'],
                "description": f"预期'{dr['name']}'时，实际应包含该关键字（自动生成）",
            })

    # ── 待探索 → exploratory ──
    exploratory_results = [dr for dr in decision_results
                           if '待探索' in dr['name']]
    if exploratory_results:
        valid_indicators = [dr['name'] for dr in decision_results
                            if '待' not in dr['name']
                            and not _is_pass_type(dr['name'], dr.get('aliases', []))]
        if is_level:
            # 等级体系：所有等级名都是有效指标
            valid_indicators = [dr['name'] for dr in decision_results
                                if '待' not in dr['name']]
        if not valid_indicators:
            valid_indicators = [dr['name'] for dr in decision_results if dr['name'] != '待探索']
        rules.append({
            "type": "exploratory",
            "triggers": ["待探索"],
            "validIndicators": valid_indicators,
            "description": "探索性用例：实际结果为任意有效等级/结果即通过（自动生成）",
        })

    # ── 待验证/待确认 → invalid_expectation ──
    invalid_results = [dr for dr in decision_results
                       if '待验证' in dr['name'] or '待确认' in dr['name']]
    if invalid_results:
        rules.append({
            "type": "invalid_expectation",
            "triggers": ["待验证", "待确认"],
            "description": "实际结果仍含待验证/待确认则判未通过（自动生成）",
        })

    # ── 兜底：报错/异常检测 ──
    rules.append({
        "type": "keyword_present",
        "triggers": ["报错", "异常", "失败"],
        "target": ["失败", "错误", "异常"],
        "description": "预期含报错/异常时，实际应包含失败相关关键字（自动生成）",
    })

    return rules


def extract_decision_results_from_raw(raw_dtypes):
    """
    将平台 dealType API 返回的原始决策类型数据转换为 decisionResults 格式。

    参数:
        raw_dtypes: fetch_decision_types() 返回的原始列表

    返回:
        [{"name", "code", "priority", "aliases"}]
    """
    results = []
    if not raw_dtypes:
        return results

    for i, dt in enumerate(raw_dtypes):
        if not isinstance(dt, dict):
            continue
        name = (dt.get('name') or dt.get('typeName') or dt.get('dealTypeName')
                or dt.get('label') or '')
        code = (dt.get('code') or dt.get('typeCode') or dt.get('dealTypeCode')
                or dt.get('value') or name)
        if not name:
            continue
        aliases = [name]
        if code and code != name:
            aliases.append(code)
        results.append({
            "name": name,
            "code": code,
            "priority": dt.get('priority', dt.get('sort', dt.get('order', i))),
            "aliases": aliases,
        })
    return results


def generate_strategy_config(policy_code, policy_detail, decision_results,
                             raw_dtypes=None, sub_strategies=None):
    """
    组装完整的策略配置文件结构。

    返回:
        可直接 json.dumps 写入文件的 dict
    """
    policy_name = ""
    version = ""
    biz_type = ""
    if policy_detail:
        policy_name = (
            policy_detail.get("policyName")
            or policy_detail.get("name")
            or ""
        )
        biz_type = (
            policy_detail.get("businessType")
            if policy_detail.get("businessType") is not None
            else policy_detail.get("bizType", "")
        )
        pub_config = policy_detail.get("publishConfig", {})
        if isinstance(pub_config, str):
            try:
                pub_config = json.loads(pub_config)
            except json.JSONDecodeError:
                pub_config = {}
        if isinstance(pub_config, dict):
            ord_config = pub_config.get("ordinaryConfig", {})
            if isinstance(ord_config, dict):
                version = ord_config.get("version", "")

    comparison_rules = generate_comparison_rules(decision_results)

    config = {
        "policyCode": policy_code,
        "policyName": policy_name,
        "policyVersion": int(version) if str(version).isdigit() else version,
        "bizType": biz_type,
    }
    if sub_strategies:
        config["subStrategies"] = sub_strategies
    if decision_results:
        config["decisionResults"] = decision_results
    config["comparisonRules"] = comparison_rules
    config["params"] = {
        "common": {
            "S_E_APIMODEL": {"type": "string", "fixed": "30"},
            "S_S_BIZID": {"type": "string", "required": True},
            "S_S_CUSTNO": {"type": "string", "required": True},
            "S_S_ORGCODE": {"type": "string", "required": True},
        },
        "strategySpecific": {},
    }
    config["testExecution"] = {
        "requiredParams": [],
        "defaults": {},
        "defaultsByCaseType": {},
        "mockRequiredCaseTypes": ["异常案例"],
        "mockScenarios": {},
    }
    if raw_dtypes:
        config["_platformDecisionTypes"] = raw_dtypes
    config["_generatedBy"] = "discover_strategy.py generate-comparison"
    config["_generatedAt"] = datetime.now().isoformat()
    config["_note"] = (
        "自动生成的策略配置骨架。comparisonRules 为基于 decisionResults 的默认规则，"
        "请根据实际测试需要手动调整。params.strategySpecific 需补充策略专有参数。"
    )
    return config
