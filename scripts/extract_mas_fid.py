from __future__ import annotations

import csv
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = "https://eservices.mas.gov.sg"
LIST_URL = f"{BASE}/fid/institution"
PRINT_URL = f"{BASE}/fid/institution/print?count=0"
OUT_DIR = Path("output")
OUT_DIR.mkdir(exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

PHONE_RE = re.compile(r"(?<!\d)(?:\+?65[\s-]?)?[689]\d{3}[\s-]?\d{4}(?!\d)")
POSTAL_RE = re.compile(r"\b\d{6}\b")
RESULT_RE = re.compile(r"([\d,]+)\s+result\(s\)", re.I)
DETAIL_RE = re.compile(r"/fid/institution/detail/", re.I)

LICENCE_TO_SECTOR = {
    "Approved CIS Trustee": "Capital Markets",
    "Approved Clearing House": "Capital Markets",
    "Approved Exchange": "Capital Markets",
    "Approved Holding Company": "Capital Markets",
    "Approved Insurance Broker": "Insurance",
    "Authorised Reinsurer (Composite)": "Insurance",
    "Authorised Reinsurer (General)": "Insurance",
    "Authorised Reinsurer (Life)": "Insurance",
    "Capital Markets Services Licensee": "Capital Markets",
    "Captive Insurer (Composite)": "Insurance",
    "Captive Insurer (General)": "Insurance",
    "Captive Insurer (Life)": "Insurance",
    "Central Depository System": "Capital Markets",
    "Credit and Charge Card Licensee": "Payments",
    "Designated Payment System Operator": "Payments",
    "Designated Payment System Settlement Institution": "Payments",
    "Direct Insurer (Composite)": "Insurance",
    "Direct Insurer (General)": "Insurance",
    "Direct Insurer (Life)": "Insurance",
    "Exempt Capital Markets Services Entity": "Capital Markets",
    "Exempt Financial Adviser": "Financial Advisory",
    "Exempt Insurance Broker": "Insurance",
    "Exempt Trust Company": "Capital Markets",
    "Finance Company": "Banking",
    "Financial Holding Company (Banking)": "Banking",
    "Financial Holding Company (Insurance)": "Insurance",
    "Full Bank": "Banking",
    "Licensed Credit Bureau": "Banking",
    "Licensed Financial Adviser": "Financial Advisory",
    "Licensed Trade Repository": "Capital Markets",
    "Licensed Trust Company": "Capital Markets",
    "Lloyd's Asia Scheme": "Insurance",
    "Local Bank": "Banking",
    "Major Payment Institution": "Payments",
    "Merchant Bank": "Banking",
    "Money-changing Licensee": "Payments",
    "Qualifying Full Bank": "Banking",
    "Recognised Clearing House": "Capital Markets",
    "Recognised Market Operator": "Capital Markets",
    "Registered Insurance Broker": "Insurance",
    "Reinsurer (Composite)": "Insurance",
    "Reinsurer (General)": "Insurance",
    "Reinsurer (Life)": "Insurance",
    "Representative Office (Banking)": "Banking",
    "Representative Office (Insurance)": "Insurance",
    "SGS Primary Dealer": "Banking",
    "Standard Payment Institution": "Payments",
    "Wholesale Bank": "Banking",
}


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = clean_text(item)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-SG,en;q=0.9",
        "Connection": "keep-alive",
    })
    return s


def request_html(session: requests.Session, url: str, tries: int = 5) -> str:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            r = session.get(url, timeout=45)
            r.raise_for_status()
            if len(r.text) < 100:
                raise RuntimeError(f"Tiny response ({len(r.text)} bytes) for {url}")
            return r.text
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(min(8, 1.5 ** attempt))
    raise RuntimeError(f"Failed to fetch {url}: {last}")


def parse_result_count(html: str) -> int | None:
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    m = RESULT_RE.search(text)
    return int(m.group(1).replace(",", "")) if m else None


