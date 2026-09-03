"use client";

import { DragEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDown, ArrowRight, Boxes, Braces, Code2, Copy, GripVertical,
  Image as ImageIcon, LoaderCircle, Pencil, Plus, Save, Search, Sparkles,
  Trash2, Workflow, X,
} from "lucide-react";
import { toast } from "sonner";
import { GenerationNodeCanvas } from "@/components/generation/generation-node-canvas";
import { GenerationTestConsole } from "@/components/generation/generation-test-console";
import { browserApiRequest } from "@/lib/api/browser-api";
import type { PricingRuleResponse } from "@/types/admin-pricing-coupons";
import type {
  GenerationExecutionEngine, GenerationModule, GenerationModuleInput,
  GenerationModuleListResponse, GenerationModuleOutput, GenerationModuleStep,
  GenerationNodePort, WorkflowInputBinding, WorkflowOutputBinding,
} from "@/types/admin-generation-modules";

const engines: { value: GenerationExecutionEngine; label: string }[] = [
  { value: "simulated", label: "Simulado" },
  { value: "local_docker", label: "Docker local" },
  { value: "owner_local", label: "Owner Local · Pinokio Windows" },
  { value: "runpod_serverless", label: "RunPod Serverless" },
  { value: "beam", label: "Beam" },
  { value: "modal", label: "Modal" },
];
const inputTypes = ["image", "file", "text", "integer", "float", "boolean", "json"] as const;
const outputTypes = ["image", "images", "file", "json", "metadata"] as const;
const emptyInput = (position: number): GenerationModuleInput => ({ key: `input_${position + 1}`, name: "Nueva entrada", input_type: "image", position, is_required: true, validation: {} });
const emptyOutput = (position: number): GenerationModuleOutput => ({ key: `output_${position + 1}`, name: "Nueva salida", output_type: "image", position, is_required: true, metadata: {} });

type EditorTarget = { mode: "create" | "edit"; type: "workflow" | "python"; step?: GenerationModuleStep } | null;
type Port = { key: string; label: string; type: string; path: string; origin: string };
type ExecutionTarget = { provider: string; value: string; label: string; build_id: number; deployment_id?: string | null; runtime_name?: string | null; version?: string | null; image_tag?: string | null };
type ExecutionTargetResponse = { items: Record<string, ExecutionTarget[]> };

function generatedInputContract(module: GenerationModule) {
  return {
    module: {
      id: module.id,
      key: module.key,
      name: module.name,
      category: module.category,
      version: module.version,
    },
    inputs: [...module.inputs]
      .sort((a, b) => a.position - b.position)
      .map((input) => ({
        id: input.id ?? null,
        key: input.key,
        name: input.name,
        description: input.description ?? null,
        type: input.input_type,
        position: input.position,
        required: input.is_required,
        default_value: input.default_value ?? null,
        validation: input.validation ?? {},
      })),
  };
}

function moduleDraftFingerprint(module: GenerationModule | null): string {
  if (!module) return "";
  return JSON.stringify({
    name: module.name,
    description: module.description ?? null,
    category: module.category,
    default_execution_engine: module.default_execution_engine ?? null,
    endpoint: module.endpoint ?? null,
    metadata: module.metadata ?? {},
    is_active: module.is_active,
    pricing_rule_id: module.pricing_rule_id ?? null,
    inputs: module.inputs.map(({ id: _id, ...item }) => item),
    outputs: module.outputs.map(({ id: _id, ...item }) => item),
  });
}

