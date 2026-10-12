#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成第三案交底书 8 张附图(SVG)并用 Playwright(Chromium) 渲染为 PNG。"""
import os, html
OUT = "/tmp/figs"
os.makedirs(OUT, exist_ok=True)

FONT = "'PingFang SC','Heiti SC','Microsoft YaHei',sans-serif"

def esc(s): return html.escape(s, quote=True)

class SVG:
    def __init__(self, w, h):
        self.w, self.h = w, h; self.parts = []
    def rect(self, x, y, w, h, lines, fill="#eef4ff", stroke="#3b6fb5", fs=15, sw=1.6,
             rx=8, tc="#12314f", bold_first=False):
        fill, stroke, tc, rx = "#ffffff", "#000000", "#000000", 0
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        lines = lines if isinstance(lines, list) else [lines]
        lh = fs * 1.35
        total = len(lines) * lh
        ty = y + h/2 - total/2 + lh/2 - fs*0.15
        for i, ln in enumerate(lines):
            fw = 700 if (bold_first and i == 0) else 400
            self.parts.append(
                f'<text x="{x+w/2}" y="{ty+i*lh}" font-family="{FONT}" font-size="{fs}" '
                f'font-weight="{fw}" fill="{tc}" text-anchor="middle">{esc(ln)}</text>')
    def box(self, x, y, w, h, label, fill="#eef4ff", stroke="#3b6fb5", sw=1.6, rx=8, fs=16, tc="#12314f"):
        """容器框：标题置顶左对齐，避免被子元素遮挡。"""
        fill, stroke, tc, rx = "#ffffff", "#000000", "#000000", 0
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')
        self.text(x+14, y+26, label, fs, tc, "start", bold=True)
    def text(self, x, y, s, fs=15, tc="#333", anchor="start", bold=False):
        tc = "#000000"
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{fs}" '
            f'font-weight="{700 if bold else 400}" fill="{tc}" text-anchor="{anchor}">{esc(s)}</text>')
    def arrow(self, x1, y1, x2, y2, label=None, color="#555", dashed=False, lfs=13,
              lx=None, ly=None):
        color = "#000000"
        dash = ' stroke-dasharray="6 5"' if dashed else ''
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="1.8"{dash} marker-end="url(#ah)"/>')
        if label:
            lx = lx if lx is not None else (x1+x2)/2
            ly = ly if ly is not None else (y1+y2)/2 - 6
            self.parts.append(
                f'<rect x="{lx-len(label)*lfs*0.32-4}" y="{ly-lfs}" width="{len(label)*lfs*0.64+8}" '
                f'height="{lfs*1.5}" fill="#ffffff" opacity="1"/>')
            self.parts.append(
                f'<text x="{lx}" y="{ly}" font-family="{FONT}" font-size="{lfs}" fill="{color}" '
                f'text-anchor="middle">{esc(label)}</text>')
    def save(self, name):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}">'
                f'<defs><marker id="ah" markerWidth="10" markerHeight="10" refX="8" refY="3" '
                f'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L8,3 L0,6 Z" fill="#000000"/>'
                f'</marker></defs><rect width="{self.w}" height="{self.h}" fill="#ffffff"/>')
        with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8") as f:
            f.write(head + "".join(self.parts) + "</svg>")

# ---------- 图1 系统三层架构 ----------
s = SVG(960, 640)
s.text(30, 40, "图1  系统三层架构与处理链路", 20, "#12314f", bold=True)
s.box(30, 60, 900, 120, "采集层（面向多控制面的采集器）", "#eafaf0", "#2e9e5b", fs=17)
cols = ["编排\n采集器","配置中心\n采集器","镜像内置\n采集器","代理入口\n采集器","持久层\n采集器","镜像仓库\n采集器","外部清单\n采集器"]
for i,c in enumerate(cols):
    x = 45 + i*128
    s.rect(x, 105, 118, 62, c.split("\n"), "#ffffff", "#2e9e5b", 13)
