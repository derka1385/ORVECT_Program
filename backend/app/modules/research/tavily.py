"""Tavily-backed external technical evidence.

Orvect never searches blindly: `decide_research` gates this module, and every
retrieved item keeps its origin so the explanation layer can only cite evidence
that actually exists. A missing or failing Tavily stays non-fatal — the case
continues on internal knowledge and is explicitly marked as unverified.
"""

import asyncio
import re
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import logger


class TavilyUnavailable(Exception):
    pass


# Evidence hierarchy (section 6). Higher rank wins when evidence is deduplicated
# and ordered; it is also what separates an OEM bulletin from a forum anecdote.
SOURCE_RANK = {
    "oem_manufacturer": 6,
    "safety_authority": 5,
    "technical_documentation": 4,
    "repair_technical_resource": 3,
    "specialist_community": 2,
    "general_web": 1,
}

OEM_DOMAINS = (
    "volkswagen", "audi", "skoda", "seat", "cupra", "bmw", "mercedes-benz", "mercedes",
    "toyota", "honda", "nissan", "mazda", "subaru", "hyundai", "kia", "ford", "opel",
    "vauxhall", "peugeot", "citroen", "renault", "dacia", "fiat", "alfaromeo", "jeep",
    "volvo", "porsche", "landrover", "jaguar", "tesla", "erwin.volkswagen", "vwserviceandparts",
)
SAFETY_AUTHORITY_DOMAINS = (
    "nhtsa.gov", "safercar.gov", "transportstyrelsen.se", "rappel.conso.gouv.fr",
    "ec.europa.eu", "gov.uk", "kba.de", "europa.eu", "car-recalls.eu", "rapex",
)
TECHNICAL_DOC_DOMAINS = (
    "sae.org", "iso.org", "bosch", "delphiautoparts", "denso", "ngk", "valeo",
    "continental-automotive", "hella", "mahle", "febi", "tecalliance", "haynes",
    "autodata-group", "identifix", "alldata", "mitchell1", "obd-codes.com",
)
REPAIR_RESOURCE_DOMAINS = (
    "rockauto", "fcpeuro", "europaparts", "autozone", "oreillyauto", "advanceautoparts",
    "carparts", "oscaro", "mister-auto", "autodoc", "partsgeek", "1aauto", "repairpal",
    "yourmechanic", "cardiagn", "workshop-manuals", "dtc-codes",
)
COMMUNITY_DOMAINS = (
    "forum", "forums", "reddit.com", "golfmk7.com", "vwvortex", "audizine", "bimmerfest",
    "bimmerforums", "e90post", "clubgolfgti", "tdiclub", "mechanics.stackexchange.com",
    "youtube.com", "briskoda", "seatcupra.net", "pistonheads", "autoscout", "planete-clio",
)


# The named lists above cannot cover the long tail the open web actually
# returns, so these patterns catch the rest. Checked only after the exact
# lists, and ordered so an automotive-safety domain is not mistaken for a
# parts shop just because it contains "auto".
SAFETY_PATTERN = re.compile(r"(?:\.gov(?:\.[a-z]{2})?$|\.gov\.|autosafety|safercar|recall|vehiclesafety|\.europa\.eu$)")
COMMUNITY_PATTERN = re.compile(r"(?:forum|community|answers?|justanswer|stackexchange|reddit|\.club$|owners?club)")
TECHNICAL_PATTERN = re.compile(r"(?:workshop-?manual|service-?manual|techinfo|technical|wiring|haynes|autodata)")
AUTOMOTIVE_PATTERN = re.compile(r"(?:auto|car(?:s|parts)?|motor|mechanic|vehicle|garage|parts|obd|dtc|diag|repair|engine|tuning|scanner)")


def classify_domain(domain: str) -> str:
    """Map a hostname onto the Orvect evidence hierarchy.

    Exact known domains win; everything else falls back to pattern signals so
    the long tail of real search results is still ranked rather than dumped
    into `general_web`.
    """
    host = (domain or "").casefold()
    if any(token in host for token in SAFETY_AUTHORITY_DOMAINS):
        return "safety_authority"
    if any(token in host for token in OEM_DOMAINS):
        return "oem_manufacturer"
    if any(token in host for token in TECHNICAL_DOC_DOMAINS):
        return "technical_documentation"
    if any(token in host for token in COMMUNITY_DOMAINS):
        return "specialist_community"
    if any(token in host for token in REPAIR_RESOURCE_DOMAINS):
        return "repair_technical_resource"
    # Pattern fallbacks, most authoritative signal first.
    if SAFETY_PATTERN.search(host):
        return "safety_authority"
    if COMMUNITY_PATTERN.search(host):
        return "specialist_community"
    if TECHNICAL_PATTERN.search(host):
        return "technical_documentation"
    if AUTOMOTIVE_PATTERN.search(host):
        return "repair_technical_resource"
    return "general_web"


def _domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").removeprefix("www.")
    except ValueError:
        return ""


def _clean(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


async def _one_search(client: httpx.AsyncClient, query: str) -> list[dict]:
    response = await client.post(
        "/search",
        json={
            "query": query,
            "search_depth": "advanced",
            "max_results": settings.tavily_results_per_query,
            "topic": "general",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        },
        headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
    )
    response.raise_for_status()
    body = response.json()
    items = []
    for raw in body.get("results", []):
        url = raw.get("url") or ""
        # A citation without a real URL is worthless and must never be invented.
        if not url.startswith(("http://", "https://")):
            continue
        domain = _domain(url)
        source_type = classify_domain(domain)
        items.append(
            {
                "title": _clean(raw.get("title"), 200) or domain,
                "url": url,
                "domain": domain,
                "snippet": _clean(raw.get("content"), 900),
                "source_type": source_type,
                "source_rank": SOURCE_RANK[source_type],
                "relevance": float(raw.get("score") or 0),
                "query": query,
            }
        )
    return items


async def search(queries: list[str]) -> tuple[list[dict], list[str]]:
    """Run capped, parallel searches. Returns (evidence, failed_queries).

    A single failing query never fails the diagnosis; only a total failure
    raises, so the caller can mark external verification unavailable.
    """
    if not settings.tavily_api_key:
        raise TavilyUnavailable("Tavily is not configured")
    capped = [q for q in dict.fromkeys(queries) if q.strip()][: settings.tavily_max_queries]
    if not capped:
        return [], []
    async with httpx.AsyncClient(
        base_url=settings.tavily_base_url, timeout=settings.tavily_timeout_seconds
    ) as client:
        outcomes = await asyncio.gather(
            *(_one_search(client, query) for query in capped), return_exceptions=True
        )
    evidence: list[dict] = []
    failed: list[str] = []
    for query, outcome in zip(capped, outcomes):
        if isinstance(outcome, Exception):
            # The query text is safe to log; the API key never is.
            logger.warning("tavily_query_failed", query=query, error_type=type(outcome).__name__)
            failed.append(query)
            continue
        evidence.extend(outcome)
    if failed and not evidence:
        raise TavilyUnavailable("Every external research query failed")
    return _dedupe(evidence), failed


def _dedupe(items: list[dict]) -> list[dict]:
    """One entry per URL, best source rank first, then Tavily relevance."""
    best: dict[str, dict] = {}
    for item in items:
        current = best.get(item["url"])
        if not current or item["relevance"] > current["relevance"]:
            best[item["url"]] = item
    return sorted(best.values(), key=lambda item: (item["source_rank"], item["relevance"]), reverse=True)
