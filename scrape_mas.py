import csv
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://eservices.mas.gov.sg"
LIST_URL = BASE + "/fid/institution"
PRINT_URL = BASE + "/fid/institution/print?count=0"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
EXPECTED = 3640

LICENCE_TO_SECTOR = {
    "Approved CIS Trustee": "Capital Markets",
    "Approved Clearing House": "Capital Markets",
    "Approved Exchange": "Capital Markets",
    "Approved Holding Company": "Capital Markets",
    "Capital Markets Services Licensee": "Capital Markets",
    "Central Depository System": "Capital Markets",
    "Exempt Capital Markets Services Entity": "Capital Markets",
    "Licensed Trade Repository": "Capital Markets",
    "Recognised Clearing House": "Capital Markets",
    "Recognised Market Operator": "Capital Markets",
    "SGS Primary Dealer": "Capital Markets",
    "Exempt Financial Adviser": "Financial Advisory",
    "Licensed Financial Adviser": "Financial Advisory",
    "Approved Insurance Broker": "Insurance",
    "Authorised Reinsurer (Composite)": "Insurance",
    "Authorised Reinsurer (General)": "Insurance",
    "Authorised Reinsurer (Life)": "Insurance",
    "Captive Insurer (Composite)": "Insurance",
    "Captive Insurer (General)": "Insurance",
    "Captive Insurer (Life)": "Insurance",
    "Direct Insurer (Composite)": "Insurance",
    "Direct Insurer (General)": "Insurance",
    "Direct Insurer (Life)": "Insurance",
    "Exempt Insurance Broker": "Insurance",
    "Financial Holding Company (Insurance)": "Insurance",
    "Lloyd's Asia Scheme": "Insurance",
    "Registered Insurance Broker": "Insurance",
    "Reinsurer (Composite)": "Insurance",
    "Reinsurer (General)": "Insurance",
    "Reinsurer (Life)": "Insurance",
    "Representative Office (Insurance)": "Insurance",
    "Credit and Charge Card Licensee": "Payments",
    "Designated Payment System Operator": "Payments",
    "Designated Payment System Settlement Institution": "Payments",
    "Major Payment Institution": "Payments",
    "Money-changing Licensee": "Payments",
    "Standard Payment Institution": "Payments",
    "Finance Company": "Banking",
    "Financial Holding Company (Banking)": "Banking",
    "Full Bank": "Banking",
    "Licensed Credit Bureau": "Banking",
    "Local Bank": "Banking",
    "Merchant Bank": "Banking",
    "Qualifying Full Bank": "Banking",
    "Representative Office (Banking)": "Banking",
    "Wholesale Bank": "Banking",
    "Licensed Trust Company": "Capital Markets",
    "Exempt Trust Company": "Capital Markets",
}
ALL_LICENCES = sorted(LICENCE_TO_SECTOR, key=len, reverse=True)


def get(url, params=None, attempts=5):
    last = None
    for i in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=45, headers=HEADERS)
            if r.status_code == 200 and len(r.text) > 500:
                return r
            last = RuntimeError(f"HTTP {r.status_code}: {r.url}")
        except Exception as e:
            last = e
        time.sleep(1.2 * (i + 1))
    raise last