s.arrow(480, 180, 480, 210)
s.box(30, 210, 900, 210, "引用分析层（核心）", "#eef4ff", "#3b6fb5", fs=17)
sub = ["目标实体规范化\n与引用解析","环境标签\n推导与归一","跨控制面\n引用图构建","污染边识别\n(四态+白名单)","静态/运行态\n语义冲突比对","转换后\n全量污染复检"]
for i,c in enumerate(sub):
    x = 45 + i*148
    s.rect(x, 258, 138, 60, c.split("\n"), "#ffffff", "#3b6fb5", 13)
s.rect(45, 335, 870, 60, ["统一环境引用记录（字段：源资源·源控制面·引用字段·ref_type·声明目标/观测目标·resolved标签·tag_conflict·runtime_status·来源证据）"],
       "#f5f9ff", "#8fb3d9", 13)
s.arrow(480, 420, 480, 450)
s.box(30, 450, 900, 120, "门禁与执行层", "#fff3ea", "#d97a2b", fs=17)
sub2 = ["部署前门禁\n(阻断/告警/未知)","类型化引用\n转换","断点续扫\n(配置项粒度)","关联闭包\n局部回滚(SCC)","运行证据\n回采复验"]
for i,c in enumerate(sub2):
    x = 60 + i*176
    s.rect(x, 498, 166, 58, c.split("\n"), "#ffffff", "#d97a2b", 13)
s.text(30, 610, "链路：采集 → 统一记录 → 实体规范化/标签归一 → 引用图 → 污染识别+语义冲突 → 门禁 → 类型化转换+全量污染复检 → 回采确认 → 必要时局部回滚", 13, "#555")
s.save("fig1")

# ---------- 图2 统一环境引用记录与引用图 ----------
s = SVG(960, 640)
s.text(30, 40, "图2  统一环境引用记录与跨控制面引用图结构", 20, "#12314f", bold=True)
s.box(30, 70, 330, 550, "统一环境引用记录", "#eef4ff", "#3b6fb5", fs=16)
fields = ["resource_id","source_control_plane","ref_field","ref_type","declared_target_ref","declared_target_entity","observed_target_ref（可空）","observed_target_entity（可空）","target_version / target_digest","runtime_status（非引用目标）","declared_env_tag","observed_env_tags（可空）","resolved_env_tag","resolution_source","tag_conflict","scan_id","collected_at","resource_version","valid_until","evidence_source"]
for i,f in enumerate(fields):
    s.text(46, 110+i*25, "· "+f, 12.5, "#12314f")
# graph
s.box(400, 70, 530, 550, "跨控制面引用图（示例）", "#f7f7fb", "#8a8ab0", fs=16)
def node(x,y,w,h,lines,fill="#ffffff",stroke="#555"):
    s.rect(x,y,w,h,lines,fill,stroke,13)
node(430,120,150,55,["Deployment","bifrost@risk-prod"],"#eafaf0","#2e9e5b")
node(430,240,150,55,["镜像内置 Nginx","proxy_pass"],"#fff3ea","#d97a2b")
node(690,120,150,55,["Service","bifrost@risk-dev"],"#fdecec","#c0392b")
node(690,240,150,55,["Nacos 配置","datasource.url"],"#fff3ea","#d97a2b")
node(690,360,150,55,["数据库","risk_dev @ test"],"#fdecec","#c0392b")
node(430,360,150,55,["外部清单","节点角色"],"#eef4ff","#3b6fb5")
s.arrow(580,147,690,147,"引用", "#c0392b")
s.arrow(505,175,505,240,"uses","#2e9e5b")
s.arrow(580,267,690,267,"指向测试库","#c0392b")
s.arrow(505,295,505,360,"声明≠观测","#3b6fb5")
s.arrow(580,387,690,387,"调度/角色声明", "#3b6fb5")
s.rect(420,452,490,28,["边语义以线上文字标注：『引用/指向测试库』=污染边 · 『声明≠观测』=漂移 · 『uses』不判污染"],"#fdecec","#c0392b",11,rx=6)
s.rect(420,486,490,28,["runtime_status 单列，描述自身运行态，不参与引用语义比较"],"#f5f9ff","#8fb3d9",12,rx=6)
s.rect(420,520,490,28,["scan_id/valid_until 界定同窗可比对证据，过期观测转 warn"],"#f5f9ff","#8fb3d9",12,rx=6)
s.save("fig2")

