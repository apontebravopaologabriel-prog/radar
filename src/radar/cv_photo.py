"""Foto del perfil: valida, limpia y guarda la imagen que sube la persona desde Ajustes.

Se decodifica con Pillow (nunca se confía en la extensión ni en el content-type declarado), se recorta al
lado mayor y se vuelve a codificar sin metadatos EXIF (pueden llevar ubicación GPS: es una foto personal).
El archivo final siempre es ``photo.jpg`` bajo el directorio de datos; cualquier otro nombre de foto vieja
(``photo.png``) se borra para que no quede un archivo huérfano. Ver ``docs/cv.md``.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

from radar.cv_targets import _PHOTO_NAMES, data_dir

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_SIDE = 640
JPEG_QUALITY = 85
FILENAME = "photo.jpg"


def save_photo(data: bytes) -> dict[str, int]:
    """Guarda la foto tras validarla y limpiarla. Devuelve el tamaño final (ancho, alto)."""
    if not data:
        raise ValueError("El archivo está vacío")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"La imagen pesa más de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()  # detecta corrupción sin decodificar los píxeles todavía
        image = Image.open(io.BytesIO(data))  # verify() deja el objeto inutilizable: se reabre
        if image.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError(f"Formato no soportado: {image.format or 'desconocido'}. Usa JPG, PNG o WEBP.")
        image.load()
    except UnidentifiedImageError as exc:
        raise ValueError("El archivo no es una imagen válida") from exc
    except OSError as exc:
        raise ValueError("La imagen está dañada o incompleta") from exc

    image = image.convert("RGB")  # descarta canal alfa y, con él, cualquier metadato asociado
    if max(image.size) > MAX_SIDE:
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)

    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / FILENAME
    tmp = target.with_name(f"{FILENAME}.tmp")
    image.save(tmp, format="JPEG", quality=JPEG_QUALITY, optimize=True)  # sin exif= => se descarta
    tmp.replace(target)
    for name in _PHOTO_NAMES:
        if name != FILENAME:
            (directory / name).unlink(missing_ok=True)
    return {"width": image.width, "height": image.height}


def remove_photo() -> bool:
    """Borra la foto guardada, si hay una. Devuelve si había algo que borrar."""
    removed = False
    for name in _PHOTO_NAMES:
        path = data_dir() / name
        if path.is_file():
            path.unlink()
            removed = True
    return removed
