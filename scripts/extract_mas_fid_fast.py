from __future__ import annotations

import csv
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://eservices.mas.gov.sg"
LIST_URL = f"{BASE}/fid/institution"
OUT = Path("fast_output_v2")
OUT.mkdir(exist_ok=True)
PAGE_SIZE = 100
MAS_HEADLINE_RESULTS = 3640
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
PHONE_RE = re.compile(r"(?<!\d)(?:\+?65[\s-]?)?[689]\d{3}[\s-]?\d{4}(?!\d)")
POSTAL_RE = re.compile(r"\b\d{6}\b")


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def sector_for(licence: str) -> str:
    x = licence.lower()
    if any(k in x for k in ("insurance", "insurer", "reinsurer", "lloyd")):
        return "Insurance"
    if any(k in x for k in ("payment", "money-changing", "credit and charge card")):
        return "Payments"
    if "financial adviser" in x:
        return "Financial Advisory"
    if any(k in x for k in ("bank", "finance company", "sgs primary dealer", "credit bureau")):
        return "Banking"
    return "Capital Markets"


def fetch(url: str) -> str:
    last: Exception | None = None
    for attempt in range(6):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=45)
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last = exc
            time.sleep(1.2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last}")


def external_website(card, source_url: str) -> str:
    for a in card.select("div.info a[href]"):
        href = urljoin(source_url, a.get("href", ""))
        host = urlparse(href).netloc.lower()
        if host and "mas.gov.sg" not in host and not href.startswith(("mailto:", "tel:")):
            return href
    return ""


