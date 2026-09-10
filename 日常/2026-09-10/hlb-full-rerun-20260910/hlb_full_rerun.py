#!/usr/bin/env python3
"""HLB 收单指标用例 —— 完整重跑（全量 8 条）
链路：加载 checkpoint 设计 -> 新 runId + 隔离重映射 -> 结构预检 -> 按序真实提交(历史->当前)
     -> classify-execution-result.js 判五态 -> mingFields 提取指标三段式证据 -> 汇总。
断点续跑：每个用例结果写 <run>/<row>/result.json，存在且 complete 则跳过。
"""
import json, os, re, time, glob, subprocess, urllib.request, datetime, pathlib, sys

R2 = "/Users/td/outputs/HLB_Acquiring_Skill全流程最小重跑_20260820_R2"
CK = f"{R2}/checkpoints"
CLASSIFY = "/Users/td/.qoderwork/skills/tiance-policy-test/scripts/classify-execution-result.js"
NEW_NS = "QWFR_0910"
HIST_SPACING = float(os.environ.get("HIST_SPACING", "0.5"))
SETTLE = float(os.environ.get("SETTLE", "15"))
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
RUN = pathlib.Path(f"/Users/td/.qoderwork/workspace/mttrqawk3qp6mzcs/hlb-full-rerun-{TS}")
RUN.mkdir(parents=True, exist_ok=True)

# 用例配置：短窗口=自然隔离(仅换token+rebase)；长窗口=额外迁移行号段到未占用命名空间
# (row, ckfile_glob, long, digit_map)
CASES = [
    ("47",  "*_47_ACQ_RS3_000014_*_minimal-rerun.json",      False, None),
    ("53",  "*53_53_ACQ_RS3_000016_*metric-alignment.json",   False, None),
    ("59",  "*_59_ACQ_RS3_000018_*_minimal-rerun.json",       False, None),
    ("71",  "*_71_ACQ_RS3_000021_*_minimal-rerun.json",       False, None),
    ("93",  "*_93_ACQ_RS3_000028_*_minimal-rerun.json",       False, None),
    ("179", "*_179_ACQ_RS4_000010_*_minimal-rerun.json",      False, None),
    ("245", "*_245_ACQ_RS4_000025_*_minimal-rerun.json",      True,  {"245": "945"}),
    ("268", "*_268_ACQ_RS4_000032_*_minimal-rerun.json",      True,  {"268": "968"}),
]
OLD_TOKENS = ["SKR2_0820", "SKR4_0821_R53", "SKR3_0821_R53"]

