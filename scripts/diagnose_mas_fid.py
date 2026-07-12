from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = "https://eservices.mas.gov.sg/fid/institution"
OUT = Path("diagnostic_output")
OUT.mkdir(exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def detail_count(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    return len({a.get("href") for a in soup.find_all("a", href=re.compile(r"/fid/institution/detail/", re.I))})


def main() -> None:
    report = {"requests": [], "browser": {"requests": [], "responses": []}}
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    urls = [
        BASE,
        BASE + "?count=0",
        BASE + "?count=10",
        BASE + "?count=50",
        BASE + "?count=100",
        BASE + "?page=2",
        BASE + "?page=2&count=100",
        BASE + "?count=100&page=2",
        BASE + "/print?count=0",
    ]
    for i, url in enumerate(urls):
        try:
            r = session.get(url, timeout=45)
            html = r.text
            (OUT / f"requests_{i}.html").write_text(html, encoding="utf-8")
            report["requests"].append({
                "url": url,
                "status": r.status_code,
                "final_url": r.url,
                "bytes": len(r.content),
                "detail_links": detail_count(html),
                "content_type": r.headers.get("content-type"),
            })
        except Exception as exc:
            report["requests"].append({"url": url, "error": str(exc)})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA, viewport={"width": 1440, "height": 1200})

        def on_request(req):
            u = req.url
            host = urlparse(u).netloc
            if "mas.gov.sg" in host:
                report["browser"]["requests"].append({
                    "method": req.method,
                    "url": u,
                    "resource_type": req.resource_type,
                    "post_data": req.post_data,
                })

        def on_response(resp):
            u = resp.url
            host = urlparse(u).netloc
            if "mas.gov.sg" in host:
                report["browser"]["responses"].append({
                    "status": resp.status,
                    "url": u,
                    "content_type": resp.headers.get("content-type"),
                })

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(BASE, wait_until="networkidle", timeout=120000)
        first = page.content()
        (OUT / "browser_initial.html").write_text(first, encoding="utf-8")
        report["browser"]["initial_url"] = page.url
        report["browser"]["initial_detail_links"] = detail_count(first)

        # Click the 100-row selector if possible.
        try:
            loc = page.get_by_text("100", exact=True)
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible():
                    el.click()
                    page.wait_for_load_state("networkidle", timeout=120000)
                    break
        except Exception as exc:
            report["browser"]["click_100_error"] = str(exc)
        after100 = page.content()
        (OUT / "browser_after_100.html").write_text(after100, encoding="utf-8")
        report["browser"]["after_100_url"] = page.url
        report["browser"]["after_100_detail_links"] = detail_count(after100)

        # Click visible page 2.
        try:
            loc = page.get_by_text("2", exact=True)
            clicked = False
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible():
                    el.click()
                    page.wait_for_load_state("networkidle", timeout=120000)
                    clicked = True
                    break
            report["browser"]["clicked_page_2"] = clicked
        except Exception as exc:
            report["browser"]["click_page_2_error"] = str(exc)
        after2 = page.content()
        (OUT / "browser_after_page2.html").write_text(after2, encoding="utf-8")
        report["browser"]["after_page2_url"] = page.url
        report["browser"]["after_page2_detail_links"] = detail_count(after2)
        browser.close()

    # Deduplicate network entries while preserving order.
    for key in ("requests", "responses"):
        seen = set()
        dedup = []
        for item in report["browser"][key]:
            marker = json.dumps(item, sort_keys=True)
            if marker not in seen:
                seen.add(marker)
                dedup.append(item)
        report["browser"][key] = dedup

    (OUT / "diagnostic_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
