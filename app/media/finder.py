"""Find, check and store real photos for lessons — free and openly licensed only.

Sources (no keys needed), in this order:
  1. Wikidata 'image' (P18) for named things (a person, monument, place) — the canonical photo;
  2. Wikimedia Commons search (photographs, bitmap files only);
  3. Openverse (800 M+ openly licensed images) only when 1–2 found too little — anonymous use is limited to a few
     searches per hour, so it is a fallback.
Rules:
  - only these hosts are contacted (egress allow-list); a descriptive User-Agent as Wikimedia requires; one request at
    a time; a 429 'Retry-After' is respected;
  - only CC0 / public domain / CC BY / CC BY-SA images (no NC/ND), always stored with title, author, licence and link;
  - only raster thumbnails (≤ 1 MB, JPEG/PNG/WebP) are downloaded — never SVG or HTML;
  - every photo is looked at by the LOCAL vision model (Ollama, free) and kept only if it really shows the thing.
"""

import base64
import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from loguru import logger
from sqlmodel import Session, select

from app.db.models import MediaAsset
from app.llm.router import AllModelsFailed, LLMRouter

# thumb.wikimedia.org: Commons thumbnails are served from there (measured 09-Oct-2026)
ALLOWED_HOSTS = {
    "commons.wikimedia.org", "upload.wikimedia.org", "thumb.wikimedia.org", "www.wikidata.org", "api.openverse.org",
}  # fmt: skip
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
CHECK_TASK = "image_check"
CAPTION_MATCH = 0.72  # caption ↔ query similarity that alone proves a match (calibrated, see check())
CAPTION_MIN = 0.60  # minimum similarity when the vision model itself also says yes
MAX_BYTES = 1_500_000
# httpx's timeout is per read, so a server sending a few bytes at a time can hold one download for many minutes
# (measured: 19 minutes for one Commons thumbnail). Hard limits for the whole download and the whole search:
DOWNLOAD_SECONDS = 30.0
FIND_SECONDS = 150.0
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
_OK_LICENSE = re.compile(
    r"^\s*(cc0|cc[ -]?zero|public domain|pd\b|pdm|cc[ -]by(?:[ -]sa)?(?:[ -]\d(?:\.\d)?)?\s*$)", re.I
)

_NOT_PHOTO = re.compile(
    r"\b(logo|icon|emblem|coat of arms|seal|flag|map|chart|graph|diagram|screenshot|svg|clipart|symbol|banner)s?\b",
    re.I,
)

CHECK_PROMPT = """You check photographs for a school lesson. Look at the picture and answer as JSON only:
{"fits": true or false, "caption": "one short sentence saying what is really visible", "reason": "few words"}
fits = true if what is asked is clearly visible in the picture (other things may be visible too), the picture is a real
photograph or a clear drawing, and it is suitable for children (no violence, no text-heavy document, no logo).
fits = false if what is asked is not in the picture."""


class MediaError(RuntimeError):
    pass


@dataclass
class Candidate:
    source: str
    page_url: str
    file_url: str  # raster thumbnail URL
    title: str
    author: str
    license: str
    license_url: str


def licence_ok(name: str) -> bool:
    """CC0, public domain, CC BY, CC BY-SA (any version) — not NC (non-commercial) or ND (no changes)."""
    return (
        bool(name)
        and bool(_OK_LICENSE.match(name.replace("_", " ")))
        and not re.search(r"\b(nc|nd)\b", name, re.I)
    )


def _clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()[:200]