log_lock_path = RUN / "progress.log"
def log(msg):
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(log_lock_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def remap_str(s, new_tok, digit_map):
    if not isinstance(s, str):
        return s
    for ot in OLD_TOKENS:
        s = s.replace(ot, new_tok)
    if digit_map:
        for o, n in digit_map.items():
            s = s.replace(o, n)
    return s

def remap_req(req, new_tok, digit_map):
    out = {}
    for k, v in req.items():
        nv = v
        if isinstance(v, str):
            nv = remap_str(v, new_tok, digit_map)
        elif isinstance(v, list):
            nv = [remap_str(x, new_tok, digit_map) if isinstance(x, str) else x for x in v]
        elif isinstance(v, dict):
            nv = {kk: remap_str(vv, new_tok, digit_map) if isinstance(vv, str) else vv
                  for kk, vv in v.items()}
        out[k] = nv
    return out

def rebase_time(req, offset):
    r = dict(req)
    if "biztime" in r:
        dt = datetime.datetime.strptime(r["biztime"], "%Y-%m-%d %H:%M:%S") + offset
        r["biztime"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        r["transactiondate"] = dt.strftime("%Y-%m-%d")
        r["transactiontime"] = dt.strftime("%H:%M:%S")
    return r

def post(endpoint, payload):
    req = urllib.request.Request(endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def walk_metrics(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith("salaxyzb_"):
                out.setdefault(k, v)
            walk_metrics(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_metrics(v, out)

def find_metric(resp, name):
    # salaxyzb_ 走 walk；其它(如 C_N_*) 在响应里按 key 命中
    bag = {}
    walk_metrics(resp, bag)
    if name in bag:
        return bag[name]
    s = json.dumps(resp, ensure_ascii=False)
    m = re.search(r'"' + re.escape(name) + r'"\s*:\s*([0-9.eE+-]+)', s)
    return float(m.group(1)) if m else None

def cmp_op(actual, op, val):
    if actual is None:
        return False
    try:
        a = float(actual)
    except Exception:
        return False
    return {">=": a >= val, ">": a > val, "<=": a <= val, "<": a < val,
            "==": a == val, "=": a == val}.get(op, False)

def run_case(row, ckfile, longcase, digit_map):
    rd = RUN / row
    (rd / "responses").mkdir(parents=True, exist_ok=True)
    rj = rd / "result.json"
    if rj.exists():
        try:
            prev = json.load(open(rj))
            if prev.get("complete"):
                log(f"row {row}: 已完成，跳过 (status={prev.get('classification',{}).get('status')})")
                return prev
        except Exception:
            pass

    d = json.load(open(ckfile))
    pm = d["planned_manifest"]
    ahr = d["actual_history_requests"]
    cur = d["actual_current_request"]
    old_cur_dt = datetime.datetime.strptime(cur["biztime"], "%Y-%m-%d %H:%M:%S")
    offset = datetime.datetime.now().replace(microsecond=0) - old_cur_dt
    new_tok = f"{NEW_NS}_R{row}"

    # 构建重映射+rebase 后的请求
    hist = []
    for item in ahr:
        req = rebase_time(remap_req(item["request"], new_tok, digit_map), offset)
        hist.append((item["endpoint"], req))
    hist.sort(key=lambda x: x[1]["biztime"])  # 历史按时间升序，早于当前
    cur_req = rebase_time(remap_req(cur, new_tok, digit_map), offset)
    cur_ep = ahr[0]["endpoint"] if cur.get("policyCode") else None
    cur_ep = ahr[-1]["endpoint"]  # 当前笔用最后一条(与生成器一致)对应的接口
    # 当前笔接口优先取 checkpoint 记录的 current_archive 对应的 endpoint
    cur_ep = ahr[0]["endpoint"]

    # ---- 结构预检 ----
    preflight = {"bizid_unique": None, "current_field_match": None, "issues": []}
    all_biz = [r["bizid"] for _, r in hist] + [cur_req["bizid"]]
    preflight["bizid_unique"] = len(set(all_biz)) == len(all_biz)
    if not preflight["bizid_unique"]:
        preflight["issues"].append("bizid 不唯一")
    exp_fields = pm.get("预期当前笔字段", {}) or {}
    mism = {k: (remap_str(str(v), new_tok, digit_map), cur_req.get(k))
            for k, v in exp_fields.items()
            if str(remap_str(str(v), new_tok, digit_map)) != str(cur_req.get(k))}
    preflight["current_field_match"] = len(mism) == 0
    if mism:
        preflight["issues"].append(f"当前笔字段不符预期: {mism}")
    json.dump({"new_token": new_tok, "offset": str(offset), "hist_count": len(hist),
               "preflight": preflight}, open(rd / "preflight.json", "w"),
              ensure_ascii=False, indent=1)

    if not preflight["bizid_unique"] or not preflight["current_field_match"]:
        result = {"row": int(row), "rule_code": d["rule_code"], "case_type": d["case_type"],
                  "new_token": new_tok, "preflight": preflight, "complete": True,
                  "classification": {"status": "无效用例", "evidence": preflight["issues"]},
                  "metric_evidence": []}
        json.dump(result, open(rj, "w"), ensure_ascii=False, indent=1)
        log(f"row {row}: 预检失败 -> 无效用例；{preflight['issues']}")
        return result

    # ---- 真实提交 ----
    hist_ok = 0
    sent = []
    for i, (ep, req) in enumerate(hist, 1):
        try:
            resp = post(ep, req)
            ok = resp.get("success") is True
            hist_ok += ok
            (rd / "responses" / f"hist_{i:03d}.json").write_text(
                json.dumps(resp, ensure_ascii=False), encoding="utf-8")
            sent.append({"i": i, "bizid": req["bizid"], "success": ok})
        except Exception as e:
            sent.append({"i": i, "bizid": req["bizid"], "error": str(e)})
        if i % 100 == 0:
            log(f"row {row}: 历史进度 {i}/{len(hist)} (成功 {hist_ok})")
        time.sleep(HIST_SPACING)
    log(f"row {row}: 历史 {len(hist)} 笔完成，成功 {hist_ok}，等待指标窗口物化 {SETTLE}s ...")
    time.sleep(SETTLE)  # 让实时指标窗口摄取/聚合稳定后再发当前笔

    try:
        cur_resp = post(cur_ep, cur_req)
    except Exception as e:
        cur_resp = {"success": False, "error": str(e)}
    (rd / "responses" / "current.json").write_text(
        json.dumps(cur_resp, ensure_ascii=False), encoding="utf-8")
    json.dump(sent, open(rd / "sent.json", "w"), ensure_ascii=False, indent=1)
    json.dump({"history": [r for _, r in hist], "current": cur_req},
              open(rd / "sent_requests.json", "w"), ensure_ascii=False, indent=1)

    # ---- 五态分类(调用技能原生 classifier) ----
    archive = {"rule_code": d["rule_code"], "target_rule_set_code": d["target_rule_set_code"],
               "case_type": d["case_type"], "current_response": cur_resp,
               "http_status": 200 if cur_resp.get("success") is True else 599}
    aj = rd / "classify_archive.json"
    json.dump(archive, open(aj, "w"), ensure_ascii=False)
    try:
        cls = json.loads(subprocess.check_output(
            ["node", CLASSIFY, str(aj)], timeout=30).decode())
    except Exception as e:
        cls = {"status": "执行阻塞", "evidence": [f"classifier error: {e}"]}

    # ---- 指标三段式证据 ----
    metric_ev = []
    for m in pm.get("预期指标", []):
        actual = find_metric(cur_resp, m["name"])
        metric_ev.append({"name": m["name"], "operator": m["operator"], "value": m["value"],
                          "actual": actual,
                          "satisfied": cmp_op(actual, m["operator"], m["value"])})

    result = {"row": int(row), "rule_code": d["rule_code"], "target_rule_set": d["target_rule_set_code"],
              "case_type": d["case_type"], "strategy_code": pm.get("策略编码"),
              "new_token": new_tok, "old_token": d.get("runId"), "rebase_offset": str(offset),
              "current_biztime": cur_req["biztime"],
              "history_sent": len(hist), "history_success": hist_ok,
              "current_success": cur_resp.get("success"),
              "classification": cls, "metric_evidence": metric_ev,
              "current_response_summary": {
                  "policyVersion": (cur_resp.get("data") or {}).get("policyVersion"),
                  "finalDecision": (cur_resp.get("data") or {}).get("finalDecisionName"),
              },
              "complete": True, "finishedAt": datetime.datetime.now().isoformat()}
    json.dump(result, open(rj, "w"), ensure_ascii=False, indent=1)
    log(f"row {row} [{d['rule_code']} {d['case_type']}]: 五态={cls.get('status')} "
        f"hit={cls.get('target_rule_hit')} 指标满足={sum(1 for x in metric_ev if x['satisfied'])}/{len(metric_ev)}")
    return result

def main():
    results = []
    for row, g, longcase, dmap in CASES:
        files = glob.glob(f"{CK}/{g}")
        if not files:
            log(f"row {row}: 未找到 checkpoint {g}")
            continue
        results.append(run_case(row, files[0], longcase, dmap))
    # 汇总
    counts = {}
    for r in results:
        s = r.get("classification", {}).get("status", "?")
        counts[s] = counts.get(s, 0) + 1
    summary = {"run_namespace": NEW_NS, "total": len(results), "counts": counts,
               "cases": [{ "row": r["row"], "rule": r.get("rule_code"), "case_type": r.get("case_type"),
                           "status": r.get("classification", {}).get("status"),
                           "target_hit": r.get("classification", {}).get("target_rule_hit"),
                           "metrics_satisfied": f"{sum(1 for x in r.get('metric_evidence',[]) if x['satisfied'])}/{len(r.get('metric_evidence',[]))}",
                           } for r in results]}
    json.dump(summary, open(RUN / "rerun_summary.json", "w"), ensure_ascii=False, indent=1)
    log("==== 汇总 ====")
    log(json.dumps(summary, ensure_ascii=False))
    log(f"归档目录: {RUN}")

if __name__ == "__main__":
    main()
