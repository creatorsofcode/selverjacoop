import re
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Dict


# ----------------------------
# CONFIG
# ----------------------------

BASE_URL = "https://www.selver.ee"
SEARCH_URL = "https://www.selver.ee/search"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

PRICE_RE = re.compile(r"(\d+[,.]\d{2})")

EXCLUDE_WORDS = ["sushi", "supp", "magus"]
INCLUDE_PATTERNS = [
    r"\bsai\b",
    r"\bsaiake\b",
    r"\bsaiakes",
    r"\bpikksai",
    r"\briivsai"
]


# ----------------------------
# COOP CONFIG (FIX FOR IMPORT ERROR)
# ----------------------------

COOP_API = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
COOP_BASE = "https://coophaapsalu.ee"

COOP_CATEGORIES = {
    "Saiad, sepikud": COOP_BASE + "/tootekategooria/pagaritooted/saiad/",
    "Leivad": COOP_BASE + "/tootekategooria/pagaritooted/leivad/",
    "Pagaritooted (koik)": COOP_BASE + "/tootekategooria/pagaritooted/",
}


# ----------------------------
# DATA MODEL
# ----------------------------

@dataclass
class Product:
    name: str
    price_eur: float
    url: str


class SelverBlockedError(Exception):
    pass


# ----------------------------
# HELPERS
# ----------------------------

def eur_to_float(text: str) -> float:
    return float(text.replace(",", ".").strip())


def normalize(text: str) -> str:
    return " ".join(text.split()).strip()


def looks_like_sai(name: str) -> bool:
    n = name.lower()

    if any(x in n for x in EXCLUDE_WORDS):
        return False

    return any(re.search(p, n) for p in INCLUDE_PATTERNS)


# ----------------------------
# SESSION
# ----------------------------

def new_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
        "Referer": "https://www.selver.ee/",
    })
    return s


# ----------------------------
# FETCH
# ----------------------------

def fetch(session, url, params=None, timeout=10):
    try:
        r = session.get(url, params=params, timeout=timeout)

        if r.status_code in (403, 429):
            raise SelverBlockedError("Blocked")

        return r.text

    except Exception:
        return ""


# ----------------------------
# SELVER PARSER
# ----------------------------

def parse_products(html: str) -> List[Product]:
    soup = BeautifulSoup(html, "html.parser")

    products = []
    seen = set()

    for a in soup.select("a[href]"):
        name = normalize(a.get_text())

        if not name:
            continue

        if not looks_like_sai(name):
            continue

        parent_text = a.parent.get_text(" ", strip=True)
        price_match = PRICE_RE.search(parent_text)

        if not price_match:
            continue

        href = a.get("href")
        if not href:
            continue

        url = href if href.startswith("http") else BASE_URL + href

        if url in seen:
            continue

        seen.add(url)

        products.append(Product(
            name=name,
            price_eur=eur_to_float(price_match.group(1)),
            url=url
        ))

    return products


# ----------------------------
# SELVER SCRAPER
# ----------------------------

def scrape_selver(query="sai", max_pages=2) -> List[Product]:
    session = new_session()
    results: Dict[str, Product] = {}

    for page in range(1, max_pages + 1):
        html = fetch(
            session,
            SEARCH_URL,
            params={"q": query, "page": page}
        )

        if not html:
            break

        products = parse_products(html)

        if not products:
            break

        before = len(results)

        for p in products:
            results[p.url] = p

        if len(results) == before:
            break

    return sorted(results.values(), key=lambda x: x.price_eur)


# ----------------------------
# COOP SCRAPER (API)
# ----------------------------

def scrape_coop(query="sai"):
    session = new_session()

    try:
        r = session.get(COOP_API, params={"search": query, "per_page": 20})
        data = r.json()

        out = []

        for item in data:
            name = item.get("name")
            price = item.get("prices", {}).get("price", 0)

            if not name:
                continue

            out.append(Product(
                name=name,
                price_eur=float(price) / 100 if price else 0,
                url=item.get("permalink", "")
            ))

        return out

    except Exception:
        return []


# ----------------------------
# COMPARE FUNCTION
# ----------------------------

def compare(query="sai"):
    selver = [p for p in scrape_selver(query) if p.price_eur > 0]
    coop = [p for p in scrape_coop(query) if p.price_eur > 0]

    selver_best = min(selver, key=lambda x: x.price_eur) if selver else None
    coop_best = min(coop, key=lambda x: x.price_eur) if coop else None

    if not selver_best and not coop_best:
        return {
            "query": query,
            "error": "no data"
        }

    if selver_best and coop_best:
        winner = "selver" if selver_best.price_eur < coop_best.price_eur else "coop"
    else:
        winner = "selver" if selver_best else "coop"

    return {
        "query": query,
        "selver_count": len(selver),
        "coop_count": len(coop),
        "selver_best": selver_best,
        "coop_best": coop_best,
        "winner": winner
    }
