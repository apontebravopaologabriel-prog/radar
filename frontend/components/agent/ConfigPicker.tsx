"use client";

import { useEffect, useRef, useState } from "react";
import type { AgentSettings } from "../../lib/mobile-api";

type Effort = "auto" | "none" | "low" | "high" | "max";
const EFFORT_LABEL: Record<string, string> = { auto: "Auto", none: "Sin razonar", low: "Bajo", high: "Alto", max: "Máximo" };

/** Selector en línea al estilo Claude Code: ↑↓ elige modelo, ←→ ajusta el effort (slider horizontal),
 *  Enter aplica ambos y Esc cierra. Ocupa el ancho del panel y pasa a columnas cuando hay espacio. */
export default function ConfigPicker({ settings, focus, onApply, onClose }: {
  settings: AgentSettings; focus: "model" | "effort"; onApply: (model: string, effort: Effort) => Promise<void>; onClose: () => void;
}) {
  const provider = settings.providers[settings.provider];
  const models = provider?.models?.length ? provider.models : [settings.model];
  const efforts = ["auto", ...(provider?.reasoning_efforts ?? [])].filter((v, i, a) => a.indexOf(v) === i) as Effort[];
  const [modelIndex, setModelIndex] = useState(Math.max(0, models.indexOf(settings.model)));
  const [effortIndex, setEffortIndex] = useState(Math.max(0, efforts.indexOf(settings.reasoning_effort as Effort)));
  const [saving, setSaving] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => { root.current?.focus(); }, []);
  const modelName = (value: string) => provider?.model_names?.[value] ?? value;

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const key = event.key;
    if (key === "Escape") { event.preventDefault(); onClose(); return; }
    if (key === "ArrowDown") { event.preventDefault(); setModelIndex((i) => (i + 1) % models.length); }
    else if (key === "ArrowUp") { event.preventDefault(); setModelIndex((i) => (i - 1 + models.length) % models.length); }
    else if (key === "ArrowRight" && efforts.length > 1) { event.preventDefault(); setEffortIndex((i) => Math.min(i + 1, efforts.length - 1)); }
    else if (key === "ArrowLeft" && efforts.length > 1) { event.preventDefault(); setEffortIndex((i) => Math.max(i - 1, 0)); }
    else if (key === "Enter") { event.preventDefault(); void apply(); }
  };
  const apply = async () => {
    if (saving) return;
    setSaving(true);
    try { await onApply(models[modelIndex], efforts[effortIndex] ?? "auto"); onClose(); } finally { setSaving(false); }
  };

  return (
    <div ref={root} className="cfg-picker" role="dialog" aria-label="Modelo y esfuerzo de razonamiento" tabIndex={-1} onKeyDown={onKeyDown} data-focus={focus}>
      <div className="cfg-picker-title">Modelo y esfuerzo</div>
      <div className="cfg-picker-body">
        <ul className="cfg-models" role="listbox" aria-label="Modelos">
          {models.map((model, index) => (
            <li key={model} role="option" aria-selected={index === modelIndex} className={index === modelIndex ? "on" : ""}
              onMouseEnter={() => setModelIndex(index)} onClick={() => { setModelIndex(index); }}>
              <span aria-hidden>{index === modelIndex ? "❯" : " "}</span>
              <span>{index + 1}. {modelName(model)}</span>
              {model === settings.model && <b>actual</b>}
            </li>
          ))}
        </ul>
        {efforts.length > 1 && (
          <div className="cfg-effort" role="slider" aria-label="Esfuerzo de razonamiento" aria-valuemin={0} aria-valuemax={efforts.length - 1} aria-valuenow={effortIndex} aria-valuetext={EFFORT_LABEL[efforts[effortIndex]]}>
            <div className="cfg-effort-track">
              {efforts.map((value, index) => (
                <button type="button" key={value} className={index === effortIndex ? "on" : index < effortIndex ? "lit" : ""} onClick={() => setEffortIndex(index)} tabIndex={-1}>
                  <i aria-hidden>{index <= effortIndex ? "●" : "○"}</i><span>{EFFORT_LABEL[value] ?? value}</span>
                </button>
              ))}
            </div>
            <small>{EFFORT_LABEL[efforts[effortIndex]]} · ← → para ajustar</small>
          </div>
        )}
      </div>
      <div className="cfg-picker-hint">↑↓ modelo · ←→ effort · Enter aplicar · Esc cerrar{saving ? " · guardando…" : ""}</div>
    </div>
  );
}