def find_card(anchor: Any) -> Any:
    best = anchor.parent
    current = anchor.parent
    for _ in range(9):
        if current is None:
            break
        links = current.find_all("a", href=DETAIL_RE)
        text = clean_text(current.get_text(" ", strip=True))
        if len(links) == 1 and len(text) <= 1800:
            best = current
            current = current.parent
            continue
        if len(links) > 1:
            break
        current = current.parent
    return best


def extract_icon_text(card: Any, keywords: tuple[str, ...]) -> str:
    for img in card.find_all(["img", "svg", "span", "i"]):
        attrs = " ".join(
            str(img.get(k, "")) for k in ("src", "alt", "title", "class", "aria-label")
        ).lower()
        if any(k in attrs for k in keywords):
            parent = img.parent
            for _ in range(3):
                if parent is None:
                    break
                text = clean_text(parent.get_text(" ", strip=True))
                if text:
                    return text
                parent = parent.parent
    return ""


def parse_records(html: str, source_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=DETAIL_RE):
        href = urljoin(BASE, anchor.get("href", ""))
        href = href.split("#", 1)[0]
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        name = clean_text(anchor.get_text(" ", strip=True))
        if not name:
            continue
        card = find_card(anchor)
        card_text = clean_text(card.get_text("\n", strip=True))
        lines = unique_keep_order([clean_text(x) for x in card.get_text("\n", strip=True).splitlines()])

        external_links: list[str] = []
        for link in card.find_all("a", href=True):
            url = urljoin(source_url, link["href"])
            host = urlparse(url).netloc.lower()
            if host and "mas.gov.sg" not in host and not url.startswith("mailto:") and not url.startswith("tel:"):
                external_links.append(url)
        website = unique_keep_order(external_links)[0] if external_links else ""

        phone = ""
        phone_hint = extract_icon_text(card, ("phone", "telephone", "tel"))
        candidates = PHONE_RE.findall(phone_hint) or PHONE_RE.findall(card_text)
        if candidates:
            phone = clean_text(candidates[0])

        address = ""
        address_hint = extract_icon_text(card, ("address", "location", "map", "pin"))
        if POSTAL_RE.search(address_hint):
            address = address_hint
        else:
            postal_lines = [x for x in lines if POSTAL_RE.search(x)]
            if postal_lines:
                address = max(postal_lines, key=len)

        licence_candidates: list[str] = []
        for li in card.find_all("li"):
            t = clean_text(li.get_text(" ", strip=True))
            if t in LICENCE_TO_SECTOR:
                licence_candidates.append(t)
        if not licence_candidates:
            for line in lines:
                if line in LICENCE_TO_SECTOR:
                    licence_candidates.append(line)
        licences = unique_keep_order(licence_candidates)
        sectors = unique_keep_order([LICENCE_TO_SECTOR[x] for x in licences if x in LICENCE_TO_SECTOR])

        records.append({
            "institution_name": name,
            "sector": "; ".join(sectors),
            "licence_type_status": "; ".join(licences),
            "office_number": phone,
            "address": address,
            "website": website,
            "mas_profile_url": href,
            "source_list_url": source_url,
        })
    return records


def try_print_page(session: requests.Session) -> tuple[list[dict[str, str]], str]:
    try:
        html = request_html(session, PRINT_URL)
        (OUT_DIR / "debug_print.html").write_text(html, encoding="utf-8")
        return parse_records(html, PRINT_URL), html
    except Exception as exc:  # noqa: BLE001
        return [], f"ERROR: {exc}"


