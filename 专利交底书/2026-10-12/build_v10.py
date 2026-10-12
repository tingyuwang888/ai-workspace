from copy import deepcopy
from pathlib import Path
import re
import shutil

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Cm, Pt, RGBColor


REFERENCE = Path('/Users/td/Downloads/专利技术交底书_一种基于规则约束图和分层执行证据的风控策略测试方法及系统_修改版 (2).docx')
OUT = Path('/Users/td/Documents/Codex/2026-10-10/x20-readme-md-scripts-update-readme/outputs/专利技术交底书V10_一种面向混合环境迁移的跨控制面配置引用校验与污染识别方法及系统.docx')
MEDIA_DIR = Path('/Users/td/Documents/Codex/2026-10-10/x20-readme-md-scripts-update-readme/work/patent-template/v4-media/word/media')

FIGURES = {
    1: MEDIA_DIR / '9d96d0d0b1be9da381dd3aaeea7c6ddafbfd4caf.png',
    2: MEDIA_DIR / '1ad106f3d6aed85d8913ef57ec2ebb0d61cbe1ed.png',
    3: MEDIA_DIR / '199b1e7134bc3a160bebe76802de78d5332e2862.png',
    4: MEDIA_DIR / '14bedca9c5af95db5f9f5c1ba5b807f351f15b17.png',
    5: MEDIA_DIR / '0bfb594b9f6ed1d2bcb4d8e737d6444d288514ce.png',
    6: MEDIA_DIR / '48c67f8ebc6e42f45234442cfb8be7dea3b9fd6e.png',
    7: MEDIA_DIR / '8d67a64ab7b014029ad36469ac2ff3e06b3754b7.png',
    8: MEDIA_DIR / '56d3ce60a96053f80a6db514f847897ad32f73ec.png',
}

FONT = 'Arial'
BLUE = '4472C4'
LIGHT_BLUE = 'D9EAF7'
BORDER = 'B4C7E7'


def clear_body(doc):
    body = doc._element.body
    for child in list(body):
        if child.tag != qn('w:sectPr'):
            body.remove(child)


def prune_orphan_images(doc):
    # Collect rIds actually referenced by embedded media across the body and
    # every header/footer part currently attached to the document.
    used = set(re.findall(r'r:(?:embed|id)="(rId\d+)"', doc._element.body.xml))
    seen_parts = set()
    for section in doc.sections:
        for hf in (
            section.header, section.footer,
            section.first_page_header, section.first_page_footer,
            section.even_page_header, section.even_page_footer,
        ):
            try:
                part = hf.part
            except Exception:
                continue
            if id(part) in seen_parts:
                continue
            seen_parts.add(id(part))
            used |= set(re.findall(r'r:(?:embed|id)="(rId\d+)"', part._element.xml))
    part = doc.part
    dropped = []
    for rid, rel in list(part.rels.items()):
        if rel.reltype == RT.IMAGE and rid not in used:
            dropped.append(rid)
            del part.rels[rid]
    return dropped


def set_repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement('w:tblHeader')
    el.set(qn('w:val'), 'true')
    tr_pr.append(el)


def disable_row_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn('w:cantSplit')) is None:
        tr_pr.append(OxmlElement('w:cantSplit'))


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn('w:shd'))
    if shd is None:
        shd = OxmlElement('w:shd')
        tc_pr.append(shd)
    shd.set(qn('w:fill'), fill)


def cell_margins(cell, top=45, start=80, bottom=45, end=80):
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = tc_pr.first_child_found_in('w:tcMar')
    if mar is None:
        mar = OxmlElement('w:tcMar')
        tc_pr.append(mar)
    for name, value in [('top', top), ('start', start), ('bottom', bottom), ('end', end)]:
        node = mar.find(qn(f'w:{name}'))
        if node is None:
            node = OxmlElement(f'w:{name}')
            mar.append(node)
        node.set(qn('w:w'), str(value))
        node.set(qn('w:type'), 'dxa')


def set_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in('w:tblBorders')
    if borders is None:
        borders = OxmlElement('w:tblBorders')
        tbl_pr.append(borders)
    for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        node = borders.find(qn(f'w:{edge}'))
        if node is None:
            node = OxmlElement(f'w:{edge}')
            borders.append(node)
        node.set(qn('w:val'), 'single')
        node.set(qn('w:sz'), '5')
        node.set(qn('w:color'), BORDER)


def font_run(run, size=10.5, bold=False, color='000000', italic=False):
    run.font.name = FONT
    rpr = run._element.get_or_add_rPr()
    for attr in ['ascii', 'hAnsi', 'eastAsia', 'cs']:
        rpr.rFonts.set(qn(f'w:{attr}'), FONT)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor.from_string(color)
    return run


def para(doc, text='', *, bold_lead=None, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
         size=10.5, before=0, after=3, line=1.20, indent=True, keep=False):
    p = doc.add_paragraph()
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.keep_with_next = keep
    if indent and align == WD_ALIGN_PARAGRAPH.JUSTIFY:
        pf.first_line_indent = Cm(0.74)
    if bold_lead and text.startswith(bold_lead):
        font_run(p.add_run(bold_lead), size=size, bold=True)
        font_run(p.add_run(text[len(bold_lead):]), size=size)
    else:
        font_run(p.add_run(text), size=size)
    return p


