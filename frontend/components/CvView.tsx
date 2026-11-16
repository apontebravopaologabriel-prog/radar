"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Career } from "../lib/mobile-api";
import { cvProfileApi } from "../lib/cv-profile-api";
import CvHistoryEditor from "./CvHistoryEditor";
import MyCvProfile from "./MyCvProfile";
import "./cv.css";

export default function CvView() {
  const [career, setCareer] = useState<Career | null>(null);
  const [hasProfile, setHasProfile] = useState(true);
  const [profileName, setProfileName] = useState<string>("");
  const [revision, setRevision] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [next, me] = await Promise.all([cvProfileApi.read(), api.me()]);
      setRevision(next.revision);
      setHasProfile(Boolean(me.name));
      setProfileName(me.name || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo cargar tu CV.");
    }
  }, []);

  useEffect(() => {
    api.career().then(setCareer).catch((reason) => setError(String(reason)));
    void refresh();
  }, [refresh]);

  return (
    <div className="cv-view">
      <div className="cv-stage">
        <header className="cv-stage-bar">
          <div className="cv-stage-title">
            <strong>Mi CV</strong>
            <span>{profileName || "Sin perfil"}</span>
          </div>
          <div className="cv-stage-actions">
            <a className="cv-pill-btn" href="/ajustes">Ajustes ↗</a>
          </div>
        </header>

        {error && <p role="alert" className="cv-note cv-stage-error">{error}</p>}

        <div className="cv-stage-pad">
          {!hasProfile ? (
            career ? <MyCvProfile career={career} onChanged={() => void refresh()} /> : <p className="cv-note">Cargando…</p>
          ) : (
            <div className="mycv-profile">
              <CvHistoryEditor key={`history-${revision}`} onChanged={() => void refresh()} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
