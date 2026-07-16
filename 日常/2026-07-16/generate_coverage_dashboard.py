#!/usr/bin/env python3
"""
覆盖率热力图 Dashboard 生成器 (Phase 4-1)
读取 coverage_pre_report.json（预期）+ coverage_actual.json（实际）+ coverage_diff.json（差异）
输出自包含的交互式 HTML 热力图。
"""
import argparse
import json
import os
import sys
from pathlib import Path


def load_json(path):
    """安全加载 JSON，不存在则返回 None。"""
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def generate_dashboard(pre_report, actual_report=None, diff_report=None, output_path="coverage_dashboard.html"):
    """生成覆盖率热力图 HTML。"""

    strategy_code = pre_report.get("strategyCode", "unknown")
    strategy_name = pre_report.get("strategyName", "未命名策略")
    generated_at = pre_report.get("generatedAt", "")
    total_cases = pre_report.get("totalCases", 0)
    dims = pre_report.get("dimensions", {})

    # 构建维度摘要数据
    dim_data = []
    # 1. Rules
    r = dims.get("rules", {})
    dim_data.append({
        "key": "rules", "label": "规则覆盖", "icon": "\U0001F4CB",
        "total": r.get("total", 0), "covered": r.get("fullyCovered", 0),
        "percent": r.get("percent", 0),
        "detail": r.get("detail", {})
    })
    # 2. RuleSets
    rs = dims.get("ruleSets", {})
    rs_total = rs.get("total", 0)
    rs_covered = sum(1 for v in rs.get("detail", {}).values() if v.get("percent", 0) == 100)
    dim_data.append({
        "key": "ruleSets", "label": "规则集覆盖", "icon": "\U0001F4C1",
        "total": rs_total, "covered": rs_covered,
        "percent": round(rs_covered / rs_total * 100, 1) if rs_total else 0,
        "detail": rs.get("detail", {})
    })
    # 3. Functions
    fn = dims.get("functions", {})
    dim_data.append({
        "key": "functions", "label": "函数覆盖", "icon": "\u2699\uFE0F",
        "total": fn.get("total", 0), "covered": fn.get("tested", 0),
        "percent": fn.get("percent", 0),
        "detail": fn.get("detail", {})
    })
    # 4. Fields
    fd = dims.get("fields", {})
    dim_data.append({
        "key": "fields", "label": "字段覆盖", "icon": "\U0001F3F7\uFE0F",
        "total": fd.get("totalInStrategy", 0), "covered": fd.get("usedInTestCases", 0),
        "percent": fd.get("percent", 0),
        "detail": {"unused": fd.get("unused", [])}
    })
    # 5. ThirdParty
    tp = dims.get("thirdParty", {})
    dim_data.append({
        "key": "thirdParty", "label": "三方接口", "icon": "\U0001F517",
        "total": tp.get("totalInStrategy", 0), "covered": tp.get("referencedCount", 0),
        "percent": round(tp.get("referencedCount", 0) / max(tp.get("totalInStrategy", 1), 1) * 100, 1),
        "detail": {"referenced": tp.get("referenced", [])}
    })
    # 6. CrossMatrix
    cm = dims.get("crossMatrix", {})
    dim_data.append({
        "key": "crossMatrix", "label": "联动矩阵", "icon": "\U0001F500",
        "total": cm.get("possibleCombinations", 0), "covered": cm.get("testedCombinations", 0),
        "percent": cm.get("percent", 0),
        "detail": {}
    })
    # 7. Branches
    br = dims.get("branches", {})
    br_total = br.get("flowCases", 0) + br.get("combinedCases", 0)
    dim_data.append({
        "key": "branches", "label": "分支覆盖", "icon": "\U0001F33F",
        "total": br_total, "covered": br_total,
        "percent": 100.0 if br_total else 0,
        "detail": {"flowCases": br.get("flowCases", 0), "combinedCases": br.get("combinedCases", 0)}
    })

    # 实际覆盖率数据（可选）
    actual_dims = {}
    if actual_report:
        actual_dims = actual_report.get("dimensions", {})

    # 差异数据（可选）
    diff_data = {}
    if diff_report:
        diff_data = diff_report

    # 综合覆盖率（7 维度加权均值）
    overall_percent = round(sum(d["percent"] for d in dim_data) / max(len(dim_data), 1), 1)

    html = _build_html(
        strategy_code=strategy_code,
        strategy_name=strategy_name,
        generated_at=generated_at,
        total_cases=total_cases,
        overall_percent=overall_percent,
        dim_data=dim_data,
        actual_dims=actual_dims,
        diff_data=diff_data,
    )

    Path(output_path).write_text(html, encoding="utf-8")
    return output_path


def _pct_color(pct):
    if pct >= 90:
        return "#22c55e"
    if pct >= 70:
        return "#eab308"
    if pct >= 50:
        return "#f97316"
    return "#ef4444"


