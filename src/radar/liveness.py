"""Verifica si las ofertas activas siguen publicadas visitando su URL pública."""

from __future__ import annotations

import httpx

from radar.db.database import connection
from radar.security import UnsafeUrlError, ensure_public_http_url

# 404/410 son señales inequívocas de que la oferta ya no existe. 403/429 casi
# siempre son bloqueo anti-bot del portal, no que la oferta haya cerrado, así
# que se tratan como "unknown" en vez de marcar la oferta como cerrada.
CLOSED_STATUS_CODES = {404, 410}

CLOSED_TEXT_SIGNALS = (
    "ya no se encuentra disponible",
    "ya no está disponible",
    "esta oferta ha finalizado",
    "oferta cerrada",
    "posición cerrada",
    "job no longer available",
    "no longer accepting applications",
    "this job is no longer available",
)


def check_application_status(
    limit: int = 50, recheck_after_days: int = 3, timeout: float = 10.0
) -> dict[str, int]:
    """Visita un lote de ofertas activas y actualiza application_status."""
    stats = {"checked": 0, "closed": 0, "open": 0, "unknown": 0, "errors": 0}
    with connection() as conn:
        rows = conn.execute(
            """SELECT j.id,
            (SELECT source_url FROM job_sources js WHERE js.job_id=j.id ORDER BY js.last_seen_at DESC LIMIT 1)
            FROM jobs j
            WHERE j.is_active = 1
            AND (j.application_checked_at IS NULL
                 OR date(j.application_checked_at) < date('now', '-' || %s || ' days'))
            ORDER BY j.application_checked_at IS NOT NULL, j.published_at DESC
            LIMIT %s""",
            (recheck_after_days, limit),
        ).fetchall()

    results: list[tuple[str, str]] = []
    def guard(request: httpx.Request) -> None:  # también se ejecuta en cada redirección
        ensure_public_http_url(str(request.url))

    with httpx.Client(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}, event_hooks={"request": [guard]}
    ) as client:
        for job_id, url in rows:
            if not url:
                continue
            stats["checked"] += 1
            try:
                response = client.get(url)
            except (httpx.HTTPError, UnsafeUrlError):
                stats["errors"] += 1
                continue
            if response.status_code in CLOSED_STATUS_CODES:
                status = "closed"
            elif response.status_code >= 400:
                status = "unknown"
            else:
                body = response.text.lower()
                status = "closed" if any(signal in body for signal in CLOSED_TEXT_SIGNALS) else "open"
            stats[status] += 1
            results.append((job_id, status))

    if results:
        with connection() as conn:
            conn.executemany(
                """UPDATE jobs SET application_status=%s, application_checked_at=now(),
                application_status_source='source_page' WHERE id=%s""",
                [(status, job_id) for job_id, status in results],
            )
            conn.commit()
    return stats
