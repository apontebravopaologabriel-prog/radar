"use client";

import { useState } from "react";
import { CV_SECTIONS, entryLabel, type CvSection } from "../lib/cv-profile-api";
import type { CvEntry } from "../lib/setup-api";

export default function CvFields({ section, entries, onChange, disabled }: { section: CvSection; entries: CvEntry[]; onChange: (entries: CvEntry[]) => void; disabled?: boolean }) {
  const config = CV_SECTIONS[section];
  return <div className="mycv-fields">
    {entries.map((entry, index) => <details key={index} className="mycv-entry" open={Object.keys(entry).length === 0}>
      <summary>{entryLabel(entry)}</summary>
      <fieldset disabled={disabled}>
        <div className="mycv-grid">{Object.entries(config.fields).map(([key, label]) => {
          const multiline = ["bullets", "skills", "description"].includes(key);
          const value = Array.isArray(entry[key]) ? entry[key].join("\n") : String(entry[key] ?? "");
          const change = (text: string) => onChange(entries.map((item, i) => i === index ? { ...item, [key]: ["bullets", "skills"].includes(key) ? text.split("\n") : text } : item));
          return <label key={key} className={multiline ? "mycv-wide" : ""}>{label}{multiline
            ? <textarea rows={key === "bullets" ? 3 : 2} maxLength={key === "bullets" || key === "skills" ? 3612 : 300} value={value} onChange={(event) => change(event.target.value)} />
            : <input maxLength={300} value={value} onChange={(event) => change(event.target.value)} />}</label>;
        })}</div>
        <div className="mycv-entry-actions">
          <button type="button" className="mycv-mini-act" disabled={disabled} onClick={() => onChange(entries.filter((_, i) => i !== index))}>[quitar]</button>
          <CopyEntry entry={entry} />
        </div>
      </fieldset>
    </details>)}
    <button type="button" className="mycv-add-act" disabled={disabled} onClick={() => onChange([...entries, {}])}>[+ añadir {config.label.toLowerCase()}]</button>
  </div>;
}

function CopyEntry({ entry }: { entry: CvEntry }) {
  const [copied, setCopied] = useState(false);
  return <button type="button" className="mycv-mini-act" onClick={async () => {
    try { await navigator.clipboard.writeText(Object.values(entry).filter(Boolean).map((value) => Array.isArray(value) ? value.join("\n") : value).join("\n")); setCopied(true); }
    catch { setCopied(false); }
  }}>{copied ? "[copiado]" : "[copiar]"}</button>;
}