def _dash(pct):
    """SVG stroke-dasharray 值。"""
    circumference = 2 * 3.14159 * 42  # r=42
    return round(circumference * pct / 100, 1)


def _build_html(strategy_code, strategy_name, generated_at, total_cases,
                overall_percent, dim_data, actual_dims, diff_data):
    """构建完整的 HTML 字符串。"""

    dim_json = json.dumps(dim_data, ensure_ascii=False)
    actual_json = json.dumps(actual_dims, ensure_ascii=False)
    diff_json = json.dumps(diff_data, ensure_ascii=False)

    ring_color = _pct_color(overall_percent)
    ring_filled = _dash(overall_percent)
    ring_empty = _dash(100 - overall_percent)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>覆盖率热力图 - {strategy_code}</title>
<style>
:root {{
  --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
  --text: #e2e8f0; --text2: #94a3b8; --accent: #38bdf8;
  --green: #22c55e; --yellow: #eab308; --red: #ef4444; --orange: #f97316;
  --radius: 12px;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; padding: 24px; min-height: 100vh; }}

.header {{ text-align: center; margin-bottom: 32px; }}
.header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 4px; }}
.header .code {{ color: var(--accent); font-size: 14px; font-family: monospace; }}
.header .meta {{ color: var(--text2); font-size: 13px; margin-top: 8px; }}

.score-ring {{ display: flex; align-items: center; justify-content: center; gap: 48px; margin-bottom: 32px; flex-wrap: wrap; }}
.ring-container {{ text-align: center; }}
.ring-container svg {{ width: 160px; height: 160px; }}
.ring-label {{ font-size: 13px; color: var(--text2); margin-top: 8px; }}

.stats-row {{ display: flex; gap: 16px; justify-content: center; margin-bottom: 32px; flex-wrap: wrap; }}
.stat-chip {{ background: var(--surface); padding: 12px 20px; border-radius: var(--radius); text-align: center; min-width: 120px; }}
.stat-chip .val {{ font-size: 24px; font-weight: 700; }}
.stat-chip .lbl {{ font-size: 12px; color: var(--text2); margin-top: 2px; }}

.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.card {{ background: var(--surface); border-radius: var(--radius); padding: 20px; cursor: pointer; transition: transform .15s, box-shadow .15s; border: 1px solid transparent; }}
.card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,.3); border-color: var(--accent); }}
.card-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }}
.card-icon {{ font-size: 24px; }}
.card-title {{ font-size: 16px; font-weight: 600; }}
.card-percent {{ margin-left: auto; font-size: 20px; font-weight: 800; }}
.card-bar {{ height: 8px; background: var(--surface2); border-radius: 4px; overflow: hidden; margin-bottom: 8px; }}
.card-bar-fill {{ height: 100%; border-radius: 4px; transition: width .5s ease; }}
.card-stats {{ display: flex; justify-content: space-between; font-size: 13px; color: var(--text2); }}

.modal-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 100; align-items: center; justify-content: center; }}
.modal-overlay.active {{ display: flex; }}
.modal {{ background: var(--surface); border-radius: var(--radius); padding: 24px; max-width: 700px; width: 90%; max-height: 80vh; overflow-y: auto; position: relative; }}
.modal h2 {{ font-size: 20px; margin-bottom: 16px; }}
.modal-close {{ position: absolute; top: 12px; right: 16px; background: none; border: none; color: var(--text2); font-size: 24px; cursor: pointer; }}
.modal-close:hover {{ color: var(--text); }}

.detail-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.detail-table th {{ text-align: left; padding: 8px; border-bottom: 1px solid var(--surface2); color: var(--text2); font-weight: 500; }}
.detail-table td {{ padding: 8px; border-bottom: 1px solid rgba(255,255,255,.05); }}
.detail-table tr:hover {{ background: rgba(255,255,255,.03); }}

.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
.badge-green {{ background: rgba(34,197,94,.15); color: var(--green); }}
.badge-yellow {{ background: rgba(234,179,8,.15); color: var(--yellow); }}
.badge-red {{ background: rgba(239,68,68,.15); color: var(--red); }}
.badge-blue {{ background: rgba(56,189,248,.15); color: var(--accent); }}

.unused-list {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
.unused-tag {{ background: var(--surface2); padding: 3px 8px; border-radius: 6px; font-size: 11px; font-family: monospace; color: var(--text2); }}

.footer {{ text-align: center; color: var(--text2); font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--surface2); }}
</style>
</head>
<body>

<div class="header">
  <h1>{strategy_name}</h1>
  <div class="code">{strategy_code}</div>
  <div class="meta">生成时间: {generated_at} &nbsp;|&nbsp; 用例总数: {total_cases} 条</div>
