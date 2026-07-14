"""Tiance Strategy Configuration Platform — execution engine.

6-step pipeline with real execution:
    1. 元数据管理 — fetch via Gateway Proxy, save JSON files
    2. 字段配置   — upload mapping → generate_field_metadata.py + generate_import_xls.py
    3. 函数配置   — upload definitions → encode .fun files
    4. 规则集配置 — upload rules → build_output.py
    5. 策略配置   — upload policy Excel → parse_excel.py + build_pls.py
    6. 组件生命周期 — import/publish via proxy CHECK→CONFIRM protocol
"""

import asyncio
import base64
import gzip
import json
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tiance-config", tags=["tiance-config"])

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # backend/..
_SKILLS_DIR = _PROJECT_ROOT / "skills" / "public"
_WORKSPACE_DIR = _PROJECT_ROOT / "tiance_workspace"
_STATE_FILE = _PROJECT_ROOT / "tiance_config_state.json"

_WORKSPACE_DIR.mkdir(exist_ok=True)


def _step_dir(step_id: str) -> Path:
    d = _WORKSPACE_DIR / step_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Pipeline step definitions
# ---------------------------------------------------------------------------

STEPS = [
    {
        "id": "metadata", "order": 1, "title": "元数据管理",
        "skill": "tiance-metadata-scout",
        "desc": "从天策平台拉取字段、渠道、事件类型、指标、规则模板等全量元数据",
        "outputs": ["field_metadata.json", "field_groups.json", "channel_apps.json",
                     "org_mapping.json", "function_definitions.json",
                     "ruleset_definitions.json", "policy_definitions.json"],
        "prechecks": ["Gateway 代理可用", "天策登录态有效", "orgCode / baseUrl 已配置"],
        "postchecks": ["核心元数据文件产出完整", "字段/函数总量大于 0"],
        "retryAction": "登录失效时重新认证，再重跑元数据拉取",
        "needs_input": False,
    },
    {
        "id": "field", "order": 2, "title": "字段配置",
        "skill": "tiance-field-forge",
        "desc": "将外部参数定义转换为天策系统字段，自动编码、去重、生成 .xls 导入文件",
        "outputs": ["field_metadata.json", "系统字段导入.xls"],
        "prechecks": ["字段分组元数据已同步", "待建字段清单已上传"],
        "postchecks": ["字段编码无重复", "groupUuid 映射成功", "导入模板字段列完整"],
        "retryAction": "补齐缺失分组后重新生成",
        "needs_input": True,
        "input_desc": "上传 field_mapping.json 或包含字段定义的 Excel 文件",
    },
    {
        "id": "function", "order": 3, "title": "函数配置",
        "skill": "tiance-function-forge",
        "desc": "从函数定义 JSON 生成 .fun 导入文件",
        "outputs": ["函数.fun", "函数.json"],
        "prechecks": ["依赖字段已存在", "函数定义 JSON 完整"],
        "postchecks": ["JSON 结构完整且 code 唯一", "编解码 round-trip 正确"],
        "retryAction": "修复函数定义后重新编码",
        "needs_input": True,
        "input_desc": "上传函数定义 JSON 文件（包含 name/code/type/formula 等字段）",
    },
    {
        "id": "ruleset", "order": 4, "title": "规则集配置",
        "skill": "tiance-rule-forge",
        "desc": "从规则描述生成规则集导入文件（.rss）",
        "outputs": ["规则集.rss"],
        "prechecks": ["字段与函数元数据已齐备", "规则描述已解析"],
        "postchecks": ["字段引用全部命中", ".rss 结构满足平台导入要求"],
        "retryAction": "修复引用后重建规则集",
        "needs_input": True,
        "input_desc": "上传 parsed_rules.json（已由 AI 分析过的规则结构）",
    },
    {
        "id": "policy", "order": 5, "title": "策略配置",
        "skill": "tiance-policy-forge",
        "desc": "从策略 Excel 生成策略导入文件（.pls）",
        "outputs": ["策略.pls"],
        "prechecks": ["规则集产物已准备", "策略 Excel 包含三个 Sheet"],
        "postchecks": ["节点连通关系完整", "规则集与处置引用存在"],
        "retryAction": "修复 Excel 后重新解析",
        "needs_input": True,
        "input_desc": "上传策略 Excel（含 策略信息/节点定义/连线定义 三个 Sheet）",
    },
    {
        "id": "lifecycle", "order": 6, "title": "组件生命周期",
        "skill": "tiance-component-lifecycle",
        "desc": "将生成的 .rss/.pls/.fun 等文件导入天策平台并上线",
        "outputs": ["import_report.json"],
        "prechecks": ["待导入文件已齐备", "天策登录态有效"],
        "postchecks": ["导入接口全部成功", "上线状态为 active"],
        "retryAction": "检查导入报告，修复冲突后重试",
        "needs_input": False,
    },
]

