"""Endurecimiento local: validación de Host/Origin, cabeceras de seguridad y permisos de los datos.

Sin `RADAR_ACCESS_TOKEN` la API confía en estar en localhost, y un sitio web malicioso podría intentar llegar a
`127.0.0.1:8100` (DNS rebinding o peticiones entre orígenes). Estas defensas no sustituyen a la clave de acceso:
la complementan.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import stat
from pathlib import Path
from urllib.parse import urlsplit

from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]", "testserver"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # No restringe scripts (Next.js exporta bloques inline); cierra los vectores baratos de inyección y marcos.
    "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'",
}


def allowed_hosts() -> set[str]:
    """Hosts aceptados: localhost, `RADAR_API_HOST` (p. ej. la IP de Tailscale) y `RADAR_ALLOWED_HOSTS`."""
    hosts = set(LOCAL_HOSTS)
    bound = os.getenv("RADAR_API_HOST", "").strip()
    if bound and bound not in {"0.0.0.0", "::"}:
        hosts.add(bound.lower())
    for item in os.getenv("RADAR_ALLOWED_HOSTS", "").split(","):
        if item.strip():
            hosts.add(item.strip().lower())
    return hosts


def _host_only(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):  # IPv6 con corchetes
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class LocalGuardMiddleware:
    """Rechaza `Host` ajenos (DNS rebinding), `Origin` ajeno en peticiones que modifican datos y añade cabeceras."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        hosts = allowed_hosts()
        host = _host_only(headers.get("host", ""))
        if host not in hosts:
            await self._reject("Host no permitido", send, scope, receive)
            return
        origin = headers.get("origin")
        if origin and scope["method"] not in SAFE_METHODS and origin != "null":
            origin_host = _host_only(urlsplit(origin).netloc)
            if origin_host not in hosts:
                await self._reject("Origen no permitido", send, scope, receive)
                return
        elif origin == "null" and scope["method"] not in SAFE_METHODS:
            await self._reject("Origen no permitido", send, scope, receive)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k.lower().encode(), v.encode()) for k, v in SECURITY_HEADERS.items() if k.lower().encode() not in existing]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)

    @staticmethod
    async def _reject(detail: str, send: Send, scope: Scope, receive: Receive) -> None:
        response: Response = JSONResponse({"detail": detail}, status_code=403)
        await response(scope, receive, send)


def restrict_umask() -> None:
    """Los archivos nuevos (base, CV, copias) nacen solo para el usuario. No afecta a Windows."""
    if os.name != "nt":
        os.umask(0o077)


def _chmod(path: Path, mode: int) -> None:
    try:
        if path.exists() and stat.S_IMODE(path.stat().st_mode) != mode:
            path.chmod(mode)
    except OSError:  # sistema de archivos sin permisos POSIX (FAT, red): no es un error
        pass


def harden_data_dir(db_file: Path, *, owned_dir: bool) -> None:
    """Pone `600` a la base y a los archivos personales de su carpeta, y `700` a las carpetas de datos.

    `owned_dir` indica que la carpeta de datos es de Radar (la creó o es la predeterminada); en una carpeta ajena
    solo se tocan los archivos de Radar, no la carpeta."""
    if os.name == "nt":
        return
    folder = db_file.parent
    if owned_dir:
        _chmod(folder, 0o700)
    for name in (db_file.name, f"{db_file.name}-wal", f"{db_file.name}-shm", "secrets.json", "cv_master.json", "photo.jpg", "photo.png"):
        _chmod(folder / name, 0o600)
    for sub in ("backups", "targets", "cvs", "careers"):
        directory = folder / sub
        if directory.is_dir():
            _chmod(directory, 0o700)
            for item in directory.rglob("*"):
                _chmod(item, 0o700 if item.is_dir() else 0o600)
    for item in folder.glob(f"{db_file.name}.*"):  # copias manuales (.bak, .pre-…)
        _chmod(item, 0o600)


class UnsafeUrlError(ValueError):
    """La URL apunta a un destino no público (red local, loopback, metadatos de nube) o no es http/https."""


def ensure_public_http_url(url: str) -> None:
    """Rechaza URLs que no sean http(s) hacia direcciones públicas.

    Las URLs de ofertas vienen de portales externos: una oferta maliciosa podría apuntar a `127.0.0.1` (la propia API de
    Radar), a la red local o a `169.254.169.254` (metadatos de nube). Se resuelve el nombre y se exige que TODAS las
    direcciones sean globales. No cubre un cambio de DNS entre la comprobación y la conexión (rebinding); reduce el riesgo, no lo anula."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnsafeUrlError(f"Solo se permiten URLs http(s): {url[:80]}")
    host = parts.hostname
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(info[4][0]) for info in socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)]
        except OSError as exc:
            raise UnsafeUrlError(f"No se pudo resolver {host}") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeUrlError(f"Destino no público: {host}")
