"use client";

import { useLayoutEffect, useMemo, useState } from "react";

// Matches the 80px cards and their 4px bottom margin in radar-map.css.
const ROW_HEIGHT = 84;
const OVERSCAN = 4;

function usePanel<T extends { id: string }>(list: T[], selectedId: string | null) {
  const [node, setNode] = useState<HTMLDivElement | null>(null);
  const [viewport, setViewport] = useState({ top: 0, height: 460 });
  const selectedIndex = useMemo(() => list.findIndex((item) => item.id === selectedId), [list, selectedId]);

  useLayoutEffect(() => {
    if (!node) return;
    const measure = () => setViewport((current) => {
      const top = node.scrollTop;
      const height = node.clientHeight;
      return current.top === top && current.height === height ? current : { top, height };
    });
    measure();
    node.addEventListener("scroll", measure, { passive: true });
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => { observer.disconnect(); node.removeEventListener("scroll", measure); };
  }, [node]);

  useLayoutEffect(() => {
    if (!node) return;
    if (selectedIndex < 0) {
      node.scrollTop = 0;
    } else {
      const top = selectedIndex * ROW_HEIGHT;
      if (top < node.scrollTop) node.scrollTop = top;
      else if (top + ROW_HEIGHT > node.scrollTop + node.clientHeight) {
        node.scrollTop = top + ROW_HEIGHT - node.clientHeight;
      }
    }
    setViewport({ top: node.scrollTop, height: node.clientHeight });
  }, [node, list, selectedIndex]);

  const start = Math.min(Math.max(0, Math.floor(viewport.top / ROW_HEIGHT) - OVERSCAN), Math.max(0, list.length - 1));
  const end = Math.min(list.length, start + Math.ceil(viewport.height / ROW_HEIGHT) + 2 * OVERSCAN);
  return {
    items: useMemo(() => list.slice(start, end), [list, start, end]),
    containerRef: setNode,
    spacerHeight: start * ROW_HEIGHT,
    bottomSpacerHeight: (list.length - end) * ROW_HEIGHT,
    trimmed: start > 0,
  };
}

/** Independent windows keep the reading list and map tray scroll positions separate. */
export function useProgressiveList<T extends { id: string }>(list: T[], selectedId: string | null) {
  const reading = usePanel(list, selectedId);
  const map = usePanel(list, selectedId);
  return {
    ...reading,
    items2: map.items,
    containerRef2: map.containerRef,
    spacerHeight2: map.spacerHeight,
    bottomSpacerHeight2: map.bottomSpacerHeight,
    trimmed2: map.trimmed,
    total: list.length,
  };
}