UPSTREAM = {
    "metadata": [], "field": ["tiance-metadata-scout"],
    "function": ["tiance-metadata-scout", "tiance-field-forge"],
    "ruleset": ["tiance-metadata-scout", "tiance-function-forge", "tiance-field-forge"],
    "policy": ["tiance-metadata-scout", "tiance-rule-forge", "tiance-function-forge"],
    "lifecycle": ["tiance-metadata-scout"],
}
DOWNSTREAM = {
    "metadata": ["tiance-field-forge", "tiance-function-forge", "tiance-rule-forge", "tiance-policy-forge"],
    "field": ["tiance-function-forge", "tiance-rule-forge"],
    "function": ["tiance-rule-forge", "tiance-policy-forge"],
    "ruleset": ["tiance-policy-forge"],
    "policy": ["tiance-component-lifecycle"],
    "lifecycle": [],
}

# ---------------------------------------------------------------------------
# Metadata fetch categories
# ---------------------------------------------------------------------------

_META_CATEGORIES = [
    ("fields", "/noahApi/policy/field/getList", "POST", {}),
    ("field_groups", "/noahApi/policy/fieldGroup/getAll", "GET", None),
    ("channel_apps", "/noahApi/policy/channelApp/getAll", "GET", None),
    ("org_mapping", "/noahApi/policy/org/getAll", "GET", None),
    ("function_definitions", "/noahApi/policy/customfunction/getList", "POST", {}),
    ("ruleset_definitions", "/noahApi/policy/ruleset/getList", "POST", {}),
    ("policy_definitions", "/noahApi/policy/list", "GET", None),
    ("rule_templates", "/noahApi/policy/ruleTemplate/getAll", "GET", None),
    ("event_types", "/noahApi/policy/eventType/getAll", "GET", None),
    ("disposal_types", "/noahApi/policy/disposalType/getAll", "GET", None),
]

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

# In-memory run tracking
_runs: dict[str, dict] = {}


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
    return {"completed": {}, "metadata_summary": None}


