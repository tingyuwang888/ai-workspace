#!/usr/bin/env python3
"""图 1：带指标的策略测试执行链路（垂直时序 + 右侧证据栏）v2 修正布局"""
from PIL import Image, ImageDraw, ImageFont

W, H = 2000, 1500
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
F_NODE  = font(22, 1)
F_SUB   = font(18, 0)
F_LBL   = font(16, 0)
F_BADGE = font(17, 1)
F_NOTE  = font(17, 0)

C_BORDER   = "#1A5276"
C_LANE_A   = "#E3F2FD"
C_LANE_B   = "#FFF3E0"
C_METRIC   = "#FF9800"
C_METRIC_L = "#FFE0B2"
C_TEXT     = "#212121"
C_ARROW    = "#1A5276"
C_DASH     = "#7B1FA2"
C_FEED     = "#00695C"

d.text((W//2, 40), "图 1  带指标的策略测试执行链路", font=F_TITLE, fill=C_TEXT, anchor="mm")
d.text((W//2, 76), "指标值三段式验证：历史贡献 + 当前笔贡献 = 最终算术值", font=F_SUB, fill="#546E7A", anchor="mm")

NODE_X = 420
NODE_W = 440
NODE_H = 80
NODE_Y0 = 150
NODE_GAP = 112

nodes = [
    ("1", "Fixture 准备", "MySQL 插入历史事件 N 条 + 当前笔 1 条", "test"),
    ("2", "提交测试请求", "POST /noah/policyTest，绑定 caseKey", "test"),
    ("3", "字段解析", "系统/动态/对象/枚举字段加载", "plat"),
    ("4", "外部数据查询", ".ds 数据源 + ETL 前置/后置/分页", "plat"),
    ("5", "函数计算", ".fun 节点执行，输入字段绑定", "plat"),
    ("6", "指标计算（重点）", ".zb 触发：窗口内历史事件 + 当前笔", "metric"),
    ("7", "规则集执行", ".rss 引用指标值做条件判断", "plat"),
    ("8", "决策流分支路由", ".pls 路由到通过/拒绝/人工审核", "plat"),
    ("9", "接口服务返回", "serviceConfig 映射出参", "plat"),
    ("10", "五态判定", "governance.py classify 逐层比对", "test"),
]

# 泳道分组（badge 画在每组首节点上方，不压框）
lanes = [
    (0, 2, "测试侧", "#1565C0"),
    (3, 8, "平台内部", "#E65100"),
    (9, 9, "测试侧", "#1565C0"),
]

def node_y(i):
    return NODE_Y0 + i * NODE_GAP

def draw_node(i, num, title, sub, kind):
    y = node_y(i)
    x0, y0 = NODE_X - NODE_W//2, y
    x1, y1 = NODE_X + NODE_W//2, y + NODE_H
    if kind == "metric":
        d.rounded_rectangle([x0-4, y0-4, x1+4, y1+4], radius=14, outline=C_METRIC, width=4)
        d.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=C_METRIC_L, outline=C_METRIC, width=3)
    elif kind == "test":
        d.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=C_LANE_A, outline=C_BORDER, width=2)
    else:
        d.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=C_LANE_B, outline=C_BORDER, width=2)
    cx, cy = x0 + 30, y0 + NODE_H//2
    d.ellipse([cx-17, cy-17, cx+17, cy+17], fill=C_BORDER, outline=C_BORDER)
    d.text((cx, cy), num, font=F_NODE, fill="white", anchor="mm")
    d.text((x0 + 60, y0 + 20), title, font=F_NODE, fill=C_TEXT, anchor="lm")
    d.text((x0 + 60, y0 + 52), sub, font=F_SUB, fill="#455A64", anchor="lm")

for i, (num, title, sub, kind) in enumerate(nodes):
    draw_node(i, num, title, sub, kind)

# 泳道 badge（水平，画在该组首节点左上方外侧）
for a, b, name, color in lanes:
    y = node_y(a)
    bx = NODE_X - NODE_W//2
    d.rounded_rectangle([bx, y-34, bx+92, y-8], radius=6, fill=color, outline=color)
    d.text((bx+46, y-21), name, font=F_BADGE, fill="white", anchor="mm")

# 主时序垂直箭头
for i in range(len(nodes)-1):
    y_from = node_y(i) + NODE_H
    y_to   = node_y(i+1)
    d.line([(NODE_X, y_from), (NODE_X, y_to-8)], fill=C_ARROW, width=3)
    d.polygon([(NODE_X-8, y_to-8), (NODE_X+8, y_to-8), (NODE_X, y_to)], fill=C_ARROW)

# 历史事件先于当前事件：节点1 → 节点6，左侧 L 形虚线
XL = NODE_X - NODE_W//2 - 70
y1 = node_y(0) + NODE_H//2
y6 = node_y(5) + NODE_H//2
d.line([(NODE_X - NODE_W//2, y1), (XL, y1)], fill=C_DASH, width=2)
yy = y1
while yy < y6:
    d.line([(XL, yy), (XL, min(yy+12, y6))], fill=C_DASH, width=2)
    yy += 22
d.line([(XL, y6), (NODE_X - NODE_W//2 - 10, y6)], fill=C_DASH, width=2)
d.polygon([(NODE_X-NODE_W//2-10, y6-6), (NODE_X-NODE_W//2-10, y6+6), (NODE_X-NODE_W//2-2, y6)], fill=C_DASH)
label = "历史事件先于当前事件"
for k, ch in enumerate(label):
    d.text((XL - 12, y1 + 30 + k*20), ch, font=F_LBL, fill=C_DASH, anchor="rm")

# 节点6 → 节点7 加粗（指标值作为规则条件入参）
y6b = node_y(5) + NODE_H
y7t = node_y(6)
d.line([(NODE_X, y6b), (NODE_X, y7t-10)], fill=C_METRIC, width=6)
d.polygon([(NODE_X-10, y7t-10), (NODE_X+10, y7t-10), (NODE_X, y7t)], fill=C_METRIC)
d.text((NODE_X + 22, (y6b+y7t)//2), "指标值 → 规则条件入参", font=F_LBL, fill=C_METRIC, anchor="lm")

# 右侧证据栏
EV_X = 1380
EV_W = 460
EV_H = 92
evidences = [
    ("设计层证据", ["design-manifest.json：预期算术 / 边界极性 / 覆盖分支"], "#BBDEFB", 0),
    ("Fixture 层证据", ["历史事件表 + 当前笔表 + 隔离键"], "#C8E6C9", 1),
    ("请求层证据", ["序列化 HTTP 请求 + CSRF / session"], "#FFF9C4", 2),
    ("指标层证据（重点）", ["历史贡献 + 当前笔贡献 + 最终算术值 三段式", "窗口 / 去重键 / 时区 / 过滤条件"], "#FFCC80", 5),
    ("规则层证据", ["目标规则命中 + fieldValues / absentFields 精确断言"], "#FFAB91", 6),
    ("治理层证据", ["五态分类 + 根因归属 + caseKey"], "#E1BEE7", 9),
]
d.text((EV_X, node_y(0) - 40), "证据链（逐层核对）", font=F_NODE, fill=C_BORDER, anchor="mm")
for name, subs, color, node_idx in evidences:
    y = node_y(node_idx) + NODE_H//2 - EV_H//2
    x0, y0, x1, y1 = EV_X - EV_W//2, y, EV_X + EV_W//2, y + EV_H
    is_metric = "指标层" in name
    d.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=color,
                        outline=C_METRIC if is_metric else C_BORDER,
                        width=3 if is_metric else 2)
    d.text((x0 + 20, y0 + 20), name, font=F_NODE, fill=C_TEXT, anchor="lm")
    for k, ln in enumerate(subs):
        d.text((x0 + 20, y0 + 50 + k*20), ln, font=F_LBL, fill="#37474F", anchor="lm")
    nx = NODE_X + NODE_W//2
    ny = node_y(node_idx) + NODE_H//2
    d.line([(nx, ny), (x0 - 10, y0 + EV_H//2)], fill=C_BORDER, width=2)
    d.polygon([(x0-10, y0+EV_H//2-6), (x0-10, y0+EV_H//2+6), (x0-2, y0+EV_H//2)], fill=C_BORDER)

# 反馈回环：节点10 底部 → 下 → 左 → 上 → 节点1 左侧（L 形外圈虚线，走底部留白区）
FB_Y = node_y(9) + NODE_H + 60
FB_X = 60
y10b = node_y(9) + NODE_H
def dash_v(x, y_from, y_to, step=12, gap=10):
    yy = y_from
    while yy > y_to:
        d.line([(x, yy), (x, max(yy-step, y_to))], fill=C_FEED, width=2)
        yy -= (step+gap)
def dash_h(y, x_from, x_to, step=12, gap=10):
    xx = x_from
    while xx > x_to:
        d.line([(xx, y), (max(xx-step, x_to), y)], fill=C_FEED, width=2)
        xx -= (step+gap)
d.line([(NODE_X, y10b), (NODE_X, FB_Y)], fill=C_FEED, width=2)
dash_h(FB_Y, NODE_X, FB_X)
dash_v(FB_X, FB_Y, y1)
d.line([(FB_X, y1), (NODE_X - NODE_W//2 - 10, y1)], fill=C_FEED, width=2)
d.polygon([(NODE_X-NODE_W//2-10, y1-6), (NODE_X-NODE_W//2-10, y1+6), (NODE_X-NODE_W//2-2, y1)], fill=C_FEED)
d.text((FB_X + 12, FB_Y - 14), "失败 → caseKey 最小重跑，新 fixtureRunId", font=F_LBL, fill=C_FEED, anchor="lm")

# 底部边界说明条
BAR_Y = H - 80
d.rectangle([60, BAR_Y, W-60, BAR_Y+56], fill="#ECEFF1", outline="#90A4AE", width=1)
d.text((80, BAR_Y+14), "边界：指标验证嵌在策略执行链路中，不覆盖独立 .zb 回归（无策略包裹）、", font=F_NOTE, fill="#37474F", anchor="lm")
d.text((80, BAR_Y+36), "指标计算 API 直测（无 /salaxy/metricApi 入口）、指标性能 / 并发（无压测能力）。", font=F_NOTE, fill="#37474F", anchor="lm")

out = "/Users/td/.qoderwork/workspace/mttrqawk3qp6mzcs/tiance_metric_policy_flow.png"
img.save(out, "PNG", optimize=True)
print(f"saved: {out} size={img.size}")
