"use client";
import { useEffect, useState } from "react";
import { setupApi } from "../lib/setup-api";

export default function ReleaseNotice() {
  const [release, setRelease] = useState<{latest?: string; url: string} | null>(null);
  useEffect(() => {
    let active = true;
    setupApi.updates().then((r) => {
      if (!active || !r.available) return;
      try { if (localStorage.getItem("radar.update.dismissed") === r.latest) return; } catch { /* Optional. */ }
      setRelease(r);
    }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  if (!release) return null;
  return <aside className="release-notice" role="status"><span>Radar {release.latest} disponible</span><a href={release.url} target="_blank" rel="noopener noreferrer">Ver actualización ↗</a><button aria-label="Ocultar aviso de actualización" onClick={() => { try { localStorage.setItem("radar.update.dismissed", release.latest ?? ""); } catch { /* Optional. */ } setRelease(null); }}>×</button></aside>;
}