def heading(doc, text, level=1):
    sizes = {1: 12.5, 2: 11.5, 3: 10.5}
    p = para(doc, text, align=WD_ALIGN_PARAGRAPH.LEFT, size=sizes[level],
             before=8 if level == 1 else 5, after=3, line=1.0, indent=False, keep=True)
    for r in p.runs:
        r.font.bold = True
    return p


def bullet(doc, text, level=0):
    p = para(doc, '', align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=10.5, after=1, line=1.1, indent=False)
    p.paragraph_format.left_indent = Cm(0.65 + 0.5 * level)
    p.paragraph_format.first_line_indent = Cm(-0.35)
    font_run(p.add_run('• '), bold=True)
    font_run(p.add_run(text))
    return p


def numbered(doc, items):
    for i, text in enumerate(items, 1):
        p = para(doc, '', align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=10.5, after=1, line=1.1, indent=False)
        p.paragraph_format.left_indent = Cm(0.75)
        p.paragraph_format.first_line_indent = Cm(-0.55)
        font_run(p.add_run(f'{i}. '), bold=True)
        font_run(p.add_run(text))


def table(doc, headers, rows, widths=None, font_size=9.5):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    set_borders(t)
    hdr = t.rows[0]
    set_repeat_header(hdr)
    disable_row_split(hdr)
    for i, h in enumerate(headers):
        c = hdr.cells[i]
        shade(c, BLUE)
        cell_margins(c)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        font_run(p.add_run(str(h)), size=font_size, bold=True, color='FFFFFF')
        if widths:
            c.width = Cm(widths[i])
    for ridx, row in enumerate(rows):
        new_row = t.add_row()
        disable_row_split(new_row)
        cells = new_row.cells
        for i, value in enumerate(row):
            c = cells[i]
            cell_margins(c)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if ridx % 2:
                shade(c, 'F2F7FB')
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.05
            font_run(p.add_run(str(value)), size=font_size)
            if widths:
                c.width = Cm(widths[i])
    para(doc, '', after=0, indent=False)
    return t


def figure(doc, no, width=14.6):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(FIGURES[no]), width=Cm(width))
    cap = para(doc, f'图{no}  ' + {
        1: '系统三层架构与处理链路',
        2: '统一环境引用记录与跨控制面引用图结构',
        3: '目标实体规范化与引用解析流程',
        4: '环境标签推导 归一与冲突保留',
        5: '污染识别与四态判定（固定优先级：阻断→告警→未知→允许，先匹配先定性）',
        6: '声明目标与观测目标的语义冲突比对',
        7: '类型化引用转换 全量复检与断点续扫',
        8: '部署门禁与污染关联闭包局部回滚',
    }[no], align=WD_ALIGN_PARAGRAPH.CENTER, size=9.5, after=4, line=1.0, indent=False)
    cap.paragraph_format.keep_with_next = True


def add_page_field(p):
    run = p.add_run()
    font_run(run, size=9, color='999999')
    begin = OxmlElement('w:fldChar'); begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText'); instr.set(qn('xml:space'), 'preserve'); instr.text = 'PAGE'
    sep = OxmlElement('w:fldChar'); sep.set(qn('w:fldCharType'), 'separate')
    end = OxmlElement('w:fldChar'); end.set(qn('w:fldCharType'), 'end')
    run._r.extend([begin, instr, sep, end])


def set_footer(doc):
    footer = doc.sections[0].footer
    p = footer.paragraphs[0]
    p.clear()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font_run(p.add_run('2026-10-12 | 内部技术资料 | 第 '), size=9, color='999999')
    add_page_field(p)
    font_run(p.add_run(' 页'), size=9, color='999999')