# ---------- 图3 目标实体规范化与引用解析 ----------
s = SVG(960, 640)
s.text(30, 40, "图3  目标实体规范化与引用解析流程", 20, "#12314f", bold=True)
s.rect(40, 80, 200, 60, ["target_ref（原始引用串）"], "#eef4ff", "#3b6fb5", 15, bold_first=True)
s.arrow(240,110,300,110)
s.rect(300, 70, 200, 80, ["按 ref_type","分派解析器"], "#fff3ea", "#d97a2b", 15, bold_first=True)
types = ["Service FQDN","ClusterIP / NodePort","JDBC 连接串","镜像 tag/digest（摘要定版）","Nacos 服务名","镜像内置配置 embedded_config","代理路由 proxy_route"]
for i,t in enumerate(types):
    s.rect(560, 36+i*54, 210, 44, [t], "#ffffff", "#d97a2b", 12)
    s.arrow(500,110,560,58+i*54)
s.arrow(770, 200, 830, 200)
s.rect(830, 160, 110, 90, ["别名表","归一"], "#eafaf0", "#2e9e5b", 14, bold_first=True)
s.arrow(885, 250, 885, 300)
s.rect(785, 300, 155, 60, ["target_entity","（图内唯一实体）"], "#eef4ff", "#3b6fb5", 13, bold_first=True)
s.text(40, 615, "镜像类以不可变摘要 target_digest 定版；无摘要时以 target_version=tag 定版，避免不同版本被合并为同一实体", 12, "#555")
s.rect(40, 460, 420, 110, ["无法解析 → 悬挂引用（dangling）", "置 resolved_env_tag = unknown", "不判污染，交人工确认"], "#f5f5f5", "#999", 14, bold_first=False)
s.rect(500, 460, 420, 110, ["一对多命中 → 展开多条引用边", "多对一命中 → 合并节点", "保留各来源证据 evidence_source"], "#f5f5f5", "#999", 14)
s.arrow(380,150,380,460,"无法解析时回退", "#999")
s.save("fig3")

# ---------- 图4 环境标签推导与归一 ----------
s = SVG(960, 560)
s.text(30, 40, "图4  环境标签推导、归一优先级与冲突保留", 20, "#12314f", bold=True)
prio = ["① 人工映射表（显式声明，最高）","② Namespace 名称（risk-dev / risk-prod）","③ 节点标签（K8s node label 环境维度）","④ Nacos 实例 / 命名空间","⑤ Harbor 项目","⑥ 镜像标签 / 集群名 命名约定"]
for i,p in enumerate(prio):
    s.rect(40, 80+i*54, 470, 44, [p], "#eef4ff" if i==0 else "#ffffff", "#3b6fb5", 13)
    if i<len(prio)-1:
        s.arrow(275,124+i*54,275,134+i*54,"按序取高","#888")
s.rect(570, 80, 350, 70, ["特殊标签 shared / global","Harbor·统一认证·日志·公共Kafka·只读库·License"], "#eafaf0", "#2e9e5b", 12, bold_first=True)
s.rect(570, 170, 350, 60, ["全部来源不可得 → resolved = unknown","不判污染，进入未知态处理"], "#f5f5f5", "#999", 12)
s.rect(570, 250, 350, 90, ["多来源取值不一致 → tag_conflict = true","同时保留 declared_env_tag 与 observed_env_tags","不静默取舍，交冲突处理分支"], "#fff3ea", "#d97a2b", 12, bold_first=True)
s.rect(570, 360, 350, 70, ["输出 resolved_env_tag + resolution_source","供污染判定与残留复检使用"], "#fff3ea", "#d97a2b", 13, bold_first=True)
s.arrow(510,102,570,110); s.arrow(510,200,570,196); s.arrow(510,268,570,290); s.arrow(745,340,745,360)
s.save("fig4")

