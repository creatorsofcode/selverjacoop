import re
from dataclasses import dataclass
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

# ----------------------------
# CONFIG
# ----------------------------

BASE_URL = "https://www.selver.ee"
SEARCH_URL = BASE_URL + "/search"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

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
# DATA MODEL
# ----------------------------

@dataclass
class Product:
    name: str
    price_eur: float
    url: str


class SelverBlockedError(RuntimeError):
    pass


# ----------------------------
# HELPERS
# ----------------------------

def eur_text_to_float(value: str) -> float:
    return float(value.replace(",", ".").strip())


def normalize(text: str) -> str:
    return " ".join(text.split()).strip()


def looks_like_sai(name: str) -> bool:
    n = name.lower()
    if any(w in n for w in EXCLUDE_WORDS):
        return False
    return any(re.search(p, n) for p in INCLUDE_PATTERNS)


# ----------------------------
# SELVER SCRAPER (requests fallback)
# ----------------------------

def scrape(query="sai", max_pages=2) -> List[Product]:
    all_products: Dict[str, Product] = {}

    for page in range(1, max_pages + 1):
        try:
            r = requests.get(
                SEARCH_URL,
                params={"q": query, "page": page},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )

            if r.status_code in (403, 429):
                raise SelverBlockedError("Blocked")

            html = r.text
        except Exception:
            break

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.ProductCard")

        if not cards:
            break

        for card in cards:
            link = card.select_one("h3 a[href]")
            if not link:
                continue

            name = normalize(link.get_text())
            href = link.get("href")

            if not name or not href:
                continue

            if not looks_like_sai(name):
                continue

            url = href if href.startswith("http") else BASE_URL + href

            all_products[url] = Product(name=name, price_eur=0.0, url=url)

    return list(all_products.values())


# ----------------------------
# SELVER PLAYWRIGHT (SAFE - optional)
# ----------------------------

def scrape_with_playwright(query="sai", max_pages=2) -> List[Product]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return scrape(query=query, max_pages=max_pages)

    all_products: Dict[str, Product] = {}
    SEARCH_URL_FULL = f"https://www.selver.ee/otsi?query={query}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)

            for page_num in range(1, max_pages + 1):
                url = f"{SEARCH_URL_FULL}&page={page_num}"

                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                try:
                    page.wait_for_selector("a[data-testid='productLink']", timeout=15000)
                except:
                    break

                items = page.query_selector_all("a[data-testid='productLink']")

                if not items:
                    break

                for item in items:
                    try:
                        name = item.inner_text().strip()
                        href = item.get_attribute("href")

                        if not name or not href:
                            continue

                        url = href if href.startswith("http") else BASE_URL + href

                        all_products[url] = Product(
                            name=name,
                            price_eur=0.0,
                            url=url,
                        )
                    except:
                        continue

            browser.close()

    except Exception as e:
        print("[selver playwright error]", e)
        return []

    return list(all_products.values())


# ----------------------------
# COOP SCRAPER (WORKING API)
# ----------------------------

COOP_API = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
COOP_BASE = "https://coophaapsalu.ee"

COOP_CATEGORIES = {
    "Saiad": COOP_BASE + "/tootekategooria/pagaritooted/saiad/",
    "Leivad": COOP_BASE + "/tootekategooria/pagaritooted/leivad/",
}


def scrape_coop(query="sai", category_url: str = "", max_pages=1) -> List[Product]:
    try:
        r = requests.get(
            COOP_API,
            params={"search": query, "per_page": 20},
            timeout=10,
        )
        data = r.json()
    except Exception:
        return []

    results = []

    for item in data:
        name = item.get("name")
        price_raw = item.get("prices", {}).get("price", 0)
        url = item.get("permalink")

        if not name or not url:
            continue

        price = float(price_raw) / 100

        results.append(
            Product(name=name, price_eur=price, url=url)
        )

    return results


def scrape_coop_with_playwright(category_url: str = "", max_pages=1):
    return scrape_coop()


# ----------------------------
# COMPARE
# ----------------------------

def compare_selver_vs_coop(query="sai", max_pages=2, engine="auto"):
    selver = scrape_with_playwright(query, max_pages) if engine != "requests" else scrape(query, max_pages)
    coop = scrape_coop(query, "", max_pages)

    selver = [p for p in selver if p.price_eur > 0]
    coop = [p for p in coop if p.price_eur > 0]

    if not selver and not coop:
        return {"winner": "no-data"}

    selver_best = min(selver, key=lambda x: x.price_eur) if selver else None
    coop_best = min(coop, key=lambda x: x.price_eur) if coop else None

    return {
        "selver_best": selver_best,
        "coop_best": coop_best,
    }
