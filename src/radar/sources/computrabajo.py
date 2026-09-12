from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from typing import Any

from radar.domain.models import RawJob


class ComputrabajoSource:
    """Cliente mínimo MCP stdio para el servidor mcp-computrabajo."""

    name = "Computrabajo"

    def __init__(self, command: str | None = None, args: list[str] | None = None):
        self.command = command or os.getenv("RADAR_COMPUTRABAJO_COMMAND", "npx")
        self.args = args or os.getenv(
            "RADAR_COMPUTRABAJO_ARGS", "-y,mcp-computrabajo@latest"
        ).split(",")

    def search(self, query: str, location: str | None = None, limit: int = 25) -> list[RawJob]:
        request_id = 1
        proc = subprocess.Popen(
            [self.command, *self.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        try:
            self._rpc(
                proc,
                request_id,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "radar", "version": "0.1.0"},
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
            return [self._to_job(item) for item in jobs[:limit]]
        finally:
            proc.terminate()

    def _rpc(
        self, proc: subprocess.Popen[str], request_id: int, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
        for line in proc.stdout:
            if not line.strip():
                continue
            data = json.loads(line)
            if "id" not in data:
                continue
            if "error" in data:
                raise RuntimeError(f"Computrabajo MCP error: {data['error']}")
            return data.get("result", {})
        raise RuntimeError("Computrabajo MCP cerró la conexión sin respuesta")

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
        published = item.get("publishedAt") or item.get("publicationDate") or item.get("datePosted")
        if published and not isinstance(published, datetime):
            try:
                published = datetime.fromisoformat(str(published))
            except ValueError:
                published = None
        return RawJob(
            source=self.name,
            title=item.get("title") or "Sin título",
            company=item.get("company") or item.get("companyName"),
            url=item.get("url") or item.get("jobUrl") or "",
            external_id=item.get("offerId") or item.get("id"),
            location=item.get("location"),
            description=item.get("description") or item.get("descriptionText"),
            published_at=published,
            salary_min=item.get("salaryMin"),
            salary_currency=item.get("salaryCurrency"),
            employment_type=item.get("employmentType"),
            raw_payload=item,
        )