def parse_page(page_no: int, source_url: str, html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("div.result-list.resize > div.inner")
    rows: list[dict[str, object]] = []
    for card in cards:
        profile_a = card.select_one('a[href*="/fid/institution/detail/"]')
        if not profile_a:
            continue
        profile_url = urljoin(BASE, profile_a.get("href", "")).split("#", 1)[0]
        heading = card.select_one("h3")
        name = clean(heading.get_text(" ", strip=True) if heading else profile_a.get_text(" ", strip=True))
        licences = [clean(a.get_text(" ", strip=True)) for a in card.select("div.category a.FilterCategory")]
        licences = list(dict.fromkeys(x for x in licences if x))

        phone = ""
        phone_a = card.select_one('a[href^="tel:"]')
        if phone_a:
            phone = clean(phone_a.get_text(" ", strip=True)) or clean(phone_a.get("href", "").replace("tel:", ""))
        if not phone:
            matches = PHONE_RE.findall(clean(card.get_text(" ", strip=True)))
            phone = clean(matches[0]) if matches else ""

        address = ""
        for tr in card.select("div.info tr"):
            img = tr.select_one("img")
            marker = " ".join(str(img.get(k, "")) for k in ("src", "alt", "title")) if img else ""
            text = clean(tr.get_text(" ", strip=True))
            if "address" in marker.lower() or POSTAL_RE.search(text):
                address = text
                break

        rows.append({
            "institution_name": name,
            "office_number": phone,
            "address": address,
            "website": external_website(card, source_url),
            "mas_profile_url": profile_url,
            "source_list_url": source_url,
            "source_page": page_no,
            "licences": licences,
        })
    return rows


def main() -> None:
    first_url = f"{LIST_URL}?page=1&count={PAGE_SIZE}"
    first_html = fetch(first_url)
    first_soup = BeautifulSoup(first_html, "lxml")
    box = first_soup.select_one("div.box-wrapper")
    if not box:
        raise SystemExit("Could not locate MAS result wrapper")
    total_pages = int(box.get("data-total", "0"))
    headline_results = int(box.get("data-hit", "0"))
    if total_pages <= 0:
        raise SystemExit("MAS page count was not available")

    page_html: dict[int, tuple[str, str]] = {1: (first_url, first_html)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {}
        for page_no in range(2, total_pages + 1):
            url = f"{LIST_URL}?page={page_no}&count={PAGE_SIZE}"
            futures[pool.submit(fetch, url)] = (page_no, url)
        for future in as_completed(futures):
            page_no, url = futures[future]
            page_html[page_no] = (url, future.result())
            print(f"Fetched page {page_no}/{total_pages}", flush=True)

    raw_cards: list[dict[str, object]] = []
    page_card_counts: dict[str, int] = {}
    for page_no in range(1, total_pages + 1):
        url, html = page_html[page_no]
        rows = parse_page(page_no, url, html)
        page_card_counts[str(page_no)] = len(rows)
        raw_cards.extend(rows)
        print(f"Parsed page {page_no}: {len(rows)} cards", flush=True)

    # Merge repeated profiles defensively and retain every exact category printed by MAS.
    merged: dict[str, dict[str, object]] = {}
    for row in raw_cards:
        key = str(row["mas_profile_url"])
        if key not in merged:
            merged[key] = dict(row)
        else:
            current = merged[key]
            old_lic = list(current.get("licences", []))
            new_lic = list(row.get("licences", []))
            current["licences"] = list(dict.fromkeys(old_lic + new_lic))
            for field in ("office_number", "address", "website"):
                if not current.get(field) and row.get(field):
                    current[field] = row[field]

    institutions = sorted(merged.values(), key=lambda r: str(r["institution_name"]).casefold())
    unique_rows: list[dict[str, object]] = []
    licence_rows: list[dict[str, object]] = []
    for idx, row in enumerate(institutions, 1):
        licences = list(row.get("licences", []))
        sectors = list(dict.fromkeys(sector_for(x) for x in licences))
        unique_rows.append({
            "no": idx,
            "institution_name": row["institution_name"],
            "sector": "; ".join(sectors),
            "licence_type_status": "; ".join(licences),
            "office_number": row["office_number"],
            "address": row["address"],
            "website": row["website"],
            "mas_profile_url": row["mas_profile_url"],
            "source_list_url": row["source_list_url"],
            "source_page": row["source_page"],
            "verification_date": "2026-07-11",
            "family_office_classification": "Unreviewed",
            "telemarketing_priority": "",
            "calling_status": "Not Called",
            "contact_result": "",
            "follow_up_date": "",
            "assigned_to": "",
            "notes": "",
        })
        for licence in licences:
            licence_rows.append({
                "licence_record_no": len(licence_rows) + 1,
                "institution_no": idx,
                "institution_name": row["institution_name"],
                "sector": sector_for(licence),
                "licence_type_status": licence,
                "office_number": row["office_number"],
                "address": row["address"],
                "website": row["website"],
                "mas_profile_url": row["mas_profile_url"],
                "source_page": row["source_page"],
                "verification_date": "2026-07-11",
            })

    unique_fields = list(unique_rows[0].keys()) if unique_rows else []
    licence_fields = list(licence_rows[0].keys()) if licence_rows else []
    with (OUT / "mas_fid_unique_institutions.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=unique_fields)
        w.writeheader(); w.writerows(unique_rows)
    with (OUT / "mas_fid_licence_records.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=licence_fields)
        w.writeheader(); w.writerows(licence_rows)
    (OUT / "mas_fid_unique_institutions.json").write_text(json.dumps(unique_rows, ensure_ascii=False), encoding="utf-8")

    report = {
        "mas_headline_results": headline_results,
        "configured_headline_results": MAS_HEADLINE_RESULTS,
        "total_pages": total_pages,
        "page_card_counts": page_card_counts,
        "raw_institution_cards": len(raw_cards),
        "unique_institution_profiles": len(unique_rows),
        "exact_licence_records": len(licence_rows),
        "duplicate_profiles_removed": len(raw_cards) - len(unique_rows),
        "with_phone": sum(bool(r["office_number"]) for r in unique_rows),
        "with_address": sum(bool(r["address"]) for r in unique_rows),
        "with_website": sum(bool(r["website"]) for r in unique_rows),
        "first_name": unique_rows[0]["institution_name"] if unique_rows else None,
        "last_name": unique_rows[-1]["institution_name"] if unique_rows else None,
        "headline_matches_licence_records": headline_results == len(licence_rows),
    }
    (OUT / "reconciliation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)

    if headline_results != MAS_HEADLINE_RESULTS:
        raise SystemExit(f"MAS headline changed: expected {MAS_HEADLINE_RESULTS}, saw {headline_results}")
    if len(unique_rows) < 2500:
        raise SystemExit(f"Too few unique institutions extracted: {len(unique_rows)}")
    if len(licence_rows) != headline_results:
        raise SystemExit(f"Licence-level reconciliation failed: headline={headline_results}, extracted={len(licence_rows)}")


if __name__ == "__main__":
    main()