</div>

<div class="score-ring">
  <div class="ring-container">
    <svg viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="42" fill="none" stroke="var(--surface2)" stroke-width="8"/>
      <circle cx="50" cy="50" r="42" fill="none" stroke="{ring_color}" stroke-width="8"
              stroke-dasharray="{ring_filled} {ring_empty}"
              stroke-dashoffset="25" stroke-linecap="round" transform="rotate(-90 50 50)"/>
      <text x="50" y="46" text-anchor="middle" fill="var(--text)" font-size="18" font-weight="800">{overall_percent}%</text>
      <text x="50" y="60" text-anchor="middle" fill="var(--text2)" font-size="7">综合覆盖率</text>
    </svg>
    <div class="ring-label">7 维度加权均值</div>
  </div>
</div>

<div class="stats-row">
  <div class="stat-chip"><div class="val">{total_cases}</div><div class="lbl">总用例数</div></div>
  <div class="stat-chip"><div class="val">{sum(d['covered'] for d in dim_data)}/{sum(d['total'] for d in dim_data)}</div><div class="lbl">覆盖项/总项</div></div>
  <div class="stat-chip"><div class="val">{sum(1 for d in dim_data if d['percent'] >= 90)}/{len(dim_data)}</div><div class="lbl">达标维度(>=90%)</div></div>
</div>

<div class="grid" id="dimGrid"></div>

<div class="modal-overlay" id="modalOverlay">
  <div class="modal" id="modal">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <div id="modalContent"></div>
  </div>
</div>

<div class="footer">
  天策策略测试覆盖率热力图 Dashboard &nbsp;|&nbsp; tiance-testcase-generator v2.4.2 Phase 4-1
</div>

<script>
const DIM_DATA = {dim_json};
const ACTUAL_DIMS = {actual_json};
const DIFF_DATA = {diff_json};

function pctColor(p) {{
  if (p >= 90) return 'var(--green)';
  if (p >= 70) return 'var(--yellow)';
  if (p >= 50) return 'var(--orange)';
  return 'var(--red)';
}}

function badgeClass(p) {{
  if (p >= 90) return 'badge-green';
  if (p >= 70) return 'badge-yellow';
  return 'badge-red';
}}

function renderGrid() {{
  const grid = document.getElementById('dimGrid');
  DIM_DATA.forEach((d, i) => {{
    const card = document.createElement('div');
    card.className = 'card';
    card.onclick = () => showDetail(i);
    card.innerHTML = `
      <div class="card-header">
        <span class="card-icon">${{d.icon}}</span>
        <span class="card-title">${{d.label}}</span>
        <span class="card-percent" style="color:${{pctColor(d.percent)}}">${{d.percent}}%</span>
      </div>
      <div class="card-bar"><div class="card-bar-fill" style="width:${{d.percent}}%;background:${{pctColor(d.percent)}}"></div></div>
      <div class="card-stats">
        <span>${{d.covered}} / ${{d.total}} 项</span>
        <span class="badge ${{badgeClass(d.percent)}}">${{d.percent >= 90 ? '达标' : d.percent >= 70 ? '待提升' : '不足'}}</span>
      </div>
    `;
    grid.appendChild(card);
  }});
}}

