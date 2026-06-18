import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

# ----------------------------
# CONFIG
# ----------------------------

BASE_URL = "https://www.selver.ee"
USER_AGENT = "Mozilla/5.0"

PRICE_RE = re.compile(r"(\d+[,.]\d{2})")

EXCLUDE_WORDS = ["sushi", "supp", "magus"]
INCLUDE_PATTERNS = [
    r"sai",
    r"kukkel",
    r"leib",
    r"ciabatta",
    r"brioche",
    r"baguette",
]


# ----------------------------
# MODEL
# ----------------------------

@dataclass
class Product:
    name: str
    price_eur: float
    url: str


# ----------------------------
# HELPERS
# ----------------------------

def normalize(text: str) -> str:
    return " ".join(text.split()).strip()


def looks_like_sai(name: str) -> bool:
    n = name.lower()
    if any(w in n for w in EXCLUDE_WORDS):
        return False
    return any(re.search(p, n) for p in INCLUDE_PATTERNS)


# ----------------------------
# SELVER (PLAYWRIGHT ONLY)
# ----------------------------

def scrape_selver(query="sai", max_pages=2) -> List[Product]:
    from playwright.sync_api import sync_playwright

    url_base = f"https://www.selver.ee/otsi?query={query}"
    results: Dict[str, Product] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for page_num in range(1, max_pages + 1):
            url = f"{url_base}&page={page_num}"
            page.goto(url, wait_until="networkidle")

            page.wait_for_timeout(3000)

            items = page.query_selector_all("a[data-testid='productLink']")

            if not items:
                break

            for item in items:
                try:
                    name = item.inner_text().strip()
                    href = item.get_attribute("href")

                    if not name or not href:
                        continue

                    full_url = href if href.startswith("http") else BASE_URL + href

                    if full_url in results:
                        continue

                    # Selveril searchis hind tihti puudub
                    results[full_url] = Product(
                        name=name,
                        price_eur=0.0,
                        url=full_url
                    )

                except:
                    continue

        browser.close()

    return list(results.values())


# ----------------------------
# COOP (API)
# ----------------------------

COOP_API = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"


def scrape_coop(query="sai") -> List[Product]:
    try:
        r = requests.get(
            COOP_API,
            params={"search": query, "per_page": 20},
            timeout=10,
        )
        data = r.json()
    except:
        return []

    results = []

    for item in data:
        name = item.get("name")
        price_raw = item.get("prices", {}).get("price", 0)
        url = item.get("permalink")

        if not name or not url:
            continue

        results.append(
            Product(
                name=name,
                price_eur=float(price_raw) / 100,
                url=url,
            )
        )

    return results


# ----------------------------
# COMPARE
# ----------------------------

def compare_selver_vs_coop(query="sai"):
    selver = scrape_selver(query)
    coop = scrape_coop(query)

    selver = [p for p in selver if p.price_eur >= 0]
    coop = [p for p in coop if p.price_eur >= 0]

    selver_best = min(selver, key=lambda x: x.price_eur) if selver else None
    coop_best = min(coop, key=lambda x: x.price_eur) if coop else None

    if not selver_best and not coop_best:
        return {"winner": "no-data"}

    if selver_best and coop_best:
        winner = "selver" if selver_best.price_eur < coop_best.price_eur else "coop"
    elif selver_best:
        winner = "selver"
    else:
        winner = "coop"

    return {
        "winner": winner,
        "selver_best": selver_best,
        "coop_best": coop_best,
        "selver_count": len(selver),
        "coop_count": len(coop),
    }
