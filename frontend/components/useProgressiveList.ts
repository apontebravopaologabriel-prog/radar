"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

// Mismo valor que `contain-intrinsic-size: auto 88px` en perf.css para .offer-scroll-card/.job-card:
// se usa para traducir la posición del scroll a un índice de la lista, y para el alto del espaciador.
const ESTIMATED_ITEM_HEIGHT = 88;
const OVERSCAN = 30; // colchón de items montados a cada lado de la ventana visible
const DEFAULT_MAX_MOUNTED = 150; // ~150 tarjetas × ~48 nodos c/u se queda dentro del presupuesto de 8 000 nodos del DOM

type ScrollTarget = HTMLElement & { __radarScrollCleanup?: () => void };

function windowFor(scrollTop: number, total: number, maxMounted: number, selectedIndex: number) {
  if (total <= maxMounted) return { start: 0, end: total };
  const centerIndex = Math.round(scrollTop / ESTIMATED_ITEM_HEIGHT);
  let start = Math.max(0, Math.min(centerIndex - OVERSCAN, total - maxMounted));
  let end = Math.min(total, start + maxMounted);
  // La oferta seleccionada nunca puede quedar fuera de la ventana, o el atajo j/k la perdería de vista.
  if (selectedIndex >= 0 && (selectedIndex < start || selectedIndex >= end)) {
    start = Math.min(start, Math.max(0, selectedIndex - OVERSCAN));
    end = Math.max(end, Math.min(total, selectedIndex + OVERSCAN));
  }
  return { start, end };
}

/** Muestra una lista larga con una ventana deslizante de tamaño acotado, calculada directamente de la
 *  posición del scroll (una ventana centrada en lo que se está viendo), no acumulando pasos de
 *  "crecer"/"recortar" por separado: toda la lista ya está en memoria (no es paginación real), así que
 *  no hace falta revelarla de a tramos, solo decidir qué parte MONTAR. Un espaciador arriba conserva el
 *  alto real del scroll. La oferta seleccionada nunca queda fuera de la ventana (atajos j/k). Sin el
 *  recorte, recorrer ~1 000 ofertas deja ~50 000 nodos montados para siempre.
 *
 *  (Una versión anterior crecía/recortaba con dos transiciones de estado independientes, una por
 *  extremo; con estimaciones de alto que no coinciden con el alto real de cada tarjeta, competían entre
 *  sí y no convergían. Recalcular la ventana entera en cada evento de scroll, sin estado acumulado que
 *  se pueda desincronizar, es más simple y no tiene esa clase de problema.)
 *
 *  Esta lista puede alimentar dos paneles visibles a la vez (el lateral y el del mapa, en el modo por
 *  defecto), CADA UNO CON SU PROPIO SCROLL: por eso hay una ventana por panel (`items`/`items2`), no una
 *  compartida. Compartir una sola ventana entre dos contenedores que se desplazan por separado deja al
 *  que no se movió mostrando el espaciador del otro, sin tarjetas visibles ahí. */
export function useProgressiveList<T extends { id: string }>(
  list: T[], selectedId: string | null, maxMounted = DEFAULT_MAX_MOUNTED,
) {
  const [scrollA, setScrollA] = useState(0);
  const [scrollB, setScrollB] = useState(0);

  useEffect(() => { setScrollA(0); setScrollB(0); }, [list]);

  const selectedIndex = useMemo(() => (selectedId ? list.findIndex((item) => item.id === selectedId) : -1), [list, selectedId]);

  const heldA = useRef<ScrollTarget | null>(null);
  const heldB = useRef<ScrollTarget | null>(null);
  const watch = useCallback((held: React.MutableRefObject<ScrollTarget | null>, node: HTMLElement | null, onMove: (top: number) => void) => {
    held.current?.__radarScrollCleanup?.();
    held.current = node as ScrollTarget | null;
    if (!node) return;
    const target = node as ScrollTarget;
    const onScroll = () => onMove(target.scrollTop);
    target.addEventListener("scroll", onScroll, { passive: true });
    target.__radarScrollCleanup = () => target.removeEventListener("scroll", onScroll);
  }, []);
  const containerRef = useCallback((node: HTMLElement | null) => watch(heldA, node, setScrollA), [watch]);
  const containerRef2 = useCallback((node: HTMLElement | null) => watch(heldB, node, setScrollB), [watch]);

  const winA = useMemo(() => windowFor(scrollA, list.length, maxMounted, selectedIndex), [scrollA, list.length, maxMounted, selectedIndex]);
  const winB = useMemo(() => windowFor(scrollB, list.length, maxMounted, selectedIndex), [scrollB, list.length, maxMounted, selectedIndex]);
  const items = useMemo(() => list.slice(winA.start, winA.end), [list, winA]);
  const items2 = useMemo(() => list.slice(winB.start, winB.end), [list, winB]);

  return {
    items, items2, containerRef, containerRef2,
    spacerHeight: winA.start * ESTIMATED_ITEM_HEIGHT, spacerHeight2: winB.start * ESTIMATED_ITEM_HEIGHT,
    trimmed: winA.start > 0, trimmed2: winB.start > 0, total: list.length,
  };
}