# ---------- 图5 污染边识别与四态判定（固定优先级·互斥） ----------
s = SVG(960, 690)
s.text(30, 38, "图5  污染边识别：固定优先级 BLOCK>UNKNOWN>WARN>ALLOW（先匹配先定性）", 17, "#12314f", bold=True)
s.rect(340, 58, 260, 40, ["遍历每条引用边"], "#eef4ff", "#3b6fb5", 14, bold_first=True)
s.arrow(470,98,470,124)
# R1
s.rect(300,124,340,44, ["resolved=unknown 且 属关键引用类型 ?"], "#ffffff","#c0392b",13)
s.arrow(640,146,720,146,"是", "#c0392b"); s.rect(720,124,200,44,["阻断 block（未知升级）"],"#fdecec","#c0392b",12,bold_first=True)
s.arrow(470,168,470,196,"否")
# R2
s.rect(300,196,340,44, ["resolved = unknown ?"], "#ffffff","#999",13)
s.arrow(640,218,720,218,"是", "#999"); s.rect(720,196,200,44,["未知 unknown（人工确认）"],"#f5f5f5","#999",12,bold_first=True)
s.arrow(470,240,470,268,"否")
# R3
s.rect(300,268,340,44, ["resolved ≠ 部署目标 且 非shared 且 未命中白名单 ?"], "#ffffff","#c0392b",12)
s.arrow(640,290,720,290,"是", "#c0392b"); s.rect(720,268,200,44,["阻断 block（污染边）"],"#fdecec","#c0392b",12,bold_first=True)
s.arrow(470,312,470,340,"否")
# R4
s.rect(300,340,340,48, ["resolved = 部署目标 且 证据存疑 ?", "(标签冲突/低置信/白名单临期/观测过期)"], "#ffffff","#d97a2b",12)
s.arrow(640,364,720,364,"是", "#d97a2b"); s.rect(720,340,200,48,["告警 warn（不阻断）"],"#fff3ea","#d97a2b",12,bold_first=True)
s.arrow(470,388,470,416,"否")
# R5
s.rect(300,416,340,44, ["resolved = 部署目标 或 shared/global 或 命中白名单 ?"], "#ffffff","#2e9e5b",12)
s.arrow(640,438,720,438,"是", "#2e9e5b"); s.rect(720,416,200,44,["允许 allow"],"#eafaf0","#2e9e5b",12,bold_first=True)
s.arrow(470,460,470,486,"否")
s.rect(360,486,220,40,["兜底 → 允许 allow"],"#eafaf0","#2e9e5b",12,bold_first=True)
s.rect(40,548,880,30,["关键：warn 仅在 resolved=部署目标 分支可达，与 block 互斥；tag_conflict 解析到错误环境仍按 R3 阻断。"],"#f5f9ff","#8fb3d9",12,rx=6)
s.text(30, 604, "关键引用类型：数据库 · 身份认证 · 核心服务调用 · 写操作目标（可配置）；命中者 unknown→block（宁误断勿漏断）。", 12, "#555")
s.text(30, 628, "多维白名单维度：源类型×目标类型 · 方向(读/写) · 环境对 · 引用字段 · 有效期 · 审批来源 —— 避免合法共享被误判。", 12, "#555")
s.text(30, 652, "待修复清单字段：源资源 · 引用字段 · 声明目标 · 观测目标 · resolved标签 · 是否命中白名单 · 来源证据。", 12, "#555")
s.save("fig5")