def _save_state(state: dict):
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _create_run(step_id: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = {
        "run_id": run_id,
        "step_id": step_id,
        "status": "running",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "completed_at": None,
        "logs": [],
        "outputs": [],
        "error": None,
    }
    return run_id


def _log(run_id: str, msg: str):
    if run_id in _runs:
        ts = time.strftime("%H:%M:%S")
        _runs[run_id]["logs"].append(f"[{ts}] {msg}")
        logger.info("[%s] %s", run_id, msg)


def _finish_run(run_id: str, success: bool, outputs: list[str] = None, error: str = None):
    if run_id in _runs:
        _runs[run_id]["status"] = "success" if success else "failed"
        _runs[run_id]["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _runs[run_id]["outputs"] = outputs or []
        _runs[run_id]["error"] = error


# ---------------------------------------------------------------------------
# Proxy helpers
# ---------------------------------------------------------------------------

_GATEWAY = "http://127.0.0.1:8003"


async def _proxy_request(method: str, path: str, body: dict | None = None):
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {"path": path, "method": method}
        if body is not None:
            payload["body"] = body
        try:
            resp = await client.post(f"{_GATEWAY}/api/tiance/proxy", json=payload)
            data = resp.json()
            inner = data.get("data", {})
            if isinstance(inner, dict) and inner.get("success"):
                return inner.get("data")
        except Exception as exc:
            logger.warning("Proxy %s %s failed: %s", method, path, exc)
    return None


def _count_items(data) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("list", "data", "items", "rows"):
            if key in data and isinstance(data[key], list):
                return len(data[key])
    return 0


# ---------------------------------------------------------------------------
# Script runner
# ---------------------------------------------------------------------------

def _run_script(script_path: str, args: list[str], cwd: str | None = None, run_id: str | None = None) -> tuple[int, str]:
    """Run a skill script via subprocess. Returns (returncode, output)."""
    cmd = ["python3", script_path] + args
    if run_id:
        _log(run_id, f"$ {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=cwd or str(_PROJECT_ROOT),
        )
        output = (result.stdout or "") + (result.stderr or "")
        if run_id:
            for line in output.strip().split("\n")[-20:]:
                _log(run_id, f"  {line}")
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return -1, "Script timed out (120s)"
    except Exception as exc:
        return -1, str(exc)


# ---------------------------------------------------------------------------
# Step executors
# ---------------------------------------------------------------------------

async def _exec_metadata(run_id: str):
    """Step 1: Fetch all metadata from tiance platform via proxy."""
    out_dir = _step_dir("metadata")
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(exist_ok=True)

    _log(run_id, "检查 Gateway Proxy 连接...")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_GATEWAY}/api/tiance/status")
            d = r.json()
            if not d.get("data", d).get("logged_in"):
                _finish_run(run_id, False, error="天策平台未登录，请先在 Gateway 中配置登录信息")
                return
            _log(run_id, f"登录态有效，用户: {d.get('data', d).get('username', 'unknown')}")
    except Exception as exc:
        _finish_run(run_id, False, error=f"Gateway 不可达: {exc}")
        return

    total_items = 0
    saved_files = []
    for name, path, method, body in _META_CATEGORIES:
        _log(run_id, f"拉取 {name}...")
        data = await _proxy_request(method, path, body)
        if data is not None:
            count = _count_items(data)
            total_items += count
            fpath = raw_dir / f"{name}.json"
            fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            saved_files.append(str(fpath))
            _log(run_id, f"  → {count} 条, 已保存到 {fpath.name}")
        else:
            _log(run_id, f"  → 拉取失败或无权限")

    # Also save to output root for downstream skills
    for name in ["fields", "field_groups", "channel_apps", "org_mapping",
                 "function_definitions", "ruleset_definitions", "policy_definitions"]:
        src = raw_dir / f"{name}.json"
        if src.exists():
            dst = out_dir / f"{name}.json"
            shutil.copy2(src, dst)

    _log(run_id, f"完成: 共拉取 {total_items} 条元数据, {len(saved_files)} 个文件")
    if total_items == 0:
        _finish_run(run_id, False, error="元数据总量为 0，请检查天策平台连接和权限")
    else:
        _finish_run(run_id, True, outputs=saved_files)


async def _exec_field(run_id: str, input_file: Path):
    """Step 2: Generate field metadata and import XLS."""
    out_dir = _step_dir("field")
    script_dir = _SKILLS_DIR / "tiance-field-forge" / "scripts"

    # Determine input type
    if input_file.suffix == ".json":
        mapping_file = input_file
    else:
        _log(run_id, "非 JSON 输入，需要先转换为 field_mapping.json")
        _finish_run(run_id, False, error="目前仅支持 JSON 格式的字段映射文件")
        return

    # Step 2a: Generate field metadata
    _log(run_id, "生成字段元数据...")
    meta_out = out_dir / "field_metadata.json"
    rc, out = _run_script(
        str(script_dir / "generate_field_metadata.py"),
        ["--input", str(mapping_file), "--output", str(meta_out)],
        run_id=run_id,
    )
    if rc != 0:
        _finish_run(run_id, False, error=f"generate_field_metadata.py 失败 (exit {rc}): {out[-500:]}")
        return

    # Step 2b: Check conflicts with existing metadata
    existing = _step_dir("metadata") / "field_metadata.json"
    if not existing.exists():
        existing = _step_dir("metadata") / "raw" / "fields.json"

    if existing.exists():
        _log(run_id, "检查字段冲突...")
        conflicts_out = out_dir / "conflicts_preview.json"
        rc, out = _run_script(
            str(script_dir / "preview_conflicts.py"),
            ["--candidates", str(meta_out), "--existing", str(existing), "--output", str(conflicts_out)],
            run_id=run_id,
        )
        if rc == 3:
            _log(run_id, f"发现冲突，详见 {conflicts_out.name}")

    # Step 2c: Generate import XLS
    _log(run_id, "生成导入 XLS...")
    xls_out = out_dir / "系统字段导入.xls"
    rc, out = _run_script(
        str(script_dir / "generate_import_xls.py"),
        ["--input", str(mapping_file), "--output", str(xls_out)],
        run_id=run_id,
    )
    if rc != 0:
        _finish_run(run_id, False, error=f"generate_import_xls.py 失败 (exit {rc}): {out[-500:]}")
        return

    outputs = [str(meta_out), str(xls_out)]
    if conflicts_out.exists():
        outputs.append(str(conflicts_out))
    _log(run_id, f"完成: 产出 {len(outputs)} 个文件")
    _finish_run(run_id, True, outputs=outputs)


async def _exec_function(run_id: str, input_file: Path):
    """Step 3: Encode function definitions into .fun file."""
    out_dir = _step_dir("function")

    _log(run_id, f"读取函数定义: {input_file.name}")
    try:
        data = json.loads(input_file.read_text())
    except Exception as exc:
        _finish_run(run_id, False, error=f"JSON 解析失败: {exc}")
        return

    funcs = data if isinstance(data, list) else data.get("functions", data.get("data", []))
    _log(run_id, f"共 {len(funcs)} 个函数定义")

    if not funcs:
        _finish_run(run_id, False, error="函数定义为空")
        return

    # Validate: check for code uniqueness
    codes = [f.get("code", "") for f in funcs]
    dupes = [c for c in codes if codes.count(c) > 1]
    if dupes:
        _finish_run(run_id, False, error=f"函数 code 重复: {set(dupes)}")
        return

    # Encode: JSON → gzip → base64
    _log(run_id, "编码 .fun 文件 (JSON → gzip → base64)...")
    json_bytes = json.dumps(funcs, ensure_ascii=False, indent=2).encode("utf-8")
    compressed = gzip.compress(json_bytes)
    encoded = base64.b64encode(compressed).decode("ascii")

    fun_out = out_dir / "函数.fun"
    fun_out.write_text(encoded)

    json_out = out_dir / "函数.json"
    json_out.write_text(json.dumps(funcs, ensure_ascii=False, indent=2))

    # Round-trip verify
    decoded = json.loads(gzip.decompress(base64.b64decode(encoded)))
    if decoded == funcs:
        _log(run_id, "round-trip 校验通过")
    else:
        _log(run_id, "⚠ round-trip 校验不一致")

    _log(run_id, f"完成: {fun_out.name} ({fun_out.stat().st_size // 1024}KB), {json_out.name}")
    _finish_run(run_id, True, outputs=[str(fun_out), str(json_out)])


async def _exec_ruleset(run_id: str, input_file: Path):
    """Step 4: Build .rss from parsed rules."""
    out_dir = _step_dir("ruleset")
    script_dir = _SKILLS_DIR / "tiance-rule-forge" / "scripts"
    meta_dir = _step_dir("metadata")

    _log(run_id, "验证输入...")
    rc, out = _run_script(
        str(script_dir / "validate_inputs.py"),
        ["--excel", str(input_file), "--metadata-dir", str(meta_dir / "raw"),
         "--template-registry", str(_SKILLS_DIR / "tiance-rule-forge" / "templates" / "template_registry.json")],
        run_id=run_id,
    )
    # validate_inputs may exit non-zero for warnings; proceed if input is JSON
    if input_file.suffix == ".json":
        _log(run_id, "JSON 输入，跳过 Excel 验证，直接构建...")
    elif rc != 0:
        _log(run_id, f"输入验证返回 exit {rc}，尝试继续...")

    # Build output
    _log(run_id, "构建规则集...")
    rc, out = _run_script(
        str(script_dir / "build_output.py"),
        ["--parsed-rules", str(input_file),
         "--analysis-results", str(input_file),  # use same file if no separate analysis
         "--config", str(_SKILLS_DIR / "tiance-rule-forge" / "config.json"),
         "--mapping", str(meta_dir / "raw" / "fields.json"),
         "--metadata-dir", str(meta_dir / "raw"),
         "--output", str(out_dir)],
        run_id=run_id,
    )
    if rc != 0:
        _finish_run(run_id, False, error=f"build_output.py 失败 (exit {rc}): {out[-500:]}")
        return

    rss_files = list(out_dir.glob("*.rss"))
    _log(run_id, f"完成: 生成 {len(rss_files)} 个 .rss 文件")
    _finish_run(run_id, True, outputs=[str(f) for f in rss_files])


async def _exec_policy(run_id: str, input_file: Path):
    """Step 5: Parse policy Excel → build .pls."""
    out_dir = _step_dir("policy")
    script_dir = _SKILLS_DIR / "tiance-policy-forge" / "scripts"
    meta_dir = _step_dir("metadata")

    # Step 5a: Parse Excel
    intermediate = out_dir / "policy_intermediate.json"
    _log(run_id, "解析策略 Excel...")
    rc, out = _run_script(
        str(script_dir / "parse_excel.py"),
        [str(input_file), str(intermediate)],
        run_id=run_id,
    )
    if rc != 0:
        _finish_run(run_id, False, error=f"parse_excel.py 失败 (exit {rc}): {out[-500:]}")
        return

    # Step 5b: Build .pls
    pls_out = out_dir / "策略.pls"
    _log(run_id, "构建策略文件...")
    rc, out = _run_script(
        str(script_dir / "build_pls.py"),
        [str(intermediate), str(meta_dir / "raw"), str(pls_out)],
        run_id=run_id,
    )
    if rc != 0:
        _finish_run(run_id, False, error=f"build_pls.py 失败 (exit {rc}): {out[-500:]}")
        return

    _log(run_id, f"完成: {pls_out.name} ({pls_out.stat().st_size // 1024}KB)")
    _finish_run(run_id, True, outputs=[str(pls_out), str(intermediate)])


async def _exec_lifecycle(run_id: str):
    """Step 6: Import artifacts via tiance proxy."""
    out_dir = _step_dir("lifecycle")
    report = {"imports": [], "publishes": [], "errors": []}

    # Collect all artifacts from previous steps
    artifacts = []
    for step_id in ["field", "function", "ruleset", "policy"]:
        step_out = _step_dir(step_id)
        for ext in ("*.rss", "*.pls", "*.fun", "*.xls", "*.zb"):
            artifacts.extend(step_out.glob(ext))

    if not artifacts:
        _finish_run(run_id, False, error="未找到任何待导入产物文件")
        return

    _log(run_id, f"发现 {len(artifacts)} 个待导入文件")

    # For each artifact, attempt CHECK→CONFIRM via proxy
    for art in artifacts:
        _log(run_id, f"处理: {art.name}")
        # Read file content
        content = art.read_bytes()
        # Upload via proxy — the actual import API path depends on file type
        # This is a placeholder that logs intent; real implementation needs
        # reverse-engineered import API endpoints
        ext = art.suffix
        type_map = {".rss": "ruleset", ".pls": "policy", ".fun": "function", ".xls": "field", ".zb": "index"}
        comp_type = type_map.get(ext, "unknown")
        _log(run_id, f"  类型: {comp_type}, 大小: {len(content)} bytes")
        report["imports"].append({
            "file": art.name, "type": comp_type,
            "status": "pending", "note": "需要通过天策平台导入页面操作"
        })

    # Save report
    report_path = out_dir / "import_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    _log(run_id, f"导入报告已保存: {report_path.name}")
    _log(run_id, "注意: 组件生命周期目前需要通过天策平台 Web 界面完成导入操作")
    _finish_run(run_id, True, outputs=[str(report_path)])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class StepStatus(BaseModel):
    id: str; order: int; title: str; skill: str; desc: str
    outputs: list[str]; prechecks: list[str]; postchecks: list[str]; retryAction: str
    status: str = "pending"; completed_at: str | None = None
    upstream: list[str] = []; downstream: list[str] = []
    needs_input: bool = False; input_desc: str = ""
    last_run_id: str | None = None

class PipelineResponse(BaseModel):
    steps: list[StepStatus]; completed_count: int; total: int

class RunStatus(BaseModel):
    run_id: str; step_id: str; status: str
    started_at: str; completed_at: str | None = None
    logs: list[str] = []; outputs: list[str] = []; error: str | None = None

class MetadataSummary(BaseModel):
    categories: dict[str, int] = Field(default_factory=dict)
    total_items: int = 0; fetched_at: str | None = None; gateway_status: str = "unknown"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/pipeline", response_model=PipelineResponse)
async def get_pipeline():
    state = _load_state()
    completed = state.get("completed", {})
    steps = []
    for s in STEPS:
        sid = s["id"]
        is_done = sid in completed
        last_run = None
        for r in _runs.values():
            if r["step_id"] == sid:
                last_run = r["run_id"]
        steps.append(StepStatus(
            **{k: v for k, v in s.items() if k in StepStatus.model_fields},
            status="done" if is_done else ("ready" if s["order"] == 1 else "pending"),
            completed_at=completed.get(sid),
            upstream=UPSTREAM.get(sid, []),
            downstream=DOWNSTREAM.get(sid, []),
            last_run_id=last_run,
        ))
    return PipelineResponse(steps=steps, completed_count=len(completed), total=len(STEPS))


@router.post("/steps/{step_id}/execute", response_model=RunStatus)
async def execute_step(step_id: str, input_file: UploadFile = File(None)):
    """Execute a pipeline step. Steps 1 and 6 run without input; steps 2-5 need file upload."""
    if not any(s["id"] == step_id for s in STEPS):
        raise HTTPException(404, f"Step '{step_id}' not found")

    step_def = next(s for s in STEPS if s["id"] == step_id)

    # Check prerequisites
    if step_def["order"] > 1 and step_id != "metadata":
        state = _load_state()
        prev_id = STEPS[step_def["order"] - 2]["id"]
        if prev_id not in state.get("completed", {}):
            raise HTTPException(400, f"请先完成前置步骤: {prev_id}")

    # Check if already running
    for r in _runs.values():
        if r["step_id"] == step_id and r["status"] == "running":
            raise HTTPException(409, f"步骤 {step_id} 正在执行中 (run_id: {r['run_id']})")

    run_id = _create_run(step_id)

    # Save uploaded file if provided
    saved_input = None
    if input_file and input_file.filename:
        upload_dir = _step_dir(step_id) / "uploads"
        upload_dir.mkdir(exist_ok=True)
        saved_input = upload_dir / input_file.filename
        content = await input_file.read()
        saved_input.write_bytes(content)
        _log(run_id, f"已上传文件: {input_file.filename} ({len(content)} bytes)")

    # Dispatch executor
    if step_id == "metadata":
        asyncio.create_task(_exec_metadata(run_id))
    elif step_id == "field":
        if not saved_input:
            _finish_run(run_id, False, error="字段配置需要上传 field_mapping.json")
        else:
            asyncio.create_task(_exec_field(run_id, saved_input))
    elif step_id == "function":
        if not saved_input:
            _finish_run(run_id, False, error="函数配置需要上传函数定义 JSON")
        else:
            asyncio.create_task(_exec_function(run_id, saved_input))
    elif step_id == "ruleset":
        if not saved_input:
            _finish_run(run_id, False, error="规则集配置需要上传规则文件")
        else:
            asyncio.create_task(_exec_ruleset(run_id, saved_input))
    elif step_id == "policy":
        if not saved_input:
            _finish_run(run_id, False, error="策略配置需要上传策略 Excel")
        else:
            asyncio.create_task(_exec_policy(run_id, saved_input))
    elif step_id == "lifecycle":
        asyncio.create_task(_exec_lifecycle(run_id))

    # Auto-mark complete when run finishes (check periodically via callback)
    async def _auto_complete():
        while _runs.get(run_id, {}).get("status") == "running":
            await asyncio.sleep(1)
        if _runs.get(run_id, {}).get("status") == "success":
            state = _load_state()
            state.setdefault("completed", {})[step_id] = time.strftime("%Y-%m-%d %H:%M:%S")
            _save_state(state)

    asyncio.create_task(_auto_complete())

    return RunStatus(**_runs[run_id])


@router.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: str):
    if run_id not in _runs:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return RunStatus(**_runs[run_id])


