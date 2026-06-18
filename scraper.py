import os
import re
from dataclasses import dataclass
from html import unescape
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

if os.getenv("RENDER") and not os.getenv("PLAYWRIGHT_BROWSERS_PATH"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/render/project/.cache/ms-playwright"

BASE_URL = "https://www.selver.ee"
SELVER_SEARCH_URL = f"{BASE_URL}/search"
COOP_API = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "et-EE,et;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "User-Agent": USER_AGENT,
}

COOP_CATEGORIES = {
    "sai": "sai",
    "leib": "leib",
    "kukkel": "kukkel",
    "ciabatta": "ciabatta",
    "baguette": "baguette",
    "brioche": "brioche",
}

PRICE_RE = re.compile(r"(\d+[,.]\d{1,2})\s*(?:€|&euro;|eur)", re.IGNORECASE)
NOISE_RE = re.compile(
    r"(lisa|ostukorvi|lemmik|hind|tavahind|kampaania|kg|g|tk|€|\d+[,.]\d{1,2})",
    re.IGNORECASE,
)
SAI_INCLUDE_RE = re.compile(r"\b(sai|saiad|röstsai|rostsai|kukkel|leib|ciabatta|brioche|baguette)\b", re.IGNORECASE)
SAI_EXCLUDE_RE = re.compile(r"(sushi|saitaku|säilitus|sailitus|supp)", re.IGNORECASE)


class SelverBlockedError(RuntimeError):
    pass


@dataclass
class Product:
    name: str
    price_eur: float
    url: str


def normalize(text: str) -> str:
    return " ".join(unescape(text or "").split()).strip()


def _price_from_text(text: str) -> Optional[float]:
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _clean_name(text: str) -> str:
    lines = [normalize(line) for line in (text or "").splitlines()]
    candidates = []
    for line in lines:
        if not line or len(line) < 3:
            continue
        if NOISE_RE.fullmatch(line) or PRICE_RE.search(line):
            continue
        candidates.append(line)
    return candidates[0] if candidates else normalize(text)


def _matches_query(name: str, query: str) -> bool:
    name = normalize(name).lower()
    query = normalize(query or "").lower()
    if not query:
        return True

    if query == "sai":
        return bool(SAI_INCLUDE_RE.search(name)) and not SAI_EXCLUDE_RE.search(name)

    return query in name


def _selver_url(query: str, page: int) -> str:
    return f"{SELVER_SEARCH_URL}?q={quote_plus(query)}&page={page}&limit=48"


def _dedupe(products: Iterable[Product]) -> List[Product]:
    seen: Dict[str, Product] = {}
    for product in products:
        key = product.url or product.name.lower()
        if key not in seen:
            seen[key] = product
    return list(seen.values())


def _parse_selver_html(html: str, query: str = "") -> List[Product]:
    soup = BeautifulSoup(html or "", "html.parser")
    products: List[Product] = []

    for card in soup.select(".ProductCard"):
        link = (
            card.select_one(".ProductCard__name a[href]")
            or card.select_one("a[data-testid='productLink'][href]")
            or card.select_one("a[href]")
        )
        if not link:
            continue

        href = link.get("href")
        if not href:
            continue

        image = card.select_one("img[alt]")
        name = _clean_name(link.get_text(" ", strip=True))
        if not name and image:
            name = _clean_name(image.get("alt", ""))
        if not name:
            name = _name_from_url(href)
        if not name:
            continue
        if not _matches_query(name, query):
            continue

        price_node = card.select_one(".ProductPrice")
        price_text = price_node.get_text(" ", strip=True) if price_node else card.get_text(" ", strip=True)
        price = _price_from_text(price_text) or 0.0

        products.append(Product(name=name, price_eur=price, url=urljoin(BASE_URL, href)))

    if products:
        return _dedupe(products)

    selectors = [
        "a[data-testid='productLink']",
        "h3 a[href]",
        "[class*='product'] a[href]",
        "a[href*='/toode/']",
        "a[href*='/product/']",
    ]

    for selector in selectors:
        for link in soup.select(selector):
            href = link.get("href")
            if not href:
                continue

            card = link
            for _ in range(5):
                if card.parent is None:
                    break
                card = card.parent

            raw_name = link.get_text(" ", strip=True) or card.get_text("\n", strip=True)
            name = _clean_name(raw_name)
            if not name:
                continue

            price = _price_from_text(card.get_text(" ", strip=True)) or 0.0
            full_url = urljoin(BASE_URL, href)
            if BASE_URL not in full_url:
                continue

            if query and not _matches_query(name, query):
                continue

            products.append(Product(name=name, price_eur=price, url=full_url))

        if products:
            break

    return _dedupe(products)


