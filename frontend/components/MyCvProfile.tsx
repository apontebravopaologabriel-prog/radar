"use client";

import { useState } from "react";
import type { Career } from "../lib/mobile-api";
import CvImportPanel from "./CvImportPanel";
import CvHistoryEditor from "./CvHistoryEditor";
import ProfileTab from "./mobile/ProfileTab";
import "./mobile/settings.css";
import "./my-cv.css";

export default function MyCvProfile({ career, onChanged }: { career: Career; onChanged?: () => void }) {
  const [epoch, setEpoch] = useState(0);
  const [error, setError] = useState("");
  const changed = () => { setEpoch((value) => value + 1); onChanged?.(); };
  return <div className="mycv-profile">
    <CvImportPanel careerId={career.active} allowManual onSaved={changed} />
    {error && <p role="alert" className="mycv-message">{error}</p>}
    <CvHistoryEditor key={`history-${epoch}`} onChanged={onChanged} />
    <details className="mycv-section"><summary>Datos personales y preferencias de búsqueda</summary><ProfileTab key={`profile-${epoch}`} career={career} onError={(reason) => setError(reason instanceof Error ? reason.message : "No se pudo guardar.")} /></details>
  </div>;
}
