#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天策 .pls 策略导出解码器

.pls 文件是 base64(gzip(JSON)) 的封装。本脚本将其还原为结构化 JSON，
并对评分卡（scorecard）类策略提取测试所需的变量与分箱清单：
  BIG_CLASS → VARIABLE → BINNING(区间/单值/缺省) 树。

评分卡总分（scoreCardMode / scoreMethod = 1，线性累加）:
  total = basicScore + Σ (每个 VARIABLE 命中分箱的 score)
分箱区间记号: [a,b] 闭、(a,b] 左开、[a,b) 右开、(a,b) 开；DFLT_VAL 为缺省兜底。

用法:
  python3 decode_pls.py <file.pls>                 # 打印结构摘要
  python3 decode_pls.py <file.pls> -o decoded.json # 导出完整解码 JSON
  python3 decode_pls.py <file.pls> --summary       # 仅摘要 JSON（供用例生成消费）
"""
import sys
import json
import base64
import gzip
import argparse
import re
from pathlib import Path


def load_pls(path):
    """把 .pls 还原为 dict。兼容 base64+gzip、纯 gzip、纯 JSON 三种来源。"""
    raw = Path(path).read_bytes()
    candidates = []
    # 1) base64 -> gzip
    try:
        candidates.append(gzip.decompress(base64.b64decode(raw)))
    except Exception:
        pass
    # 2) base64 -> plain json (no gzip)
    try:
        candidates.append(base64.b64decode(raw))
    except Exception:
        pass
    # 3) raw gzip
    try:
        candidates.append(gzip.decompress(raw))
    except Exception:
        pass
    # 4) raw bytes (already json)
    candidates.append(raw)

    last_err = None
    for blob in candidates:
        try:
            text = blob.decode('utf-8') if isinstance(blob, (bytes, bytearray)) else blob
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise ValueError(f"无法解码 .pls: {last_err}")


def parse_range(rng):
    """把分箱区间字符串解析为 (下界, 下闭, 上界, 上闭) 或 ('DFLT',) 。"""
    if rng is None:
        return None
    s = str(rng).strip()
    if s.upper() in ('DFLT_VAL', 'DFLT', 'DEFAULT'):
        return {'kind': 'default'}
    m = re.match(r'^([\[\(])\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*([\]\)])$', s)
    if m:
        lo, lo_closed = float(m.group(2)), m.group(1) == '['
        hi, hi_closed = float(m.group(3)), m.group(4) == ']'
        return {'kind': 'range', 'low': lo, 'low_closed': lo_closed,
                'high': hi, 'high_closed': hi_closed}
    m = re.match(r'^(-?\d+(?:\.\d+)?)$', s)
    if m:
        return {'kind': 'exact', 'value': float(m.group(1))}
    return {'kind': 'raw', 'text': s}


def bin_hits(parsed_range, value):
    """判断数值是否落入某个已解析的分箱（供预期算分用）。"""
    if not parsed_range:
        return False
    k = parsed_range['kind']
    if k == 'default':
        return False  # 缺省仅在其它箱都不命中时兜底
    if k == 'exact':
        return float(value) == parsed_range['value']
    if k == 'range':
        v = float(value)
        left = (v >= parsed_range['low']) if parsed_range['low_closed'] else (v > parsed_range['low'])
        right = (v <= parsed_range['high']) if parsed_range['high_closed'] else (v < parsed_range['high'])
        return left and right
    return False


def _maybe_json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return v
    return v


def summarize(decoded):
    """从解码 JSON 抽取策略身份 + 评分卡变量/分箱清单。"""
    out = {'source_keys': list(decoded.keys()), 'policies': [], 'scorecards': []}

    for item in decoded.get('policyCombineExportData', []) or []:
        pe = item.get('policyExportData', {}) or {}
        pvl = item.get('policyVersionExportDataList', []) or []
        out['policies'].append({
            'code': pe.get('code'),
            'name': pe.get('name'),
            'businessType': pe.get('businessType'),
            'orgCode': pe.get('orgCode'),
            'appCode': pe.get('appCode'),
            'mode': pe.get('mode'),
            'eventType': pe.get('eventType'),
            'version': (pvl[0].get('version') if pvl and isinstance(pvl[0], dict) else None),
        })

    for sc in decoded.get('scorecardExportDataList', []) or []:
        content = _maybe_json(sc.get('content')) or []
        variables = []
        for big in content if isinstance(content, list) else []:
            for var in big.get('children', []) or []:
                bins = []
                for b in var.get('children', []) or []:
                    pr = parse_range(b.get('range'))
                    bins.append({
                        'type': b.get('type'),
                        'range': b.get('range'),
                        'score': b.get('score'),
                        'parsed': pr,
                    })
                variables.append({
                    'bigClassId': big.get('id'),
                    'bigClassName': big.get('name'),
                    'varId': var.get('id'),          # 计分字段编码，如 C_F_DQSHZHF / S_N_AGE
                    'varName': var.get('name'),
                    'dataType': var.get('dataType'),
                    'scoreMethod': var.get('scoreMethod'),
                    'bins': bins,
                })
        out['scorecards'].append({
            'code': sc.get('scoreCardCode'),
            'name': sc.get('scoreCardName'),
            'mode': sc.get('scoreCardMode'),          # 1 = 线性累加
            'basicScore': sc.get('basicScore'),
            'output': _maybe_json(sc.get('outputData')),
            'variables': variables,
        })
    return out


def expected_score(scorecard, values):
    """按线性累加算给定入参下的预期总分。values: {varId: number}。"""
    total = float(scorecard.get('basicScore') or 0)
    detail = {}
    for var in scorecard['variables']:
        vid = var['varId']
        got = None
        if vid in values and values[vid] is not None:
            val = values[vid]
            for b in var['bins']:
                if b['parsed'] and b['parsed']['kind'] == 'default':
                    continue
                if bin_hits(b['parsed'], val):
                    got = float(b['score'])
                    break
            if got is None:  # 全部未命中 -> 缺省兜底分
                for b in var['bins']:
                    if b['parsed'] and b['parsed']['kind'] == 'default':
                        got = float(b['score'])
                        break
        if got is None:
            got = 0.0
        detail[vid] = got
        total += got
    return total, detail


def main():
    ap = argparse.ArgumentParser(description='天策 .pls 策略导出解码器')
    ap.add_argument('pls', help='.pls 文件路径')
    ap.add_argument('-o', '--output', help='导出完整解码 JSON 的路径')
    ap.add_argument('--summary', action='store_true', help='仅输出结构摘要 JSON')
    args = ap.parse_args()

    decoded = load_pls(args.pls)
    summ = summarize(decoded)

    if args.output:
        Path(args.output).write_text(
            json.dumps(decoded, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"[decode_pls] 完整 JSON 已导出: {args.output}", file=sys.stderr)

    if args.summary:
        print(json.dumps(summ, ensure_ascii=False, indent=2))
        return

    # 人类可读摘要
    for p in summ['policies']:
        print(f"策略: {p['name']} (code={p['code']}, version={p['version']}, "
              f"businessType={p['businessType']}, org={p['orgCode']}, mode={p['mode']})")
    for sc in summ['scorecards']:
        mode = {1: '线性累加'}.get(sc['mode'], f"mode={sc['mode']}")
        print(f"\n评分卡: {sc['name']} (code={sc['code']}, {mode}, 基础分={sc['basicScore']})")
        for var in sc['variables']:
            bins = ', '.join(f"{b['range']}→{b['score']}" for b in var['bins'])
            print(f"  变量 {var['varName']} [{var['varId']}] ({var['dataType']}): {bins}")
        max_total = float(sc['basicScore'] or 0) + sum(
            max((float(b['score']) for b in var['bins']), default=0)
            for var in sc['variables'])
        print(f"  理论满分: {max_total}")


if __name__ == '__main__':
    main()
