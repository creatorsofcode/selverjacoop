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
INCLUDE_PATTERNS = [r"\bsai\b", r"\bsaiake\b", r"\bsaiakes", r"\bpikksai", r"\briivsai"]


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
# HTTP SESSION
# ----------------------------

def new_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html",
        "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
    })
    return session


# ----------------------------
# SAFE FETCH
# ----------------------------

def fetch(url, params=None, timeout=10):
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code in (403, 429):
            raise SelverBlockedError("Blocked")
        return r.text
    except SelverBlockedError:
        raise
    except Exception:
        return ""


# ----------------------------
# SELVER PARSER
# ----------------------------

def parse_products(html: str) -> List[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()

    for a in soup.select("h3 a[href]"):
        name = normalize(a.get_text())
        href = a.get("href")

        if not name or not href:
            continue

        if not looks_like_sai(name):
            continue

        parent_text = a.parent.get_text(" ", strip=True)
        price_match = PRICE_RE.search(parent_text)

        if not price_match:
            continue

        price = eur_text_to_float(price_match.group(1))
        url = href if href.startswith("http") else BASE_URL + href

        if url in seen:
            continue

        seen.add(url)
        products.append(Product(name=name, price_eur=price, url=url))

    return products


# ----------------------------
# MAIN SCRAPER (SELVER)
# ----------------------------

def scrape(query="sai", max_pages=2) -> List[Product]:
    all_products: Dict[str, Product] = {}

    for page in range(1, max_pages + 1):
        html = fetch(
            SEARCH_URL,
            params={"q": query, "page": page},
            timeout=10
        )

        if not html:
            break

        products = parse_products(html)

        if not products:
            break

        before = len(all_products)

        for p in products:
            all_products[p.url] = p

        if len(all_products) == before:
            break

    return sorted(all_products.values(), key=lambda x: x.price_eur)


# ----------------------------
# COOP SCRAPER (API-BASED)
# ----------------------------

COOP_API = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
COOP_BASE = "https://coophaapsalu.ee"
COOP_CATEGORIES = {
    "Saiad, sepikud": COOP_BASE + "/tootekategooria/pagaritooted/saiad/",
    "Leivad": COOP_BASE + "/tootekategooria/pagaritooted/leivad/",
    "Pagaritooted (koik)": COOP_BASE + "/tootekategooria/pagaritooted/",
}


def scrape_coop(query="sai", category_url: str = "", max_pages=1) -> List[Product]:
    session = new_session()
    results = []

    try:
        r = session.get(
            COOP_API,
            params={"search": query, "per_page": 20},
            timeout=10
        )
        data = r.json()

        for item in data:
            name = item.get("name")
            price_raw = item.get("prices", {}).get("price", 0)
            price = float(price_raw) / 100
            url = item.get("permalink")

            if name and url:
                results.append(Product(name=name, price_eur=price, url=url))

    except Exception:
        return []

    return results


def scrape_with_playwright(query="sai", max_pages=2) -> List[Product]:
    # Fallback: keeps API compatibility if Playwright isn't installed/available.
    return scrape(query=query, max_pages=max_pages)


def scrape_coop_with_playwright(category_url: str = "", max_pages=1) -> List[Product]:
    # Fallback: keeps API compatibility if Playwright isn't installed/available.
    return scrape_coop(query="sai", category_url=category_url, max_pages=max_pages)


# ----------------------------
# COMPARE SELVER VS COOP
# ----------------------------

def compare_selver_vs_coop(
    query="sai",
    max_pages=2,
    coop_category_url: str = "",
    engine: str = "auto",
):
    selver = scrape(query, max_pages)
    coop = scrape_coop(query=query, category_url=coop_category_url, max_pages=max_pages)

    selver = [p for p in selver if p.price_eur > 0]
    coop = [p for p in coop if p.price_eur > 0]

    if not selver and not coop:
        return {
            "query": query,
            "selver_count": 0,
            "coop_count": 0,
            "winner_store": "no-data",
            "price_diff_eur": None,
            "price_diff_pct": None,
            "selver_cheapest": None,
            "coop_cheapest": None,
            "summary": "Molemast poest ei leitud sobivaid tooteid.",
        }

    selver_best = min(selver, key=lambda x: x.price_eur) if selver else None
    coop_best = min(coop, key=lambda x: x.price_eur) if coop else None

    if selver_best and coop_best:
        winner = "selver" if selver_best.price_eur < coop_best.price_eur else "coop"
        diff_eur = round(abs(selver_best.price_eur - coop_best.price_eur), 2)
        max_price = max(selver_best.price_eur, coop_best.price_eur)
        diff_pct = round((diff_eur / max_price) * 100, 2) if max_price > 0 else None
    elif selver_best:
        winner = "selver"
        diff_eur = None
        diff_pct = None
    else:
        winner = "coop"
        diff_eur = None
        diff_pct = None

    return {
        "query": query,
        "selver_count": len(selver),
        "coop_count": len(coop),
        "winner_store": winner,
        "price_diff_eur": diff_eur,
        "price_diff_pct": diff_pct,
        "selver_cheapest": selver_best,
        "coop_cheapest": coop_best,
        "summary": "Vordlus tehtud.",
    }