export default function GenerationModulesPage() {
  const [items, setItems] = useState<GenerationModule[]>([]);
  const [pricingRules, setPricingRules] = useState<PricingRuleResponse[]>([]);
  const [selected, setSelected] = useState<GenerationModule | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingModule, setDeletingModule] = useState(false);
  const [editor, setEditor] = useState<EditorTarget>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [executionTargets, setExecutionTargets] = useState<Record<string, ExecutionTarget[]>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = new URLSearchParams({ limit: "200" });
      if (search.trim()) q.set("search", search.trim());
      const [response, rules, targets] = await Promise.all([
        browserApiRequest<GenerationModuleListResponse>(`/api/admin/generation-modules?${q}`),
        browserApiRequest<PricingRuleResponse[]>("/api/admin/pricing-rules"),
        browserApiRequest<ExecutionTargetResponse>("/api/admin/generation-module-execution-targets"),
      ]);
      setItems(response.items);
      setPricingRules(rules);
      setExecutionTargets(targets.items ?? {});
      setSelected(current => current ? response.items.find(item => item.id === current.id) ?? null : current);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "No fue posible cargar los módulos.");
    } finally { setLoading(false); }
  }, [search]);

  useEffect(() => { const timer = setTimeout(() => void load(), 200); return () => clearTimeout(timer); }, [load]);

  const saveModule = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const updated = await browserApiRequest<GenerationModule>(`/api/admin/generation-modules/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: selected.name, description: selected.description, category: selected.category,
          default_execution_engine: selected.default_execution_engine, endpoint: selected.endpoint ?? null, metadata: selected.metadata, is_active: selected.is_active, pricing_rule_id: selected.pricing_rule_id ?? null,
          inputs: selected.inputs.map(({ id, ...item }) => item),
          outputs: selected.outputs.map(({ id, ...item }) => item),
        }),
      });
      setSelected(updated);
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      toast.success("Módulo guardado.");
      await load();
    } catch (error) { toast.error(error instanceof Error ? error.message : "No fue posible guardar."); }
    finally { setSaving(false); }
  };

  const persistedSelected = selected
    ? items.find((item) => item.id === selected.id) ?? null
    : null;
  const hasUnsavedModuleChanges = Boolean(
    selected &&
    persistedSelected &&
    moduleDraftFingerprint(selected) !== moduleDraftFingerprint(persistedSelected),
  );

  const deleteSelectedModule = async () => {
    if (!selected) return;
    const accepted = window.confirm(
      `¿Eliminar definitivamente el módulo "${selected.name}"? Solo puede borrarse si nunca tuvo ejecuciones. Si tiene historial, el sistema lo protegerá y deberás dejarlo inactivo.`,
    );
    if (!accepted) return;
    setDeletingModule(true);
    try {
      await browserApiRequest(`/api/admin/generation-modules/${selected.id}`, { method: "DELETE" });
      toast.success("Módulo eliminado.");
      setSelected(null);
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "No fue posible eliminar el módulo.");
    } finally {
      setDeletingModule(false);
    }
  };

  return <div className="space-y-7">
    <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div><p className="text-xs font-semibold uppercase tracking-[.28em] text-red-400">Pipeline visual</p><h1 className="mt-2 text-3xl font-semibold text-white">Módulos de generación</h1><p className="mt-2 max-w-3xl text-sm text-zinc-500">Arrastra pasos, edítalos y deja que el editor sugiera conexiones por nombre y tipo.</p></div>
      <button onClick={() => setCreateOpen(true)} className="inline-flex h-11 items-center gap-2 rounded-xl bg-red-600 px-4 text-sm font-semibold text-white hover:bg-red-500"><Plus size={17}/>Nuevo módulo</button>
    </header>
    <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
      <section className="luxia-panel overflow-hidden rounded-3xl">
        <div className="border-b border-white/6 p-4"><div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-700" size={16}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar módulos..." className="h-10 w-full rounded-xl border border-white/7 bg-black/30 pl-10 pr-3 text-sm text-white outline-none focus:border-red-500/40"/></div></div>
        <div className="max-h-[760px] overflow-y-auto p-3">{loading ? <div className="flex justify-center p-10"><LoaderCircle className="animate-spin text-red-500"/></div> : items.map(module => {
          const active = module.is_active;
          const selectedCard = selected?.id === module.id;
          return <button key={module.id} onClick={() => setSelected(module)} className={`mb-2 w-full rounded-2xl border p-4 text-left transition ${active ? "border-emerald-500/25 bg-emerald-500/[.045] hover:border-emerald-400/45" : "border-red-500/25 bg-red-500/[.045] hover:border-red-400/45"} ${selectedCard ? active ? "ring-1 ring-emerald-400/55" : "ring-1 ring-red-400/55" : ""}`}>
            <div className="flex items-start justify-between gap-3"><p className="font-medium text-white">{module.name}</p><span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[.12em] ${active ? "border-emerald-500/25 bg-emerald-500/10 text-emerald-300" : "border-red-500/25 bg-red-500/10 text-red-300"}`}><span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-emerald-400" : "bg-red-400"}`}/>{active ? "Activo" : "Inactivo"}</span></div>
            <div className="mt-3 flex gap-3 text-xs text-zinc-600"><span>{module.inputs.length} entradas</span><span>{module.steps.length} pasos</span><span>{module.outputs.length} salidas</span></div>
          </button>;
        })}</div>
      </section>
      {!selected ? <EmptyState/> : <ModuleEditor module={selected} savedModule={persistedSelected} hasUnsavedChanges={hasUnsavedModuleChanges} pricingRules={pricingRules} executionTargets={executionTargets} setModule={setSelected} saving={saving} deleting={deletingModule} onSave={saveModule} onDelete={deleteSelectedModule} onOpenEditor={setEditor}/>} 
    </div>
    {editor && selected && <StepEditor module={selected} target={editor} onClose={() => setEditor(null)} onSaved={module => { setSelected(module); setEditor(null); void load(); }}/>} 
    {createOpen && <CreateModuleModal onClose={() => setCreateOpen(false)} onCreated={module => { setItems(current => [module, ...current]); setSelected(module); setCreateOpen(false); }}/>} 
  </div>;
}

function EmptyState() { return <section className="luxia-panel flex min-h-[560px] flex-col items-center justify-center rounded-3xl p-10 text-center"><Boxes size={44} className="text-zinc-800"/><h2 className="mt-5 text-xl font-semibold text-white">Selecciona un módulo</h2><p className="mt-2 max-w-md text-sm text-zinc-600">Aquí aparecerá el editor visual del pipeline.</p></section>; }