def closest_card(anchor):
    node = anchor
    best = anchor.parent
    for _ in range(10):
        parent = node.parent
        if parent is None:
            break
        links = parent.find_all("a", href=re.compile(r"/fid/institution/detail/"))
        if len(links) == 1:
            best = parent
            node = parent
            continue
        if len(links) > 1:
            break
        node = parent
    return best


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def parse_html(html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    seen = set()
    anchors = soup.find_all("a", href=re.compile(r"/fid/institution/detail/"))
    for a in anchors:
        href = urljoin(BASE, a.get("href", ""))
        if not href or href in seen:
            continue
        seen.add(href)
        name = clean(a.get_text(" ", strip=True))
        if not name:
            continue
        card = closest_card(a)
        text = clean(card.get_text(" | ", strip=True))

        licences = []
        for lic in ALL_LICENCES:
            if re.search(r"(?<!\w)" + re.escape(lic) + r"(?!\w)", text, re.I):
                licences.append(lic)
        # Preserve order while removing duplicates.
        licences = list(dict.fromkeys(licences))

        sectors = []
        for lic in licences:
            sec = LICENCE_TO_SECTOR.get(lic)
            if sec and sec not in sectors:
                sectors.append(sec)

        website = ""
        for link in card.find_all("a", href=True):
            h = link["href"].strip()
            if h.startswith("http") and "eservices.mas.gov.sg" not in h and "mas.gov.sg" not in h:
                website = h
                break

        phone = ""
        tel = card.find("a", href=re.compile(r"^tel:", re.I))
        if tel:
            phone = clean(tel.get("href", "").split(":", 1)[-1])
        if not phone:
            phone_matches = re.findall(r"(?:\+?65[\s-]*)?[689]\d{3}[\s-]*\d{4}", text)
            if phone_matches:
                phone = clean(phone_matches[0])

        address = ""
        # Singapore addresses on the directory normally end with a six-digit postal code.
        candidates = re.findall(r"(?:^|\|)\s*([^|]{8,220}?\b\d{6})\s*(?=\||$)", text)
        for cand in reversed(candidates):
            cand = clean(cand)
            if name.lower() not in cand.lower() and not re.fullmatch(r"\+?65?\s*\d+", cand):
                address = cand
                break
        if not address:
            pieces = [clean(x) for x in card.stripped_strings]
            for piece in reversed(pieces):
                if re.search(r"\b\d{6}\b", piece) and len(piece) > 8:
                    address = piece
                    break

        rows.append({
            "Institution Name": name,
            "Sector": "; ".join(sectors),
            "Licence Type / Status": "; ".join(licences),
            "Telephone": phone,
            "Address": address,
            "Website": website,
            "MAS Profile URL": href,
            "Source Page": source_url,
            "Extracted On": date.today().isoformat(),
        })
    return rows


def fetch_page(page):
    params = {"count": "0"}
    if page > 1:
        params["page"] = str(page)
    r = get(LIST_URL, params=params)
    return page, r.url, parse_html(r.text, r.url)


def main():
    records = {}
    method = "print"
    try:
        r = get(PRINT_URL)
        for row in parse_html(r.text, r.url):
            records[row["MAS Profile URL"]] = row
        print(f"Print endpoint yielded {len(records)} unique institutions")
    except Exception as exc:
        print(f"Print endpoint failed: {exc}")

    if len(records) < 3000:
        method = "paginated"
        # The public directory currently exposes 280 pages. Fetch a small buffer so
        # future page-count changes do not silently truncate the result.
        pages = range(1, 321)
        empty_run = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fetch_page, p): p for p in pages}
            page_results = []
            for fut in as_completed(futures):
                p = futures[fut]
                try:
                    page_results.append(fut.result())
                except Exception as exc:
                    print(f"Page {p} failed: {exc}")
        for page, source, rows in sorted(page_results):
            if not rows:
                empty_run += 1
            else:
                empty_run = 0
                for row in rows:
                    records[row["MAS Profile URL"]] = row
            print(f"page={page} rows={len(rows)} cumulative={len(records)}")

    rows = sorted(records.values(), key=lambda r: (r["Institution Name"].casefold(), r["MAS Profile URL"]))
    for i, row in enumerate(rows, 1):
        row["A-Z Index"] = i

    columns = [
        "A-Z Index", "Institution Name", "Sector", "Licence Type / Status",
        "Telephone", "Address", "Website", "MAS Profile URL", "Source Page", "Extracted On"
    ]
    with open("mas_financial_institutions.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

    summary = {
        "expected_count": EXPECTED,
        "actual_count": len(rows),
        "method": method,
        "first_name": rows[0]["Institution Name"] if rows else None,
        "last_name": rows[-1]["Institution Name"] if rows else None,
        "date": date.today().isoformat(),
    }
    with open("summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))

    if len(rows) < 3500:
        raise SystemExit(f"Extraction incomplete: {len(rows)} records")


if __name__ == "__main__":
    main()
