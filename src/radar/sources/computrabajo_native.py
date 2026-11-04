"""Public Computrabajo search/detail over bounded HTTP, without Node or portal sessions."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from radar import __version__
from radar.normalize import normalize_text

BASE = "https://pe.computrabajo.com"
DETAIL = "https://oferta.computrabajo.com/offer/"


def _slug(text):
    return re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", normalize_text(text)))[:200]


def fetch(client, url):
    with client.stream("GET", url) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > 5*1024*1024:
                raise ValueError("Computrabajo devolvió una respuesta demasiado grande")
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")


def cards(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("article.box_offer"):
        link = card.select_one("h2 a.js-o-link")
        if not link:
            continue
        href = str(link.get("href") or "").split("#")[0]
        if not href:
            continue
        url = urljoin(BASE, href)
        if urlsplit(url).hostname != "pe.computrabajo.com":
            continue
        company = card.select_one("[offer-grid-article-company-url]") or card.select_one("p.dFlex.vm_fx")
        location = card.select_one("p.fs16.fc_base.mt5:not(.dFlex) span.mr10")
        published = card.select_one("p.fs13.fc_aux")
        salary = card.select_one(".icon.i_salary")
        mode = card.select_one(".icon.i_home_office, .icon.i_home")
        results.append({"offerId": card.get("data-id"), "title": link.get_text(" ", strip=True),
                        "company": company.get_text(" ", strip=True) if company else None,
                        "location": location.get_text(" ", strip=True) if location else None,
                        "publishedDate": published.get_text(" ", strip=True) if published else None,
                        "salary": salary.parent.get_text(" ", strip=True) if salary else None,
                        "modality": mode.parent.get_text(" ", strip=True) if mode else None, "url": url})
    if not results and not re.search(r"no (?:se encontraron|encontramos|hay) (?:ofertas|resultados)|0 ofertas", normalize_text(soup.get_text(" "))):
        raise RuntimeError("Computrabajo no devolvió tarjetas reconocibles; puede haber cambiado el formato o bloqueado la consulta.")
    return results


def detail(payload):
    offer = payload.get("o")
    if not isinstance(offer, dict):
        raise ValueError("Computrabajo devolvió un detalle sin oferta")  # noqa: TRY004 - malformed source payload
    description = BeautifulSoup(str(offer.get("ld") or ""), "html.parser").get_text("\n", strip=True)
    return {"title": offer.get("ltr") or offer.get("t"), "company": offer.get("cn"),
            "description": description, "city": offer.get("c"), "department": offer.get("l"),
            "salary": offer.get("lss"), "contractType": offer.get("lsj"), "workday": offer.get("lset")}


def search(query, location, limit, enrich=True):
    url = BASE + "/trabajo-de-" + _slug(query)
    if location:
        url += "-en-" + _slug(location)
    headers = {"User-Agent": f"Radar/{__version__} (+https://github.com/apontebravopaologabriel-prog/radar)", "Accept": "text/html,application/json"}
    with httpx.Client(timeout=30, headers=headers, follow_redirects=False) as client:
        selected = cards(fetch(client, url))[:max(0, min(limit, 50))]
        if enrich:
            for item in selected:
                offer_id = str(item.get("offerId") or "")
                if not re.fullmatch(r"[a-fA-F0-9]{32}", offer_id):
                    continue
                try:
                    data = detail(json.loads(fetch(client, DETAIL+offer_id+"/d/j?ipo=3&iapo=1")))
                    # Keep publication date, identity, location and public URL from the search card.
                    item.update({k: v for k, v in data.items() if v})
                except (httpx.HTTPError, ValueError):
                    continue
        return selected
