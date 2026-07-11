from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

BASE = "https://eservices.mas.gov.sg"
LIST = f"{BASE}/fid/institution"
OUT = Path("fast_output")
OUT.mkdir(exist_ok=True)
EXPECTED = 3640
PAGE_SIZE = 100
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
DETAIL_PATTERN = re.compile(r"/fid/institution/detail/", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?65[\s-]?)?[689]\d{3}[\s-]?\d{4}(?!\d)")
POSTAL_RE = re.compile(r"\b\d{6}\b")

LICENCES = [
    "Approved CIS Trustee", "Approved Clearing House", "Approved Exchange", "Approved Holding Company",
    "Approved Insurance Broker", "Authorised Reinsurer (Composite)", "Authorised Reinsurer (General)",
    "Authorised Reinsurer (Life)", "Capital Markets Services Licensee", "Captive Insurer (Composite)",
    "Captive Insurer (General)", "Captive Insurer (Life)", "Central Depository System",
    "Credit and Charge Card Licensee", "Designated Payment System Operator",
    "Designated Payment System Settlement Institution", "Direct Insurer (Composite)",
    "Direct Insurer (General)", "Direct Insurer (Life)", "Exempt Capital Markets Services Entity",
    "Exempt Financial Adviser", "Exempt Insurance Broker", "Exempt Trust Company", "Finance Company",
    "Financial Holding Company (Banking)", "Financial Holding Company (Insurance)", "Full Bank",
    "Licensed Credit Bureau", "Licensed Financial Adviser", "Licensed Trade Repository", "Licensed Trust Company",
    "Lloyd's Asia Scheme", "Local Bank", "Major Payment Institution", "Merchant Bank",
    "Money-changing Licensee", "Qualifying Full Bank", "Recognised Clearing House", "Recognised Market Operator",
    "Registered Insurance Broker", "Reinsurer (Composite)", "Reinsurer (General)", "Reinsurer (Life)",
    "Representative Office (Banking)", "Representative Office (Insurance)", "SGS Primary Dealer",
    "Standard Payment Institution", "Wholesale Bank",
]
SECTOR_MAP = {
    **{x: "Insurance" for x in LICENCES if any(k in x for k in ("Insur", "Reinsur", "Lloyd"))},
    **{x: "Payments" for x in LICENCES if any(k in x for k in ("Payment", "Money-changing", "Credit and Charge"))},
    **{x: "Financial Advisory" for x in LICENCES if "Financial Adviser" in x},
}
for x in LICENCES:
    SECTOR_MAP.setdefault(x, "Banking" if any(k in x for k in ("Bank", "Finance Company", "SGS Primary Dealer", "Credit Bureau")) else "Capital Markets")


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = clean(item)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def fetch_page(page: int) -> tuple[int, str, str]:
    url = f"{LIST}?page={page}&count={PAGE_SIZE}"
    last: Exception | None = None
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=45, headers={"User-Agent": UA})
            r.raise_for_status()
            return page, url, r.text
        except Exception as exc:
            last = exc
            import time
            time.sleep(1 + attempt)
    raise RuntimeError(f"page {page} failed: {last}")


def card_for(anchor: Tag, ancestor_counts: dict[int, int]) -> Tag:
    best = anchor.parent if isinstance(anchor.parent, Tag) else anchor
    node: Any = anchor.parent
    while isinstance(node, Tag):
        count = ancestor_counts.get(id(node), 0)
        if count == 1:
            best = node
        elif count > 1:
            break
        if node.name in ("body", "html"):
            break
        node = node.parent
    return best


def icon_value(card: Tag, keyword: str) -> str:
    for img in card.find_all("img"):
        attrs = " ".join(str(img.get(k, "")) for k in ("src", "alt", "title", "class")).lower()
        if keyword in attrs:
            node: Any = img.parent
            for _ in range(4):
                if not isinstance(node, Tag):
                    break
                text = clean(node.get_text(" ", strip=True))
                if text and len(text) < 700:
                    return text
                node = node.parent
    return ""


