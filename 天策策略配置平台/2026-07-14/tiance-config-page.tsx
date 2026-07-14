"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2, Circle, Lock, FileText, RefreshCw,
  ArrowRight, ArrowLeft, Play, Upload, Loader2, Download,
  ChevronLeft, AlertTriangle,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface StepData {
  id: string; order: number; title: string; skill: string; desc: string;
  outputs: string[]; prechecks: string[]; postchecks: string[]; retryAction: string;
  status: "pending" | "ready" | "done" | "error";
  completed_at: string | null; upstream: string[]; downstream: string[];
  needs_input: boolean; input_desc: string; last_run_id: string | null;
}
interface PipelineData { steps: StepData[]; completed_count: number; total: number; }
interface RunData {
  run_id: string; step_id: string; status: string;
  started_at: string; completed_at: string | null;
  logs: string[]; outputs: string[]; error: string | null;
}
interface MetadataSummary {
  categories: Record<string, number>; total_items: number;
  fetched_at: string | null; gateway_status: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const FLOW_RULES = [
  { tone: "red", title: "硬校验", detail: "失败即阻断当前步骤。例：登录失效、DSL 语法错误、code 重复、groupUuid 为空。" },
  { tone: "yellow", title: "软校验", detail: "记录风险但不阻断。例：description 为空、未使用入参、单行表达式过长。" },
  { tone: "blue", title: "平台预检", detail: "导入前做重名、签名等价、模糊重复三层比对，命中后要求人工确认。" },
];
const CATEGORY_LABELS: Record<string, string> = {
  fields: "字段", field_groups: "字段分组", channel_apps: "渠道应用", org_mapping: "机构映射",
  function_definitions: "函数定义", ruleset_definitions: "规则集", policy_definitions: "策略",
  rule_templates: "规则模板", event_types: "事件类型", disposal_types: "处置类型",
};
const GRADIENT_MAP: Record<string, string> = {
  metadata: "from-blue-500 to-blue-600", field: "from-emerald-500 to-emerald-600",
  function: "from-amber-500 to-amber-600", ruleset: "from-purple-500 to-purple-600",
  policy: "from-rose-500 to-rose-600", lifecycle: "from-cyan-500 to-cyan-600",
};
const ICON_MAP: Record<string, string> = {
  metadata: "🔍", field: "📋", function: "ƒ", ruleset: "📐", policy: "🎯", lifecycle: "🚀",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function TianceConfigPage() {
  const [pipeline, setPipeline] = useState<PipelineData | null>(null);
  const [metadata, setMetadata] = useState<MetadataSummary | null>(null);
  const [activeTab, setActiveTab] = useState<"config" | "overview">("config");
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Execution state
  const [currentRun, setCurrentRun] = useState<RunData | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchPipeline = useCallback(async () => {
    try {
      const res = await fetch("/api/tiance-config/pipeline");
      if (res.ok) setPipeline(await res.json());
    } catch { /* ignore */ }
  }, []);

  const fetchMetadata = useCallback(async () => {
    try {
      const res = await fetch("/api/tiance-config/metadata/summary");
      if (res.ok) setMetadata(await res.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    Promise.all([fetchPipeline(), fetchMetadata()]).finally(() => setLoading(false));
  }, [fetchPipeline, fetchMetadata]);

  // Poll run status during execution
  const pollRun = useCallback((runId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/tiance-config/runs/${runId}`);
        if (res.ok) {
          const data: RunData = await res.json();
          setCurrentRun(data);
          if (data.status !== "running") {
            clearInterval(pollRef.current!);
            pollRef.current = null;
            setIsExecuting(false);
            fetchPipeline();
            fetchMetadata();
          }
        }
      } catch { /* ignore */ }
    }, 1000);
  }, [fetchPipeline, fetchMetadata]);

  useEffect(() => {
    if (logEndRef.current) logEndRef.current.scrollIntoView({ behavior: "smooth" });
  }, [currentRun?.logs]);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // Execute a step
  const executeStep = async (stepId: string) => {
    const step = pipeline?.steps.find(s => s.id === stepId);
    if (!step) return;

    setIsExecuting(true);
    setCurrentRun(null);

    const formData = new FormData();
    if (uploadFile) formData.append("input_file", uploadFile);

    try {
      const res = await fetch(`/api/tiance-config/steps/${stepId}/execute`, {
        method: "POST", body: formData,
      });
      if (res.ok) {
        const run: RunData = await res.json();
        setCurrentRun(run);
        pollRun(run.run_id);
      } else {
        const err = await res.json();
        setCurrentRun({
          run_id: "error", step_id: stepId, status: "failed",
          started_at: "", completed_at: "", logs: [], outputs: [],
          error: err.detail || "执行失败",
        });
        setIsExecuting(false);
      }
    } catch (e) {
      setCurrentRun({
        run_id: "error", step_id: stepId, status: "failed",
        started_at: "", completed_at: "", logs: [], outputs: [],
        error: String(e),
      });
      setIsExecuting(false);
    }
    setUploadFile(null);
  };

  const resetPipeline = async () => {
    await fetch("/api/tiance-config/pipeline/reset", { method: "POST" });
    fetchPipeline(); setCurrentRun(null);
  };

  const currentStep = pipeline?.steps.find(s => s.id === selectedStep) ?? null;

  // --- Render ---

  const renderPipelineBar = () => {
    if (!pipeline) return null;
    return (
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {pipeline.steps.map((step, i) => {
          const isDone = step.status === "done";
          const isActive = selectedStep === step.id;
          return (
            <div key={step.id} className="flex items-center gap-2">
              <button onClick={() => setSelectedStep(step.id)} className="flex items-center gap-3 cursor-pointer">
                <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white shrink-0 transition-all
                  ${isDone ? "bg-emerald-500" : isActive ? "bg-blue-600 ring-4 ring-blue-200" : "bg-gray-300"}`}>
                  {isDone ? "✓" : step.order}
                </div>
                <div className="text-left">
                  <div className={`text-sm font-semibold ${isActive ? "text-blue-600" : isDone ? "text-emerald-600" : "text-gray-700"}`}>
                    {step.title}
                  </div>
                  <div className="text-xs text-gray-400">{step.skill}</div>
                </div>
              </button>
              {i < pipeline.steps.length - 1 && (
                <div className={`w-8 h-0.5 shrink-0 ${isDone ? "bg-emerald-300" : "bg-gray-200"}`} />
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const renderModuleCards = () => {
    if (!pipeline) return null;
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {pipeline.steps.map((step) => {
          const isActive = selectedStep === step.id;
          const isLocked = step.status === "pending" && step.order > 1;
          return (
            <button key={step.id} onClick={() => setSelectedStep(step.id)}
              className={`text-left rounded-2xl border-2 p-5 transition-all relative
                ${isActive ? "border-blue-300 bg-blue-50/50 shadow-lg shadow-blue-100" : "border-gray-200 bg-white hover:border-gray-300"}
                ${isLocked ? "opacity-60" : ""}`}>
              {isLocked && (
                <span className="absolute top-3 right-3 text-xs bg-gray-100 text-gray-500 px-2 py-1 rounded-full flex items-center gap-1">
                  <Lock className="w-3 h-3" /> 依赖前置
                </span>
              )}
              {step.status === "done" && (
                <span className="absolute top-3 right-3 text-xs bg-emerald-100 text-emerald-700 px-2 py-1 rounded-full flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> 已完成
                </span>
              )}
              <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${GRADIENT_MAP[step.id] ?? "from-gray-400 to-gray-500"} flex items-center justify-center text-white text-lg mb-3`}>
                {ICON_MAP[step.id]}
              </div>
              <h3 className="text-base font-bold mb-1">{step.title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed mb-3 min-h-[3rem]">{step.desc}</p>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {step.outputs.map(o => (
                  <span key={o} className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">{o}</span>
                ))}
              </div>
              <div className="text-xs text-gray-400 font-mono">{step.skill}</div>
            </button>
          );
        })}
      </div>
    );
  };

  const renderLogPanel = () => {
    if (!currentRun) return null;
    const isRunning = currentRun.status === "running";
    const isSuccess = currentRun.status === "success";
    return (
      <div className={`rounded-xl border ${isSuccess ? "border-emerald-200 bg-emerald-50" : isRunning ? "border-blue-200 bg-blue-50" : "border-red-200 bg-red-50"} p-4 mt-4`}>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-bold flex items-center gap-2">
            {isRunning && <Loader2 className="w-4 h-4 animate-spin text-blue-600" />}
            {isSuccess && <CheckCircle2 className="w-4 h-4 text-emerald-600" />}
            {!isRunning && !isSuccess && <AlertTriangle className="w-4 h-4 text-red-600" />}
            执行日志
          </h4>
          <span className="text-xs text-gray-500">{currentRun.started_at}</span>
        </div>
        {/* Log output */}
        <div className="bg-gray-900 rounded-lg p-3 max-h-48 overflow-y-auto font-mono text-xs text-gray-300 space-y-0.5">
          {currentRun.logs.map((log, i) => (
            <div key={i} className={log.includes("→") ? "text-emerald-400" : log.includes("⚠") || log.includes("失败") ? "text-amber-400" : ""}>
              {log}
            </div>
          ))}
          {isRunning && <div className="text-blue-400 animate-pulse">执行中...</div>}
          <div ref={logEndRef} />
        </div>
        {/* Outputs */}
        {currentRun.outputs.length > 0 && (
          <div className="mt-3">
            <p className="text-xs font-bold text-gray-600 mb-1">产出文件:</p>
            <div className="flex flex-wrap gap-2">
              {currentRun.outputs.map((o, i) => {
                const fname = o.split("/").pop() || o;
                const stepId = currentRun.step_id;
                return (
                  <a key={i} href={`/api/tiance-config/downloads/${stepId}/${fname}`}
                    className="text-xs bg-white border border-gray-200 rounded-lg px-2 py-1 flex items-center gap-1 hover:bg-gray-50">
                    <Download className="w-3 h-3" /> {fname}
                  </a>
                );
              })}
            </div>
          </div>
        )}
        {/* Error */}
        {currentRun.error && (
          <div className="mt-3 text-sm text-red-700 bg-red-100 rounded-lg p-3">{currentRun.error}</div>
        )}
      </div>
    );
  };

  const renderDetailPanel = () => {
    if (!currentStep) {
      return (
        <div className="flex items-center justify-center h-full min-h-[600px] text-gray-400">
          <div className="text-center">
            <ChevronLeft className="w-10 h-10 mx-auto mb-3 opacity-50" />
            <p>点击左侧模块查看详情</p>
          </div>
        </div>
      );
    }
    const s = currentStep;
    const isDone = s.status === "done";
    const isLocked = s.status === "pending" && s.order > 1;

    return (
      <div className="p-6 space-y-5">
        <div className="flex items-center gap-4">
          <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${GRADIENT_MAP[s.id] ?? "from-gray-400 to-gray-500"} flex items-center justify-center text-white text-2xl`}>
            {ICON_MAP[s.id]}
          </div>
          <div>
            <h2 className="text-xl font-bold">{s.title}</h2>
            <span className="text-xs text-gray-400 font-mono">{s.skill}</span>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
          <h4 className="text-sm font-bold mb-2">功能说明</h4>
          <p className="text-sm text-gray-600 leading-relaxed">{s.desc}</p>
        </div>

        <div>
          <h4 className="text-sm font-bold mb-2">产出文件</h4>
          <div className="space-y-2">
            {s.outputs.map(o => (
              <div key={o} className="flex items-center gap-2 border border-gray-200 rounded-xl px-3 py-2.5 bg-white text-sm">
                <FileText className="w-4 h-4 text-emerald-500 shrink-0" />
                <span className="font-mono text-gray-700">{o}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <h4 className="text-xs font-bold mb-2 text-gray-500">上游依赖</h4>
            {s.upstream.length === 0 ? <p className="text-xs text-gray-400">无前置依赖</p> : (
              <div className="space-y-1.5">
                {s.upstream.map(u => (
                  <div key={u} className="flex items-center gap-1.5 text-xs">
                    <ArrowLeft className="w-3 h-3 text-blue-500" />
                    <span className="font-mono bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{u}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <h4 className="text-xs font-bold mb-2 text-gray-500">下游消费</h4>
            {s.downstream.length === 0 ? <p className="text-xs text-gray-400">终端环节</p> : (
              <div className="space-y-1.5">
                {s.downstream.map(d => (
                  <div key={d} className="flex items-center gap-1.5 text-xs">
                    <ArrowRight className="w-3 h-3 text-orange-500" />
                    <span className="font-mono bg-orange-50 text-orange-700 px-2 py-0.5 rounded-full">{d}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-3">
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
            <h4 className="text-xs font-bold mb-2">执行前校验</h4>
            {s.prechecks.map((c, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-gray-600 mt-1">
                <Circle className="w-3 h-3 text-blue-500 mt-1 shrink-0" /><span>{c}</span>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <h4 className="text-xs font-bold mb-2">生成后校验</h4>
            {s.postchecks.map((c, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-gray-600 mt-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-500 mt-1 shrink-0" /><span>{c}</span>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <h4 className="text-xs font-bold mb-2 text-amber-800">失败处理</h4>
            <p className="text-sm text-amber-700">{s.retryAction}</p>
          </div>
        </div>

        {/* Execution section */}
        <div className="border-t border-gray-200 pt-4">
          {/* File upload for steps that need input */}
          {s.needs_input && !isDone && (
            <div className="mb-4">
              <p className="text-xs text-gray-500 mb-2">{s.input_desc}</p>
              <label className="flex items-center gap-2 border-2 border-dashed border-gray-300 rounded-xl p-4 cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition">
                <Upload className="w-5 h-5 text-gray-400" />
                <span className="text-sm text-gray-500">
                  {uploadFile ? uploadFile.name : "点击上传文件..."}
                </span>
                <input type="file" className="hidden"
                  onChange={e => setUploadFile(e.target.files?.[0] ?? null)} />
              </label>
            </div>
          )}

          {/* Execute button */}
          <button
            onClick={() => executeStep(s.id)}
            disabled={isLocked || isExecuting || (s.needs_input && !uploadFile && !isDone)}
            className={`w-full rounded-xl py-3 font-bold text-sm text-white transition flex items-center justify-center gap-2
              bg-gradient-to-r ${GRADIENT_MAP[s.id] ?? "from-gray-400 to-gray-500"}
              hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed`}>
            {isExecuting ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> 执行中...</>
            ) : isDone ? (
              <><RefreshCw className="w-4 h-4" /> 重新执行</>
            ) : (
              <><Play className="w-4 h-4" /> {isLocked ? "请先完成前置步骤" : `执行 ${s.title}`}</>
            )}
          </button>

          {isDone && s.completed_at && (
            <p className="text-xs text-center text-gray-400 mt-2">完成时间：{s.completed_at}</p>
          )}
        </div>

        {/* Execution log */}
        {currentRun && currentRun.step_id === s.id && renderLogPanel()}
      </div>
    );
  };

  const renderMetadataPanel = () => {
    if (!metadata) return null;
    return (
      <div className="rounded-2xl border border-gray-200 bg-white p-5 mt-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold">元数据概览</h3>
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-1 rounded-full ${
              metadata.gateway_status === "logged_in" ? "bg-emerald-100 text-emerald-700"
              : metadata.gateway_status === "unreachable" ? "bg-red-100 text-red-700"
              : "bg-amber-100 text-amber-700"}`}>
              {metadata.gateway_status === "logged_in" ? "已连接" : metadata.gateway_status === "unreachable" ? "不可达" : "未登录"}
            </span>
            <button onClick={fetchMetadata} className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
              <RefreshCw className="w-3 h-3" /> 刷新
            </button>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {Object.entries(metadata.categories).map(([key, count]) => (
            <div key={key} className="rounded-xl border border-gray-100 bg-gray-50 p-3 text-center">
              <div className="text-lg font-bold text-gray-800">{count.toLocaleString()}</div>
              <div className="text-xs text-gray-500 mt-1">{CATEGORY_LABELS[key] ?? key}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 text-xs text-gray-400 flex justify-between">
          <span>共 {metadata.total_items.toLocaleString()} 项</span>
          {metadata.fetched_at && <span>更新于 {metadata.fetched_at}</span>}
        </div>
      </div>
    );
  };

  const renderOverview = () => (
    <div className="space-y-6">
      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <h3 className="text-base font-bold mb-4">平台架构</h3>
        <div className="space-y-5">
          <div>
            <h4 className="text-xs font-bold text-gray-500 mb-2">用户输入层</h4>
            <div className="flex flex-wrap gap-2">
              {["Excel 文件", "自然语言描述", "对话式交互"].map(item => (
                <span key={item} className="px-3 py-2 rounded-xl border border-blue-200 bg-blue-50 text-blue-800 text-sm">{item}</span>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-xs font-bold text-gray-500 mb-2">AI Agent 层（TDForge）</h4>
            <div className="rounded-xl border border-blue-100 bg-blue-50/50 p-4">
              <p className="text-sm text-gray-600 mb-3"><strong>Lead Agent</strong> 负责路由、编排和对话式引导。</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {pipeline?.steps.map(s => (
                  <div key={s.id} className="border border-blue-100 bg-white rounded-xl p-3 text-xs">
                    <div className="font-bold">{ICON_MAP[s.id]} {s.title}</div>
                    <div className="text-gray-400 font-mono mt-1">{s.skill}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div>
            <h4 className="text-xs font-bold text-gray-500 mb-2">产出层</h4>
            <div className="flex flex-wrap gap-2">
              {[".fun 函数文件", ".rss 规则集文件", ".pls 策略文件", ".zb 指标文件", ".xls 字段文件"].map(item => (
                <span key={item} className="px-3 py-2 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-sm">{item}</span>
              ))}
            </div>
          </div>
          <div>
            <h4 className="text-xs font-bold text-gray-500 mb-2">目标平台</h4>
            <div className="flex flex-wrap gap-2">
              <span className="px-3 py-2 rounded-xl border border-orange-200 bg-orange-50 text-orange-800 text-sm">天策决策中台</span>
              <span className="px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-gray-600 text-sm">导入 → 上线 → 冒烟测试 → 生产验证</span>
            </div>
          </div>
        </div>
      </div>
      <div className="rounded-2xl border border-gray-200 bg-white p-6">
        <h3 className="text-base font-bold mb-4">Skill 依赖关系</h3>
        <div className="font-mono text-sm text-gray-600 space-y-2">
          <div className="flex items-center gap-2">
            <span className="bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full text-xs">metadata-scout</span>
            <span>→ 提供元数据给所有下游 Skill</span>
          </div>
          <div className="ml-7 flex items-center gap-1 flex-wrap">
            <span>├→</span>
            <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full text-xs">field-forge</span>
            <span>→</span>
            <span className="bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full text-xs">function-forge</span>
            <span>→</span>
            <span className="bg-purple-100 text-purple-800 px-2 py-0.5 rounded-full text-xs">rule-forge</span>
            <span>→</span>
            <span className="bg-rose-100 text-rose-800 px-2 py-0.5 rounded-full text-xs">policy-forge</span>
          </div>
          <div className="ml-7 flex items-center gap-1">
            <span>└→</span>
            <span className="bg-cyan-100 text-cyan-800 px-2 py-0.5 rounded-full text-xs">component-lifecycle</span>
            <span>（导入上线）</span>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex size-full flex-col">
      <div className="sticky top-0 z-10 border-b border-gray-200 bg-white/95 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center text-white font-bold text-lg">策</div>
            <div>
              <h1 className="text-lg font-bold leading-tight">天策策略配置平台</h1>
              <p className="text-xs text-gray-400">Tiance Strategy Configuration Platform</p>
            </div>
          </div>
          <div className="flex items-center bg-gray-100 rounded-xl p-1 gap-0.5">
            <button onClick={() => setActiveTab("config")}
              className={`px-4 py-2 rounded-lg text-sm transition ${activeTab === "config" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"}`}>配置流程</button>
            <button onClick={() => setActiveTab("overview")}
              className={`px-4 py-2 rounded-lg text-sm transition ${activeTab === "overview" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"}`}>全局视图</button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-7xl mx-auto px-6 py-6">
          {loading ? (
            <div className="flex items-center justify-center py-24 text-gray-400">
              <RefreshCw className="w-5 h-5 animate-spin mr-2" /> 加载中...
            </div>
          ) : activeTab === "config" ? (
            <div className="space-y-6">
              <div className="rounded-2xl border border-gray-200 bg-white p-5">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-sm font-bold">标准配置流程</h3>
                  {pipeline && pipeline.completed_count > 0 && (
                    <button onClick={resetPipeline} className="text-xs text-gray-400 hover:text-red-500 flex items-center gap-1 transition">
                      <RefreshCw className="w-3 h-3" /> 重置全部
                    </button>
                  )}
                </div>
                <p className="text-xs text-gray-400 mb-4">
                  已完成 {pipeline?.completed_count ?? 0}/{pipeline?.total ?? 6} 步
                </p>
                {renderPipelineBar()}
              </div>

              <div className="rounded-2xl border border-gray-200 bg-white p-5">
                <div className="flex items-start justify-between gap-4 mb-4">
                  <div>
                    <h3 className="text-sm font-bold">流程内校验规则</h3>
                    <p className="text-xs text-gray-400 mt-1">校验嵌入每个步骤的执行前、生成后和失败处理逻辑里。</p>
                  </div>
                  <span className="shrink-0 text-xs px-3 py-2 rounded-xl border border-amber-300 bg-amber-50 text-amber-700">
                    元数据步骤优先检查连接、认证和 orgCode
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {FLOW_RULES.map(rule => (
                    <div key={rule.title} className={`rounded-xl border p-4 text-sm ${
                      rule.tone === "red" ? "bg-red-50 border-red-200 text-red-900"
                      : rule.tone === "yellow" ? "bg-amber-50 border-amber-200 text-amber-900"
                      : "bg-blue-50 border-blue-200 text-blue-900"}`}>
                      <div className="font-bold mb-2">■ {rule.title}</div>
                      <p className="text-xs leading-relaxed opacity-80">{rule.detail}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                <div className="lg:col-span-7">
                  {renderModuleCards()}
                  {renderMetadataPanel()}
                </div>
                <div className="lg:col-span-5 rounded-2xl border border-gray-200 bg-white min-h-[600px]">
                  {renderDetailPanel()}
                </div>
              </div>
            </div>
          ) : renderOverview()}
        </div>
      </div>
    </div>
  );
}
