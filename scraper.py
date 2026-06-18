```python
import re
from dataclasses import dataclass
from typing import Dict, List

import requests

# ----------------------------
# CONFIG
# ----------------------------

BASE_URL = "https://www.selver.ee"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT
}

COOP_CATEGORIES = {
    "sai": "sai",
    "leib": "leib",
    "kukkel": "kukkel",
    "ciabatta": "ciabatta",
    "baguette": "baguette",
    "brioche": "brioche",
}

PRICE_RE = re.compile(r"(\d+[,.]\d{2})")

EXCLUDE_WORDS = [
    "sushi",
    "supp",
    "magus",
]

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

    if any(word in n for word in EXCLUDE_WORDS):
        return False

    return any(re.search(pattern, n) for pattern in INCLUDE_PATTERNS)


# ----------------------------
# SELVER
# ----------------------------


def scrape_selver(query: str = "sai", max_pages: int = 2) -> List[Product]:
    from playwright.sync_api import sync_playwright

    results: Dict[str, Product] = {}

    search_url = f"https://www.selver.ee/otsi?query={query}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        page = browser.new_page(
            user_agent=USER_AGENT
        )

        for page_num in range(1, max_pages + 1):
            try:
                url = f"{search_url}&page={page_num}"

                page.goto(
                    url,
                    wait_until="networkidle",
                    timeout=30000
                )

                page.wait_for_timeout(2000)

                items = page.query_selector_all(
                    "a[data-testid='productLink']"
                )

                if not items:
                    break

                for item in items:
                    try:
                        name = normalize(item.inner_text())

                        href = item.get_attribute("href")

                        if not name or not href:
                            continue

                        full_url = (
                            href
                            if href.startswith("http")
                            else BASE_URL + href
                        )

                        if full_url in results:
                            continue

                        results[full_url] = Product(
                            name=name,
                            price_eur=0.0,
                            url=full_url,
                        )

                    except Exception:
                        continue

            except Exception:
                continue

        browser.close()

    return list(results.values())


# ----------------------------
# COOP
# ----------------------------

COOP_API = (
    "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
)


def scrape_coop(query: str = "sai") -> List[Product]:
    try:
        response = requests.get(
            COOP_API,
            params={
                "search": query,
                "per_page": 20,
            },
            headers=HEADERS,
            timeout=15,
        )

        response.raise_for_status()

        data = response.json()

    except Exception:
        return []

    results: List[Product] = []

    for item in data:
        try:
            name = item.get("name")
            url = item.get("permalink")

            if not name or not url:
                continue

            prices = item.get("prices", {})

            price_raw = prices.get("price")

            if price_raw is None:
                continue

            price_eur = float(price_raw) / 100

            results.append(
                Product(
                    name=name,
                    price_eur=price_eur,
                    url=url,
                )
            )

        except Exception:
            continue

    return results


# ----------------------------
# COMPARE
# ----------------------------


def compare_selver_vs_coop(query: str = "sai"):
    selver = scrape_selver(query)
    coop = scrape_coop(query)

    # Coopil on hinnad olemas
    coop = [p for p in coop if p.price_eur > 0]

    # Selveris praegu hinnad puuduvad
    selver = [p for p in selver if p.price_eur > 0]

    selver_best = (
        min(selver, key=lambda p: p.price_eur)
        if selver
        else None
    )

    coop_best = (
        min(coop, key=lambda p: p.price_eur)
        if coop
        else None
    )

    if not selver_best and not coop_best:
        return {
            "winner": "no-data",
            "selver_best": None,
            "coop_best": None,
            "selver_count": 0,
            "coop_count": 0,
        }

    if selver_best and coop_best:
        winner = (
            "selver"
            if selver_best.price_eur < coop_best.price_eur
            else "coop"
        )
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


if __name__ == "__main__":
    print(compare_selver_vs_coop("sai"))
```