def _name_from_url(href: str) -> str:
    slug = (href or "").strip("/").split("/")[-1]
    if not slug:
        return ""

    words = []
    for part in slug.split("-"):
        if not part:
            continue
        if part.isdigit():
            words.append(part)
        elif len(part) == 1 and part.lower() in {"g", "l"}:
            words.append(part)
        else:
            words.append(part.capitalize())

    return normalize(" ".join(words))


def scrape(query: str = "sai", max_pages: int = 2) -> List[Product]:
    products: List[Product] = []

    session = requests.Session()
    session.headers.update(HEADERS)

    for page in range(1, max_pages + 1):
        response = session.get(_selver_url(query, page), timeout=15)

        if response.status_code in {401, 403, 429, 503}:
            raise SelverBlockedError(
                f"Selver returned HTTP {response.status_code}; server may be blocked by anti-bot protection."
            )

        response.raise_for_status()
        page_products = _parse_selver_html(response.text, query)
        if not page_products:
            break
        products.extend(page_products)

    return _dedupe(products)


def _product_from_playwright_card(card, query: str) -> Optional[Product]:
    link = card.locator("a[href]").first
    if link.count() == 0:
        return None

    href = link.get_attribute("href")
    if not href:
        return None

    name = ""
    for selector in [
        "[data-testid*='name' i]",
        "[class*='name' i]",
        "[class*='title' i]",
        "h3",
        "a[href]",
    ]:
        candidate = card.locator(selector).first
        if candidate.count():
            name = _clean_name(candidate.inner_text(timeout=1500))
            if name:
                break

    if not name:
        name = _clean_name(card.inner_text(timeout=1500))
    if not name:
        return None

    price = _price_from_text(card.inner_text(timeout=1500)) or 0.0
    if query and not _matches_query(name, query):
        return None

    return Product(name=name, price_eur=price, url=urljoin(BASE_URL, href))