function ModuleEditor({ module, savedModule, hasUnsavedChanges, pricingRules, executionTargets, setModule, saving, deleting, onSave, onDelete, onOpenEditor }: { module: GenerationModule; savedModule: GenerationModule | null; hasUnsavedChanges: boolean; pricingRules: PricingRuleResponse[]; executionTargets: Record<string, ExecutionTarget[]>; setModule: (module: GenerationModule) => void; saving: boolean; deleting: boolean; onSave: () => void; onDelete: () => void; onOpenEditor: (target: EditorTarget) => void }) {
  const patch = (value: Partial<GenerationModule>) => setModule({ ...module, ...value });
  return <section className="luxia-panel overflow-hidden rounded-3xl">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/6 p-5"><div className="flex items-center gap-3"><span className={`h-3 w-3 rounded-full ${module.is_active ? "bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,.9)]" : "bg-red-500 shadow-[0_0_14px_rgba(239,68,68,.55)]"}`}/><div><h2 className="text-xl font-semibold text-white">{module.name}</h2><p className="mt-1 font-mono text-xs text-zinc-600">{module.key} · ID {module.id} · {module.is_active ? "ACTIVO" : "INACTIVO"}</p></div></div><div className="flex flex-wrap gap-2"><button onClick={onDelete} disabled={deleting || saving} className="inline-flex h-10 items-center gap-2 rounded-xl border border-red-500/20 bg-red-950/15 px-4 text-sm font-semibold text-red-300 disabled:opacity-50">{deleting ? <LoaderCircle size={16} className="animate-spin"/> : <Trash2 size={16}/>}Eliminar módulo</button><button onClick={onSave} disabled={saving || deleting} className="inline-flex h-10 items-center gap-2 rounded-xl bg-red-600 px-4 text-sm font-semibold text-white disabled:opacity-50">{saving ? <LoaderCircle size={16} className="animate-spin"/> : <Save size={16}/>}Guardar módulo</button></div></div>
    <div className="space-y-7 p-5">
      <div className="grid gap-4 md:grid-cols-6"><Field label="Nombre"><input value={module.name} onChange={e => patch({ name: e.target.value })} className="gm-input"/></Field><Field label="Categoría"><input value={module.category} onChange={e => patch({ category: e.target.value })} className="gm-input"/></Field><Field label="Motor"><select value={module.default_execution_engine ?? ""} onChange={e => {
        const nextEngine = e.target.value ? e.target.value as GenerationExecutionEngine : null;
        patch({
          default_execution_engine: nextEngine,
          endpoint: null,
          metadata: { ...module.metadata, execution_target: {} },
          is_active: nextEngine ? module.is_active : false,
        });
      }} className="gm-input"><option value="">Sin motor todavía</option>{engines.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select><span className="mt-1 block text-[10px] text-zinc-600">Al cambiar de proveedor se limpia el destino anterior para impedir usar accidentalmente un runtime de otro proveedor.</span></Field><ExecutionTargetField module={module} targets={executionTargets} patch={patch}/><Field label="Pricing rule"><select value={module.pricing_rule_id ?? ""} onChange={e => patch({ pricing_rule_id: e.target.value ? Number(e.target.value) : null })} className="gm-input"><option value="">Sin regla</option>{pricingRules.map(rule => <option key={rule.id} value={rule.id}>{rule.title} · {rule.required_tokens} tokens</option>)}</select></Field><Field label="Estado"><select value={String(module.is_active)} onChange={e => patch({ is_active: e.target.value === "true" })} className={`gm-input ${module.is_active ? "border-emerald-500/40 text-emerald-300" : ""}`}><option value="true" disabled={!module.default_execution_engine}>Activo</option><option value="false">Inactivo</option></select>{!module.default_execution_engine && <span className="mt-1 block text-[10px] text-zinc-600">Elige un motor antes de activarlo.</span>}</Field></div>

      <div className="mt-4 rounded-2xl border border-white/7 bg-black/20 p-4">
        <div className="mb-3">
          <p className="text-xs font-semibold uppercase tracking-[.18em] text-zinc-500">Integración AppWeb</p>
          <p className="mt-1 text-xs leading-5 text-zinc-600">Automático crea una pestaña y utiliza el formulario dinámico actual. Administrado no crea interfaz automáticamente: el módulo sigue disponible por la API de Generation Modules para construir una pantalla personalizada.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Título de pestaña">
            <input
              value={String(module.metadata?.appweb_tab_title ?? module.name)}
              onChange={e => patch({ metadata: { ...module.metadata, appweb_tab_title: e.target.value } })}
              placeholder="Ej. Crear Try-On"
              className="gm-input"
            />
          </Field>
          <Field label="Modo de interfaz">
            <select
              value={module.metadata?.appweb_mode === "managed" ? "managed" : "automatic"}
              onChange={e => patch({ metadata: { ...module.metadata, appweb_mode: e.target.value } })}
              className="gm-input"
            >
              <option value="automatic">Automático · formulario dinámico</option>
              <option value="managed">Administrado · interfaz personalizada</option>
            </select>
          </Field>
        </div>
      </div>
      <ContractEditor module={module} setModule={setModule}/>

      <section className="rounded-2xl border border-cyan-500/15 bg-cyan-500/[.025] p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[.22em] text-cyan-300/80">Contrato de inputs</p>
            <h3 className="mt-1 text-sm font-semibold text-white">JSON del formulario</h3>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-500">
              Describe exactamente los inputs públicos del módulo: key, nombre, tipo, requerido, default_value,
              validaciones y posición. Este JSON sirve para construir una interfaz AppWeb administrada sin adivinar campos.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              const json = JSON.stringify(generatedInputContract(module), null, 2);
              void navigator.clipboard.writeText(json)
                .then(() => toast.success("Contrato de inputs copiado."))
                .catch(() => toast.error("No fue posible copiar el JSON."));
            }}
            className="gm-secondary shrink-0"
          >
            <Copy size={15}/>
            Copiar JSON
          </button>
        </div>
        <pre className="mt-4 max-h-[420px] overflow-auto rounded-xl border border-white/6 bg-black/40 p-4 font-mono text-[12px] leading-5 text-zinc-300">
          {JSON.stringify(generatedInputContract(module), null, 2)}
        </pre>
      </section>

      <div>
        <div className="mb-3 flex flex-col gap-3 rounded-2xl border border-white/7 bg-black/25 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="text-[10px] font-semibold uppercase tracking-[.22em] text-zinc-500">Nodos disponibles</p><p className="mt-1 text-xs text-zinc-600">Agrega nuevos pasos al pipeline antes de conectarlos en el canvas.</p></div>
          <div className="flex flex-wrap gap-2"><button onClick={() => onOpenEditor({ mode: "create", type: "workflow" })} className="gm-secondary"><Workflow size={15}/>Workflow</button><button onClick={() => onOpenEditor({ mode: "create", type: "python" })} className="gm-secondary"><Code2 size={15}/>Python</button></div>
        </div>
        <div className="mb-4"><h3 className="text-sm font-semibold uppercase tracking-[.18em] text-zinc-400">Canvas de nodos</h3><p className="mt-1 text-xs text-zinc-600">Conecta outputs con inputs arrastrando entre los puertos, igual que en ComfyUI.</p></div><GenerationNodeCanvas module={module} onModule={setModule} onEdit={step=>onOpenEditor({mode:"edit",type:step.step_type,step})}/>
      </div>
      <GenerationTestConsole module={savedModule ?? module} hasUnsavedChanges={hasUnsavedChanges}/>
    </div>
  </section>;
}

