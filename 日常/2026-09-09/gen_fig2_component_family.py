#!/usr/bin/env python3
"""图 2：天策测试组件族工作流（四层泳道：支撑/生成/执行/治理闭环）"""
from PIL import Image, ImageDraw, ImageFont

W, H = 2400, 1120
BG = "#FFFFFF"
FONT_PATH = "/System/Library/Fonts/PingFang.ttc"
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

def font(size, idx=0):
    try:
        return ImageFont.truetype(FONT_PATH, size, index=idx)
    except Exception:
        return ImageFont.load_default()

F_TITLE = font(34, 1)
F_SUB   = font(18, 0)
F_LANE  = font(22, 1)
F_BOX   = font(19, 1)
F_BOXS  = font(15, 0)
F_CIRC  = font(24, 1)
F_LBL   = font(16, 0)

C_TEXT  = "#212121"
C_ARROW = "#1A5276"
C_DASH  = "#00695C"

LANE_SUP  = "#ECEFF1"
LANE_GEN  = "#E3F2FD"
LANE_EXEC = "#E8F5E9"
LANE_GOV  = "#FFF3E0"

d.text((W//2, 40), "图 2  天策测试组件族工作流（生成 → 执行 → 治理闭环）", font=F_TITLE, fill=C_TEXT, anchor="mm")
d.text((W//2, 76), "12 个 skill 分四层：支撑层提供元数据与生命周期，生成层产出 8 类组件，执行层完成测试，治理闭环 A-H 串联全部阶段", font=F_SUB, fill="#546E7A", anchor="mm")

def lane_band(y0, y1, color, label):
    d.rectangle([40, y0, W-40, y1], fill=color, outline=None)
    d.text((60, y0+14), label, font=F_LANE, fill="#37474F", anchor="lm")

def box(cx, cy, w, h, title, sub, outline="#1A5276", fill="#FFFFFF"):
    x0, y0, x1, y1 = cx-w//2, cy-h//2, cx+w//2, cy+h//2
    d.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=fill, outline=outline, width=2)
    d.text((cx, cy-12), title, font=F_BOX, fill=C_TEXT, anchor="mm")
    if sub:
        d.text((cx, cy+16), sub, font=F_BOXS, fill="#455A64", anchor="mm")

def varrow(x, y_from, y_to, color=C_ARROW, width=3, head=9):
    d.line([(x, y_from), (x, y_to-head)], fill=color, width=width)
    d.polygon([(x-head, y_to-head), (x+head, y_to-head), (x, y_to)], fill=color)

def harrow(x_from, x_to, y, color=C_ARROW, width=3, head=8):
    d.line([(x_from, y), (x_to-head, y)], fill=color, width=width)
    d.polygon([(x_to-head, y-head), (x_to-head, y+head), (x_to, y)], fill=color)

# ---- Lane 1 支撑层 ----
L1_Y = 170
lane_band(110, 230, LANE_SUP, "支撑层")
box(900,  L1_Y, 520, 76, "tiance-metadata-scout", "元数据缓存：字段/规则/策略/函数/数据源/合同")
box(1560, L1_Y, 520, 76, "tiance-component-lifecycle", "组件导入/上线/下线/删除 全生命周期总调度")

# ---- Lane 2 生成层 ----
L2_Y = 380
lane_band(290, 470, LANE_GEN, "生成层（8 类组件）")
gen = [
    ("field-forge", "字段 .xls"),
    ("datasource-forge", "外部数据 .ds"),
    ("etl-forge", "ETL .etl"),
    ("function-forge", "函数 .fun"),
    ("realtime-metric-forge", "指标 .zb"),
    ("rule-forge", "规则集 .rss"),
    ("policy-forge", "策略 .pls"),
    ("service-config-forge", "接口服务 CSV"),
]
gw, gg = 262, 26
total = 8*gw + 7*gg
x0 = (W - total)//2
gen_centers = []
for i, (name, sub) in enumerate(gen):
    cx = x0 + i*(gw+gg) + gw//2
    gen_centers.append(cx)
    box(cx, L2_Y, gw, 84, name, sub, outline="#1565C0", fill="#FFFFFF")

# ---- Lane 3 执行层 ----
L3_Y = 590
lane_band(500, 680, LANE_EXEC, "执行层（4 个 metric-*）")
exe = [
    ("testcase-generator", "用例设计 + 覆盖门禁"),
    ("policy-test", "平台执行 + Fixture + 证据"),
    ("report-checker", "报告审计 4 维度"),
    ("agent-loop", "治理闭环编排 A-H"),
]
ew, eg = 460, 60
total_e = 4*ew + 3*eg
xe0 = (W - total_e)//2
exe_centers = []
for i, (name, sub) in enumerate(exe):
    cx = xe0 + i*(ew+eg) + ew//2
    exe_centers.append(cx)
    box(cx, L3_Y, ew, 84, "tiance-metric-" + name, sub, outline="#2E7D32", fill="#FFFFFF")

# ---- Lane 4 治理闭环 ----
L4_Y = 830
lane_band(740, 980, LANE_GOV, "治理闭环（A-H 八阶段）")
stages = ["A 范围备份", "B 设计门禁", "C 平台门禁", "D Fixture", "E 逐笔执行", "F 五态复核", "G 报告审计", "H 完成重跑"]
n = len(stages)
span = 2100
sx0 = (W - span)//2
step = span // (n-1)
circ_r = 52
centers = [sx0 + i*step for i in range(n)]
for i, (cx, name) in enumerate(zip(centers, stages)):
    d.ellipse([cx-circ_r, L4_Y-circ_r, cx+circ_r, L4_Y+circ_r], fill="#FFFFFF", outline="#E65100", width=3)
    d.text((cx, L4_Y), name.split()[0], font=F_CIRC, fill="#E65100", anchor="mm")
    d.text((cx, L4_Y + circ_r + 26), name.split()[1], font=F_LBL, fill="#37474F", anchor="mm")
    if i < n-1:
        harrow(cx+circ_r, centers[i+1]-circ_r, L4_Y, color="#E65100", width=3)

# H → B 反馈虚线（下方 L 形）
FB_Y = L4_Y + circ_r + 70
hx, bx = centers[7], centers[1]
d.line([(hx, L4_Y+circ_r), (hx, FB_Y)], fill=C_DASH, width=2)
xx = hx
while xx > bx:
    d.line([(xx, FB_Y), (max(xx-12, bx), FB_Y)], fill=C_DASH, width=2)
    xx -= 22
d.line([(bx, FB_Y), (bx, L4_Y+circ_r+8)], fill=C_DASH, width=2)
d.polygon([(bx-6, L4_Y+circ_r+8), (bx+6, L4_Y+circ_r+8), (bx, L4_Y+circ_r)], fill=C_DASH)
d.text(((hx+bx)//2, FB_Y - 12), "失败 → caseKey 最小重跑（B 阶段重新设计受影响用例）", font=F_LBL, fill=C_DASH, anchor="mm")

# ---- 层间连接 ----
varrow(W//2, 230, 290, width=4)
d.text((W//2 + 16, 260), "元数据下发", font=F_LBL, fill=C_ARROW, anchor="lm")
varrow(W//2, 470, 500, width=4)
d.text((W//2 + 16, 485), "组件产出物汇入测试", font=F_LBL, fill=C_ARROW, anchor="lm")
# 执行层 ↔ 治理闭环 双向
varrow(W//2 - 40, 680, 740, width=3)
varrow(W//2 + 40, 740, 680, width=3)
d.polygon([(W//2+40-8, 688), (W//2+40+8, 688), (W//2+40, 680)], fill=C_ARROW)
d.text((W//2 + 70, 710), "skill 承担阶段责任", font=F_LBL, fill=C_ARROW, anchor="lm")

# 执行层内部串联箭头（generator → policy-test → report-checker → agent-loop）
for i in range(3):
    harrow(exe_centers[i]+ew//2, exe_centers[i+1]-ew//2, L3_Y, color="#2E7D32", width=3)

# (生成层到执行层的汇入由层间主箭头表达，不再画悬空短线)

# 底部说明
BAR_Y = H - 90
d.rectangle([60, BAR_Y, W-60, BAR_Y+56], fill="#ECEFF1", outline="#90A4AE", width=1)
d.text((80, BAR_Y+14), "说明：支撑层为生成层与执行层提供元数据与组件生命周期；生成层 8 类组件产出物是执行层的测试对象；", font=F_LBL, fill="#37474F", anchor="lm")
d.text((80, BAR_Y+36), "执行层 4 个 skill 由 agent-loop 按 A-H 八阶段编排，所有产物通过 caseKey 串联，失败走最小重跑而非全量。", font=F_LBL, fill="#37474F", anchor="lm")

out = "/Users/td/.qoderwork/workspace/mttrqawk3qp6mzcs/tiance_component_family.png"
img.save(out, "PNG", optimize=True)
print(f"saved: {out} size={img.size}")