def scrape_with_playwright(query: str = "sai", max_pages: int = 2) -> List[Product]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is not installed correctly.") from exc

    products: List[Product] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
            ],
        )
        page = browser.new_page(
            extra_http_headers=HEADERS,
            locale="et-EE",
            user_agent=USER_AGENT,
            viewport={"width": 1365, "height": 900},
        )

        try:
            for page_num in range(1, max_pages + 1):
                response = page.goto(
                    _selver_url(query, page_num),
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                if response and response.status in {401, 403, 429, 503}:
                    raise SelverBlockedError(
                        f"Selver returned HTTP {response.status}; server may be blocked by anti-bot protection."
                    )

                try:
                    page.wait_for_selector(
                        "a[data-testid='productLink'], h3 a[href], [class*='product' i] a[href]",
                        timeout=12000,
                    )
                except PlaywrightTimeoutError:
                    pass

                page.wait_for_timeout(1500)

                page_products = _parse_selver_html(page.content(), query)
                if not page_products:
                    cards = page.locator(
                        "[data-testid*='product' i], article, [class*='product' i]"
                    )
                    for i in range(min(cards.count(), 80)):
                        try:
                            product = _product_from_playwright_card(cards.nth(i), query)
                            if product:
                                page_products.append(product)
                        except Exception:
                            continue

                if not page_products:
                    if page_num == 1:
                        body = normalize(page.locator("body").inner_text(timeout=3000))
                        if any(token in body.lower() for token in ["cloudflare", "access denied", "captcha"]):
                            raise SelverBlockedError("Selver anti-bot page was shown.")
                    break

                products.extend(page_products)
        finally:
            browser.close()

    return _dedupe(products)


def scrape_selver(query: str = "sai", max_pages: int = 2) -> List[Product]:
    return scrape_with_playwright(query, max_pages)


def _coop_search_term(query: str, coop_category_url: Optional[str]) -> str:
    return (coop_category_url or query or "sai").strip()


def scrape_coop(
    query: str = "sai",
    coop_category_url: Optional[str] = None,
    max_pages: int = 2,
) -> List[Product]:
    results: List[Product] = []
    term = _coop_search_term(query, coop_category_url)

    for page in range(1, max_pages + 1):
        response = requests.get(
            COOP_API,
            params={"search": term, "per_page": 20, "page": page},
            headers=HEADERS,
            timeout=15,
        )

        if response.status_code == 400 and page > 1:
            break
        response.raise_for_status()
        data = response.json()
        if not data:
            break

        for item in data:
            try:
                price_raw = item.get("prices", {}).get("price")
                if price_raw is None:
                    continue
                name = normalize(item.get("name"))
                if not _matches_query(name, query):
                    continue
                results.append(
                    Product(
                        name=name,
                        price_eur=float(price_raw) / 100,
                        url=item.get("permalink"),
                    )
                )
            except Exception:
                continue

    return _dedupe(results)


def scrape_coop_with_playwright(
    coop_category_url: str = "sai",
    max_pages: int = 2,
) -> List[Product]:
    return scrape_coop(coop_category_url, coop_category_url, max_pages)


def _best(products: List[Product]) -> Optional[Product]:
    priced = [product for product in products if product.price_eur > 0]
    return min(priced, key=lambda product: product.price_eur) if priced else None


def compare_selver_vs_coop(
    query: str = "sai",
    max_pages: int = 2,
    coop_category_url: Optional[str] = None,
    engine: str = "auto",
):
    if engine == "requests":
        selver_products = scrape(query, max_pages)
    else:
        selver_products = scrape_with_playwright(query, max_pages)

    coop_products = scrape_coop(query, coop_category_url, max_pages)
    selver_cheapest = _best(selver_products)
    coop_cheapest = _best(coop_products)

    price_diff_eur = None
    price_diff_pct = None
    winner = "no-data"

    if selver_cheapest and coop_cheapest:
        price_diff_eur = abs(selver_cheapest.price_eur - coop_cheapest.price_eur)
        base = max(selver_cheapest.price_eur, coop_cheapest.price_eur)
        price_diff_pct = (price_diff_eur / base * 100) if base else 0
        winner = "selver" if selver_cheapest.price_eur < coop_cheapest.price_eur else "coop"
    elif selver_cheapest:
        winner = "selver"
    elif coop_cheapest:
        winner = "coop"

    if winner == "no-data":
        summary = "Ei leidnud hinnaga tooteid kummastki poest."
    elif winner == "selver":
        summary = "Selverist leiti odavam hinnaga toode."
    else:
        summary = "Coopist leiti odavam hinnaga toode."

    return {
        "query": query,
        "summary": summary,
        "winner": winner,
        "selver_cheapest": selver_cheapest,
        "coop_cheapest": coop_cheapest,
        "selver_count": len(selver_products),
        "coop_count": len(coop_products),
        "price_diff_eur": price_diff_eur,
        "price_diff_pct": price_diff_pct,
    }


if __name__ == "__main__":
    selected_engine = os.getenv("ENGINE", "playwright")
    print(compare_selver_vs_coop("sai", engine=selected_engine))