# ---------- 图6 静态/运行态语义比对与分级 ----------
s = SVG(960, 560)
s.text(30, 40, "图6  声明目标与观测目标的语义冲突比对与分级", 20, "#12314f", bold=True)
s.rect(40, 80, 250, 54, ["前置：同一 scan_id / 有效窗口内", "跨窗或超过 valid_until → 转 warn"], "#f5f9ff", "#8fb3d9", 12, bold_first=True)
s.rect(40, 158, 250, 54, ["declared_target（静态声明）","如 bifrost.risk-prod.svc.cluster.local"], "#eef4ff", "#3b6fb5", 11, bold_first=True)
s.rect(40, 232, 250, 54, ["observed_target（运行观测）","如 ClusterIP 10.96.23.18 / UID"], "#fff3ea", "#d97a2b", 11, bold_first=True)
s.arrow(290,185,360,190); s.arrow(290,259,360,215)
s.rect(360, 165, 180, 78, ["分别归一为","同一 target_entity","（别名表）"], "#eafaf0", "#2e9e5b", 12, bold_first=True)
s.arrow(540,204,610,204)
s.rect(610, 165, 120, 78, ["语义","比较"], "#eef4ff", "#3b6fb5", 13, bold_first=True)
s.arrow(730,185,800,150,"一致", "#2e9e5b"); s.rect(800,120,120,50,["通过"],"#eafaf0","#2e9e5b",13,bold_first=True)
s.arrow(730,225,790,250,"不一致", "#c0392b"); s.rect(790,240,150,44,["配置漂移冲突"],"#fdecec","#c0392b",12,bold_first=True)
s.arrow(865,284,865,320,"按关键性分级","#555")
s.rect(40, 320, 890, 120, ["冲突分级（供门禁判据）：",
       "· 阻断级：数据库 / 身份认证 / 核心服务调用 / 写操作目标 不一致",
       "· 阻断或告警（按配置）：节点角色 / 镜像摘要 / 实际运行形态 不一致",
       "· 告警级：文档描述 / 非关键监控地址 不一致 —— 独立于污染边，刻画“描述本身与现实不符”，与 tag_conflict 互证"],
       "#f5f9ff", "#8fb3d9", 13)
s.save("fig6")

