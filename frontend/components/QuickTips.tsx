"use client";
import { useEffect, useState } from "react";
const TIPS = [["Explora por distrito", "Selecciona un distrito del mapa para ver sus ofertas. Las ubicaciones y distancias son aproximadas."], ["Revisa y guarda", "Abre una oferta para revisar la descripción. Usa ★ para guardarla y comparar sus requisitos en Mi CV."], ["Sigue solo lo que avanza", "Cuando recibas una respuesta, usa Me contactaron. Procesos guarda el próximo paso si te sirve; no necesitas registrar cada solicitud."]];
export default function QuickTips() {
  const [step, setStep] = useState<number | null>(null);
  const finish = () => { try { localStorage.removeItem("radar.tips.pending"); } catch { /* Optional. */ } setStep(null); };
  useEffect(() => {
    try { if (localStorage.getItem("radar.tips.pending") === "1") setStep(0); } catch { /* Optional. */ }
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { try { localStorage.removeItem("radar.tips.pending"); } catch { /* Optional. */ } setStep(null); } };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);
  if (step === null) return null;
  return <div className="radar-tip" role="dialog" aria-label="Guía rápida de Radar"><small>{step + 1} / {TIPS.length}</small><h3>{TIPS[step][0]}</h3><p>{TIPS[step][1]}</p><button onClick={finish}>Omitir</button><button onClick={() => step + 1 === TIPS.length ? finish() : setStep(step + 1)}>{step + 1 === TIPS.length ? "Listo" : "Siguiente"}</button></div>;
}