function ExecutionTargetField({ module, targets, patch }: { module: GenerationModule; targets: Record<string, ExecutionTarget[]>; patch: (value: Partial<GenerationModule>) => void }) {
  const engine = module.default_execution_engine;
  if (engine === "owner_local") return <Field label="Destino"><div className="gm-input flex items-center text-zinc-400">Owner Local global</div><span className="mt-1 block text-[10px] text-zinc-600">Owner Private usa el endpoint global de Pinokio configurado en Proveedores de infraestructura.</span></Field>;
  if (engine === "modal" || engine === "runpod_serverless" || engine === "beam") {
    const options = targets[engine] ?? [];
    const labels: Record<string,string> = { modal: "App / Runtime Modal", runpod_serverless: "Endpoint RunPod", beam: "Deployment Beam" };
    return <Field label={labels[engine]}><select value={module.endpoint ?? ""} onChange={e => patch({ endpoint: e.target.value || null })} className="gm-input"><option value="">Seleccionar destino</option>{options.map(item => <option key={`${item.build_id}-${item.deployment_id ?? item.value}`} value={item.value}>{item.label}</option>)}</select><span className="mt-1 block text-[10px] text-zinc-600">{options.length ? "Catálogo leído de deployments del Runtime Builder." : "No hay deployments disponibles de este proveedor en Runtime Builder."}</span></Field>;
  }
  if (engine === "local_docker") {
    const options = targets.local_docker ?? [];
    return <Field label="Runtime Docker"><select value={module.endpoint ?? ""} onChange={e => {
      const target = e.target.value || null;
      const selected = options.find(item => item.value === target);
      patch({
        endpoint: target,
        metadata: {
          ...module.metadata,
          execution_target: selected ? {
            provider: "local_docker",
            image_tag: selected.image_tag ?? null,
            build_id: selected.build_id,
            runtime_name: selected.runtime_name ?? null,
            version: selected.version ?? null,
          } : {},
        },
      });
    }} className="gm-input"><option value="">Seleccionar runtime Docker</option>{options.map(item => <option key={`${item.build_id}-${item.value}`} value={item.value}>{item.label}</option>)}</select><span className="mt-1 block text-[10px] text-zinc-600">{options.length ? "El Docker Local Manager levanta o reutiliza automáticamente esta imagen y Docker asigna un puerto libre." : "No hay imágenes Docker construidas disponibles en Runtime Builder."}</span></Field>;
  }
  return <Field label="Destino"><div className="gm-input flex items-center text-zinc-600">No requerido</div></Field>;
}