def parse_page(page: int, source_url: str, html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    anchors = [a for a in soup.find_all("a", href=DETAIL_PATTERN) if clean(a.get_text(" ", strip=True))]
    ancestor_counts: dict[int, int] = defaultdict(int)
    for anchor in anchors:
        node: Any = anchor
        while isinstance(node, Tag):
            ancestor_counts[id(node)] += 1
            if node.name in ("body", "html"):
                break
            node = node.parent

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in anchors:
        profile = urljoin(BASE, anchor.get("href", "")).split("#", 1)[0]
        if profile in seen:
            continue
        seen.add(profile)
        name = clean(anchor.get_text(" ", strip=True))
        card = card_for(anchor, ancestor_counts)
        text = clean(card.get_text("\n", strip=True))
        lines = unique(card.get_text("\n", strip=True).splitlines())

        phone_hint = icon_value(card, "phone")
        phones = PHONE_RE.findall(phone_hint) or PHONE_RE.findall(text)
        phone = clean(phones[0]) if phones else ""

        address_hint = icon_value(card, "address")
        if POSTAL_RE.search(address_hint):
            address = address_hint
        else:
            address_lines = [line for line in lines if POSTAL_RE.search(line)]
            address = max(address_lines, key=len) if address_lines else ""

        websites: list[str] = []
        for a in card.find_all("a", href=True):
            href = urljoin(source_url, a.get("href", ""))
            host = urlparse(href).netloc.lower()
            if host and "mas.gov.sg" not in host and not href.startswith(("mailto:", "tel:")):
                websites.append(href)
        website = unique(websites)[0] if websites else ""

        found_licences = [lic for lic in LICENCES if lic in text]
        sectors = unique([SECTOR_MAP[lic] for lic in found_licences])

        rows.append({
            "institution_name": name,
            "sector": "; ".join(sectors),
            "licence_type_status": "; ".join(found_licences),
            "office_number": phone,
            "address": address,
            "website": website,
            "mas_profile_url": profile,
            "source_list_url": source_url,
            "source_page": str(page),
        })
    return rows


def main() -> None:
    pages = math.ceil(EXPECTED / PAGE_SIZE)
    raw_pages: dict[int, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_page, p): p for p in range(1, pages + 1)}
        for future in as_completed(futures):
            page, url, html = future.result()
            raw_pages[page] = (url, html)
            print(f"fetched page {page}: {len(html)} chars", flush=True)

    all_rows: dict[str, dict[str, str]] = {}
    page_counts: dict[str, int] = {}
    for page in range(1, pages + 1):
        url, html = raw_pages[page]
        rows = parse_page(page, url, html)
        page_counts[str(page)] = len(rows)
        for row in rows:
            all_rows[row["mas_profile_url"]] = row
        print(f"parsed page {page}: {len(rows)} rows, cumulative {len(all_rows)}", flush=True)

    data = sorted(all_rows.values(), key=lambda x: x["institution_name"].casefold())
    for i, row in enumerate(data, 1):
        row.update({
            "no": str(i), "verification_date": "2026-07-11", "family_office_classification": "",
            "telemarketing_priority": "", "calling_status": "Not Called", "contact_result": "",
            "follow_up_date": "", "assigned_to": "", "notes": "",
        })

    fields = [
        "no", "institution_name", "sector", "licence_type_status", "office_number", "address", "website",
        "mas_profile_url", "source_list_url", "source_page", "verification_date", "family_office_classification",
        "telemarketing_priority", "calling_status", "contact_result", "follow_up_date", "assigned_to", "notes",
    ]
    with (OUT / "mas_fid_master.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
    (OUT / "mas_fid_master.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    report = {
        "expected_count": EXPECTED,
        "unique_records": len(data),
        "page_counts": page_counts,
        "with_phone": sum(bool(x["office_number"]) for x in data),
        "with_address": sum(bool(x["address"]) for x in data),
        "with_website": sum(bool(x["website"]) for x in data),
        "first_name": data[0]["institution_name"] if data else None,
        "last_name": data[-1]["institution_name"] if data else None,
        "duplicate_profile_urls_removed": sum(page_counts.values()) - len(data),
    }
    (OUT / "extraction_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    if len(data) != EXPECTED:
        raise SystemExit(f"VALIDATION FAILED: expected {EXPECTED}, got {len(data)}")


if __name__ == "__main__":
    main()