def discover_request_pagination(session: requests.Session) -> tuple[str, int, list[dict[str, str]], str]:
    candidates = [
        f"{LIST_URL}?count=100&page={{page}}",
        f"{LIST_URL}?page={{page}}&count=100",
        f"{LIST_URL}?count=50&page={{page}}",
        f"{LIST_URL}?page={{page}}&count=50",
        f"{LIST_URL}?count=0&page={{page}}",
        f"{LIST_URL}?page={{page}}&count=0",
        f"{LIST_URL}?page={{page}}",
    ]
    best: tuple[str, int, list[dict[str, str]], str] | None = None
    for template in candidates:
        try:
            h1 = request_html(session, template.format(page=1))
            r1 = parse_records(h1, template.format(page=1))
            h2 = request_html(session, template.format(page=2))
            r2 = parse_records(h2, template.format(page=2))
            u1 = {x["mas_profile_url"] for x in r1}
            u2 = {x["mas_profile_url"] for x in r2}
            score = len(u1) + len(u2 - u1)
            if u1 and u2 and u1 != u2 and (best is None or score > best[1]):
                best = (template, score, r1, h1)
        except Exception:
            continue
    if best is None:
        raise RuntimeError("Could not identify request-based pagination parameters")
    return best


def crawl_requests(session: requests.Session, expected: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    template, _, first_records, first_html = discover_request_pagination(session)
    per_page = len(first_records)
    if per_page <= 0:
        raise RuntimeError("Pagination discovery returned no records")
    pages = max(1, math.ceil(expected / per_page) + 3)
    all_by_url: dict[str, dict[str, str]] = {x["mas_profile_url"]: x for x in first_records}
    empty_streak = 0
    for page_num in range(2, pages + 1):
        url = template.format(page=page_num)
        html = request_html(session, url)
        rows = parse_records(html, url)
        before = len(all_by_url)
        for row in rows:
            all_by_url[row["mas_profile_url"]] = row
        added = len(all_by_url) - before
        print(f"request page={page_num} rows={len(rows)} added={added} total={len(all_by_url)}", flush=True)
        if added == 0:
            empty_streak += 1
        else:
            empty_streak = 0
        if len(all_by_url) >= expected or empty_streak >= 3:
            break
    report = {
        "method": "requests-pagination",
        "template": template,
        "per_page": per_page,
        "pages_attempted": page_num,
        "unique_records": len(all_by_url),
    }
    (OUT_DIR / "debug_first_page.html").write_text(first_html, encoding="utf-8")
    return list(all_by_url.values()), report


def crawl_playwright(expected: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    from playwright.sync_api import sync_playwright

    by_url: dict[str, dict[str, str]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, viewport={"width": 1440, "height": 1200})
        page.goto(LIST_URL, wait_until="networkidle", timeout=120000)

        # Prefer 100 rows per page when the control is available.
        try:
            control = page.get_by_text("100", exact=True).last
            if control.is_visible():
                control.click()
                page.wait_for_load_state("networkidle", timeout=120000)
        except Exception:
            pass

        page_num = 0
        unchanged = 0
        previous_total = -1
        while page_num < 500 and len(by_url) < expected:
            page_num += 1
            html = page.content()
            if page_num == 1:
                (OUT_DIR / "debug_browser_first.html").write_text(html, encoding="utf-8")
            rows = parse_records(html, page.url)
            for row in rows:
                by_url[row["mas_profile_url"]] = row
            print(f"browser page={page_num} rows={len(rows)} total={len(by_url)} url={page.url}", flush=True)

            if len(by_url) == previous_total:
                unchanged += 1
            else:
                unchanged = 0
            previous_total = len(by_url)
            if unchanged >= 3:
                break

            next_locator = page.locator(
                'a[aria-label*="Next" i], button[aria-label*="Next" i], '
                'a[title*="Next" i], button[title*="Next" i], '
                'li.next a, a.next, button.next'
            ).filter(has_not=page.locator('[disabled]'))
            clicked = False
            if next_locator.count() > 0:
                for i in range(next_locator.count()):
                    item = next_locator.nth(i)
                    try:
                        if item.is_visible() and item.is_enabled():
                            old = page.url
                            item.click()
                            page.wait_for_load_state("networkidle", timeout=120000)
                            if page.url != old or page_num == 1:
                                clicked = True
                                break
                    except Exception:
                        continue
            if not clicked:
                # Numeric fallback: click the next visible page number.
                target = str(page_num + 1)
                loc = page.get_by_text(target, exact=True)
                for i in range(loc.count()):
                    item = loc.nth(i)
                    try:
                        if item.is_visible():
                            item.click()
                            page.wait_for_load_state("networkidle", timeout=120000)
                            clicked = True
                            break
                    except Exception:
                        continue
            if not clicked:
                break
        browser.close()
    return list(by_url.values()), {
        "method": "playwright-pagination",
        "pages_attempted": page_num,
        "unique_records": len(by_url),
    }


def merge_record(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    out = dict(old)
    for key, value in new.items():
        if not out.get(key) and value:
            out[key] = value
        elif key in ("sector", "licence_type_status") and value:
            parts = unique_keep_order((out.get(key, "") + "; " + value).split(";"))
            out[key] = "; ".join(parts)
    return out


def write_outputs(records: list[dict[str, str]], report: dict[str, Any]) -> None:
    merged: dict[str, dict[str, str]] = {}
    for row in records:
        url = row.get("mas_profile_url", "")
        if not url:
            continue
        merged[url] = merge_record(merged.get(url, {}), row)
    data = sorted(merged.values(), key=lambda x: x.get("institution_name", "").casefold())
    for idx, row in enumerate(data, start=1):
        row["no"] = str(idx)
        row["verification_date"] = "2026-07-11"
        row["family_office_classification"] = ""
        row["telemarketing_priority"] = ""
        row["calling_status"] = "Not Called"
        row["contact_result"] = ""
        row["follow_up_date"] = ""
        row["assigned_to"] = ""
        row["notes"] = ""

    fields = [
        "no", "institution_name", "sector", "licence_type_status", "office_number",
        "address", "website", "mas_profile_url", "source_list_url", "verification_date",
        "family_office_classification", "telemarketing_priority", "calling_status",
        "contact_result", "follow_up_date", "assigned_to", "notes",
    ]
    with (OUT_DIR / "mas_fid_master.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(data)
    (OUT_DIR / "mas_fid_master.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    report = dict(report)
    report.update({
        "unique_records_written": len(data),
        "with_phone": sum(bool(x.get("office_number")) for x in data),
        "with_address": sum(bool(x.get("address")) for x in data),
        "with_website": sum(bool(x.get("website")) for x in data),
        "first_name": data[0]["institution_name"] if data else None,
        "last_name": data[-1]["institution_name"] if data else None,
    })
    (OUT_DIR / "extraction_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


def main() -> None:
    session = make_session()
    landing = request_html(session, f"{LIST_URL}?count=0")
    (OUT_DIR / "debug_landing.html").write_text(landing, encoding="utf-8")
    expected = parse_result_count(landing) or int(os.environ.get("EXPECTED_COUNT", "3640"))

    records: list[dict[str, str]] = []
    report: dict[str, Any] = {"expected_count": expected}

    print_rows, _ = try_print_page(session)
    if print_rows:
        print(f"print page records={len(print_rows)}", flush=True)
        records.extend(print_rows)
        report["print_page_records"] = len(print_rows)

    if len({x['mas_profile_url'] for x in records}) < expected:
        try:
            req_rows, req_report = crawl_requests(session, expected)
            records.extend(req_rows)
            report["requests"] = req_report
        except Exception as exc:  # noqa: BLE001
            report["requests_error"] = str(exc)
            print(f"requests crawl failed: {exc}", flush=True)

    if len({x['mas_profile_url'] for x in records}) < expected:
        try:
            browser_rows, browser_report = crawl_playwright(expected)
            records.extend(browser_rows)
            report["playwright"] = browser_report
        except Exception as exc:  # noqa: BLE001
            report["playwright_error"] = str(exc)
            print(f"playwright crawl failed: {exc}", flush=True)

    write_outputs(records, report)
    unique = len({x.get('mas_profile_url') for x in records if x.get('mas_profile_url')})
    if unique != expected:
        raise SystemExit(f"VALIDATION FAILED: expected {expected} unique institutions, extracted {unique}")


if __name__ == "__main__":
    main()
