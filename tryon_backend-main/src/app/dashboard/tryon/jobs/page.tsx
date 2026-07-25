"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3,
  Coins, Cpu, Eye, FilterX, LoaderCircle, RefreshCcw, RotateCcw, Search,
  Square, Trash2, UserRound, XCircle,
} from "lucide-react";

import { browserApiRequest } from "@/lib/api/browser-api";
import type {
  GenerationExecutionStatus,
  GenerationModule,
  GenerationModuleExecution,
  GenerationModuleListResponse,
} from "@/types/admin-generation-modules";

type ExecutionListResponse = {
  items: GenerationModuleExecution[];
  total: number;
  skip: number;
  limit: number;
};

const ACTIVE_STATUSES = new Set<GenerationExecutionStatus>(["queued", "running"]);
const TERMINAL_STATUSES = new Set<GenerationExecutionStatus>(["completed", "failed", "cancelled"]);

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("es-MX");
}

function formatDuration(ms?: number | null) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds} s`;
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

function engineLabel(engine: string) {
  if (engine === "local_docker") return "Local";
  if (engine === "runpod_serverless") return "RunPod Serverless";
  if (engine === "simulated") return "Simulado";
  return engine;
}

function statusLabel(status: string) {
  return ({ queued: "En cola", running: "Ejecutando", completed: "Completado", failed: "Fallido", cancelled: "Cancelado" } as Record<string, string>)[status] ?? status;
}

function queueLabel(item: GenerationModuleExecution) {
  if (item.engine === "local_docker") return item.status === "queued" ? "Cola local" : "Worker local";
  if (item.engine === "runpod_serverless") {
    if (item.provider_status === "IN_QUEUE" || item.status === "queued") return "Cola RunPod";
    return "RunPod";
  }
  return "Simulado";
}

function providerState(item: GenerationModuleExecution) {
  return item.provider_status || (item.status === "queued" ? "Esperando despacho" : statusLabel(item.status));
}

function originLabel(item: GenerationModuleExecution) {
  const origin = typeof item.context?.origin === "string" ? item.context.origin.toLowerCase() : "";
  if (origin === "appweb") return "AppWeb";
  if (origin === "backoffice" || origin === "admin") return "BackOffice";
  if (origin === "api") return "API";
  if (origin === "system") return "Sistema";
  return item.user_id ? "AppWeb / API" : "BackOffice";
}

function safeSteps(item: GenerationModuleExecution) {
  return Array.isArray(item.steps) ? item.steps : [];
}

function safeLogs(item: GenerationModuleExecution) {
  return Array.isArray(item.logs) ? item.logs : [];
}

function prettyJson(value: unknown) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

function statusClass(status: string) {
  if (status === "completed") return "border-emerald-500/20 bg-emerald-500/10 text-emerald-300";
  if (status === "running") return "border-blue-500/20 bg-blue-500/10 text-blue-300";
  if (status === "queued") return "border-amber-500/20 bg-amber-500/10 text-amber-300";
  return "border-red-500/20 bg-red-500/10 text-red-300";
}

function resultLinks(value: unknown, prefix = "Resultado"): Array<{ label: string; href: string }> {
  if (typeof value === "string" && (/^https?:\/\//.test(value) || value.startsWith("/"))) {
    return [{ label: prefix, href: value }];
  }
  if (Array.isArray(value)) return value.flatMap((item, index) => resultLinks(item, `${prefix} ${index + 1}`));
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => resultLinks(item, key));
  }
  return [];
}

export default function UnifiedAiJobsPage() {
  const [modules, setModules] = useState<GenerationModule[]>([]);
  const [executions, setExecutions] = useState<GenerationModuleExecution[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [moduleId, setModuleId] = useState("");
  const [status, setStatus] = useState("");
  const [engine, setEngine] = useState("");
  const [userId, setUserId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [expandedModules, setExpandedModules] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<GenerationModuleExecution | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "500", skip: "0" });
      if (search.trim()) params.set("search", search.trim());
      if (moduleId) params.set("module_id", moduleId);
      if (status) params.set("status", status);
      if (engine) params.set("engine", engine);
      if (userId) params.set("user_id", userId);
      if (dateFrom) params.set("created_from", new Date(`${dateFrom}T00:00:00`).toISOString());
      if (dateTo) params.set("created_to", new Date(`${dateTo}T23:59:59`).toISOString());

      const [moduleResponse, executionResponse] = await Promise.all([
        browserApiRequest<GenerationModuleListResponse>("/api/admin/generation-modules?limit=500"),
        browserApiRequest<ExecutionListResponse>(`/api/admin/generation-module-executions?${params}`),
      ]);
      const moduleItems = Array.isArray(moduleResponse)
        ? (moduleResponse as unknown as GenerationModule[])
        : Array.isArray(moduleResponse.items)
          ? moduleResponse.items
          : [];
      setModules(moduleItems);
      const executionItems = Array.isArray(executionResponse.items) ? executionResponse.items : [];
      setExecutions(executionItems);
      setSelectedIds((current) => new Set([...current].filter((id) => executionItems.some((item) => item.id === id))));
      setTotal(Number(executionResponse.total ?? 0));
      setExpandedModules((current) => current.size ? current : new Set(moduleItems.map((item) => item.id)));
      setSelected((current) => {
        if (!current) return null;
        return executionResponse.items.find((item) => item.id === current.id) ?? current;
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No fue posible cargar los trabajos de IA.");
    } finally {
      if (!silent) setIsLoading(false);
    }
  }, [dateFrom, dateTo, engine, moduleId, search, status, userId]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!executions.some((item) => ACTIVE_STATUSES.has(item.status) || Boolean(item.cancel_requested))) return;
    const timer = window.setInterval(() => void load(true), 3000);
    return () => window.clearInterval(timer);
  }, [executions, load]);

  const modulesById = useMemo(() => new Map(modules.map((item) => [item.id, item])), [modules]);
  const grouped = useMemo(() => {
    const map = new Map<number, GenerationModuleExecution[]>();
    for (const execution of executions) {
      const current = map.get(execution.module_id) ?? [];
      current.push(execution);
      map.set(execution.module_id, current);
    }
    return [...map.entries()].sort((a, b) => {
      const aName = modulesById.get(a[0])?.name ?? a[1][0]?.module_key ?? "";
      const bName = modulesById.get(b[0])?.name ?? b[1][0]?.module_key ?? "";
      return aName.localeCompare(bName, "es");
    });
  }, [executions, modulesById]);

  const metrics = useMemo(() => ({
    total,
    active: executions.filter((item) => ACTIVE_STATUSES.has(item.status)).length,
    queued: executions.filter((item) => item.status === "queued").length,
    localActive: executions.filter((item) => item.engine === "local_docker" && item.status === "running").length,
    runpodActive: executions.filter((item) => item.engine === "runpod_serverless" && ACTIVE_STATUSES.has(item.status)).length,
    completed: executions.filter((item) => item.status === "completed").length,
    failed: executions.filter((item) => item.status === "failed").length,
    tokens: executions.reduce((sum, item) => sum + (item.tokens_charged ?? 0), 0),
  }), [executions, total]);

  async function jobAction(execution: GenerationModuleExecution, action: "cancel" | "retry") {
    setBusyId(execution.id);
    setError(null);
    try {
      await browserApiRequest(`/api/admin/generation-modules/executions/${execution.id}/${action}`, {
        method: "POST",
        ...(action === "retry" ? { body: JSON.stringify({}) } : {}),
      });
      await load(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No fue posible completar la operación.");
    } finally {
      setBusyId(null);
    }
  }


  async function bulkAction(action: "bulk-cancel" | "bulk-delete") {
    const ids = [...selectedIds];
    if (!ids.length) return;
    if (action === "bulk-delete" && !window.confirm(`¿Eliminar ${ids.length} ejecución(es) seleccionada(s)? Las activas se omitirán.`)) return;
    setBulkBusy(true);
    setError(null);
    try {
      await browserApiRequest(`/api/admin/generation-modules/executions/${action}`, {
        method: "POST",
        body: JSON.stringify({ ids }),
      });
      setSelectedIds(new Set());
      await load(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "No fue posible completar la operación masiva.");
    } finally {
      setBulkBusy(false);
    }
  }

  function toggleExecution(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function clearFilters() {
    setSearch(""); setModuleId(""); setStatus(""); setEngine(""); setUserId(""); setDateFrom(""); setDateTo("");
  }

  function toggleModule(id: number) {
    setExpandedModules((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  return <div className="space-y-7">
    <header className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-red-500">Operación centralizada</p>
        <h1 className="mt-2 text-3xl font-semibold text-white">Trabajos IA</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-500">Una sola vista para supervisar todas las ejecuciones de los módulos de generación, con progreso en vivo, usuario, motor, consumo, resultados, errores y acciones.</p>
      </div>
      <button onClick={() => void load()} disabled={isLoading} className="flex h-11 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-4 text-sm text-zinc-300 hover:bg-white/[0.06] disabled:opacity-50">
        {isLoading ? <LoaderCircle size={16} className="animate-spin" /> : <RefreshCcw size={16} />} Actualizar
      </button>
    </header>

    {error && <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-300"><AlertTriangle className="mr-2 inline" size={16}/>{error}</div>}

    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
      <Metric label="Total encontrado" value={metrics.total} icon={Activity}/>
      <Metric label="En cola" value={metrics.queued} icon={Clock3}/>
      <Metric label="Local ejecutando" value={metrics.localActive} icon={Cpu}/>
      <Metric label="RunPod activos" value={metrics.runpodActive} icon={Activity}/>
      <Metric label="Completados" value={metrics.completed} icon={CheckCircle2}/>
      <Metric label="Tokens cargados" value={metrics.tokens} icon={Coins}/>
    </section>

    <section className="luxia-panel rounded-3xl p-5">
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-4">
        <label className="relative xl:col-span-2"><Search className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-600" size={16}/><input value={search} onChange={(e)=>setSearch(e.target.value)} placeholder="ID, módulo, motor, estado o error..." className="h-11 w-full rounded-xl border border-white/10 bg-black/30 pl-11 pr-4 text-sm text-white outline-none focus:border-red-500/40"/></label>
        <select value={moduleId} onChange={(e)=>setModuleId(e.target.value)} className="h-11 rounded-xl border border-white/10 bg-[#09090a] px-3 text-sm text-zinc-300"><option value="">Todos los módulos</option>{modules.map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <input type="number" min="1" value={userId} onChange={(e)=>setUserId(e.target.value)} placeholder="ID de usuario" className="h-11 rounded-xl border border-white/10 bg-black/30 px-4 text-sm text-white"/>
        <select value={status} onChange={(e)=>setStatus(e.target.value)} className="h-11 rounded-xl border border-white/10 bg-[#09090a] px-3 text-sm text-zinc-300"><option value="">Todos los estados</option><option value="queued">En cola</option><option value="running">Ejecutando</option><option value="completed">Completados</option><option value="failed">Fallidos</option><option value="cancelled">Cancelados</option></select>
        <select value={engine} onChange={(e)=>setEngine(e.target.value)} className="h-11 rounded-xl border border-white/10 bg-[#09090a] px-3 text-sm text-zinc-300"><option value="">Todos los motores</option><option value="simulated">Simulado</option><option value="local_docker">Local</option><option value="runpod_serverless">RunPod Serverless</option></select>
        <input type="date" value={dateFrom} onChange={(e)=>setDateFrom(e.target.value)} className="h-11 rounded-xl border border-white/10 bg-[#09090a] px-3 text-sm text-zinc-300" title="Desde"/>
        <div className="flex gap-3"><input type="date" value={dateTo} onChange={(e)=>setDateTo(e.target.value)} className="h-11 min-w-0 flex-1 rounded-xl border border-white/10 bg-[#09090a] px-3 text-sm text-zinc-300" title="Hasta"/><button onClick={clearFilters} title="Limpiar filtros" className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-white/10 text-zinc-400 hover:text-white"><FilterX size={17}/></button></div>
      </div>
    </section>

    <section className="luxia-panel flex flex-wrap items-center justify-between gap-3 rounded-3xl p-4">
      <label className="flex items-center gap-3 text-sm text-zinc-300"><input type="checkbox" checked={executions.length > 0 && executions.every((item) => selectedIds.has(item.id))} onChange={() => setSelectedIds(executions.length > 0 && executions.every((item) => selectedIds.has(item.id)) ? new Set() : new Set(executions.map((item) => item.id)))} className="size-4 accent-red-600"/>Seleccionar todo <span className="text-zinc-600">({selectedIds.size})</span></label>
      <div className="flex flex-wrap gap-2"><button disabled={bulkBusy || !executions.some((item) => selectedIds.has(item.id) && ACTIVE_STATUSES.has(item.status))} onClick={() => void bulkAction("bulk-cancel")} className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/10 px-3 text-sm text-zinc-300 disabled:opacity-40"><Square size={14}/>Cancelar seleccionadas</button><button disabled={bulkBusy || selectedIds.size === 0} onClick={() => void bulkAction("bulk-delete")} className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/10 px-3 text-sm text-zinc-300 disabled:opacity-40"><Trash2 size={15}/>Eliminar seleccionadas</button></div>
    </section>

    {isLoading ? <section className="luxia-panel flex min-h-72 items-center justify-center rounded-3xl"><div className="text-center"><LoaderCircle className="mx-auto animate-spin text-red-500"/><p className="mt-4 text-sm text-zinc-500">Consultando trabajos...</p></div></section> : grouped.length === 0 ? <section className="luxia-panel rounded-3xl p-12 text-center"><Activity className="mx-auto text-zinc-700"/><h2 className="mt-4 font-semibold text-white">No hay trabajos que coincidan</h2><p className="mt-2 text-sm text-zinc-500">Ajusta los filtros o ejecuta un módulo de generación.</p></section> : <div className="space-y-4">
      {grouped.map(([id, jobs]) => {
        const module = modulesById.get(id);
        const isExpanded = expandedModules.has(id);
        const active = jobs.filter((item)=>ACTIVE_STATUSES.has(item.status)).length;
        return <section key={id} className="luxia-panel overflow-hidden rounded-3xl">
          <button onClick={()=>toggleModule(id)} className="flex w-full items-center justify-between gap-4 border-b border-white/6 p-5 text-left hover:bg-white/[0.02]">
            <div className="flex min-w-0 items-center gap-4">{isExpanded?<ChevronDown size={18}/>:<ChevronRight size={18}/>}<div><h2 className="font-semibold text-white">{module?.name ?? jobs[0]?.module_key}</h2><p className="mt-1 text-xs text-zinc-600">{module?.key ?? jobs[0]?.module_key} · {jobs.length} trabajo{jobs.length===1?"":"s"}{active?` · ${active} activo${active===1?"":"s"}`:""}</p></div></div>
            {active>0&&<span className="rounded-full border border-blue-500/20 bg-blue-500/10 px-3 py-1 text-xs text-blue-300">Actualización en vivo</span>}
          </button>
          {isExpanded && <div className="overflow-x-auto"><table className="w-full min-w-[1120px] text-left text-sm"><thead className="text-[10px] uppercase tracking-wider text-zinc-600"><tr><th className="p-4">Seleccionar</th><th>Trabajo</th><th>Usuario</th><th>Motor</th><th>Estado</th><th>Progreso</th><th>Tokens</th><th>Tiempo</th><th>Resultado / error</th><th className="pr-4">Acciones</th></tr></thead><tbody>{jobs.map((job)=>{
            const links=resultLinks(job.outputs).slice(0,2); const busy=busyId===job.id;
            return <tr key={job.id} className="border-t border-white/5 align-top"><td className="p-4"><input type="checkbox" checked={selectedIds.has(job.id)} onChange={()=>toggleExecution(job.id)} className="size-4 accent-red-600"/></td><td className="pt-4"><p className="font-medium text-white">{job.module_key}</p><p className="mt-1 max-w-40 truncate font-mono text-[10px] text-zinc-700" title={job.id}>{job.id}</p><p className="mt-1 text-[10px] text-zinc-600">{formatDate(job.created_at)}</p></td><td><div className="pt-4"><div className="flex items-center gap-2 text-zinc-300"><UserRound size={14}/>{originLabel(job)}</div><p className="mt-1 text-[10px] text-zinc-600">{job.user_id?`Usuario #${job.user_id}`:"Administrador"}</p></div></td><td className="pt-4 text-zinc-400"><Cpu size={14} className="mr-2 inline"/>{engineLabel(job.engine)}<p className="mt-1 text-[10px] text-zinc-600">{job.queue_name || queueLabel(job)}{job.queue_position ? ` · #${job.queue_position}` : ""}</p></td><td className="pt-4"><span className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase ${statusClass(job.status)}`}>{statusLabel(job.status)}</span></td><td className="pt-4"><div className="w-32"><div className="flex justify-between text-[10px] text-zinc-600"><span>{job.progress}%</span><span>{safeSteps(job).filter(s=>s.status==="completed").length}/{safeSteps(job).length}</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-white/5"><div className="h-full bg-red-600 transition-all" style={{width:`${job.progress}%`}}/></div></div></td><td className="pt-4 text-zinc-400">{job.tokens_charged??0}</td><td className="pt-4 text-zinc-500">{formatDuration(job.duration_ms)}</td><td className="max-w-xs pt-4">{job.error?<p className="line-clamp-2 text-xs text-red-300" title={job.error}>{job.error}</p>:links.length?<div className="flex flex-col gap-1">{links.map((link)=><a key={`${link.label}-${link.href}`} href={link.href} target="_blank" rel="noreferrer" className="truncate text-xs text-blue-300 hover:text-blue-200">{link.label}</a>)}</div>:<span className="text-xs text-zinc-600">{ACTIVE_STATUSES.has(job.status)?"Procesando...":"Sin archivo visible"}</span>}</td><td className="pr-4 pt-3"><div className="flex gap-2"><button onClick={()=>setSelected(job)} className="flex size-9 items-center justify-center rounded-lg border border-white/10 text-zinc-400 hover:text-white" title="Ver detalle"><Eye size={15}/></button>{ACTIVE_STATUSES.has(job.status)&&<button disabled={busy} onClick={()=>void jobAction(job,"cancel")} className="flex size-9 items-center justify-center rounded-lg border border-white/10 text-zinc-400 hover:text-red-300 disabled:opacity-40" title="Cancelar">{busy?<LoaderCircle size={15} className="animate-spin"/>:<Square size={14}/>}</button>}{TERMINAL_STATUSES.has(job.status)&&<button disabled={busy} onClick={()=>void jobAction(job,"retry")} className="flex size-9 items-center justify-center rounded-lg bg-red-600 text-white hover:bg-red-500 disabled:opacity-40" title="Reintentar">{busy?<LoaderCircle size={15} className="animate-spin"/>:<RotateCcw size={15}/>}</button>}</div></td></tr>})}</tbody></table></div>}
        </section>
      })}
    </div>}

    {selected && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm" onMouseDown={(e)=>{if(e.target===e.currentTarget)setSelected(null)}}><section className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-3xl border border-white/10 bg-[#0b0b0d] p-6 shadow-2xl"><div className="flex items-start justify-between gap-4"><div><p className="text-[10px] uppercase tracking-[.2em] text-red-500">Detalle de ejecución</p><h2 className="mt-2 text-xl font-semibold text-white">{modulesById.get(selected.module_id)?.name ?? selected.module_key}</h2><p className="mt-1 font-mono text-[11px] text-zinc-600">{selected.id}</p></div><button onClick={()=>setSelected(null)} className="flex size-9 items-center justify-center rounded-xl border border-white/10 text-zinc-400 hover:text-white"><XCircle size={17}/></button></div><div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><Detail label="Estado" value={statusLabel(selected.status)}/><Detail label="Motor" value={engineLabel(selected.engine)}/><Detail label="Cola" value={`${selected.queue_name || queueLabel(selected)}${selected.queue_position ? ` · posición ${selected.queue_position}` : ""}`}/><Detail label="Estado proveedor" value={providerState(selected)}/><Detail label="Origen" value={originLabel(selected)}/><Detail label="Usuario" value={selected.user_id?`#${selected.user_id}`:"Administrador"}/><Detail label="Job remoto" value={selected.provider_job_id || "—"}/><Detail label="Endpoint remoto" value={selected.provider_endpoint_id || "—"}/><Detail label="Intentos de despacho" value={String(selected.dispatch_attempts ?? 0)}/><Detail label="Heartbeat" value={formatDate(selected.heartbeat_at)}/><Detail label="Duración" value={formatDuration(selected.duration_ms)}/><Detail label="Cancelación solicitada" value={selected.cancel_requested?"Sí":"No"}/></div><div className="mt-6"><h3 className="text-sm font-semibold text-white">Pasos</h3><div className="mt-3 space-y-2">{safeSteps(selected).map((step)=><div key={step.step_key} className="rounded-2xl border border-white/6 bg-black/20 p-4"><div className="flex justify-between gap-4"><div><p className="text-sm text-white">{step.step_name}</p><p className="mt-1 text-xs text-zinc-600">{step.step_type} · {step.step_key}</p></div><span className={`h-fit rounded-full border px-2.5 py-1 text-[10px] uppercase ${statusClass(step.status)}`}>{statusLabel(step.status)}</span></div>{step.error&&<p className="mt-3 text-xs text-red-300">{step.error}</p>}</div>)}</div></div><div className="mt-6 grid gap-4 lg:grid-cols-2"><section><h3 className="text-sm font-semibold text-white">Entradas</h3><pre className="mt-3 max-h-64 overflow-auto rounded-2xl border border-white/6 bg-black/30 p-4 text-[11px] leading-5 text-zinc-400">{prettyJson(selected.inputs)}</pre></section><section><h3 className="text-sm font-semibold text-white">Salidas</h3><pre className="mt-3 max-h-64 overflow-auto rounded-2xl border border-white/6 bg-black/30 p-4 text-[11px] leading-5 text-zinc-400">{prettyJson(selected.outputs)}</pre></section></div><div className="mt-6"><h3 className="text-sm font-semibold text-white">Registro</h3><div className="mt-3 max-h-60 space-y-2 overflow-auto rounded-2xl border border-white/6 bg-black/30 p-4 font-mono text-[11px]">{safeLogs(selected).length?safeLogs(selected).map((log,index)=><p key={`${log.timestamp}-${index}`} className={log.level==="error"?"text-red-300":log.level==="warning"?"text-amber-300":"text-zinc-500"}>[{formatDate(log.timestamp)}] {log.message}</p>):<p className="text-zinc-600">Sin eventos registrados.</p>}</div></div></section></div>}
  </div>;
}

function Metric({label,value,icon:Icon}:{label:string;value:number;icon:React.ComponentType<{size?:number}>}){return <article className="luxia-panel rounded-2xl p-5"><div className="flex items-start justify-between"><div><p className="text-[10px] font-semibold uppercase tracking-[.18em] text-zinc-600">{label}</p><p className="mt-4 text-2xl font-semibold text-white">{value.toLocaleString("es-MX")}</p></div><div className="flex size-10 items-center justify-center rounded-xl border border-red-500/15 bg-red-950/15 text-red-400"><Icon size={18}/></div></div></article>}
function Detail({label,value}:{label:string;value:string}){return <div className="rounded-2xl border border-white/6 bg-black/20 p-4"><p className="text-[10px] uppercase tracking-wider text-zinc-600">{label}</p><p className="mt-2 text-sm text-white">{value}</p></div>}
