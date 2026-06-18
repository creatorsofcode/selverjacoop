import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin
import requests
from bs4 import BeautifulSoup

# ----------------------------
# CONFIG
# ----------------------------
BASE_URL = "https://www.selver.ee"
SEARCH_URL = BASE_URL + "/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
}

PRICE_RE = re.compile(r"(\d+[,.]\d{2})\s*€?")
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
    price_eur: Optional[float] = None
    url: str = ""


# ----------------------------
# HELPERS
# ----------------------------
def looks_like_sai(name: str) -> bool:
    n = name.lower()
    if any(w in n for w in EXCLUDE_WORDS):
        return False
    return any(re.search(p, n) for p in INCLUDE_PATTERNS)


def eur_text_to_float(value: str) -> Optional[float]:
    try:
        return float(value.replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None


def extract_price_near(tag) -> Optional[float]:
    """
    Best-effort: otsib hinda lingi vanem-elemendi tekstist.
    NB: see on heuristika, kuna Selveri tegelik HTML-struktuur
    pole mulle praegu nähtav. Kontrolli päris lehe peal (Inspect),
    kas hind asub mõnes konkreetses klassis (nt span.price) — see
    annaks usaldusväärsema selektori kui "lähim vanem-tekst".
    """
    parent = tag.find_parent(["li", "div", "article"])
    if not parent:
        return None
    match = PRICE_RE.search(parent.get_text(" ", strip=True))
    if not match:
        return None
    return eur_text_to_float(match.group(1))


# ----------------------------
# SELVER (BEST EFFORT)
# ----------------------------
def search_selver(query: str) -> List[dict]:
    encoded_query = quote_plus(query)  # fix: korralik URL-encoding
    url = f"{SEARCH_URL}?q={encoded_query}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return [{"error": f"Selver HTTP {r.status_code}"}]

        html = r.text.lower()
        if len(r.text) < 1500 or "cloudflare" in html:
            return [{"error": "Selver blocked or JS-rendered page"}]

        soup = BeautifulSoup(r.text, "html.parser")
        products = []
        seen = set()

        for a in soup.select("a[href]"):
            name = a.get_text(" ", strip=True)
            href = a.get("href")

            if not name or len(name) < 3 or not href:
                continue
            if "selver" in name.lower():
                continue
            if not looks_like_sai(name):
                continue
            if href in seen:
                continue
            seen.add(href)

            full_url = urljoin(BASE_URL, href)  # fix: ei dubleeri absoluutsete linkide korral
            price = extract_price_near(a)  # fix: kasutab varem defineeritud, kuid kasutamata loogikat

            product = Product(name=name, price_eur=price, url=full_url)
            products.append(asdict(product))

            if len(products) >= 20:
                break

        return products
    except Exception as e:
        return [{"error": str(e)}]


# ----------------------------
# COOP (STABLE API)
# ----------------------------
def search_coop(query: str) -> List[dict]:
    url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
    try:
        r = requests.get(url, params={"search": query, "per_page": 20}, timeout=15)

        if r.status_code != 200:
            return [{"error": f"Coop API returned status {r.status_code}"}]

        data = r.json()
        if not isinstance(data, list):
            return [{"error": "Unexpected Coop API response"}]

        results = []
        for item in data:
            prices = item.get("prices", {}) or {}
            raw_price = prices.get("price")
            minor_unit = prices.get("currency_minor_unit", 2)

            price_eur = None
            if raw_price is not None:
                try:
                    # fix: Store API tagastab hinna "minor units" kujul
                    # (nt "1990" + minor_unit=2 tähendab 19.90, mitte 1990 eurot)
                    price_eur = int(raw_price) / (10 ** minor_unit)
                except (ValueError, TypeError):
                    price_eur = None

            results.append({
                "name": item.get("name"),
                "price_eur": price_eur,
                "url": item.get("permalink"),
            })

        return results
    except Exception as e:
        return [{"error": str(e)}]


# ----------------------------
# COMPARE
# ----------------------------
def compare(query: str):
    selver = search_selver(query)
    coop = search_coop(query)
    selver_clean = [p for p in selver if "error" not in p]
    coop_clean = [p for p in coop if "error" not in p]
    return {
        "query": query,
        "selver_count": len(selver_clean),
        "coop_count": len(coop_clean),
        "selver": selver,
        "coop": coop,
    }
