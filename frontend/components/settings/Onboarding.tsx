"use client";

import { useEffect, useState } from "react";
import { api, type Career } from "../../lib/mobile-api";
import { setupApi } from "../../lib/setup-api";
import CvImportPanel from "../CvImportPanel";
import RefreshPanel from "./RefreshPanel";

export default function Onboarding({ onDone, onError, onPause }: { onDone: () => void; onError: (e: unknown) => void; onPause?: () => void }) {
  const [career, setCareer] = useState<Career | null>(null);
  const [market, setMarket] = useState("");
  const [name, setName] = useState("");
  const [saved, setSaved] = useState(false);
  const [firstRun, setFirstRun] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([api.career(), setupApi.state(), api.me()]).then(([c, state, me]) => {
      if (!active) return;
      setCareer(c); setMarket(state.draft?.career_id ?? c.active); setName(me.name); setFirstRun(!state.completed);
    }).catch(onError);
    return () => { active = false; };
  }, [onError]);
  if (!career) return <p className="m-empty">Cargando…</p>;
  if (saved) return <div className="m-stack">
    <header className="m-head"><span className="m-eyebrow">[LISTO]</span><h1>Tu CV está guardado</h1><p>Puedes actualizarlo cuando quieras en Mi CV.</p></header>
    {firstRun && <RefreshPanel places={["Lima"]} autoStart onError={onError} />}
    <button className="m-primary" onClick={onDone}>Ir al mapa</button>
  </div>;
  return <div className="m-stack mycv-profile">
    <header className="m-head"><span className="m-eyebrow">[INICIO]</span><h1>Empieza con tu CV</h1><p>Importa tus datos, revísalos una vez y empieza a explorar ofertas.</p></header>
    <section className="m-card"><label>Mercado · Lima/Callao<select value={market} onChange={(event) => setMarket(event.target.value)}>{career.tracks.map((track) => <option key={track.id} value={track.id}>{track.name}</option>)}</select></label></section>
    <CvImportPanel key={market} careerId={market} initialName={name} allowManual onSaved={() => { try { localStorage.setItem("radar.market", market); } catch { /* Optional. */ } setSaved(true); }} />
    {onPause && <button type="button" onClick={onPause}>Continuar después</button>}
  </div>;
}