# ---------- 图7 类型化转换—残留复验—断点续扫 ----------
s = SVG(960, 560)
s.text(30, 40, "图7  类型化引用转换—全量污染复检—断点续扫闭环", 20, "#12314f", bold=True)
s.rect(40, 90, 180, 56, ["命中 block 的引用边"], "#fdecec", "#c0392b", 14, bold_first=True)
s.arrow(220,118,280,118)
s.rect(280, 80, 240, 80, ["按 ref_type 调用结构化解析器","（非字符串替换）"], "#fff3ea", "#d97a2b", 13, bold_first=True)
tags = ["namespace","database","profile","image","embedded_config","proxy_route","service","node/cluster"]
for i,t in enumerate(tags):
    s.rect(560+(i%3)*130, 66+(i//3)*52, 120, 42, [t], "#ffffff", "#d97a2b", 11)
s.arrow(520,120,560,90)
s.arrow(760,160,820,180)
s.text(40, 340, "注：ConfigMap 覆盖镜像内置配置属 embedded_config / proxy_route 转换，不归入 image 类", 12, "#555")
s.rect(820, 170, 120, 60, ["记录转换前后","取值/解析器"], "#eef4ff", "#3b6fb5", 12, bold_first=True)
s.arrow(880,230,880,270)
s.rect(720, 270, 220, 56, ["重新采集→重建引用图→全量污染复检"], "#eafaf0", "#2e9e5b", 12, bold_first=True)
s.arrow(720,298,560,298,"污染边集合为空?","#2e9e5b")
s.rect(400, 270, 160, 56, ["是 → 放行"], "#eafaf0", "#2e9e5b", 14, bold_first=True)
s.arrow(480,270,480,226,"否：回到转换","#c0392b")
# resume box
s.box(40, 380, 880, 140, "断点续扫（配置项粒度）", "#f5f9ff", "#8fb3d9", fs=15)
s.text(60, 420, "每项状态：{ config_id, input_hash, transform_status, output_hash, verified }", 14, "#12314f")
s.text(60, 452, "处理前：检查 transform_status 与 input_hash（输入未变则跳过）", 14, "#12314f")
s.text(60, 484, "中断恢复后：仅对 非DONE 或 输入已变 的配置项继续执行 —— 不重复处理已完成项", 14, "#12314f")
s.save("fig7")

# ---------- 图8 门禁与关联闭包局部回滚 ----------
s = SVG(960, 520)
s.text(30, 40, "图8  部署前门禁与污染关联闭包局部回滚", 20, "#12314f", bold=True)
s.box(40, 80, 400, 180, "部署前门禁（拟实现，见原型）", "#fff3ea", "#d97a2b", fs=15)
s.text(60, 128, "触发阻断条件（任一）：", 14, "#12314f", bold=True)
s.text(70, 156, "· 存在 block 级污染边（含未知态按关键性升级）", 13, "#12314f")
s.text(70, 182, "· 存在阻断级配置漂移冲突", 14, "#12314f")
s.text(70, 208, "· 转换后全量污染复检残留非空", 14, "#12314f")
s.text(60, 238, "→ 阻断下发/启动，输出待修复清单（可选启用，否则仅告警）", 13, "#c0392b")
s.box(520, 80, 420, 180, "污染关联闭包局部回滚", "#eef4ff", "#3b6fb5", fs=15)
s.text(540, 128, "① 起点：污染边的源端资源", 14, "#12314f")
s.text(540, 152, "② 范围：仅在参与污染传播的边(references/routes_to/", 12, "#12314f")
s.text(555, 170, "stores_in/registered_with)上反向可达；uses 共享边不扩张", 12, "#12314f")
s.text(540, 192, "③ 约束：与 本次变更集 求交集", 13, "#12314f")
s.text(540, 214, "④ 前提：存在变更前可恢复快照（否则转人工）", 13, "#12314f")
s.text(540, 236, "⑤ 顺序：SCC 强连通缩合后按拓扑序 自被依赖者→依赖者", 12, "#12314f")
s.box(40, 300, 900, 180, "回滚效果示意", "#f7f7fb", "#8a8ab0", fs=15)
def gn(x,y,lines,fill,st): s.rect(x,y,150,50,lines,fill,st,12)
gn(70,350,["被污染资源","(起点)"],"#fdecec","#c0392b")
gn(300,350,["下游调用者X","(回滚)"],"#fff3ea","#d97a2b")
gn(530,350,["下游调用者Y","(回滚)"],"#fff3ea","#d97a2b")
gn(760,350,["无关资源Z","(保留)"],"#eafaf0","#2e9e5b")
s.arrow(220,375,300,375,"反向", "#c0392b")
s.arrow(450,375,530,375,"反向", "#c0392b")
s.arrow(680,375,760,375,"不在闭包","#2e9e5b",dashed=True)
s.text(70,455, "仅回滚 {起点, X, Y} ∩ 变更集；Z 未受影响，保留其部署结果，避免整环境回退", 13, "#555")
s.save("fig8")

print("SVG generated:", sorted(os.listdir(OUT)))

# ---------- render to PNG via playwright ----------
from playwright.sync_api import sync_playwright
scales = 2
with sync_playwright() as p:
    b = p.chromium.launch()
    for name in ["fig1","fig2","fig3","fig4","fig5","fig6","fig7","fig8"]:
        svgp = os.path.join(OUT, name+".svg")
        pngp = os.path.join(OUT, name+".png")
        # read svg dims
        import re
        txt = open(svgp, encoding="utf-8").read()
        w = int(re.search(r'width="(\d+)"', txt).group(1))
        h = int(re.search(r'height="(\d+)"', txt).group(1))
        pg = b.new_page(viewport={"width":w,"height":h}, device_scale_factor=scales)
        pg.goto("file://"+svgp)
        pg.wait_for_timeout(150)
        pg.screenshot(path=pngp, clip={"x":0,"y":0,"width":w,"height":h})
        pg.close()
    b.close()
print("PNG rendered:", [f for f in sorted(os.listdir(OUT)) if f.endswith('.png')])
