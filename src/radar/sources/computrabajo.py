from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from radar import __version__
from radar.domain.models import RawJob

RPC_TIMEOUT_SECONDS = 30.0
PINNED_VERSION = "1.0.0"  # versión fija: `@latest` ejecutaría código remoto sin revisar en cada corrida


class ComputrabajoSource:
    """Cliente mínimo MCP stdio para el servidor mcp-computrabajo."""

    name = "Computrabajo"

    def __init__(self, command: str | None = None, args: list[str] | None = None):
        configured = command or os.getenv("RADAR_COMPUTRABAJO_COMMAND")
        self.native = not configured and os.getenv("RADAR_COMPUTRABAJO_TRANSPORT", "native") != "mcp"
        configured = configured or "npx"
        self.command = shutil.which(configured) or configured
        self.args = args or os.getenv("RADAR_COMPUTRABAJO_ARGS", f"-y,mcp-computrabajo@{PINNED_VERSION}").split(",")

    def search(self, query: str, location: str | None = None, limit: int = 25) -> list[RawJob]:
        if self.native:
            from radar.sources.computrabajo_native import search

            return [self._to_job(item) for item in search(query, location, limit, os.getenv("RADAR_COMPUTRABAJO_DETAILS", "1") != "0")]
        request_id = 1
        enrich_details = os.getenv("RADAR_COMPUTRABAJO_DETAILS", "1") != "0"
        if not Path(self.command).is_file() and not shutil.which(self.command):
            raise RuntimeError("Computrabajo no está disponible: falta el adaptador incluido o Node.js. Las demás fuentes pueden continuar.")
        proc = subprocess.Popen(
            [self.command, *self.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        try:
            self._rpc(
                proc,
                request_id,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "radar", "version": __version__},
                },
            )
            self._notify(proc, "notifications/initialized", {})
            result = self._rpc(
                proc,
                request_id + 2,
                "tools/call",
                {
                    "name": "search-jobs",
                    "arguments": {
                        "keyword": query,
                        "location": location,
                        "country": "pe",
                        "page": 1,
                    },
                },
            )
            jobs = self._extract_jobs(result)
            request_id += 2
            selected = jobs[:limit]
            if enrich_details:
                enriched: list[dict[str, Any]] = []
                for item in selected:
                    offer_id = item.get("offerId") or item.get("id")
                    detail = self._get_detail(proc, request_id + 1, offer_id) if offer_id else None
                    request_id += 1
                    enriched.append(self._merge_detail(item, detail))
                selected = enriched
            return [self._to_job(item) for item in selected]
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if proc.stdin:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()

    def _rpc(
        self,
        proc: subprocess.Popen[str],
        request_id: int,
        method: str,
        params: dict[str, Any],
        timeout: float = RPC_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
        # A single blocking reader works for subprocess pipes on Windows and Unix.
        if not hasattr(proc, "_radar_lines"):
            lines = queue.Queue(maxsize=1024)
            proc._radar_lines = lines

            def read_lines():
                try:
                    while True:
                        line = proc.stdout.readline(1_048_577)
                        if not line:
                            lines.put_nowait(None)
                            return
                        if len(line) > 1_048_576:
                            lines.put_nowait(ValueError("Respuesta MCP demasiado grande"))
                            return
                        lines.put_nowait(line)
                except (OSError, ValueError, queue.Full):
                    return

            threading.Thread(target=read_lines, daemon=True, name="computrabajo-stdio").start()
        deadline = time.monotonic() + timeout
        while True:
            try:
                line = proc._radar_lines.get(timeout=max(0, deadline-time.monotonic()))
            except queue.Empty as exc:
                raise TimeoutError(f"Computrabajo MCP no respondió en {timeout}s para '{method}'") from exc
            if line is None:
                raise RuntimeError("Computrabajo MCP cerró la conexión sin respuesta")
            if isinstance(line, Exception):
                raise line
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("id") != request_id:
                continue
            if "error" in data:
                raise RuntimeError(f"Computrabajo MCP error: {data['error']}")
            return data.get("result", {})

    @staticmethod
    def _notify(proc: subprocess.Popen[str], method: str, params: dict[str, Any]) -> None:
        assert proc.stdin
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n")
        proc.stdin.flush()

    @staticmethod
    def _extract_jobs(result: dict[str, Any]) -> list[dict[str, Any]]:
        structured = result.get("structuredContent") or result.get("structured_content") or {}
        if isinstance(structured.get("jobs"), list):
            return structured["jobs"]
        for item in result.get("content", []):
            if item.get("type") == "text":
                try:
                    payload = json.loads(item.get("text", ""))
                    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
                        return payload["jobs"]
                except json.JSONDecodeError:
                    pass
        return []

    def _to_job(self, item: dict[str, Any]) -> RawJob:
        detail_description = item.get("description") or item.get("descriptionText")
        structured_context = "\n".join(
            value
            for value in (
                f"Empresa: {item.get('companyDescription')}" if item.get("companyDescription") else None,
                f"Modalidad: {item.get('modality')}" if item.get("modality") else None,
                f"Jornada: {item.get('workday')}" if item.get("workday") else None,
                f"Salario: {item.get('salary')}" if item.get("salary") else None,
            )
            if value
        )
        description = "\n".join(value for value in (detail_description, structured_context) if value)
        published = self._parse_published_at(
            item.get("publishedAt")
            or item.get("publicationDate")
            or item.get("datePosted")
            or item.get("publishedDate")
        )
        return RawJob(
            source=self.name,
            title=item.get("title") or "Sin título",
            company=item.get("company") or item.get("companyName"),
            url=item.get("url") or item.get("jobUrl") or "",
            external_id=item.get("offerId") or item.get("id"),
            location=item.get("location") or ", ".join(filter(None, (item.get("city"), item.get("department")))),
            description=description or None,
            published_at=published,
            salary_min=item.get("salaryMin"),
            salary_currency=item.get("salaryCurrency"),
            employment_type=item.get("employmentType") or item.get("contractType"),
            work_mode=item.get("workMode") or item.get("modality"),
            raw_payload=item,
        )

    def _get_detail(
        self, proc: subprocess.Popen[str], request_id: int, offer_id: str | None
    ) -> dict[str, Any] | None:
        """Enriquece una tarjeta; un fallo aislado conserva el resultado resumido."""
        if not offer_id:
            return None
        try:
            result = self._rpc(
                proc,
                request_id,
                "tools/call",
                {
                    "name": "get-job-detail",
                    "arguments": {"offerId": offer_id, "country": "pe"},
                },
            )
            return self._extract_detail(result)
        except (RuntimeError, TimeoutError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _extract_detail(result: dict[str, Any]) -> dict[str, Any] | None:
        structured = result.get("structuredContent") or result.get("structured_content") or {}
        if isinstance(structured.get("job"), dict):
            return structured["job"]
        for item in result.get("content", []):
            if item.get("type") != "text":
                continue
            try:
                payload = json.loads(item.get("text", ""))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("job"), dict):
                return payload["job"]
        return None

    @staticmethod
    def _merge_detail(summary: dict[str, Any], detail: dict[str, Any] | None) -> dict[str, Any]:
        if not detail:
            return summary
        # The detail endpoint may expose an authenticated applyUrl and a
        # different publication date. Keep the public search URL and date.
        merged = {**summary, **detail}
        merged["url"] = summary.get("url") or detail.get("url") or detail.get("applyUrl")
        for key in ("publishedDate", "publicationDate", "datePosted"):
            if summary.get(key):
                merged[key] = summary[key]
                break
        return merged

    @staticmethod
    def _parse_published_at(value: Any) -> datetime | None:
        """Parse Computrabajo ISO dates and relative Spanish labels."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip().lower()
        now = datetime.now(UTC)
        if text in {"hoy", "today"}:
            return now
        if text == "ayer":
            return now - timedelta(days=1)
        relative = re.search(r"hace\s+(\d+)\s+(minuto|hora|día|dia|semana|mes)(?:s)?", text)
        if relative:
            amount = int(relative.group(1))
            unit = relative.group(2)
            if unit == "minuto":
                return now - timedelta(minutes=amount)
            if unit == "hora":
                return now - timedelta(hours=amount)
            if unit in {"día", "dia"}:
                return now - timedelta(days=amount)
            if unit == "semana":
                return now - timedelta(weeks=amount)
            return now - timedelta(days=amount * 30)
        try:
            return datetime.fromisoformat(text.replace("z", "+00:00"))
        except ValueError:
            return None
