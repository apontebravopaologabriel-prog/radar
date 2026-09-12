from __future__ import annotations

import hashlib
import re
import unicodedata

from radar.domain.models import RawJob


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().strip()
    return re.sub(r"\s+", " ", value)


def clean_description(value: str | None) -> str:
    text = value or ""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fingerprint(job: RawJob) -> str:
    company = normalize_text(job.company)
    title = normalize_text(job.title)
    location = normalize_text(job.location)
    payload = f"{company}|{title}|{location}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_hash(job: RawJob) -> str:
    payload = "|".join((normalize_text(job.title), clean_description(job.description)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