class MediaFinder:
    def __init__(self, router: LLMRouter, engine, settings, client: httpx.Client | None = None):
        self.router, self.engine, self.settings = router, engine, settings
        self.folder = Path(settings.data_dir) / "media"
        self.client = client or httpx.Client(
            headers={"User-Agent": settings.media_user_agent}, timeout=20.0, follow_redirects=False
        )

    # ------------------------------------------------------------ HTTP (allow-listed hosts only)
    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        if urlparse(url).hostname not in ALLOWED_HOSTS:
            raise MediaError(f"host not allowed: {urlparse(url).hostname}")
        for attempt in range(2):
            response = self.client.get(url, params=params)
            if response.status_code == 429 and attempt == 0:
                time.sleep(min(10.0, float(response.headers.get("Retry-After", "5") or 5)))
                continue
            if response.status_code in {301, 302, 303, 307, 308}:  # follow only to allowed hosts
                target = response.headers.get("Location", "")
                if urlparse(target).hostname not in ALLOWED_HOSTS:
                    raise MediaError(f"redirect to a host that is not allowed: {target[:80]}")
                url, params = target, None
                continue
            response.raise_for_status()
            return response
        raise MediaError("rate limited (429) — try again later")

    # ------------------------------------------------------------ sources
    def _commons_files(self, params: dict) -> list[Candidate]:
        base = {
            "action": "query", "format": "json", "prop": "imageinfo", "iiprop": "url|mime|extmetadata",
            "iiurlwidth": 800,
            "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ObjectName|ImageDescription",
        }  # fmt: skip
        data = self._get(COMMONS_API, {**base, **params}).json()
        pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        found = []
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            value = lambda key: (meta.get(key) or {}).get("value", "")  # noqa: E731
            licence = _clean(value("LicenseShortName"))
            thumb = info.get("thumburl") or ""
            if (
                info.get("mime") not in {"image/jpeg", "image/png", "image/webp"}
                or not thumb
                or not licence_ok(licence)
            ):
                continue
            found.append(
                Candidate("commons", info.get("descriptionurl", ""), thumb,
                          _clean(value("ObjectName")) or page.get("title", "").removeprefix("File:"),
                          _clean(value("Artist")) or "unknown", licence, _clean(value("LicenseUrl")))
            )  # fmt: skip
        return found

    def search_commons(self, query: str, limit: int = 8) -> list[Candidate]:
        return self._commons_files(
            {
                "generator": "search",
                "gsrsearch": f"{query} filetype:bitmap",
                "gsrnamespace": 6,
                "gsrlimit": limit,
            }
        )

    def wikidata_image(self, name: str) -> list[Candidate]:
        """The main image (P18) of the Wikidata item best matching a name (person, monument, place …)."""
        hits = (
            self._get(
                WIKIDATA_API,
                {
                    "action": "wbsearchentities",
                    "search": name,
                    "language": "en",
                    "format": "json",
                    "limit": 1,
                },
            )
            .json()
            .get("search", [])
        )
        if not hits:
            return []
        entity = self._get(
            WIKIDATA_API,
            {"action": "wbgetclaims", "entity": hits[0]["id"], "property": "P18", "format": "json"},
        ).json()
        claims = (entity.get("claims") or {}).get("P18") or []
        if not claims:
            return []
        filename = claims[0]["mainsnak"]["datavalue"]["value"]
        found = self._commons_files({"titles": f"File:{filename}"})
        for c in found:
            c.source = "wikidata"
        return found

    def search_openverse(self, query: str, limit: int = 6) -> list[Candidate]:
        data = self._get(
            OPENVERSE_API, {"q": query, "page_size": limit, "license": "cc0,pdm,by,by-sa", "mature": "false"}
        ).json()
        found = []
        for item in data.get("results", []):
            licence = f"{item.get('license', '')} {item.get('license_version', '')}".strip()
            name = "Public domain" if item.get("license") in {"cc0", "pdm"} else f"CC {licence.upper()}"
            if not item.get("id") or not licence_ok(name):
                continue
            found.append(
                Candidate("openverse", item.get("foreign_landing_url", ""), f"{OPENVERSE_API}{item['id']}/thumb/",
                          _clean(item.get("title", "")), _clean(item.get("creator", "")) or "unknown", name,
                          item.get("license_url", ""))
            )  # fmt: skip
        return found

    # ------------------------------------------------------------ download + check
    def _download(self, candidate: Candidate) -> tuple[bytes, str]:
        """Stream the thumbnail with a hard total time limit and size cap (allowed hosts and redirects only)."""
        url, started = candidate.file_url, time.monotonic()
        for _hop in range(3):
            if urlparse(url).hostname not in ALLOWED_HOSTS:
                raise MediaError(f"host not allowed: {urlparse(url).hostname}")
            with self.client.stream("GET", url) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = response.headers.get("Location", "")
                    continue
                response.raise_for_status()
                kind = response.headers.get("Content-Type", "").split(";")[0].strip()
                if kind not in IMAGE_TYPES:
                    raise MediaError(f"not a photo ({kind})")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        raise MediaError("file too large")
                    if time.monotonic() - started > DOWNLOAD_SECONDS:
                        raise MediaError(f"download slower than {DOWNLOAD_SECONDS:.0f} s — skipped")
                return bytes(data), IMAGE_TYPES[kind]
        raise MediaError("too many redirects")

    def check(self, image: bytes, kind: str, query: str, concept: str) -> tuple[bool, str, str]:
        """Local vision model: does the picture really show `query`? → (fits, caption, note)."""
        mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[kind]
        url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
        messages = [
            {"role": "system", "content": CHECK_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": f"Lesson concept: {concept}\nThe picture should show: {query}"},
                {"type": "image_url", "image_url": {"url": url}},
            ]},
        ]  # fmt: skip
        try:
            result = self.router.complete(CHECK_TASK, messages)
            verdict = json.loads(re.search(r"\{.*\}", result.text, re.S).group(0))
        except (AllModelsFailed, AttributeError, json.JSONDecodeError) as exc:
            return False, "", f"check failed: {exc}"[:200]
        caption = str(verdict.get("caption", ""))[:200]
        said_yes = bool(verdict.get("fits"))
        # The small local model's yes/no is unreliable (measured: it described "a railway level crossing gate" and
        # still said no), but its caption is good. So the caption is compared with the query by meaning (local
        # embeddings; calibrated on 12 pairs: matches ≥ 0.73, mismatches ≤ 0.69).
        similarity = self._similarity(query, caption) if caption else 0.0
        fits = similarity >= CAPTION_MATCH or (said_yes and similarity >= CAPTION_MIN)
        return fits, caption, f"model said {'yes' if said_yes else 'no'}; caption match {similarity:.2f}"

    def _similarity(self, a: str, b: str) -> float:
        import numpy as np

        try:
            vectors = np.array(self.router.embed("embed", [a, b]).vectors, dtype=np.float32)
        except AllModelsFailed:
            return 0.0
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        return float(vectors[0] @ vectors[1])

    # ------------------------------------------------------------ the whole step
    def find(
        self, query: str, *, concept: str = "", lesson_id: int | None = None, keep: int = 2,
        max_checks: int = 5, named: bool = False,
    ) -> list[MediaAsset]:  # fmt: skip
        """Photos that fit `query` (cached by query). `named` = a specific thing → Wikidata first."""
        query = " ".join(query.split())[:120]
        with Session(self.engine) as s:
            cached = s.exec(
                select(MediaAsset).where(MediaAsset.query == query, MediaAsset.fits == True)
            ).all()  # noqa: E712
            tried = {a.page_url for a in s.exec(select(MediaAsset).where(MediaAsset.query == query)).all()}
        # also for photos stored before the title rule existed (a stored publisher's logo was being reused)
        cached = [a for a in cached if not (m := _NOT_PHOTO.search(a.title)) or m.group(0).lower() in query.lower()]
        if len(cached) >= keep:
            return cached[:keep]
        kept = list(cached)
        checks = 0
        self._deadline = time.monotonic() + FIND_SECONDS
        seen = set(tried)
        words = query.split()
        # The full phrase first; if nothing fits, shorter phrases (measured: 'runners on a circular running track'
        # found Saturn's rings and trams — all rightly rejected — while 'running track' finds the right photos).
        phrases = [query] + [" ".join(words[-n:]) for n in (3, 2) if len(words) > n]
        for number, phrase in enumerate(dict.fromkeys(phrases)):
            if len(kept) >= keep or checks >= max_checks or self._late():
                break
            candidates = self._candidates(phrase, named and number == 0, keep)
            # judged against the phrase that found them ('running track'), stored under the full query
            checks = self._check_candidates(
                candidates, query, phrase, concept, lesson_id, keep, max_checks, kept, seen, checks
            )
        return kept[:keep]

    def _late(self) -> bool:
        late = time.monotonic() > getattr(self, "_deadline", float("inf"))
        if late:
            logger.info(f"Photo search stopped after {FIND_SECONDS:.0f} s (slow network) — kept what was found")
        return late

    def _candidates(self, phrase: str, named: bool, keep: int) -> list[Candidate]:
        candidates: list[Candidate] = []
        for source in ([self.wikidata_image] if named else []) + [self.search_commons]:
            try:
                candidates += source(phrase)
            except (httpx.HTTPError, MediaError, KeyError, ValueError) as exc:
                logger.warning(f"Media search '{phrase}' ({source.__name__}) failed: {exc}")
        if len(candidates) < keep:
            try:
                candidates += self.search_openverse(phrase)
            except (httpx.HTTPError, MediaError, ValueError) as exc:
                logger.info(f"Openverse skipped for '{phrase}': {exc}")
        return candidates

    def _check_candidates(  # noqa: PLR0913
        self, candidates, query, phrase, concept, lesson_id, keep, max_checks, kept, seen, checks
    ) -> int:
        for candidate in candidates:
            if len(kept) >= keep or checks >= max_checks or self._late():
                break
            family = re.sub(r"[\W\d_]+", "", candidate.title.lower())[
                :40
            ]  # 'Roof Project (3)' = 'Roof Project (4)'
            if candidate.page_url in seen or (family and family in seen):
                continue
            not_photo = _NOT_PHOTO.search(candidate.title)
            if not_photo and not_photo.group(0).lower() not in phrase.lower():
                continue  # measured: 'open book' found a publisher's logo, and the small vision model accepted it
            seen.update({candidate.page_url, family})
            try:
                data, kind = self._download(candidate)
            except (httpx.HTTPError, MediaError) as exc:
                logger.info(f"Skipped {candidate.page_url}: {exc}")
                continue
            checks += 1
            fits, caption, note = self.check(data, kind, phrase, concept)
            digest = hashlib.sha256(data).hexdigest()
            relative = ""
            if fits:
                self.folder.mkdir(parents=True, exist_ok=True)
                relative = f"media/{digest}.{kind}"
                (Path(self.settings.data_dir) / relative).write_bytes(data)
            asset = MediaAsset(
                query=query, lesson_id=lesson_id, concept=concept, source=candidate.source,
                page_url=candidate.page_url, title=candidate.title, author=candidate.author,
                license=candidate.license, license_url=candidate.license_url, sha256=digest,
                local_path=relative, caption=caption, fits=fits, check_note=note,
            )  # fmt: skip
            with Session(self.engine) as s:
                s.add(asset)
                s.commit()
                s.refresh(asset)
            if fits:
                kept.append(asset)
        return checks

    def path_of(self, asset: MediaAsset) -> Path:
        return Path(self.settings.data_dir) / asset.local_path
