"""Ayuda curada de Radar (`help.md`): la única fuente de la que el agente explica el producto."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

HELP_FILE = Path(__file__).with_name("help.md")


@cache
def _topics() -> dict[str, str]:
    parts = re.split(r"^## (\S+)\n", HELP_FILE.read_text(encoding="utf-8"), flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def help_topics() -> list[str]:
    return list(_topics())


def read_help(topic: str) -> str:
    topics = _topics()
    if topic not in topics:
        raise ValueError(f"Tema desconocido: {topic}. Disponibles: {', '.join(topics)}")
    return topics[topic]