def title_block(doc):
    p = para(doc, '技 术 交 底 书', align=WD_ALIGN_PARAGRAPH.CENTER, size=16,
             before=0, after=8, line=1.0, indent=False)
    p.runs[0].font.bold = True
    para(doc, '发明名称：一种面向混合环境迁移的跨控制面配置引用校验与污染识别方法及系统',
         size=11, after=3, line=1.05, indent=False)
    para(doc, '本专利发明人：王挺宇、陈辰', size=10.5, after=2, line=1.0, indent=False)
    para(doc, '技术交底书撰写人及技术联系人：王挺宇', size=10.5, after=2, line=1.0, indent=False)
    para(doc, '电话：18225082820  E-MAIL：tingyu.wang@tongdun.net',
         size=10.5, after=6, line=1.0, indent=False)


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REFERENCE, OUT)
    doc = Document(OUT)
    clear_body(doc)
    set_footer(doc)
    title_block(doc)

    heading(doc, '术语解释', 1)
    terms = [
        ('控制面', '独立保存并提供一类环境配置事实的服务或数据源，包括容器编排、配置中心、镜像内置配置、反向代理、持久层、镜像仓库及外部部署清单。'),
        ('环境引用记录', '把不同控制面的字段级引用规约成统一结构，记录源资源、引用字段、引用类型、声明目标、观测目标、环境标签、证据来源及采集窗口。'),
        ('目标实体与引用边', '目标串经类型化解析和别名归一形成唯一目标实体；引用者指向被引用资源形成有向边，多控制面节点及引用边组成跨控制面引用图。'),
        ('污染边', '目标实体不属于本次部署目标环境，且未命中适用于该引用类型、操作类型和资源用途的有效允许关系白名单的引用边；shared/global仅表示具备共享资格，不当然排除污染。'),
        ('标签冲突与语义冲突', '声明侧与观测侧环境标签不一致形成标签冲突；声明目标实体与运行态观测目标实体不一致形成配置漂移冲突。'),
        ('四态判定', '每条引用边按固定规则唯一判定为阻断（BLOCK）、告警（WARN）、未知（UNKNOWN）或允许（ALLOW）；数据库、认证、核心服务及写操作等关键未知引用可升级为阻断。'),
        ('全量污染复检', '迁移转换后重新采集并执行完整污染判定，确认不存在未获允许的非目标环境引用。'),
    ]
    for name, desc in terms:
        para(doc, f'{name}：{desc}', bold_lead=f'{name}：', after=1)

    heading(doc, '1、现有技术背景及最接近的实现方案', 1)
    para(doc, '本发明解决的技术问题是：在容器与虚拟机或裸机混合承载、各控制面相互独立的多套环境之间迁移应用时，自动发现部署产物中残留的错误环境引用，以及静态配置与运行状态不一致造成的配置漂移，从而保证迁移后环境的配置引用正确性与隔离性。')
    para(doc, '现有Helm、Kustomize等多环境模板要求所有环境差异已被模板化，无法检查镜像内配置、配置中心连接串、前端硬编码地址和外部清单；GitOps主要比较单一编排控制面的期望状态和实际状态，不能判断声明本身是否引用了错误环境；配置中心导出导入通常原样搬运，不能识别内容中的源环境连接；传统CMDB和流量拓扑粒度多为主机或服务级，不能定位到具体配置字段。')
    para(doc, '在实际混合部署中，同一应用的配置事实通常由Kubernetes API、Nacos、镜像文件系统、Nginx、数据库、Harbor及人工部署清单分别保存。上述控制面没有统一对象标识，同一服务可能同时以FQDN、ClusterIP、NodePort、镜像内upstream或前端硬编码地址出现，单纯逐文件搜索无法确认这些字符串是否指向同一资源。')
    para(doc, '声明式模板只能约束已参数化的字段；若错误值已经写入模板、镜像或配置中心，模板渲染仍会稳定地产出错误配置。GitOps能够发现集群实际状态偏离Git声明，却不能发现Git声明本身引用了错误环境。基于运行流量形成的拓扑又必须等应用启动并产生流量后才能工作，无法承担部署前校验。')
    table(doc, ['相关技术', '主要能力', '与本发明的区别'], [
        ['CN111984373A', 'Kubernetes控制面内环境一致性校验', '不涉及配置中心、镜像内配置、外部清单等跨控制面字段级引用。'],
        ['CN113703915A/B', '基于环境标签与虚拟机流量形成访问关系图', '关系来自运行流量；本发明解析静态配置字段，无流量时也能识别污染。'],
        ['CN116185991A', '数据库迁移前比较源和目标环境参数', '面向数据库参数；本发明覆盖多控制面并构建字段级引用图。'],
        ['CN115587188A/B', '静态与动态运维知识融合图谱', '用于运维知识管理，不以跨环境污染和迁移复检为目标。'],
    ], widths=[3.2, 6.0, 8.0])
    para(doc, '上述公开文献编号及其权利要求相关性应由代理机构在正式检索中再次核验；本稿仅按技术类别描述差异，不把初步检索结果作为新颖性或创造性的最终结论。')

    heading(doc, '2、现有技术缺点及本发明目的', 1)
    numbered(doc, [
        '配置事实分散在多个控制面，缺乏统一数据结构和跨控制面引用比对。',
        '缺乏以部署目标环境为基准的污染判定，生产应用连接测试库等问题通常在运行后才暴露。',
        '静态声明、人工清单和实际运行状态之间缺少同窗口语义比对，容易产生错误拓扑和假冲突。',
        '配置迁移多使用字符串替换，缺少类型化转换、全量复检及配置项级中断续跑。',
        '问题处置多为整环境回退，缺乏基于引用关系和本次变更集的受控局部回滚。',
    ])
    para(doc, '本发明通过统一环境引用记录、目标实体规范化、环境标签归一与冲突保留、四态污染识别、声明目标和观测目标的语义比对、类型化引用转换及全量污染复检，形成跨控制面的迁移校验闭环；可选地进一步执行部署门禁、断点续扫和污染关联闭包局部回滚。')

    heading(doc, '3、本发明技术方案的详细阐述', 1)
    heading(doc, '（1）系统整体架构', 2)
    para(doc, '系统包括采集层、引用分析层、门禁与执行层。采集层面向编排、配置中心、镜像内配置、代理入口、持久层、镜像仓库和外部清单采集字段级引用；引用分析层完成实体解析、标签判定、引用图构建、污染识别和语义冲突比对；门禁与执行层用于类型化转换、全量复检、断点续扫及可选门禁和局部回滚。')
    figure(doc, 1, 14.8)
    para(doc, '所述校验可在三个阶段协同执行，且各阶段可单独或组合启用：其一为迁移前静态扫描，仅依据各控制面配置字段完成目标实体规范化与污染判定，无需应用运行即可发现生产引用测试环境等污染；其二为转换后全量复检，对迁移产物重新采集并完整执行四态判定，确认不存在未获允许的残留污染；其三为取得运行证据后的语义比对，在同一采集窗口内将观测目标与声明目标分别归一为实体后比较，以识别节点角色、运行形态、后端地址等配置漂移。三者共用同一套统一环境引用记录、目标实体规范化与四态判定规则。')

    heading(doc, '（2）统一环境引用记录与跨控制面引用图', 2)
    table(doc, ['字段', '含义', '示例'], [
        ['resource_id', '源资源唯一标识，精确到发生引用的配置对象或文件。', 'image/nginx-tiance@sha256:9a1c:/etc/nginx/nginx.conf'],
        ['source_control_plane', '源控制面类型。', 'image_bundled_config / config_center'],
        ['ref_field', '构成引用的字段、键或文件位置。', 'upstream.risk_api.proxy_pass'],
        ['ref_type / edge_type', '引用类型及图边语义。', 'proxy_route / routes_to'],
        ['declared_target_ref', '静态声明中的目标原始串。', 'bifrost.risk-dev.svc.cluster.local'],
        ['declared_target_entity', '声明目标规范化后的实体。', 'entity://svc/bifrost@cluster-a/risk-dev'],
        ['observed_target_ref', '运行时实际目标原始串，可空。', '10.96.23.18:3306/risk_dev'],
        ['observed_target_entity', '运行时目标规范化后的实体，可空。', 'entity://db/risk_dev@test'],
        ['target_version / digest', '多版本实体的版本及不可变摘要。', 'v1.2.3 / sha256:9a1c'],
        ['runtime_status', '运行健康状态，不作为引用目标比较。', 'Running / CrashLoopBackOff'],
        ['declared_env_tag', '声明侧环境标签。', 'risk-dev'],
        ['observed_env_tags', '观测侧环境标签集合。', '[test]'],
        ['resolved_env_tag', '经规则归一后的判定标签。', 'risk-dev / shared / unknown'],
        ['resolution_source / confidence', '标签来源及置信度。', 'namespace / 0.95'],
        ['tag_conflict', '声明与观测标签是否冲突。', 'true / false'],
        ['operation_type / purpose', '引用的只读、读写属性及用途。', 'read_write / primary_database'],
        ['criticality', '错误引用的技术影响等级。', 'critical / normal'],
        ['scan_id / collected_at', '采集窗口及采集时刻。', 'scan-2026-04-11-01 / 10:22:07Z'],
        ['resource_version / valid_until', '资源版本及证据有效期。', 'nacos@rev-295 / 10:52:07Z'],
        ['evidence_source', '形成记录的快照或证据位置。', 'risk-prod#nacos-app-b'],
        ['change_set_id / snapshot_ref', '本次变更集及变更前快照。', 'chg-20260411-03 / snap://nacos/294'],
    ], widths=[4.2, 7.3, 5.7], font_size=8.3)
    para(doc, '部署目标环境标签deploy_target_env_tag作为图级上下文保存，不在每条记录内重复。声明目标与观测目标必须属于同一引用类型并经过实体规范化后才可比较；运行状态仅用于解释运行健康度，不能拿CrashLoopBackOff等状态值与服务地址进行语义比较。')

    heading(doc, '记录示例A：镜像内置Nginx指向源环境', 3)
    table(doc, ['字段', '取值'], [
        ['resource_id / source_control_plane', 'image/nginx-tiance@sha256:9a1c:/etc/nginx/nginx.conf / image_bundled_config'],
        ['ref_field / ref_type', 'upstream.risk_api.proxy_pass / proxy_route'],
        ['declared_target_ref / entity', 'bifrost.risk-dev.svc.cluster.local / entity://svc/bifrost@cluster-a/risk-dev'],
        ['observed_target_ref / entity', '空 / 空；Pod尚未建立有效连接'],
        ['runtime_status', 'CrashLoopBackOff'],
        ['resolved_env_tag / deploy_target_env_tag', 'risk-dev / risk-prod'],
        ['判定', '明确属于非目标环境且未获允许，输出BLOCK污染边。'],
    ], widths=[6.0, 11.0], font_size=8.8)
    para(doc, '该记录的源资源是镜像内配置文件，而不是Deployment。Deployment通过uses边指向镜像配置文件，镜像配置文件再通过routes_to边指向risk-dev服务，由此形成可追溯的跨控制面引用路径。')

    heading(doc, '记录示例B：生产应用实际读取测试数据库', 3)
    table(doc, ['字段', '取值'], [
        ['resource_id / source_control_plane', 'nacos:risk-prod:app-b/datasource.url / config_center'],
        ['ref_field / ref_type', 'spring.datasource.url / database'],
        ['declared_target_ref / entity', 'jdbc:mysql://10.96.23.18:3306/risk_dev / entity://db/risk_dev@test'],
        ['observed_target_ref / entity', '连接池实际目标同上 / entity://db/risk_dev@test'],
        ['operation_type / purpose', 'read_write / primary_database'],
        ['resolved_env_tag / deploy_target_env_tag', 'test / risk-prod'],
        ['判定', '关键读写引用指向非目标环境，输出BLOCK污染边并进入门禁。'],
    ], widths=[6.0, 11.0], font_size=8.8)
    figure(doc, 2, 14.0)

    heading(doc, '（3）目标实体规范化与引用解析', 2)
    para(doc, '系统按引用类型选择解析器：Service FQDN、ClusterIP、NodePort及UID经运行态Service快照和别名表归一；JDBC连接串解析主机、端口和库名；镜像以仓库、项目、名称及不可变摘要定版；配置中心服务名、镜像内配置和代理路由解析为对应逻辑实体。无法解析者标记为悬挂引用并置unknown；一对多目标展开为多条边，多对一目标合并节点并保留各来源证据。实体标识还携带cluster_id或environment_scope，防止不同集群同名资源误合并。')
    para(doc, '别名表由采集窗口内的资源快照生成，例如把Service的FQDN、ClusterIP、UID和NodePort地址绑定到同一实体。实体解析结果记录解析器类型、候选实体、选中实体、解析置信度和来源快照；无法唯一确定时保留全部候选或进入unknown状态。')
    table(doc, ['引用类型', '解析方式', '实体定界信息'], [
        ['service', '解析FQDN的服务名和命名空间，或由ClusterIP、NodePort、UID反查Service快照。', 'cluster_id + namespace + service_uid'],
        ['database', '解析连接串的协议、主机、端口和库名，再用IP及实例映射表归一。', 'environment_scope + instance + database'],
        ['image', '解析仓库、项目、名称、标签和摘要；优先以不可变摘要定版。', 'registry + project + image + digest'],
        ['embedded_config', '定位镜像摘要、文件路径、配置段及字段。', 'image_digest + file_path + config_key'],
        ['proxy_route', '解析生效upstream、目标协议、主机、端口及路径。', 'proxy_instance + route_key + target_entity'],
        ['node / cluster', '由节点名称、标签、角色和集群标识归一。', 'cluster_id + node_uid / cluster_uid'],
    ], widths=[3.2, 8.8, 5.0], font_size=8.7)
    para(doc, '若一个通配域名或负载均衡地址对应多个后端实体，则展开为多条候选边并分别判定；若多个地址归一为同一实体，则合并目标节点但保留每条来源证据。只有候选唯一或满足预设置信阈值时才写入selected_entity，否则保留候选集合并输出UNKNOWN，防止错误归一造成误放行。')
    figure(doc, 3, 14.4)

    heading(doc, '（4）环境标签归一及污染四态判定', 2)
    para(doc, '声明标签和观测标签分别从人工映射、Namespace、节点标签、配置中心实例、镜像仓库项目及命名约定推导。高精度来源用于形成判定标签，但所有来源及冲突均保留。无法确定时置unknown；shared/global仅表示资源具备共享资格，数据库、认证、消息及写操作等关键资源仍须命中允许关系白名单。')
    para(doc, '标签推导按人工映射、命名空间、节点标签、配置中心实例、镜像仓库项目、命名约定的顺序评估。人工映射可作为判定基准，但当运行态观测结果与其不一致时，系统必须同时输出tag_conflict、冲突来源和各自置信度，不能用高优先级值覆盖低优先级证据。')
    figure(doc, 4, 14.2)
    table(doc, ['顺序', '条件', '状态'], [
        ['1', 'unknown且属于数据库、认证、核心调用或写操作等关键引用', 'BLOCK'],
        ['2', '明确属于非目标环境，且未命中有效白名单', 'BLOCK'],
        ['3', '命中白名单但临近失效，或目标环境正确但证据低置信、过期或存在标签冲突', 'WARN'],
        ['4', '非关键unknown', 'UNKNOWN'],
        ['5', '目标环境正确且无告警条件，或非目标环境/具共享资格资源命中适用于该引用类型、操作类型与用途且有效、未临近失效的白名单', 'ALLOW'],
    ], widths=[1.5, 12.0, 3.4])
    para(doc, '白名单至少限定源环境、目标环境、目标实体或类别、引用类型、操作类型、资源用途、有效期和审批来源。白名单过期视为未命中；临近失效进入告警。')
    para(doc, 'shared/global仅表示资源具备被多环境共享的资格，并非自动授权。数据库、消息、身份认证和写操作等关键资源即使标记为shared/global，也须匹配操作类型与用途均符合的白名单；非关键且明确属于全局公共服务的引用可按预设策略允许。')
    para(doc, '四态规则采用先匹配先定性的固定顺序，使每条引用边只落入一个状态：先处理关键UNKNOWN，再处理明确跨环境且未授权的BLOCK，随后处理证据低置信、标签冲突、证据过期或白名单临期的WARN，最后才进入UNKNOWN或ALLOW。策略执行结果同时记录命中规则、输入证据、白名单条目和判定时间，供复检与审计重放。')
    figure(doc, 5, 13.6)

    heading(doc, '（5）声明目标与运行观测的语义比对', 2)
    para(doc, '仅对同一scan_id或同一有效采集窗口内的声明证据与观测证据进行比较。域名、ClusterIP、UID等经别名表归一为同一实体时判一致，否则形成配置漂移冲突。数据库、认证、核心服务及写操作目标不一致为阻断级；节点角色、镜像摘要和运行形态按关键性分级；非关键监控和文档描述冲突为告警级。运行态观测可来源于Pod环境变量、进程参数、Nacos有效配置、Service Endpoint、Nginx生效配置、数据库连接池元数据或调用日志。')
    para(doc, '每轮采集生成scan_id，并保存collected_at、resource_version和valid_until；当采集期间资源版本变化或观测已经过期时，不把差异直接认定为漂移，而是要求重新采集或输出告警，从而避免由取数时间差造成假冲突。')
    table(doc, ['比较维度', '声明侧证据', '观测侧证据', '分级示例'], [
        ['数据库目标', 'Nacos/JDBC配置中的实例与库名', '连接池元数据或实际会话目标', '生产写入测试库：阻断级'],
        ['服务后端', '前端、网关或代理配置的地址', 'Endpoint、路由或调用目标', '核心服务不一致：阻断级'],
        ['节点与调度', 'nodeSelector、亲和性、人工角色清单', 'Pod实际节点及节点标签', '关键隔离节点错误：阻断或告警'],
        ['镜像版本', '声明标签或摘要', 'Pod实际镜像摘要', '核心镜像不一致：阻断或告警'],
        ['运行形态', '清单声明VM或K8s', '实际进程、Pod或Deployment', '导致入口地址错误：阻断级'],
        ['监控与文档', '监控地址或拓扑描述', '实际探测地址', '不影响业务调用：告警级'],
    ], widths=[3.1, 4.8, 4.8, 4.3], font_size=8.5)
    figure(doc, 6, 14.2)

    heading(doc, '（6）类型化转换 全量复检和断点续扫', 2)
    para(doc, '对阻断边按ref_type调用结构化解析器：分别修改Namespace、JDBC主机和库名、Profile、镜像项目及摘要、镜像内配置、代理路由、Service FQDN、节点选择器和集群名。转换后重新采集并完整执行实体解析、标签判定和污染四态判断，确认不存在未获允许的非目标环境引用。')
    table(doc, ['引用类型', '转换对象', '校验重点'], [
        ['namespace / service', 'YAML对象命名空间、Service名及FQDN分段', '目标对象存在，且归一后环境为目标环境'],
        ['database', '结构化解析JDBC URL的主机、端口和库名', '只读/读写属性及实际连接目标'],
        ['profile', '应用配置中的环境Profile字段', '生效Profile与部署目标一致'],
        ['image', 'Harbor项目、镜像标签及摘要', '摘要可解析且与目标仓库实体一致'],
        ['embedded_config', '镜像内生效文件，或用ConfigMap覆盖', '覆盖挂载位置及生效内容无源环境引用'],
        ['proxy_route', 'Nginx upstream、代理主机和路径', '路由实体及运行态生效配置一致'],
        ['node / cluster', 'nodeSelector、亲和性、集群标识', '实际调度节点和隔离标签一致'],
    ], widths=[3.4, 7.4, 6.2], font_size=8.7)
    table(doc, ['状态字段', '说明'], [
        ['config_id / change_set_id', '配置项标识及本次变更集标识。'],
        ['input_hash / output_hash', '转换前后内容摘要。'],
        ['transform_status / verified', '处理状态和复检状态。'],
        ['snapshot_ref', '变更前可恢复快照。'],
    ], widths=[6.0, 11.0])
    para(doc, '中断恢复时，仅处理未完成或input_hash发生变化的配置项；已完成且输入未变化的配置项直接跳过。')
    para(doc, '每项转换前创建snapshot_ref并写入change_set_id；执行成功后保存output_hash，复检通过后再置verified=true。若进程在第N项后中断，恢复时先比较当前输入摘要与原input_hash：摘要相同且状态为DONE/verified的项目跳过，摘要变化或未完成项目重新进入转换和复检。该机制将续跑范围限制在配置项层级，避免对已完成项目重复写入。')
    figure(doc, 7, 14.5)

    heading(doc, '（7）部署门禁及污染关联闭包局部回滚', 2)
    para(doc, '存在任何BLOCK状态引用、阻断级配置漂移冲突或复检残留时，门禁阻断配置下发或应用启动。回滚以污染边源端资源为起点，仅沿references、routes_to、stores_in、registered_with等传播边反向查找依赖者，并与change_set_id对应的变更集求交；共享资源uses边不扩张闭包。含环子图先计算强连通分量，再对缩合图排序。')
    numbered(doc, [
        '从最外层依赖者开始隔离流量。',
        '从被依赖资源开始恢复配置和快照；无快照则转人工确认。',
        '按依赖顺序重新启动和验证，污染边消失后解除隔离。',
    ])
    figure(doc, 8, 14.5)

    heading(doc, '（8）实施例', 2)
    heading(doc, '真实实施例', 3)
    para(doc, '将risk-dev应用复制到risk-prod时，为避免直接修改原Deployment导致测试环境消失，新建独立Namespace并转换镜像、Nacos地址、节点亲和性等配置。部署后发现镜像内Nginx仍引用risk-dev服务域名并引起CrashLoopBackOff；随后以ConfigMap覆盖生效配置。又因约295项Nacos配置被原样迁入，生产应用实际读取测试数据库；经全量导出、类型化替换和残留扫描后恢复正确。过程中还发现外部清单节点角色与集群实际角色不符，以及后端实际运行于K8s但前端仍使用虚拟机硬编码地址。')
    table(doc, ['阶段', '现场事实', '本发明对应处理'], [
        ['迁移准备', '直接修改risk-dev Deployment会导致测试环境消失，因此建立独立risk-prod命名空间。', '采集源部署并生成独立目标图上下文，不把原资源原地改造成生产资源。'],
        ['首轮部署', '镜像内Nginx仍指向risk-dev服务，Pod出现CrashLoopBackOff。', '从镜像文件提取proxy_route记录，识别BLOCK污染边并定位到具体文件字段。'],
        ['代理修复', '提取生效配置，将源环境路由替换后通过ConfigMap覆盖镜像配置。', '按embedded_config/proxy_route执行结构化转换，并重新采集生效配置。'],
        ['配置迁移', '约295项Nacos配置原样导入，13个应用可启动。', '逐项建立config_id与input_hash，执行数据库、服务地址和Profile解析。'],
        ['数据污染', '生产页面出现不应存在的数据，确认生产应用读取测试库。', '声明目标和连接池观测目标均归一到测试数据库，判为关键BLOCK。'],
        ['全量复检', '替换数据库连接、重启并初始化生产库。', '重新构图，确认除共享或白名单外不存在任何非目标环境引用。'],
        ['漂移发现', '外部清单节点角色与集群实际角色不符；后端实际运行于K8s而前端仍写VM地址。', '以同窗口声明/观测实体比对输出配置漂移冲突并按影响分级。'],
    ], widths=[2.6, 7.2, 7.2], font_size=8.6)
    heading(doc, '规则演算实施例', 3)
    para(doc, '本实施例以规则推演方式说明系统对给定输入的处理过程（系按规则的确定性推演，非真实运行记录）：采用与真实实施例相同的迁移输入，在下发前执行采集、实体归一、引用图构建与污染识别；按四态规则，risk-dev代理路由及测试数据库连接被判定为BLOCK，门禁拒绝本次下发，完成类型化转换和全量复检后放行。')
    numbered(doc, [
        '对Kubernetes、Nacos、镜像文件和外部清单生成同一scan_id下的环境引用记录。',
        '解析出risk-dev代理路由和test数据库实体，按固定顺序输出BLOCK及证据链。',
        '门禁拒绝配置下发，并生成包含resource_id、ref_field、目标实体和替换映射的清单。',
        '执行类型化转换；以约295项配置为例，按配置项状态机推演：假设处理在第N项后中断，恢复时对已完成且input_hash未变项置跳过，对未完成或input_hash变化项重新进入转换与复检。',
        '重新采集并构图；按规则，仅当污染边和阻断级漂移均清零时判定放行，并回采运行证据。',
    ])

    heading(doc, '（9）有益效果', 2)
    numbered(doc, [
        '将编排、配置中心、镜像、代理、数据库和人工清单中的字段级引用统一为可追溯图结构。',
        '在应用启动和产生业务数据前识别生产引用测试环境等污染。',
        '通过实体语义归一、共享资格和多维白名单降低简单字符串扫描误报。',
        '通过采集窗口和证据有效期避免不同时间快照造成假冲突。',
        '通过配置项级续扫及受变更集约束的局部回滚减少整批重做和整环境回退。',
    ])

    heading(doc, '4、本发明的关键点和欲保护点', 1)
    numbered(doc, [
        '统一环境引用记录及跨控制面目标实体规范化。',
        '声明与观测环境标签冲突保留、证据窗口一致性及四态污染判定。',
        '带操作类型、用途、有效期及审批来源的多维允许关系白名单。',
        '声明目标与观测目标在实体层面的语义冲突识别和分级。',
        '按引用类型执行结构化转换及转换后的全量污染复检。',
        '配置项粒度断点续扫。',
        '部署门禁和受传播边类型、变更集及快照约束的局部回滚。',
    ])

    doc.add_page_break()
    heading(doc, '5、权利要求书草稿（供代理人参考）', 1)
    claims = [
        ('权利要求1（独立方法）', '一种基于跨控制面引用图的混合环境配置污染识别与迁移校验方法，包括：通过面向多个独立控制面的采集器采集配置项并形成统一环境引用记录，所述统一环境引用记录至少携带源资源标识、源控制面类型、引用字段、引用类型和声明目标串；按引用类型把声明目标、以及在取得运行态证据时的观测目标，分别规范化为引用图中具有唯一标识或可唯一寻址的目标实体；推导并保留声明侧、观测侧环境标签及标签冲突；构建资源节点和引用边组成的跨控制面引用图；依据部署目标环境、共享资格和允许关系白名单，按固定优先级将每条引用边唯一判定为阻断、告警、未知或允许；对迁移产物重新执行完整污染判定，输出残留污染。'),
        ('权利要求2（实体解析）', '根据权利要求1所述的方法，其中，所述规范化中，目标串包括服务域名、集群IP、节点端口、数据库连接串、镜像标签与摘要、镜像内配置、代理路由和配置中心服务名；通过别名表和cluster_id或environment_scope归一同一资源的多种地址，一对多展开为多条边，多对一合并实体并保留各来源证据。'),
        ('权利要求3（标签和采集窗口）', '根据权利要求1所述的方法，其中，记录携带声明标签、可选观测标签、标签来源、置信度、冲突标志、scan_id、采集时间、资源版本和有效期；仅对同一有效采集窗口内的声明与观测证据执行语义比较，跨窗或过期证据不直接判定冲突而转入告警。'),
        ('权利要求4（四态判定优先级）', '根据权利要求1所述的方法，其中，所述唯一判定采用先匹配先定性的固定顺序，使每条引用边只落入一个状态：判定环境标签为未知且属于数据库、认证、核心调用或写操作等关键引用者，判定为阻断；明确属于非目标环境且未命中有效白名单者，判定为阻断；命中白名单但临近失效、或目标环境正确但证据低置信、过期或存在标签冲突者，判定为告警；判定环境标签为未知且非关键者，判定为未知；目标环境正确且不存在告警条件，或者非目标环境资源或具有共享资格的资源命中适用于该引用类型、操作类型和资源用途且有效、未临近失效的允许关系白名单者，判定为允许。'),
        ('权利要求5（允许关系白名单）', '根据权利要求4所述的方法，其中，所述允许关系白名单至少限定源环境、目标环境、目标实体或类别、引用类型、只读或读写操作类型、资源用途、有效期和审批来源；白名单过期视为未命中，临近失效转入告警；数据库、认证、消息及写操作等关键资源即使标记为共享资格，仍须命中操作类型与用途均符合的白名单方可允许。'),
        ('权利要求6（语义冲突及分级）', '根据权利要求1所述的方法，还包括：在同一采集窗口内将声明目标和观测目标分别归一为实体后比较，识别节点角色、运行形态、后端地址、实际连接和调度节点等配置漂移，并按数据库、认证、核心调用、写操作等关键性分为阻断级或告警级。'),
        ('权利要求7（类型化转换与全量复检）', '根据权利要求1所述的方法，还包括：对被判定为阻断的引用按Namespace、数据库、Profile、镜像、镜像内配置、代理路由、服务、节点或集群类型调用对应结构化解析器改写；改写后重新采集并完整执行实体解析、标签判定与污染四态判断，残留集合为空时判定迁移通过。'),
        ('权利要求8（断点续扫）', '根据权利要求7所述的方法，其中，按配置项记录change_set_id、输入摘要、状态、输出摘要、验证标志和snapshot_ref，中断恢复后仅处理未完成或输入摘要发生变化的配置项。'),
        ('权利要求9（部署门禁之一·污染边与漂移）', '根据权利要求6所述的方法，还包括：在配置下发或应用启动前，当存在被判定为阻断状态的引用边或被分级为阻断级的配置漂移冲突时，阻断本次部署并输出结构化待修复清单。'),
        ('权利要求10（部署门禁之二·复检残留）', '根据权利要求7所述的方法，还包括：当转换后全量污染复检得到的残留污染集合非空时，同样阻断本次部署。'),
        ('权利要求11（局部回滚）', '根据权利要求1所述的方法，还包括污染关联闭包局部回滚：以污染边源端资源为起点，仅沿参与污染传播的引用边反向可达得到依赖者，并与本次变更集求交形成回滚闭包，共享资源的uses边不扩张闭包；对含环子图先计算强连通分量再对缩合图拓扑排序，依次执行隔离流量、恢复快照及重启验证。'),
        ('权利要求12（独立系统）', '一种跨控制面配置引用一致性校验系统，包括配置采集层和引用分析层；所述配置采集层面向多个独立控制面采集配置项并形成统一环境引用记录，所述统一环境引用记录至少包括源资源标识、源控制面类型、引用字段、引用类型和声明目标串；所述引用分析层用于执行目标实体规范化、环境标签归一与冲突保留以及跨控制面引用图构建；所述引用分析层还用于依据部署目标环境、共享资格和允许关系白名单，按照阻断判定条件、告警判定条件、未知判定条件及允许判定条件的固定顺序，对每条引用边执行先匹配先定性的四态污染识别，使每条引用边唯一判定为阻断、告警、未知或允许；并执行语义冲突识别及转换后全量复检的残留污染识别。'),
        ('权利要求13（系统转换模块）', '根据权利要求12所述的系统，还包括执行模块，按引用类型对被判定为阻断的引用执行结构化转换，并在转换后执行全量污染复检。'),
        ('权利要求14（系统续扫模块）', '根据权利要求13所述的系统，其中，所述执行模块还包括配置项级状态记录及中断恢复模块，用于在恢复时仅处理未完成或输入变化的配置项。'),
        ('权利要求15（系统门禁模块）', '根据权利要求12所述的系统，还包括门禁模块，用于在存在阻断状态引用、阻断级漂移冲突或复检残留时阻断部署。'),
        ('权利要求16（系统回滚模块）', '根据权利要求12所述的系统，还包括回滚模块，用于基于传播边类型、本次变更集、强连通分量和变更前快照执行局部回滚。'),
        ('权利要求17（电子设备）', '一种电子设备，包括处理器与存储器，所述处理器执行存储器中的计算机程序时实现权利要求1至11任一项所述的方法。'),
        ('权利要求18（计算机可读存储介质）', '一种计算机可读存储介质，其上存储的计算机程序被处理器执行时实现权利要求1至11任一项所述的方法。'),
    ]
    for title, body in claims:
        para(doc, f'{title}：{body}', bold_lead=f'{title}：', after=0, line=0.95)

    doc.core_properties.title = '一种面向混合环境迁移的跨控制面配置引用校验与污染识别方法及系统'
    doc.core_properties.author = '王挺宇、陈辰'
    doc.core_properties.last_modified_by = 'Codex'
    update_fields = doc.settings.element.find(qn('w:updateFields'))
    if update_fields is None:
        update_fields = OxmlElement('w:updateFields')
        doc.settings.element.append(update_fields)
    update_fields.set(qn('w:val'), 'true')
    dropped = prune_orphan_images(doc)
    doc.save(OUT)
    print('dropped orphan images:', dropped)
    print(OUT)


if __name__ == '__main__':
    build()