function showDetail(idx) {{
  const d = DIM_DATA[idx];
  let html = '<h2>' + d.icon + ' ' + d.label + ' <span style="color:' + pctColor(d.percent) + '; font-size:24px">' + d.percent + '%</span></h2>';

  if (d.key === 'rules') {{
    html += '<table class="detail-table"><tr><th>规则</th><th>名称</th><th>规则集</th><th>用例</th><th>命中</th><th>未命中</th><th>边界</th></tr>';
    for (const [k, v] of Object.entries(d.detail)) {{
      html += '<tr><td><code>' + k + '</code></td><td>' + (v.name || '') + '</td><td>' + (v.ruleSet || '') + '</td>'
        + '<td>' + v.cases + '</td>'
        + '<td>' + (v.hasHit ? '<span class="badge badge-green">&#10003;</span>' : '<span class="badge badge-red">&#10007;</span>') + '</td>'
        + '<td>' + (v.hasMiss ? '<span class="badge badge-green">&#10003;</span>' : '<span class="badge badge-red">&#10007;</span>') + '</td>'
        + '<td>' + (v.hasBoundary ? '<span class="badge badge-green">&#10003;</span>' : '<span class="badge badge-red">&#10007;</span>') + '</td></tr>';
    }}
    html += '</table>';
  }} else if (d.key === 'ruleSets') {{
    html += '<table class="detail-table"><tr><th>规则集</th><th>名称</th><th>规则数</th><th>已测</th><th>用例</th><th>覆盖率</th></tr>';
    for (const [k, v] of Object.entries(d.detail)) {{
      html += '<tr><td><code>' + k + '</code></td><td>' + (v.name || '') + '</td><td>' + v.totalRules + '</td><td>' + v.rulesTested + '</td><td>' + v.cases + '</td><td><span class="badge ' + badgeClass(v.percent) + '">' + v.percent + '%</span></td></tr>';
    }}
    html += '</table>';
  }} else if (d.key === 'functions') {{
    html += '<table class="detail-table"><tr><th>函数</th><th>用例</th><th>正案例</th><th>反案例</th></tr>';
    for (const [k, v] of Object.entries(d.detail)) {{
      html += '<tr><td>' + k + '</td><td>' + v.cases + '</td>'
        + '<td>' + (v.hasPositive ? '<span class="badge badge-green">&#10003;</span>' : '<span class="badge badge-red">&#10007;</span>') + '</td>'
        + '<td>' + (v.hasNegative ? '<span class="badge badge-green">&#10003;</span>' : '<span class="badge badge-red">&#10007;</span>') + '</td></tr>';
    }}
    html += '</table>';
  }} else if (d.key === 'fields') {{
    const unused = d.detail.unused || [];
    html += '<p>策略字段总数: ' + d.total + ' | 已使用: ' + d.covered + ' | 未使用: ' + unused.length + '</p>';
    if (unused.length) {{
      html += '<div style="margin-top:12px"><strong>未覆盖字段:</strong></div><div class="unused-list">';
      unused.forEach(f => html += '<span class="unused-tag">' + f + '</span>');
      html += '</div>';
    }}
  }} else if (d.key === 'thirdParty') {{
    const refs = d.detail.referenced || [];
    html += '<p>三方接口总数: ' + d.total + ' | 已引用: ' + refs.length + '</p>';
    if (refs.length) {{
      html += '<table class="detail-table"><tr><th>#</th><th>接口名称</th><th>状态</th></tr>';
      refs.forEach((r, i) => {{
        html += '<tr><td>' + (i+1) + '</td><td>' + r + '</td><td><span class="badge badge-green">已覆盖</span></td></tr>';
      }});
      html += '</table>';
    }}
  }} else if (d.key === 'crossMatrix') {{
    html += '<p>可能组合: ' + d.total + ' | 已测组合: ' + d.covered + '</p>';
  }} else if (d.key === 'branches') {{
    html += '<table class="detail-table"><tr><th>分支类型</th><th>用例数</th></tr>';
    html += '<tr><td>决策流分支</td><td>' + (d.detail.flowCases || 0) + '</td></tr>';
    html += '<tr><td>组合场景</td><td>' + (d.detail.combinedCases || 0) + '</td></tr>';
    html += '</table>';
  }}

  if (ACTUAL_DIMS && ACTUAL_DIMS[d.key]) {{
    const a = ACTUAL_DIMS[d.key];
    const aPct = a.percent || 0;
    html += '<div style="margin-top:16px;padding:12px;background:var(--surface2);border-radius:8px">'
      + '<strong>实际覆盖率:</strong> <span style="color:' + pctColor(aPct) + '; font-weight:700">' + aPct + '%</span>'
      + ' (预期 ' + d.percent + '% -> 差距 ' + (d.percent - aPct).toFixed(1) + '%)</div>';
  }}

  document.getElementById('modalContent').innerHTML = html;
  document.getElementById('modalOverlay').classList.add('active');
}}

function closeModal() {{
  document.getElementById('modalOverlay').classList.remove('active');
}}

document.getElementById('modalOverlay').addEventListener('click', function(e) {{
  if (e.target === e.currentTarget) closeModal();
}});
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeModal(); }});

renderGrid();
</script>
</body>
</html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="覆盖率热力图 Dashboard 生成器",
        epilog="示例: python3 generate_coverage_dashboard.py coverage_pre_report.json",
    )
    parser.add_argument("pre_report", help="预期覆盖率报告 (coverage_pre_report.json)")
    parser.add_argument("--actual", default=None, help="实际覆盖率报告 (coverage_actual.json)")
    parser.add_argument("--diff", default=None, help="覆盖率差异报告 (coverage_diff.json)")
    parser.add_argument("-o", "--output", default=None, help="输出 HTML 路径（默认同目录 coverage_dashboard.html）")
    args = parser.parse_args()

    pre = load_json(args.pre_report)
    if not pre:
        print(f"错误：无法读取预期覆盖率报告: {args.pre_report}", file=sys.stderr)
        sys.exit(1)

    actual = load_json(args.actual) if args.actual else None
    diff = load_json(args.diff) if args.diff else None

    output = args.output or str(Path(args.pre_report).parent / "coverage_dashboard.html")
    generate_dashboard(pre, actual, diff, output)
    print(f"Dashboard 已生成: {output}", file=sys.stderr)
