"use client";

import {
  CheckCircle2,
  Clipboard,
  Container,
  Database,
  LoaderCircle,
  Play,
  Save,
  Search,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { browserApiRequest } from "@/lib/api/browser-api";
import type {
  RuntimeContextJob,
  RuntimeLaunchSettings,
  RuntimeModelExportSettings,
  RuntimeModelVolumeAnalysis,
  RuntimeModelVolumeExportResponse,
} from "@/types/admin-runtime-builder";

const input =
  "h-11 w-full rounded-xl border border-white/10 bg-black/25 px-3 text-sm text-white outline-none focus:border-red-500/50";

type TerminalFormat = "powershell" | "cmd" | "bash" | "single-line";

const terminalLabels: Record<TerminalFormat, string> = {
  powershell: "PowerShell",
  cmd: "CMD",
  bash: "Bash / Zsh",
  "single-line": "Una sola línea",
};

const defaults: RuntimeLaunchSettings = {
  build_name: "ia-comfyui-python-build",
  image_name: "ia-comfyui-python",
  container_name: "ia-comfyui-python-container",
  host_port: 8190,
  container_port: 8188,
  models_volume: "",
  workflows_volume: "",
  output_volume: "",
  models_mount_path: "/app/ComfyUI/models",
  workflows_mount_path: "/app/ComfyUI/user/default/workflows",
  output_mount_path: "/app/ComfyUI/output",
  gpu_mode: "nvidia",
  restart_policy: "unless-stopped",
  extra_arguments: [],
};

export function RuntimeMega3Panel() {
  const [volumes, setVolumes] = useState<Array<{ name: string }>>([]);
  const [settings, setSettings] =
    useState<RuntimeModelExportSettings | null>(null);
  const [launch, setLaunch] = useState(defaults);
  const [terminalFormat, setTerminalFormat] = useState<TerminalFormat>("powershell");
  const [analysis, setAnalysis] =
    useState<RuntimeModelVolumeAnalysis | null>(null);
  const [result, setResult] =
    useState<RuntimeModelVolumeExportResponse | null>(null);
  const [job, setJob] = useState<RuntimeContextJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [savingModels, setSavingModels] = useState(false);
  const [savingRuntime, setSavingRuntime] = useState(false);
  const [savingAll, setSavingAll] = useState(false);

  const load = useCallback(async () => {
    const [v, s, l] = await Promise.all([
      browserApiRequest<{ items: Array<{ name: string }> }>(
        "/api/admin/docker-file-manager/volumes",
      ),
      browserApiRequest<RuntimeModelExportSettings>(
        "/api/admin/runtime-builder/models-volume/settings",
      ),
      browserApiRequest<RuntimeLaunchSettings>(
        "/api/admin/runtime-builder/runtime-launch/settings",
      ),
    ]);
    setVolumes(v.items);
    setSettings(s);
    setLaunch(l);
  }, []);

  useEffect(() => {
    void load().catch((error) =>
      toast.error(
        error instanceof Error
          ? error.message
          : "No se pudo cargar la configuración.",
      ),
    );
  }, [load]);

  const patch = <K extends keyof RuntimeModelExportSettings>(
    key: K,
    value: RuntimeModelExportSettings[K],
  ) => setSettings((current) => (current ? { ...current, [key]: value } : current));

  const patchLaunch = <K extends keyof RuntimeLaunchSettings>(
    key: K,
    value: RuntimeLaunchSettings[K],
  ) => setLaunch((current) => ({ ...current, [key]: value }));

  const persistModelSettings = async (showToast = true) => {
    if (!settings) return false;
    setSavingModels(true);
    try {
      const saved = await browserApiRequest<RuntimeModelExportSettings>(
        "/api/admin/runtime-builder/models-volume/settings",
        { method: "PUT", body: JSON.stringify(settings) },
      );
      setSettings(saved);
      if (showToast) toast.success("Configuración del exportador guardada.");
      return true;
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "No se pudo guardar el exportador.",
      );
      return false;
    } finally {
      setSavingModels(false);
    }
  };

  const persistRuntimeSettings = async (showToast = true) => {
    setSavingRuntime(true);
    try {
      const saved = await browserApiRequest<RuntimeLaunchSettings>(
        "/api/admin/runtime-builder/runtime-launch/settings",
        { method: "PUT", body: JSON.stringify(launch) },
      );
      setLaunch(saved);
      if (showToast) toast.success("Runtime Configuration guardada.");
      return true;
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "No se pudo guardar Runtime Configuration.",
      );
      return false;
    } finally {
      setSavingRuntime(false);
    }
  };

  const saveAllConfiguration = async () => {
    setSavingAll(true);
    try {
      const [modelsSaved, runtimeSaved] = await Promise.all([
        persistModelSettings(false),
        persistRuntimeSettings(false),
      ]);
      if (modelsSaved && runtimeSaved) {
        toast.success("Toda la configuración fue guardada.");
      }
    } finally {
      setSavingAll(false);
    }
  };

  const wait = async (created: RuntimeContextJob) => {
    let current = created;
    let transientErrors = 0;

    while (["queued", "running"].includes(current.status)) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      try {
        current = await browserApiRequest<RuntimeContextJob>(
          `/api/admin/runtime-builder/context/jobs/${created.job_id}`,
        );
        transientErrors = 0;
        setJob(current);
      } catch (error) {
        transientErrors += 1;
        if (transientErrors >= 3) throw error;
      }
    }

    if (current.status === "failed") {
      throw new Error(current.error || "Exportación fallida.");
    }
    if (!current.result) throw new Error("La exportación terminó sin resultado.");
    return current.result as RuntimeModelVolumeExportResponse;
  };

  const analyze = async () => {
    if (!settings?.comfyui_path) {
      toast.error("Indica la ruta de ComfyUI.");
      return;
    }
    setBusy(true);
    try {
      setAnalysis(
        await browserApiRequest<RuntimeModelVolumeAnalysis>(
          "/api/admin/runtime-builder/models-volume/analyze",
          {
            method: "POST",
            body: JSON.stringify({ comfyui_path: settings.comfyui_path }),
          },
        ),
      );
      toast.success("Análisis completado.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Error de análisis.",
      );
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    if (!settings?.comfyui_path) {
      toast.error("Indica la ruta de ComfyUI.");
      return;
    }
    if (
      settings.destination_type === "docker_volume" &&
      !settings.docker_volume
    ) {
      toast.error("Selecciona un volumen.");
      return;
    }

    setBusy(true);
    setResult(null);
    setJob({
      job_id: "creating",
      status: "queued",
      phase: "requesting",
      progress: 1,
      message: "Solicitando trabajo de exportación al backend…",
    } as RuntimeContextJob);

    try {
      // El endpoint de exportación ya persiste model_export mediante
      // _save_mega3_settings. Guardar primero mediante otro PUT duplicaba la
      // operación y podía dejar la interfaz bloqueada antes de crear el job.
      const created = await browserApiRequest<RuntimeContextJob>(
        "/api/admin/runtime-builder/models-volume/export",
        { method: "POST", body: JSON.stringify(settings) },
      );
      setJob(created);
      setResult(await wait(created));
      toast.success("Exportación terminada.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Exportación fallida.",
      );
    } finally {
      setBusy(false);
    }
  };

  const formattedCommand = formatDockerCommand(
    buildInteractiveDockerRunLines(
      launch,
      settings?.docker_volume,
    ),
    terminalFormat,
  );

  if (!settings) {
    return (
      <div className="luxia-panel rounded-3xl p-8 text-zinc-500">
        Cargando configuración…
      </div>
    );
  }

  const anySaving = savingModels || savingRuntime || savingAll;

  return (
    <div className="space-y-5">
      <div className="flex justify-end">
        <button
          onClick={() => void saveAllConfiguration()}
          disabled={busy || anySaving}
          className="inline-flex h-11 items-center gap-2 rounded-xl bg-red-700 px-5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {savingAll ? (
            <LoaderCircle className="animate-spin" size={16} />
          ) : (
            <Save size={16} />
          )}
          Guardar todo
        </button>
      </div>

      <section className="luxia-panel rounded-3xl p-5">
        <Header
          icon={<Database />}
          eyebrow="Workflow Model Exporter"
          title="Exportación reproducible de modelos"
          text="Exporta los modelos requeridos a una carpeta local, Docker, Modal, RunPod o Beam y revisa el progreso de cada ejecución."
        />
        <div className="grid gap-4 lg:grid-cols-3">
          <Field label="Ruta local de ComfyUI">
            <input
              className={input}
              value={settings.comfyui_path}
              onChange={(event) => patch("comfyui_path", event.target.value)}
              placeholder="F:\\ComfyUI"
            />
          </Field>
          <Field label="Directorio local de salida">
            <input
              className={input}
              value={settings.output_directory}
              onChange={(event) =>
                patch("output_directory", event.target.value)
              }
              placeholder="F:\\runtime_exports"
            />
          </Field>
          <Field label="Destino">
            <select
              className={input}
              value={settings.destination_type}
              onChange={(event) =>
                patch(
                  "destination_type",
                  event.target
                    .value as RuntimeModelExportSettings["destination_type"],
                )
              }
            >
              <option value="local">Carpeta local</option>
              <option value="docker_volume">Volumen Docker</option>
              <option value="modal">Volumen Modal</option>
              <option value="runpod">RunPod Network Volume</option>
              <option value="beam">Volumen Beam</option>
            </select>
          </Field>
        </div>

        {settings.destination_type === "modal" && (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Field label="Volumen Modal configurado">
              <div className={`${input} flex items-center text-zinc-300`}>
                Se usará el volumen configurado en Proveedores de infraestructura
              </div>
              <span className="mt-2 block text-xs text-zinc-600">
                El backend toma automáticamente el nombre del volumen Modal activo.
              </span>
            </Field>
            <Field label="Subcarpeta opcional dentro del volumen Modal">
              <input
                className={input}
                value={settings.docker_path}
                onChange={(event) => patch("docker_path", event.target.value)}
                placeholder="Vacío = raíz del volumen"
              />
              <span className="mt-2 block text-xs text-zinc-600">
                Déjalo vacío para exportar directamente las carpetas de modelos.
              </span>
            </Field>
          </div>
        )}

        {(settings.destination_type === "runpod" || settings.destination_type === "beam") && (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Field label={settings.destination_type === "runpod" ? "RunPod Network Volume configurado" : "Volumen Beam configurado"}>
              <div className={`${input} flex items-center text-zinc-300`}>
                Se usarán las credenciales y el volumen configurados en Proveedores de infraestructura
              </div>
              <span className="mt-2 block text-xs text-zinc-600">
                {settings.destination_type === "runpod"
                  ? "RunPod requiere además Access Key y Secret de su S3 API."
                  : "Beam utiliza su CLI aislado para copiar la carpeta al volumen."}
              </span>
            </Field>
            <Field label="Subcarpeta opcional dentro del volumen">
              <input
                className={input}
                value={settings.docker_path}
                onChange={(event) => patch("docker_path", event.target.value)}
                placeholder="Vacío = raíz del volumen"
              />
            </Field>
          </div>
        )}

        {settings.destination_type === "docker_volume" && (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Field label="Volumen Docker">
              <select
                className={input}
                value={settings.docker_volume}
                onChange={(event) =>
                  patch("docker_volume", event.target.value)
                }
              >
                <option value="">Selecciona…</option>
                {volumes.map((volume) => (
                  <option key={volume.name}>{volume.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Subcarpeta opcional dentro del volumen">
              <input
                className={input}
                value={settings.docker_path}
                onChange={(event) => patch("docker_path", event.target.value)}
                placeholder="Vacío = raíz del volumen"
              />
              <span className="mt-2 block text-xs text-zinc-600">
                Déjalo vacío para exportar directamente unet/, vae/, loras/ y
                las demás categorías en la raíz.
              </span>
            </Field>
          </div>
        )}

        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <Toggle
            label="Omitir idénticos"
            value={settings.skip_identical}
            set={(value) => patch("skip_identical", value)}
          />
          <Toggle
            label="Sobrescribir diferentes"
            value={settings.overwrite}
            set={(value) => patch("overwrite", value)}
          />
          <Toggle
            label="Calcular SHA-256"
            value={settings.calculate_sha256}
            set={(value) => patch("calculate_sha256", value)}
          />
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <Btn
            onClick={() => void persistModelSettings()}
            disabled={busy || anySaving}
          >
            {savingModels ? (
              <LoaderCircle className="animate-spin" size={16} />
            ) : (
              <Save size={16} />
            )}
            Guardar exportador
          </Btn>
          <Btn onClick={() => void analyze()} disabled={busy || anySaving}>
            <Search size={16} />
            Analizar
          </Btn>
          <button
            onClick={() => void run()}
            disabled={busy || anySaving}
            className="inline-flex h-11 items-center gap-2 rounded-xl bg-red-700 px-5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? (
              <LoaderCircle className="animate-spin" size={16} />
            ) : (
              <Play size={16} />
            )}
            Exportar
          </button>
        </div>

        {job && (
          <div className="mt-5">
            <div className="flex justify-between text-sm">
              <span className="text-zinc-400">
                {job.message || "Procesando exportación…"}
              </span>
              <b className="text-red-300">{job.progress || 0}%</b>
            </div>
            <div className="mt-2 h-2 rounded-full bg-white/5">
              <div
                className="h-2 rounded-full bg-red-700 transition-all"
                style={{ width: `${Math.max(1, job.progress || 0)}%` }}
              />
            </div>
          </div>
        )}

        {analysis && (
          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Detectados" value={analysis.models_detected} />
            <Metric label="Encontrados" value={analysis.models_found} />
            <Metric label="Faltantes" value={analysis.models_missing} />
            <Metric label="Tamaño" value={bytes(analysis.bytes_total)} />
          </div>
        )}
      </section>

      <section className="luxia-panel rounded-3xl p-5">
        <Header
          icon={<Container />}
          eyebrow="Runtime Configuration"
          title="Configuración de ejecución Docker"
          text="El comando interactivo usa el build real con tag 1.0.0, GPU, puertos y los volúmenes configurados. Se elimina al salir."
        />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Text
            label="Nombre del build"
            value={launch.build_name}
            set={(value) => patchLaunch("build_name", value)}
          />
          <Text
            label="Nombre de imagen"
            value={launch.image_name}
            set={(value) => patchLaunch("image_name", value)}
          />
          <Text
            label="Nombre de contenedor"
            value={launch.container_name}
            set={(value) => patchLaunch("container_name", value)}
          />
          <div className="md:col-span-2 xl:col-span-3 rounded-xl border border-white/8 bg-black/20 px-4 py-3 text-xs text-zinc-500">
            Imagen que ejecutará Docker:{" "}
            <strong className="text-zinc-300">
              {runtimeImageReference(launch.build_name)}
            </strong>
            . El campo “Nombre de imagen” se conserva como metadato de publicación y no reemplaza el build local.
          </div>
          <NumberField
            label="Puerto host"
            value={launch.host_port}
            set={(value) => patchLaunch("host_port", value)}
          />
          <NumberField
            label="Puerto contenedor"
            value={launch.container_port}
            set={(value) => patchLaunch("container_port", value)}
          />
          <Field label="GPU">
            <select
              className={input}
              value={launch.gpu_mode}
              onChange={(event) =>
                patchLaunch(
                  "gpu_mode",
                  event.target.value as RuntimeLaunchSettings["gpu_mode"],
                )
              }
            >
              <option value="nvidia">NVIDIA</option>
              <option value="auto">Auto</option>
              <option value="none">Sin GPU</option>
            </select>
          </Field>
          <Volume
            label="Volumen modelos"
            value={launch.models_volume}
            set={(value) => patchLaunch("models_volume", value)}
            list={volumes}
          />
          <Volume
            label="Volumen workflows"
            value={launch.workflows_volume}
            set={(value) => patchLaunch("workflows_volume", value)}
            list={volumes}
          />
          <Volume
            label="Volumen outputs"
            value={launch.output_volume}
            set={(value) => patchLaunch("output_volume", value)}
            list={volumes}
          />
        </div>

        <div className="mt-5 flex justify-end">
          <Btn
            onClick={() => void persistRuntimeSettings()}
            disabled={busy || anySaving}
          >
            {savingRuntime ? (
              <LoaderCircle className="animate-spin" size={16} />
            ) : (
              <Save size={16} />
            )}
            Guardar Runtime Configuration
          </Btn>
        </div>

        <div className="mt-5 rounded-2xl border border-white/10 bg-black/40 p-4">
          <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Docker Run interactivo
              </span>
              <p className="mt-1 text-xs text-zinc-600">
                Comando interactivo real con --rm -it. Si los volúmenes del runtime están vacíos, reutiliza el volumen Docker del exportador para modelos y workflows.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="h-9 rounded-lg border border-white/10 bg-zinc-950 px-3 text-xs text-zinc-200 outline-none focus:border-red-500/50"
                value={terminalFormat}
                onChange={(event) =>
                  setTerminalFormat(event.target.value as TerminalFormat)
                }
              >
                {(
                  Object.entries(terminalLabels) as Array<
                    [TerminalFormat, string]
                  >
                ).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                onClick={() => {
                  void navigator.clipboard.writeText(formattedCommand);
                  toast.success(
                    `Comando ${terminalLabels[terminalFormat]} copiado.`,
                  );
                }}
                disabled={!formattedCommand}
                className="inline-flex h-9 items-center gap-2 rounded-lg border border-white/10 px-3 text-xs text-zinc-300 disabled:opacity-50"
              >
                <Clipboard size={15} />
                Copiar
              </button>
            </div>
          </div>
          <pre className="overflow-x-auto whitespace-pre-wrap text-sm leading-7 text-emerald-300">
            {formattedCommand || "Generando comando…"}
          </pre>
          {terminalFormat === "powershell" && (
            <p className="mt-3 text-xs text-zinc-600">
              PowerShell utiliza el acento grave (`) para continuar el comando.
              No debe haber espacios después de ese carácter.
            </p>
          )}
          {terminalFormat === "cmd" && (
            <p className="mt-3 text-xs text-zinc-600">
              CMD utiliza el símbolo ^ para continuar el comando en la línea
              siguiente.
            </p>
          )}
          {terminalFormat === "bash" && (
            <p className="mt-3 text-xs text-zinc-600">
              Bash y Zsh utilizan la barra invertida \ para continuar el
              comando.
            </p>
          )}
        </div>
      </section>

      {result && <Summary result={result} />}
    </div>
  );
}

function Header({
  icon,
  eyebrow,
  title,
  text,
}: {
  icon: React.ReactNode;
  eyebrow: string;
  title: string;
  text: string;
}) {
  return (
    <div className="mb-5 flex gap-4">
      <div className="flex size-12 items-center justify-center rounded-2xl border border-red-500/20 bg-red-950/20 text-red-400">
        {icon}
      </div>
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-red-500">
          {eyebrow}
        </p>
        <h2 className="mt-1 font-semibold text-white">{title}</h2>
        <p className="mt-1 text-sm text-zinc-500">{text}</p>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label>
      <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {label}
      </span>
      {children}
    </label>
  );
}

function Text({
  label,
  value,
  set,
}: {
  label: string;
  value: string;
  set: (value: string) => void;
}) {
  return (
    <Field label={label}>
      <input
        className={input}
        value={value}
        onChange={(event) => set(event.target.value)}
      />
    </Field>
  );
}

function NumberField({
  label,
  value,
  set,
}: {
  label: string;
  value: number;
  set: (value: number) => void;
}) {
  return (
    <Field label={label}>
      <input
        type="number"
        className={input}
        value={value}
        onChange={(event) => set(Number(event.target.value))}
      />
    </Field>
  );
}

function Volume({
  label,
  value,
  set,
  list,
}: {
  label: string;
  value: string;
  set: (value: string) => void;
  list: Array<{ name: string }>;
}) {
  return (
    <Field label={label}>
      <select
        className={input}
        value={value}
        onChange={(event) => set(event.target.value)}
      >
        <option value="">Sin volumen</option>
        {list.map((item) => (
          <option key={item.name}>{item.name}</option>
        ))}
      </select>
    </Field>
  );
}

function Toggle({
  label,
  value,
  set,
}: {
  label: string;
  value: boolean;
  set: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between rounded-2xl border border-white/8 bg-black/20 px-4 py-3 text-sm text-zinc-300">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={value}
        onChange={(event) => set(event.target.checked)}
        className="size-4 accent-red-600"
      />
    </label>
  );
}

function Btn({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/10 px-5 text-sm font-semibold text-zinc-200 disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-2xl border border-white/8 bg-black/20 p-4">
      <span className="text-xs uppercase text-zinc-500">{label}</span>
      <p className="mt-2 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

function Summary({ result }: { result: RuntimeModelVolumeExportResponse }) {
  const summary = result as RuntimeModelVolumeExportResponse & {
    models_overwritten?: number;
    errors?: number;
    elapsed_seconds?: number;
  };

  return (
    <section className="luxia-panel rounded-3xl p-5">
      <div className="flex items-center gap-3">
        <CheckCircle2 className="text-emerald-400" />
        <div>
          <h3 className="font-semibold text-white">Resumen de exportación</h3>
          <p className="text-sm text-zinc-500">
            La operación terminó y el manifiesto quedó generado.
          </p>
        </div>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <Metric label="Exportados" value={result.models_copied} />
        <Metric
          label="Sobrescritos"
          value={summary.models_overwritten || 0}
        />
        <Metric label="Omitidos" value={result.models_skipped} />
        <Metric label="Faltantes" value={result.models_missing} />
        <Metric label="Errores" value={summary.errors || 0} />
        <Metric
          label="Tiempo"
          value={`${summary.elapsed_seconds || 0} s`}
        />
      </div>
      {result.warnings.length > 0 && (
        <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-950/10 p-4 text-sm text-amber-200">
          <div className="flex gap-2 font-semibold">
            <TriangleAlert size={16} />
            Advertencias
          </div>
          {result.warnings.map((warning, index) => (
            <p className="mt-2 text-zinc-400" key={index}>
              • {warning}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}


function asTrimmedString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function runtimeImageReference(buildName: unknown): string {
  const normalizedBuildName = asTrimmedString(buildName);
  if (!normalizedBuildName) return "ia-comfyui-python-build:1.0.0";

  const lastSlash = normalizedBuildName.lastIndexOf("/");
  const lastColon = normalizedBuildName.lastIndexOf(":");
  return lastColon > lastSlash
    ? normalizedBuildName
    : `${normalizedBuildName}:1.0.0`;
}

function buildInteractiveDockerRunLines(
  launch: RuntimeLaunchSettings,
  exportedModelsVolume: unknown,
): string[] {
  // Este bloque es deliberadamente interactivo y efímero.
  // La política de reinicio pertenece al comando detached del backend.
  const lines = ["docker run --rm -it"];

  const gpuMode = asTrimmedString(launch?.gpu_mode);
  if (gpuMode === "nvidia" || gpuMode === "auto") {
    lines.push("  --gpus all");
  }

  const containerName =
    asTrimmedString(launch?.container_name) || "generation-runtime";
  lines.push(`  --name ${containerName}`);

  const hostPort = Number(launch?.host_port) || 8190;
  const containerPort = Number(launch?.container_port) || 8188;
  lines.push(`  -p ${hostPort}:${containerPort}`);

  const fallbackVolume = asTrimmedString(exportedModelsVolume);
  const normalizedBuildName =
    asTrimmedString(launch?.build_name) || "ia-comfyui-python-build";
  const imageBaseName = normalizedBuildName
    .replace(/:[^/]+$/, "")
    .replace(/-build$/i, "");
  const derivedSharedVolume = `${imageBaseName}-volume`;

  const modelsVolume =
    asTrimmedString(launch?.models_volume)
    || fallbackVolume
    || derivedSharedVolume;
  const workflowsVolume =
    asTrimmedString(launch?.workflows_volume)
    || fallbackVolume
    || modelsVolume;
  const outputVolume = asTrimmedString(launch?.output_volume);

  const mounts: Array<[string, string]> = [
    [
      modelsVolume,
      asTrimmedString(launch?.models_mount_path)
        || "/app/ComfyUI/models",
    ],
    [
      workflowsVolume,
      asTrimmedString(launch?.workflows_mount_path)
        || "/app/ComfyUI/user/default/workflows",
    ],
    [
      outputVolume,
      asTrimmedString(launch?.output_mount_path)
        || "/app/ComfyUI/output",
    ],
  ];

  const mounted = new Set<string>();
  for (const [volume, destination] of mounts) {
    if (!volume || !destination) continue;
    const mount = `${volume}:${destination}`;
    if (mounted.has(mount)) continue;
    mounted.add(mount);
    lines.push(`  -v ${mount}`);
  }

  const extraArguments = Array.isArray(launch?.extra_arguments)
    ? launch.extra_arguments
    : [];

  for (const argument of extraArguments) {
    const normalized = asTrimmedString(argument);
    if (normalized) lines.push(`  ${normalized}`);
  }

  lines.push(`  ${runtimeImageReference(launch?.build_name)}`);
  return lines;
}

function formatDockerCommand(
  lines: string[],
  terminal: TerminalFormat,
): string {
  const clean = lines.map((line) => line.trim()).filter(Boolean);
  if (clean.length === 0) return "";

  if (terminal === "single-line") {
    return clean.join(" ");
  }

  const continuation =
    terminal === "powershell" ? "`" : terminal === "cmd" ? "^" : "\\";

  return clean
    .map((line, index) =>
      index < clean.length - 1 ? `${line} ${continuation}` : line,
    )
    .join("\n");
}

function bytes(value: number) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1,
  );
  return `${(value / 1024 ** index).toFixed(index ? 2 : 0)} ${units[index]}`;
}