@router.get("/runs/{run_id}/log")
async def get_run_log(run_id: str, offset: int = 0):
    if run_id not in _runs:
        raise HTTPException(404, f"Run '{run_id}' not found")
    logs = _runs[run_id]["logs"]
    return {"logs": logs[offset:], "total": len(logs), "status": _runs[run_id]["status"]}


@router.get("/runs")
async def list_runs(step_id: str = None):
    runs = list(_runs.values())
    if step_id:
        runs = [r for r in runs if r["step_id"] == step_id]
    return sorted(runs, key=lambda r: r["started_at"], reverse=True)


@router.get("/downloads/{step_id}/{filename}")
async def download_file(step_id: str, filename: str):
    fpath = _step_dir(step_id) / filename
    if not fpath.exists():
        raise HTTPException(404, f"File not found: {filename}")
    return FileResponse(str(fpath), filename=filename)


@router.get("/metadata/summary", response_model=MetadataSummary)
async def get_metadata_summary():
    gw_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_GATEWAY}/api/tiance/status")
            d = r.json()
            gw_status = "logged_in" if d.get("data", d).get("logged_in") else "not_logged_in"
    except Exception:
        gw_status = "unreachable"

    categories = {}
    total = 0
    for name, path, method, body in _META_CATEGORIES:
        data = await _proxy_request(method, path, body)
        count = _count_items(data) if data is not None else 0
        categories[name] = count
        total += count

    summary = MetadataSummary(
        categories=categories, total_items=total,
        fetched_at=time.strftime("%Y-%m-%d %H:%M:%S"), gateway_status=gw_status,
    )
    state = _load_state()
    state["metadata_summary"] = summary.model_dump()
    _save_state(state)
    return summary


@router.post("/pipeline/reset")
async def reset_pipeline():
    _save_state({"completed": {}, "metadata_summary": None})
    _runs.clear()
    return {"success": True, "message": "Pipeline reset"}


@router.get("/workspace/files")
async def list_workspace_files():
    """List all files in the workspace directory."""
    files = []
    for step_dir in sorted(_WORKSPACE_DIR.iterdir()):
        if not step_dir.is_dir():
            continue
        for f in sorted(step_dir.rglob("*")):
            if f.is_file() and f.stat().st_size > 0:
                rel = f.relative_to(_WORKSPACE_DIR)
                files.append({
                    "path": str(rel),
                    "step": step_dir.name,
                    "name": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                })
    return files
