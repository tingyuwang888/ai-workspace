#!/usr/bin/env python3
"""HLB 指标用例重放：SKR4_0821_R53 row53 正案例 → 新隔离键 QWR1_0910_R53，时间 rebasing 到当前，三段式比对"""
import json, time, urllib.request, datetime, pathlib, sys

R2 = "/Users/td/outputs/HLB_Acquiring_Skill全流程最小重跑_20260820_R2"
CK = f"{R2}/checkpoints/SKR4_0821_R53_53_ACQ_RS3_000016_正案例_confirmed-metric-alignment.json"
RUN_ID = "QWR1_0910_R53"
OLD_TOKEN = "SKR4_0821_R53"
TS = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
OUT = pathlib.Path(f"/Users/td/.qoderwork/workspace/mttrqawk3qp6mzcs/hlb-metric-replay-{TS}")
(OUT / "responses").mkdir(parents=True, exist_ok=True)

ck = json.load(open(CK))
ahr = ck["actual_history_requests"]
cur = json.loads(json.dumps(ck["actual_current_request"]))
OLD_CURRENT_DT = datetime.datetime.strptime(cur["biztime"], "%Y-%m-%d %H:%M:%S")
OFFSET = datetime.datetime.now().replace(microsecond=0) - OLD_CURRENT_DT

def rebase(req):
    s = json.dumps(req, ensure_ascii=False).replace(OLD_TOKEN, RUN_ID)
    r = json.loads(s)
    dt = datetime.datetime.strptime(r["biztime"], "%Y-%m-%d %H:%M:%S") + OFFSET
    r["biztime"] = dt.strftime("%Y-%m-%d %H:%M:%S")
    r["transactiondate"] = dt.strftime("%Y-%m-%d")
    r["transactiontime"] = dt.strftime("%H:%M:%S")
    return r

def post(endpoint, payload):
    req = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def walk_find(obj, key_pred, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if key_pred(k): out.append((k, v))
            walk_find(v, key_pred, out)
    elif isinstance(obj, list):
        for v in obj: walk_find(v, key_pred, out)

sent = []
print(f"== 重放开始 runId={RUN_ID} offset={OFFSET} ==")
for i, item in enumerate(ahr, 1):
    payload = rebase(item["request"])
    resp = post(item["endpoint"], payload)
    sent.append({"stage": f"history_{i:02d}", "bizid": payload.get("bizid"), "biztime": payload.get("biztime"),
                 "success": resp.get("success"), "code": resp.get("code")})
    (OUT / "responses" / f"history_{i:02d}.json").write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.15)
hist_ok = all(s["success"] for s in sent)
print(f"历史 23 笔提交完成，全部 success={hist_ok}")

cur_payload = rebase(cur)
cur_resp = post(ck["actual_history_requests"][0]["endpoint"], cur_payload)
(OUT / "responses" / "current.json").write_text(json.dumps(cur_resp, ensure_ascii=False), encoding="utf-8")
sent.append({"stage": "current", "bizid": cur_payload.get("bizid"), "biztime": cur_payload.get("biztime"),
             "success": cur_resp.get("success"), "code": cur_resp.get("code")})
(OUT / "sent_requests.json").write_text(json.dumps(sent, ensure_ascii=False, indent=1), encoding="utf-8")

# 指标实际值：响应 mingFields
metrics_found = {}
pairs = []
walk_find(cur_resp, lambda k: isinstance(k, str) and k.startswith("salaxyzb_m_"), pairs)
for k, v in pairs:
    metrics_found.setdefault(k, v)
TARGET = ["salaxyzb_m_cardno_distinct_5m", "salaxyzb_m_consume_cnt_5m", "salaxyzb_m_decline_cnt_5m"]
actual = {t: metrics_found.get(t) for t in TARGET}

# 目标规则命中
hits = []
walk_find(cur_resp, lambda k: k in ("hitRules", "ruleSetResults", "executedRuleSets"), hits)
resp_s = json.dumps(cur_resp, ensure_ascii=False)
target_hit = None
import re
m = re.search(r'ACQ_RS3_000016[^}]{0,200}?"hit"\s*:\s*(true|false)', resp_s)
if m: target_hit = m.group(1) == "true"
else:
    target_hit = resp_s.count("ACQ_RS3_000016") > 0 and '"hit": true' in resp_s or None

# 三段式比对：历史贡献(15,15,8) + 当前笔贡献(1,1,0) = 预期最终(16,16,8)
HIST_CONTRIB = {TARGET[0]: 15, TARGET[1]: 15, TARGET[2]: 8}
CUR_CONTRIB  = {TARGET[0]: 1,  TARGET[1]: 1,  TARGET[2]: 0}
expected_final = {t: HIST_CONTRIB[t] + CUR_CONTRIB[t] for t in TARGET}
thresholds = {TARGET[0]: 15, TARGET[1]: 15, TARGET[2]: 8}

comparison = []
for t in TARGET:
    a = actual.get(t)
    comparison.append({
        "metric": t,
        "历史贡献": HIST_CONTRIB[t], "当前笔贡献": CUR_CONTRIB[t], "预期最终": expected_final[t],
        "实际": a, "阈值>=": thresholds[t],
        "算术一致": a == expected_final[t], "阈值满足": (a is not None and a >= thresholds[t]),
    })
arith_ok = all(c["算术一致"] for c in comparison)
thresh_ok = all(c["阈值满足"] for c in comparison)

if target_hit and thresh_ok and arith_ok and cur_resp.get("success"):
    verdict, reason = "通过", "目标规则命中且三指标三段式算术与阈值全部一致"
elif cur_resp.get("success") is not True:
    verdict, reason = "执行阻塞", "当前笔响应 success!=true"
elif target_hit is None or target_hit is False:
    verdict, reason = "执行阻塞" if target_hit is None else "失败", "目标规则命中证据缺失或未命中"
else:
    verdict, reason = "失败", "指标三段式或阈值不一致"

result = {"runId": RUN_ID, "source_checkpoint": CK, "rebase_offset": str(OFFSET),
          "history_success": hist_ok, "current_success": cur_resp.get("success"),
          "target_rule": "ACQ_RS3_000016", "target_hit": target_hit,
          "comparison": comparison, "verdict": verdict, "reason": reason,
          "finishedAt": datetime.datetime.now().isoformat()}
(OUT / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1))
print("归档:", OUT)
