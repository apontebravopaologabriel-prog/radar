"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

/** Muestra una lista larga por tramos: el DOM crece solo cuando el usuario se acerca al final.
 *  Con 1 100+ ofertas evita ~30 000 nodos; la oferta seleccionada siempre queda incluida (atajos j/k). */
export function useProgressiveList<T extends { id: string }>(list: T[], selectedId: string | null, step = 60) {
  const [count, setCount] = useState(step);
  const [sentinel, setSentinel] = useState<HTMLElement | null>(null);

  useEffect(() => { setCount(step); }, [list, step]);

  const selectedIndex = useMemo(() => (selectedId ? list.findIndex((item) => item.id === selectedId) : -1), [list, selectedId]);
  const visible = Math.min(list.length, Math.max(count, selectedIndex >= 0 ? selectedIndex + step / 2 : 0));
  const hasMore = visible < list.length;

  useEffect(() => {
    if (!sentinel || !hasMore || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setCount((c) => Math.min(c + step, list.length));
    }, { rootMargin: "600px 0px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [sentinel, hasMore, step, list.length, visible]);

  const items = useMemo(() => list.slice(0, visible), [list, visible]);
  const sentinelRef = useCallback((node: HTMLElement | null) => setSentinel(node), []);
  return { items, hasMore, sentinelRef, total: list.length };
}
