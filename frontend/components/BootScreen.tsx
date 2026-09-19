"use client";

import { CSSProperties, useEffect, useState } from "react";

const LINES: { text: string; ok?: boolean }[] = [
  { text: "> BOOTING RADAR OS v2.4..." },
  { text: "> ESTABLISHING SATELLITE LINK... OK", ok: true },
  { text: "> DECRYPTING MARKET SIGNALS..." },
  { text: "> CONNECTING TO RADAR API..." },
  { text: "> LOADING GEOSPATIAL GRID... OK", ok: true },
  { text: "> READY." },
];

const STEP_MS = 190;
// The real app is already loading data behind this overlay. The typewriter
// intro always plays in full (it's the point), but once it's done we don't
// keep the user waiting on a fixed timer — we exit as soon as `ready` is
// true, with a short ceiling so a stuck request never leaves this stuck up.
const MAX_EXTRA_WAIT_MS = 1400;

export default function BootScreen({ ready, onDone }: { ready: boolean; onDone: () => void }) {
  const [introDone, setIntroDone] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const introMs = LINES.length * STEP_MS + 250;
    const timer = setTimeout(() => setIntroDone(true), introMs);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!introDone || exiting) return;
    if (ready) {
      const timer = setTimeout(() => setExiting(true), 100);
      return () => clearTimeout(timer);
    }
    const ceiling = setTimeout(() => setExiting(true), MAX_EXTRA_WAIT_MS);
    return () => clearTimeout(ceiling);
  }, [introDone, ready, exiting]);

  useEffect(() => {
    if (!exiting) return;
    const timer = setTimeout(onDone, 320);
    return () => clearTimeout(timer);
  }, [exiting, onDone]);

  return (
    <div className={`boot-screen ${exiting ? "is-exiting" : ""}`} role="status" aria-live="polite">
      <div className="boot-lines">
        {LINES.map((line, index) => (
          <span
            key={line.text}
            className={`boot-line ${line.ok ? "ok" : ""}`}
            style={{ "--boot-w": `${line.text.length}ch`, "--boot-delay": `${index * (STEP_MS / 1000)}s` } as CSSProperties}
          >
            {line.text}
          </span>
        ))}
        <span className="boot-cursor" aria-hidden="true" />
      </div>
      <div className="boot-progress">
        <div className="boot-progress-track"><div className="boot-progress-fill" /></div>
        <p className="boot-percent">Sincronizando radar de empleo · Lima Metropolitana</p>
      </div>
    </div>
  );
}