function ModuleInputNode({ module }: { module: GenerationModule }) { return <div className="rounded-2xl border border-blue-500/20 bg-blue-500/[.05] p-4"><div className="flex items-center gap-2 text-sm font-semibold text-blue-300"><Braces size={16}/>Entradas del módulo</div><div className="mt-3 flex flex-wrap gap-2">{module.inputs.map(input => <PortChip key={input.key} label={input.key} type={input.input_type}/>)}</div></div>; }
function ModuleOutputNode({ module }: { module: GenerationModule }) { return <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[.05] p-4"><div className="flex items-center gap-2 text-sm font-semibold text-emerald-300"><ImageIcon size={16}/>Salidas publicadas</div><div className="mt-3 flex flex-wrap gap-2">{module.outputs.map(output => <PortChip key={output.key} label={output.key} type={output.output_type}/>)}</div></div>; }
function PortChip({ label, type }: { label: string; type: string }) { return <span className="rounded-full border border-white/8 bg-black/25 px-3 py-1.5 font-mono text-[11px] text-zinc-300">{label}<span className="ml-2 text-zinc-600">{type}</span></span>; }

function FlowConnector({ previous, current, module }: { previous: GenerationModuleStep | null; current: GenerationModuleStep | null; module: GenerationModule }) {
  const suggestions = useMemo(() => current ? suggestConnections(module, previous, current) : [], [module, previous, current]);
  return <div className="flex min-h-16 flex-col items-center justify-center gap-1"><ArrowDown size={18} className="text-zinc-700"/>{current && <div className="flex flex-wrap items-center justify-center gap-2">{suggestions.slice(0, 3).map(item => <span key={`${item.target}-${item.source}`} className={`rounded-full px-2.5 py-1 text-[10px] ${item.confidence === "exact" ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"}`}>{item.source} <ArrowRight className="inline" size={10}/> {item.target}</span>)}{suggestions.length === 0 && <span className="text-[10px] text-zinc-700">contexto completo disponible</span>}</div>}</div>;
}

function StepNode({ step, module, ...props }: { step: GenerationModuleStep; module: GenerationModule; draggable: boolean; onDragStart: () => void; onDragOver: (event: DragEvent<HTMLDivElement>) => void; onDrop: () => void; onEdit: () => void; onDuplicate: () => void; onDelete: () => void }) {
  const inputs = describeStepInputs(step, module); const outputs = describeStepOutputs(step, module);
  return <div draggable={props.draggable} onDragStart={props.onDragStart} onDragOver={props.onDragOver} onDrop={props.onDrop} className="group rounded-2xl border border-white/8 bg-black/25 p-4 transition hover:border-red-500/25">
    <div className="flex items-start gap-3"><GripVertical className="mt-1 cursor-grab text-zinc-700 group-active:cursor-grabbing" size={19}/><div className={`flex h-10 w-10 items-center justify-center rounded-xl ${step.step_type === "workflow" ? "bg-purple-500/10 text-purple-300" : "bg-red-500/10 text-red-300"}`}>{step.step_type === "workflow" ? <Workflow size={19}/> : <Code2 size={19}/>}</div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-medium text-white">{step.name}</p><span className="rounded-full bg-white/5 px-2 py-1 font-mono text-[10px] text-zinc-500">{step.key}</span><span className={`rounded-full px-2 py-1 text-[10px] ${step.is_enabled ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800 text-zinc-500"}`}>{step.is_enabled ? "Activo" : "Inactivo"}</span></div><div className="mt-3 grid gap-3 md:grid-cols-2"><PortGroup title="Recibe" ports={inputs}/><PortGroup title="Produce" ports={outputs}/></div></div><div className="flex gap-1"><button onClick={props.onEdit} className="gm-icon" title="Editar"><Pencil size={15}/></button><button onClick={props.onDuplicate} className="gm-icon" title="Duplicar"><Copy size={15}/></button><button onClick={props.onDelete} className="gm-icon text-red-400" title="Eliminar"><Trash2 size={15}/></button></div></div>
  </div>;
}
function PortGroup({ title, ports }: { title: string; ports: Port[] }) { return <div><p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">{title}</p><div className="flex flex-wrap gap-1.5">{ports.length ? ports.slice(0, 6).map(port => <PortChip key={`${port.origin}-${port.key}`} label={port.label} type={port.type}/>) : <span className="text-xs text-zinc-700">Contexto completo</span>}</div></div>; }

function describeStepInputs(step: GenerationModuleStep, module: GenerationModule): Port[] {
  if (step.step_type === "workflow") {
    return ((step.configuration?.input_bindings ?? []) as WorkflowInputBinding[]).map((binding, index) => {
      const sourcePath = binding.source_path?.trim() || binding.module_input_key?.trim() || `input_${index + 1}`;
      const portKey = binding.module_input_key?.trim() || binding.input_field?.trim() || `input_${index + 1}`;
      const input = module.inputs.find(item => item.key === binding.module_input_key);
      return {
        key: portKey,
        label: `${sourcePath} → ${binding.node_id}.${binding.input_field}`,
        type: input?.input_type ?? inferType(portKey),
        path: sourcePath,
        origin: binding.source_path ? "pipeline" : "module",
      };
    });
  }
  const mapping = step.input_mapping ?? {};
  return Object.entries(mapping).map(([key, value]) => ({ key, label: `${key} ← ${String(value)}`, type: inferType(key), path: String(value), origin: "mapping" }));
}
function describeStepOutputs(step: GenerationModuleStep, module: GenerationModule): Port[] {
  if (step.step_type === "workflow") return ((step.configuration?.output_bindings ?? []) as WorkflowOutputBinding[]).map(binding => { const output = module.outputs.find(item => item.key === binding.module_output_key); return { key: binding.module_output_key, label: `${binding.node_id} → ${binding.module_output_key}`, type: output?.output_type ?? "image", path: `${step.key}.${binding.module_output_key}`, origin: step.key }; });
  const mapping = step.output_mapping ?? {};
  return Object.keys(mapping).map(key => ({ key, label: key, type: inferType(key), path: `${step.key}.${key}`, origin: step.key }));
}
function inferType(key: string) { const value = key.toLowerCase(); if (value.includes("image") || value.includes("photo") || value.includes("mask")) return "image"; if (value.includes("file") || value.includes("path")) return "file"; if (value.includes("count") || value.includes("width") || value.includes("height")) return "integer"; return "json"; }
function suggestConnections(module: GenerationModule, previous: GenerationModuleStep | null, current: GenerationModuleStep) {
  const sources: Port[] = previous ? describeStepOutputs(previous, module) : module.inputs.map(input => ({ key: input.key, label: input.key, type: input.input_type, path: input.key, origin: "module" }));
  const targets = describeStepInputs(current, module);
  return targets.map(target => {
    const exact = sources.find(source => source.key === target.key);
    const sameType = sources.find(source => source.type === target.type || (source.type === "images" && target.type === "image"));
    const source = exact ?? sameType ?? sources[0];
    return source ? { target: target.key, source: source.path, confidence: exact ? "exact" : sameType ? "type" : "fallback" } : null;
  }).filter(Boolean) as { target: string; source: string; confidence: "exact" | "type" | "fallback" }[];
}

function ContractEditor({ module, setModule }: { module: GenerationModule; setModule: (module: GenerationModule) => void }) {
  const updateInput = (index: number, value: Partial<GenerationModuleInput>) => setModule({ ...module, inputs: module.inputs.map((item, current) => current === index ? { ...item, ...value } : item) });
  const updateOutput = (index: number, value: Partial<GenerationModuleOutput>) => setModule({ ...module, outputs: module.outputs.map((item, current) => current === index ? { ...item, ...value } : item) });
  return <div className="grid gap-5 xl:grid-cols-2">
    <Contract title="Assets del formulario" onAdd={() => setModule({ ...module, inputs: [...module.inputs, emptyInput(module.inputs.length)] })}>
      {module.inputs.map((input, index) => <div key={input.id ?? index} className="grid gap-2 rounded-xl border border-white/5 p-3">
        <div className="grid gap-2 md:grid-cols-2"><input className="gm-input" value={input.key} onChange={e => updateInput(index, { key: e.target.value })} placeholder="id_estable"/><input className="gm-input" value={input.name} onChange={e => updateInput(index, { name: e.target.value })} placeholder="Título visible"/></div>
        <div className="grid gap-2 md:grid-cols-[1fr_auto_auto]"><select className="gm-input" value={input.input_type} onChange={e => updateInput(index, { input_type: e.target.value as GenerationModuleInput["input_type"] })}>{inputTypes.map(type => <option key={type}>{type}</option>)}</select><label className="flex items-center gap-2 px-2 text-xs text-zinc-400"><input type="checkbox" checked={input.is_required} onChange={e => updateInput(index, { is_required: e.target.checked })}/>Obligatorio</label><button className="gm-delete" onClick={() => setModule({ ...module, inputs: module.inputs.filter((_, current) => current !== index).map((item, position) => ({ ...item, position })) })}><X size={15}/></button></div>
      </div>)}
    </Contract>
    <Contract title="Puertos del nodo Output" onAdd={() => setModule({ ...module, outputs: [...module.outputs, emptyOutput(module.outputs.length)] })}>
      {module.outputs.map((output, index) => <div key={output.id ?? index} className="grid gap-2 rounded-xl border border-white/5 p-3">
        <div className="grid gap-2 md:grid-cols-2"><input className="gm-input" value={output.key} onChange={e => updateOutput(index, { key: e.target.value })} placeholder="id_estable"/><input className="gm-input" value={output.name} onChange={e => updateOutput(index, { name: e.target.value })} placeholder="Título visible"/></div>
        <div className="grid gap-2 md:grid-cols-[1fr_auto]"><select className="gm-input" value={output.output_type} onChange={e => updateOutput(index, { output_type: e.target.value as GenerationModuleOutput["output_type"] })}>{outputTypes.map(type => <option key={type}>{type}</option>)}</select><button className="gm-delete" onClick={() => setModule({ ...module, outputs: module.outputs.filter((_, current) => current !== index).map((item, position) => ({ ...item, position })) })}><X size={15}/></button></div>
      </div>)}
    </Contract>
  </div>;
}

function StepEditor({ module, target, onClose, onSaved }: { module: GenerationModule; target: NonNullable<EditorTarget>; onClose: () => void; onSaved: (module: GenerationModule) => void }) {
  return target.type === "workflow" ? <WorkflowStepEditor module={module} target={target} onClose={onClose} onSaved={onSaved}/> : <PythonStepEditor module={module} target={target} onClose={onClose} onSaved={onSaved}/>;
}
function emptyPort(side: "input" | "output", index: number): GenerationNodePort {
  return { id: `${side}_${index + 1}`, label: `${side === "input" ? "Entrada" : "Salida"} ${index + 1}`, data_type: "image", node_id: "", field: side === "input" ? "image" : "images", is_required: true };
}

const nodePortTypes = ["image", "images", "mask", "file", "text", "integer", "float", "boolean", "json", "metadata", "auto"];

function NodePortsEditor({ title, side, ports, setPorts, comfy }: { title: string; side: "input" | "output"; ports: GenerationNodePort[]; setPorts: (ports: GenerationNodePort[]) => void; comfy: boolean }) {
  const update = (index: number, patch: Partial<GenerationNodePort>) => setPorts(ports.map((port, current) => current === index ? { ...port, ...patch } : port));
  return <Contract title={title} onAdd={() => setPorts([...ports, emptyPort(side, ports.length)])}>
    {ports.map((port, index) => <div key={`${side}-${index}`} className="space-y-2 rounded-xl border border-white/5 p-3">
      <div className="grid gap-2 md:grid-cols-2"><input className="gm-input" value={port.id} onChange={e => update(index, { id: e.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, "_") })} placeholder="id_puerto"/><input className="gm-input" value={port.label} onChange={e => update(index, { label: e.target.value })} placeholder="Título visible"/></div>
      <div className={`grid gap-2 ${comfy ? "md:grid-cols-[1fr_1fr_1fr_auto]" : "md:grid-cols-[1fr_auto]"}`}>
        <select className="gm-input" value={port.data_type} onChange={e => update(index, { data_type: e.target.value })}>{nodePortTypes.map(type => <option key={type}>{type}</option>)}</select>
        {comfy && <input className="gm-input" value={port.node_id ?? ""} onChange={e => update(index, { node_id: e.target.value })} placeholder="Node ID ComfyUI"/>}
        {comfy && <input className="gm-input" value={port.field ?? ""} onChange={e => update(index, { field: e.target.value })} placeholder={side === "input" ? "input_field" : "output_field"}/>}
        <button className="gm-delete" onClick={() => setPorts(ports.filter((_, current) => current !== index))}><X size={15}/></button>
      </div>
    </div>)}
  </Contract>;
}

function WorkflowStepEditor({ module, target, onClose, onSaved }: { module: GenerationModule; target: NonNullable<EditorTarget>; onClose: () => void; onSaved: (module: GenerationModule) => void }) {
  const step = target.step; const config = step?.configuration ?? {};
  const [key, setKey] = useState(step?.key ?? `workflow_${module.steps.length + 1}`);
  const [name, setName] = useState(step?.name ?? "Workflow ComfyUI");
  const [description, setDescription] = useState(step?.description ?? "");
  const [json, setJson] = useState(JSON.stringify(config.workflow ?? {}, null, 2));
  const [inputPorts, setInputPorts] = useState<GenerationNodePort[]>((config.input_ports ?? []) as GenerationNodePort[]);
  const [outputPorts, setOutputPorts] = useState<GenerationNodePort[]>((config.output_ports ?? []) as GenerationNodePort[]);
  const [enabled, setEnabled] = useState(step?.is_enabled ?? true);
  const [busy, setBusy] = useState(false);
  const parsed = useMemo(() => { try { return JSON.parse(json); } catch { return null; } }, [json]);

  const autoDetect = () => {
    if (!parsed) return toast.error("El JSON no es válido.");
    const nodes = Object.entries(parsed) as [string, { class_type?: string; inputs?: Record<string, unknown> }][];
    const candidates = nodes.flatMap(([nodeId, node]) => Object.keys(node.inputs ?? {}).filter(field => /image|mask|text|prompt|seed/i.test(field)).map(field => ({ nodeId, field })));
    if (!inputPorts.length) setInputPorts(candidates.slice(0, Math.max(1, module.inputs.length)).map((item, index) => ({ id: `input_${index + 1}`, label: item.field, data_type: /image/i.test(item.field) ? "image" : /mask/i.test(item.field) ? "mask" : "text", node_id: item.nodeId, field: item.field, is_required: true })));
    const outputNodes = nodes.filter(([, node]) => /saveimage|previewimage|vae decode/i.test(node.class_type ?? ""));
    if (!outputPorts.length && outputNodes.length) setOutputPorts(outputNodes.map(([nodeId], index) => ({ id: `output_${index + 1}`, label: `Salida ${index + 1}`, data_type: "image", node_id: nodeId, field: "images", is_required: true })));
    toast.success("Puertos sugeridos. Revisa IDs, títulos y tipos.");
  };

  const save = async () => {
    if (!parsed) return toast.error("El JSON no es válido.");
    if (!inputPorts.every(port => port.id && port.label && port.node_id && port.field) || !outputPorts.every(port => port.id && port.label && port.node_id)) return toast.error("Completa todos los puertos del Workflow.");
    setBusy(true);
    try {
      const existingInputs = (config.input_bindings ?? []) as WorkflowInputBinding[];
      const existingOutputs = (config.output_bindings ?? []) as WorkflowOutputBinding[];
      const inputBindings = inputPorts.map(port => {
        const previous = existingInputs.find(binding => binding.port_id === port.id || binding.input_field === port.field);
        return { port_id: port.id, module_input_key: previous?.module_input_key ?? null, source_path: previous?.source_path ?? null, node_id: String(port.node_id), input_field: String(port.field) };
      }).filter(binding => binding.module_input_key || binding.source_path);
      const outputBindings = outputPorts.map(port => ({ port_id: port.id, module_output_key: port.id, node_id: String(port.node_id) }));
      const url = target.mode === "edit" ? `/api/admin/generation-modules/${module.id}/steps/${step!.id}/workflow` : `/api/admin/generation-modules/${module.id}/steps/workflow`;
      const body = target.mode === "edit"
        ? { name, description, workflow_name: name, workflow_json: parsed, input_bindings: inputBindings, output_bindings: outputBindings, input_ports: inputPorts, output_ports: outputPorts, is_enabled: enabled }
        : { key, name, description, position: Math.max(-1, ...module.steps.map(item => item.position)) + 1, workflow_name: name, workflow_json: parsed, input_bindings: inputBindings, output_bindings: outputBindings, input_ports: inputPorts, output_ports: outputPorts, is_enabled: enabled };
      onSaved(await browserApiRequest<GenerationModule>(url, { method: target.mode === "edit" ? "PATCH" : "POST", body: JSON.stringify(body) }));
      toast.success(target.mode === "edit" ? "Workflow actualizado." : "Workflow agregado.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "No fue posible guardar."); } finally { setBusy(false); }
  };

  return <ModalShell title={target.mode === "edit" ? "Editar Workflow" : "Agregar Workflow"} onClose={onClose}>
    <div className="grid gap-3 md:grid-cols-2">{target.mode === "create" && <Field label="Clave"><input className="gm-input" value={key} onChange={e => setKey(e.target.value)}/></Field>}<Field label="Nombre"><input className="gm-input" value={name} onChange={e => setName(e.target.value)}/></Field></div>
    <Field label="Descripción"><input className="gm-input" value={description} onChange={e => setDescription(e.target.value)}/></Field>
    <div className="mt-4 flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">JSON API de ComfyUI</p><button onClick={autoDetect} className="gm-secondary"><Sparkles size={14}/>Detectar puertos</button></div>
    <textarea className="gm-input mt-2 min-h-64 py-3 font-mono text-xs" value={json} onChange={e => setJson(e.target.value)}/>
    <div className="mt-5 grid gap-4 xl:grid-cols-2"><NodePortsEditor title="Inputs del Workflow" side="input" ports={inputPorts} setPorts={setInputPorts} comfy/><NodePortsEditor title="Outputs del Workflow" side="output" ports={outputPorts} setPorts={setOutputPorts} comfy/></div>
    <label className="mt-4 flex items-center gap-2 text-sm text-zinc-400"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>Nodo activo</label>
    <button onClick={() => void save()} disabled={busy || !parsed} className="mt-5 h-11 w-full rounded-xl bg-red-600 font-semibold text-white disabled:opacity-40">{busy ? "Guardando..." : "Guardar Workflow"}</button>
  </ModalShell>;
}

function PythonStepEditor({ module, target, onClose, onSaved }: { module: GenerationModule; target: NonNullable<EditorTarget>; onClose: () => void; onSaved: (module: GenerationModule) => void }) {
  const step = target.step; const config = step?.configuration ?? {};
  const [key, setKey] = useState(step?.key ?? `python_${module.steps.length + 1}`);
  const [name, setName] = useState(step?.name ?? "Paso Python");
  const [description, setDescription] = useState(step?.description ?? "");
  const [entrypoint, setEntrypoint] = useState(String(config.entrypoint ?? "run"));
  const [source, setSource] = useState(String(config.source_code ?? "def run(inputs):\n    return inputs\n"));
  const [inputPorts, setInputPorts] = useState<GenerationNodePort[]>(((config.input_ports ?? []) as GenerationNodePort[]).length ? (config.input_ports as GenerationNodePort[]) : Object.keys(step?.input_mapping ?? {}).map(id => ({ id, label: id, data_type: "auto" })));
  const [outputPorts, setOutputPorts] = useState<GenerationNodePort[]>(((config.output_ports ?? []) as GenerationNodePort[]).length ? (config.output_ports as GenerationNodePort[]) : Object.keys(step?.output_mapping ?? {}).map(id => ({ id, label: id, data_type: "auto" })));
  const [enabled, setEnabled] = useState(step?.is_enabled ?? true);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!inputPorts.every(port => port.id && port.label) || !outputPorts.every(port => port.id && port.label)) return toast.error("Completa IDs y títulos de todos los puertos.");
    setBusy(true);
    try {
      const currentInputMapping = step?.input_mapping ?? {};
      const inputMapping = Object.fromEntries(inputPorts.filter(port => currentInputMapping[port.id] !== undefined).map(port => [port.id, currentInputMapping[port.id]]));
      const outputMapping = Object.fromEntries(outputPorts.map(port => [port.id, String(step?.output_mapping?.[port.id] ?? port.id)]));
      const url = target.mode === "edit" ? `/api/admin/generation-modules/${module.id}/steps/${step!.id}/python` : `/api/admin/generation-modules/${module.id}/steps/python`;
      const body = target.mode === "edit"
        ? { name, description, source_code: source, entrypoint, timeout_seconds: Number(config.timeout_seconds ?? 300), input_mapping: inputMapping, output_mapping: outputMapping, input_ports: inputPorts, output_ports: outputPorts, is_enabled: enabled }
        : { key, name, description, position: Math.max(-1, ...module.steps.map(item => item.position)) + 1, source_code: source, entrypoint, timeout_seconds: 300, input_mapping: inputMapping, output_mapping: outputMapping, input_ports: inputPorts, output_ports: outputPorts, is_enabled: enabled };
      onSaved(await browserApiRequest<GenerationModule>(url, { method: target.mode === "edit" ? "PATCH" : "POST", body: JSON.stringify(body) }));
      toast.success(target.mode === "edit" ? "Python actualizado." : "Python agregado.");
    } catch (error) { toast.error(error instanceof Error ? error.message : "No fue posible guardar."); } finally { setBusy(false); }
  };

  return <ModalShell title={target.mode === "edit" ? "Editar Python" : "Agregar Python"} onClose={onClose}>
    <div className="grid gap-3 md:grid-cols-3">{target.mode === "create" && <Field label="Clave"><input className="gm-input" value={key} onChange={e => setKey(e.target.value)}/></Field>}<Field label="Nombre"><input className="gm-input" value={name} onChange={e => setName(e.target.value)}/></Field><Field label="Función"><input className="gm-input" value={entrypoint} onChange={e => setEntrypoint(e.target.value)}/></Field></div>
    <Field label="Descripción"><input className="gm-input" value={description} onChange={e => setDescription(e.target.value)}/></Field>
    <div className="mt-5 grid gap-4 xl:grid-cols-2"><NodePortsEditor title="Inputs de Python" side="input" ports={inputPorts} setPorts={setInputPorts} comfy={false}/><NodePortsEditor title="Outputs de Python" side="output" ports={outputPorts} setPorts={setOutputPorts} comfy={false}/></div>
    <div className="mt-5 rounded-xl border border-cyan-500/15 bg-cyan-500/5 p-3"><p className="text-xs font-semibold uppercase tracking-wider text-cyan-300">Variables disponibles en el código</p><div className="mt-2 space-y-1">{inputPorts.map(port => <code key={port.id} className="block text-xs text-zinc-300">inputs[{JSON.stringify(port.id)}] <span className="text-zinc-600"># {port.label} · {port.data_type}</span></code>)}</div><div className="mt-3 space-y-1">{outputPorts.map(port => <code key={port.id} className="block text-xs text-zinc-300">return &#123;{JSON.stringify(port.id)}: valor&#125; <span className="text-zinc-600"># {port.label} · {port.data_type}</span></code>)}</div></div>
    <div className="mt-4"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">Código Python</p><textarea className="gm-input min-h-96 py-3 font-mono text-xs" value={source} onChange={e => setSource(e.target.value)}/></div>
    <label className="mt-4 flex items-center gap-2 text-sm text-zinc-400"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)}/>Nodo activo</label>
    <button onClick={() => void save()} disabled={busy} className="mt-5 h-11 w-full rounded-xl bg-red-600 font-semibold text-white disabled:opacity-40">{busy ? "Guardando..." : "Guardar Python"}</button>
  </ModalShell>;
}

function collectAvailablePorts(module: GenerationModule, current?: GenerationModuleStep) { const ordered = [...module.steps].sort((a, b) => a.position - b.position); const limit = current ? ordered.findIndex(item => item.id === current.id) : ordered.length; return [...module.inputs.map(input => ({ key: input.key, label: input.name, type: input.input_type, path: input.key, origin: "module" })), ...ordered.slice(0, limit).flatMap(step => describeStepOutputs(step, module))]; }
function JsonMapping({ title, value, onChange }: { title: string; value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void }) { const [text, setText] = useState(JSON.stringify(value, null, 2)); useEffect(() => setText(JSON.stringify(value, null, 2)), [value]); return <div className="mt-4"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">{title}</p><textarea className="gm-input min-h-28 py-3 font-mono text-xs" value={text} onChange={e => { setText(e.target.value); try { onChange(JSON.parse(e.target.value)); } catch {} }}/></div>; }

function CreateModuleModal({ onClose, onCreated }: { onClose: () => void; onCreated: (module: GenerationModule) => void }) {
  const [form, setForm] = useState({ key: "", name: "", description: "", category: "tryon", appwebTabTitle: "", appwebMode: "automatic" as "automatic" | "managed" });
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    try {
      const module = await browserApiRequest<GenerationModule>("/api/admin/generation-modules", {
        method: "POST",
        body: JSON.stringify({
          key: form.key,
          name: form.name,
          description: form.description,
          category: form.category,
          version: 1,
          is_active: false,
          metadata: {
            appweb_mode: form.appwebMode,
            appweb_tab_title: form.appwebTabTitle.trim() || form.name.trim(),
          },
          inputs: [],
          outputs: [],
          steps: [],
        }),
      });
      onCreated(module);
      toast.success("Módulo creado como borrador. Configura motor, runtime, precio e integración AppWeb cuando estés listo.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "No fue posible crear el módulo.");
    } finally {
      setBusy(false);
    }
  };

  return <ModalShell title="Nuevo módulo" onClose={onClose}>
    <div className="rounded-2xl border border-cyan-500/15 bg-cyan-500/[.04] p-4 text-sm leading-6 text-cyan-100/80">
      Crea primero la ficha básica. El motor, endpoint, precio, entradas, salidas y pasos se pueden configurar después.
    </div>
    <div className="mt-4 grid gap-4 md:grid-cols-2">
      <Field label="Clave"><input className="gm-input" value={form.key} onChange={e => setForm({ ...form, key: e.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, "-") })}/></Field>
      <Field label="Nombre"><input className="gm-input" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}/></Field>
      <Field label="Categoría"><input className="gm-input" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}/></Field>
      <Field label="Descripción"><input className="gm-input" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}/></Field>
      <Field label="Título de pestaña"><input className="gm-input" value={form.appwebTabTitle} onChange={e => setForm({ ...form, appwebTabTitle: e.target.value })} placeholder={form.name || "Ej. Crear Try-On"}/></Field>
      <Field label="Integración AppWeb"><select className="gm-input" value={form.appwebMode} onChange={e => setForm({ ...form, appwebMode: e.target.value as "automatic" | "managed" })}><option value="automatic">Automático · formulario dinámico</option><option value="managed">Administrado · interfaz personalizada</option></select></Field>
    </div>
    <button disabled={busy || form.key.length < 2 || form.name.length < 2 || form.category.length < 2} onClick={() => void create()} className="mt-5 h-11 w-full rounded-xl bg-red-600 font-semibold text-white disabled:opacity-40">{busy ? "Creando..." : "Crear borrador"}</button>
  </ModalShell>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block"><span className="mb-2 block text-xs font-semibold uppercase tracking-wider text-zinc-600">{label}</span>{children}</label>; }
function Contract({ title, onAdd, children }: { title: string; onAdd: () => void; children: React.ReactNode }) { return <div><div className="mb-3 flex items-center justify-between"><h3 className="text-xs font-semibold uppercase tracking-[.18em] text-zinc-500">{title}</h3><button onClick={onAdd} className="gm-secondary"><Plus size={14}/>Agregar</button></div><div className="space-y-2 rounded-2xl border border-white/6 bg-white/[.015] p-3">{children}</div></div>; }
function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) { return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"><div className="max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-3xl border border-white/10 bg-[#0b0b0d] shadow-2xl"><div className="sticky top-0 z-10 flex items-center justify-between border-b border-white/7 bg-[#0b0b0d]/95 p-5"><h2 className="text-xl font-semibold text-white">{title}</h2><button onClick={onClose} className="gm-icon"><X size={18}/></button></div><div className="p-5">{children}</div></div></div>; }
