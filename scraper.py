import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# ----------------------------
# CONFIG
# ----------------------------

BASE_URL = "https://www.selver.ee"
SEARCH_URL = BASE_URL + "/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

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


def eur_text_to_float(value: str) -> float:
    return float(value.replace(",", ".").strip())


# ----------------------------
# SELVER (BEST EFFORT)
# ----------------------------
def search_selver(query: str) -> List[dict]:
    url = f"{SEARCH_URL}?q={query}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)

        if r.status_code != 200:
            return [{"error": f"Selver HTTP {r.status_code}"}]

        html = r.text.lower()

        # JS / blocked detection
        if len(r.text) < 1500 or "cloudflare" in html:
            return [{"error": "Selver blocked or JS-rendered page"}]

        soup = BeautifulSoup(r.text, "html.parser")

        products = []
        seen = set()

        for a in soup.select("a[href]"):
            name = a.get_text(" ", strip=True)
            href = a.get("href")

            if not name or len(name) < 3:
                continue

            if not href:
                continue

            if "selver" in name.lower():
                continue

            if not looks_like_sai(name):
                continue

            if href in seen:
                continue

            seen.add(href)

            products.append({
                "name": name,
                "url": BASE_URL + href
            })

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
        data = r.json()

        return [
            {
                "name": item.get("name"),
                "price": item.get("prices", {}).get("price"),
                "url": item.get("permalink")
            }
            for item in data
        ]

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
        "coop": coop
    }
