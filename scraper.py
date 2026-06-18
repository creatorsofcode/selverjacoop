import re
import subprocess
import sys
import os
import importlib
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from requests.exceptions import ProxyError

try:
    cloudscraper = importlib.import_module("cloudscraper")
except Exception:
    cloudscraper = None

BASE_URL = "https://www.selver.ee"
SEARCH_URL = BASE_URL + "/search"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
PRICE_RE = re.compile(r"(\d+[,.]\d{2})\s*(?:€|â‚¬|EUR)?")

EXCLUDE_WORDS = [
    "sushi", "saialille", "salvei", "saitaku", "saidafarm",
    "magusain", "maitsaine", "mosaiik", "saint ", "sansai",
    "saiakuubik", "supp", "kiirsupp", "püreesupp", "kartulipuder",
]
INCLUDE_PATTERNS = [
    r"\bsai\b", r"\bsai,", r"\bsaiake\b", r"\bsaiakes",
    r"\bsarvesai", r"\br[öo]stsai", r"\bkodusai",
    r"\bpikksai", r"\briivsai", r"\bsaib\b", r"\bsaiaviil",
]


@dataclass
class Product:
    name: str
    price_eur: float
    url: str


class SelverBlockedError(RuntimeError):
    """Raised when Selver responds with anti-bot/login challenge instead of products."""


def eur_text_to_float(value: str) -> float:
    return float(value.replace(",", ".").strip())


def normalize_name(text: str) -> str:
    return " ".join(text.split()).strip()


def looks_like_sai_product(name: str) -> bool:
    lowered = name.lower()
    if any(x in lowered for x in EXCLUDE_WORDS):
        return False
    return any(re.search(pattern, lowered) for pattern in INCLUDE_PATTERNS)


def parse_products_from_soup(soup: BeautifulSoup, query: Optional[str] = None) -> List[Product]:
    products: List[Product] = []
    seen: set = set()
    query_tokens = [t for t in (query or "").lower().split() if t]

    for heading in soup.select("h3 a[href]"):
        name = normalize_name(heading.get_text(" ", strip=True))
        href = heading.get("href", "")
        if not name or not href:
            continue

        lowered_name = name.lower()
        if query_tokens and not all(token in lowered_name for token in query_tokens):
            continue

        price_match = None
        for parent in heading.parents:
            if parent.name not in {"article", "li", "div"}:
                continue
            card_text = parent.get_text(" ", strip=True)
            if not card_text:
                continue
            price_match = PRICE_RE.search(card_text)
            if price_match:
                break

        if not price_match:
            continue

        price = eur_text_to_float(price_match.group(1))
        product_url = href if href.startswith("http") else BASE_URL + href
        key = (name.lower(), product_url)
        if key in seen:
            continue
        seen.add(key)
        products.append(Product(name=name, price_eur=price, url=product_url))

    return products


def _fetch_html_requests(url: str, session: requests.Session, params: Optional[Dict[str, str]] = None) -> str:
    try:
        response = session.get(url, params=params, timeout=10)
        if response.status_code == 403:
            raise SelverBlockedError("Selver blocked this server/IP (HTTP 403).")
        response.raise_for_status()
        if _looks_like_selver_block_page(response.text, response.url):
            raise SelverBlockedError("Selver suunas paringu sisselogimise/anti-bot lehele.")
        return response.text
    except ProxyError as exc:
        raise RuntimeError(
            "Proxy blokeeris välisühenduse. PythonAnywhere free konto piirab välisvõrku. "
            "Kasuta tasulist kontot või küsi toe kaudu domeeni whitelisti."
        ) from exc


def _new_requests_session() -> requests.Session:
    # Selver often serves Cloudflare challenge pages to plain requests.
    # cloudscraper uses a browser-like challenge solver and usually avoids login/challenge loops.
    if cloudscraper is not None:
        session = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})
    else:
        session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "et-EE,et;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.selver.ee/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    # Optional escape hatch if host has broken proxy env vars.
    if os.getenv("DISABLE_SYSTEM_PROXY", "0") == "1":
        session.trust_env = False

    # Optional Selver-specific outbound proxy, useful when Selver blocks server IP.
    selver_proxy = os.getenv("SELVER_PROXY_URL", "").strip()
    if selver_proxy:
        session.proxies.update({"http": selver_proxy, "https": selver_proxy})
    return session


def _playwright_proxy_config() -> Optional[dict]:
    proxy_url = os.getenv("SELVER_PROXY_URL", "").strip()
    if not proxy_url:
        return None

    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        return None

    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"

    config = {"server": server}
    if parsed.username:
        config["username"] = parsed.username
    if parsed.password:
        config["password"] = parsed.password
    return config


def _looks_like_selver_block_page(html: str, final_url: str = "") -> bool:
    lowered = (html or "").lower()
    final_url_l = (final_url or "").lower()
    if "/user/login" in final_url_l or "login" in final_url_l and "selver.ee" in final_url_l:
        return True
    block_markers = [
        "logi sisse",
        "sisselog",
        "just a moment",
        "cloudflare",
        "captcha",
        "verify you are human",
        "attention required",
    ]
    return any(marker in lowered for marker in block_markers)


def _is_valid_selver_product_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "selver.ee" not in host:
        return False
    if any(x in path for x in ["/user", "/login", "/konto", "/cart", "/ostukorv"]):
        return False
    return True


def scrape_with_requests(query: str = "sai", max_pages: int = 5, limit: int = 48) -> List[Product]:
    session = _new_requests_session()

    all_products: Dict[str, Product] = {}
    for page in range(1, max_pages + 1):
        html = _fetch_html_requests(
            SEARCH_URL, session,
            params={"q": query, "page": str(page), "limit": str(limit)},
        )
        soup = BeautifulSoup(html, "html.parser")
        products = parse_products_from_soup(soup, query=query)
        products = [p for p in products if _is_valid_selver_product_url(p.url)]
        if not products:
            break
        before = len(all_products)
        for item in products:
            all_products[item.url] = item
        if len(all_products) == before:
            break

    return sorted(all_products.values(), key=lambda x: (x.name.lower(), x.price_eur))


def _install_playwright_chromium() -> None:
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def _build_playwright_context(browser):
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="et-EE",
        timezone_id="Europe/Tallinn",
        viewport={"width": 1440, "height": 960},
        device_scale_factor=1,
        is_mobile=False,
        has_touch=False,
        color_scheme="light",
        ignore_https_errors=True,
        extra_http_headers={
            "Accept-Language": "et-EE,et;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['et-EE', 'et', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
        """
    )
    return context


def scrape_with_playwright(query: str = "sai", max_pages: int = 5, limit: int = 48) -> List[Product]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright pole saadaval. Paigalda: pip install playwright") from exc

    def _run() -> List[Product]:
        all_products: Dict[str, Product] = {}
        with sync_playwright() as p:
            proxy_cfg = _playwright_proxy_config()
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
                proxy=proxy_cfg,
            )
            context = _build_playwright_context(browser)
            page_obj = context.new_page()
            for page in range(1, max_pages + 1):
                url = f"{SEARCH_URL}?q={query}&page={page}&limit={limit}"
                page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Cloudflare challenge: give the JS challenge a chance to finish.
                try:
                    page_obj.wait_for_load_state("networkidle", timeout=45000)
                except Exception:
                    pass

                page_obj.wait_for_timeout(12000)
                html = page_obj.content()

                # One retry after the challenge page in case Cloudflare flips cookies.
                if "Just a moment" in html or "<title>Just a moment" in html:
                    page_obj.wait_for_timeout(15000)
                    page_obj.reload(wait_until="domcontentloaded", timeout=30000)
                    try:
                        page_obj.wait_for_load_state("networkidle", timeout=30000)
                    except Exception:
                        pass
                    page_obj.wait_for_timeout(8000)
                    html = page_obj.content()

                # If Selver redirects to login/challenge, retry once from the homepage
                # to refresh session cookies before parsing products.
                if _looks_like_selver_block_page(html, page_obj.url):
                    page_obj.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
                    page_obj.wait_for_timeout(3000)
                    page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        page_obj.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass
                    page_obj.wait_for_timeout(5000)
                    html = page_obj.content()

                if _looks_like_selver_block_page(html, page_obj.url):
                    break
                
                soup = BeautifulSoup(html, "html.parser")
                products = parse_products_from_soup(soup, query=query)
                products = [p for p in products if _is_valid_selver_product_url(p.url)]
                if not products:
                    break
                before = len(all_products)
                for item in products:
                    all_products[item.url] = item
                if len(all_products) == before:
                    break
            context.close()
            browser.close()
        return sorted(all_products.values(), key=lambda x: (x.name.lower(), x.price_eur))

    try:
        return _run()
    except Exception as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        _install_playwright_chromium()
        return _run()


def scrape(query: str = "sai", max_pages: int = 5) -> List[Product]:
    """Entry point used by Flask: requests first, then bounded Playwright fallback."""
    request_error: Optional[str] = None
    request_blocked = False
    try:
        products = scrape_with_requests(query=query, max_pages=max_pages)
        products = [p for p in products if _is_valid_selver_product_url(p.url)]
        if products:
            return products
        request_error = "Requests path returned no Selver products."
    except Exception as exc:
        request_error = str(exc)
        request_blocked = isinstance(exc, SelverBlockedError)

    enable_playwright_fallback = os.getenv("SELVER_ENABLE_PLAYWRIGHT_FALLBACK", "1") == "1"
    if not enable_playwright_fallback:
        raise RuntimeError(
            request_error
            or "Selver scraping failed. If blocked, configure SELVER_PROXY_URL."
        )

    try:
        products = scrape_with_playwright(query=query, max_pages=max_pages)
    except Exception as exc:
        if request_blocked:
            raise SelverBlockedError(request_error or "Selver anti-bot/login block") from exc
        raise RuntimeError(
            request_error
            or f"Selver scraping failed (Playwright fallback failed: {exc})"
        ) from exc

    products = [p for p in products if _is_valid_selver_product_url(p.url)]
    if products:
        return products

    if request_blocked:
        raise SelverBlockedError(request_error or "Selver anti-bot/login block")
    raise RuntimeError(
        request_error
        or "Selver returned no products. If this server IP is blocked, set SELVER_PROXY_URL."
    )


# ---------------------------------------------------------------------------
# Coop (coophaapsalu.ee – WooCommerce) scraper
# ---------------------------------------------------------------------------

COOP_BASE = "https://coophaapsalu.ee"
# Category page for saiad/sepikud – all sai-type bread products
COOP_SAI_CATEGORY = COOP_BASE + "/tootekategooria/pagaritooted/saiad/"
COOP_API_PRODUCTS = COOP_BASE + "/wp-json/wc/store/v1/products"
COOP_PRICE_RE = re.compile(r"([\d\s]+[,.]?\d*)\s*[€â‚¬]")


def _parse_coop_price(raw: str) -> float:
    """Extract the first (sale or regular) price from a WooCommerce .price text."""
    # Price text can be e.g. "3,49€12,46€ / KG" – take the first number
    m = re.search(r"([\d]+[,.][\d]+|[\d]+)", raw.replace("\xa0", "").replace(" ", ""))
    if m:
        return float(m.group(1).replace(",", "."))
    return 0.0


def _parse_coop_api_price(prices: dict) -> float:
    if not prices:
        return 0.0
    raw = prices.get("price") or prices.get("sale_price") or prices.get("regular_price") or ""
    if not raw:
        return 0.0
    try:
        minor_unit = int(prices.get("currency_minor_unit", 2))
    except Exception:
        minor_unit = 2
    try:
        return float(raw) / (10 ** minor_unit)
    except Exception:
        return 0.0


def _parse_coop_products_from_soup(soup: BeautifulSoup) -> List[Product]:
    products: List[Product] = []
    seen: set = set()
    for li in soup.select("li.product:not(.product-category)"):
        name_el = li.select_one("h2")
        price_el = li.select_one(".price")
        link_el = li.select_one("a[href]")
        if not name_el or not link_el:
            continue
        name = " ".join(name_el.get_text(" ", strip=True).split())
        price_raw = price_el.get_text(" ", strip=True) if price_el else ""
        price = _parse_coop_price(price_raw)
        url = link_el.get("href", "")
        if not url or url in seen:
            continue
        seen.add(url)
        products.append(Product(name=name, price_eur=price, url=url))
    return products


def _parse_coop_products_from_api(items: list) -> List[Product]:
    products: List[Product] = []
    seen: set = set()
    for item in items:
        name = normalize_name(item.get("name", ""))
        url = item.get("permalink", "")
        if not name or not url:
            continue
        price = _parse_coop_api_price(item.get("prices", {}))
        if url in seen:
            continue
        seen.add(url)
        products.append(Product(name=name, price_eur=price, url=url))
    return products


def scrape_coop_api(query: str = "sai", max_pages: int = 3, per_page: int = 40) -> List[Product]:
    session = _new_requests_session()
    all_products: Dict[str, Product] = {}

    for page_num in range(1, max_pages + 1):
        try:
            resp = session.get(
                COOP_API_PRODUCTS,
                params={"search": query, "page": page_num, "per_page": per_page},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except ProxyError as exc:
            raise RuntimeError(
                "Proxy blokeeris välisühenduse. PythonAnywhere free konto piirab välisvõrku. "
                "Kasuta tasulist kontot või küsi toe kaudu domeeni whitelisti."
            ) from exc
        except Exception:
            break

        if not isinstance(data, list) or not data:
            break

        products = _parse_coop_products_from_api(data)
        if not products:
            break

        before = len(all_products)
        for item in products:
            all_products[item.url] = item
        if len(all_products) == before:
            break

    return sorted(all_products.values(), key=lambda x: (x.name.lower(), x.price_eur))


def scrape_coop_with_playwright(category_url: str = COOP_SAI_CATEGORY, max_pages: int = 5) -> List[Product]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright pole saadaval.") from exc

    def _run() -> List[Product]:
        all_products: Dict[str, Product] = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page_obj = browser.new_page()
            for page_num in range(1, max_pages + 1):
                url = category_url if page_num == 1 else f"{category_url}page/{page_num}/"
                page_obj.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page_obj.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                soup = BeautifulSoup(page_obj.content(), "html.parser")
                products = _parse_coop_products_from_soup(soup)
                if not products:
                    break
                before = len(all_products)
                for item in products:
                    all_products[item.url] = item
                if len(all_products) == before:
                    break
            browser.close()
        return sorted(all_products.values(), key=lambda x: (x.name.lower(), x.price_eur))

    try:
        return _run()
    except Exception as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        _install_playwright_chromium()
        return _run()


def scrape_coop_with_requests(category_url: str = COOP_SAI_CATEGORY, max_pages: int = 5) -> List[Product]:
    session = _new_requests_session()
    all_products: Dict[str, Product] = {}
    for page_num in range(1, max_pages + 1):
        url = category_url if page_num == 1 else f"{category_url}page/{page_num}/"
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except ProxyError as exc:
            raise RuntimeError(
                "Proxy blokeeris välisühenduse. PythonAnywhere free konto piirab välisvõrku. "
                "Kasuta tasulist kontot või küsi toe kaudu domeeni whitelisti."
            ) from exc
        except Exception:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        products = _parse_coop_products_from_soup(soup)
        if not products:
            break
        before = len(all_products)
        for item in products:
            all_products[item.url] = item
        if len(all_products) == before:
            break
    return sorted(all_products.values(), key=lambda x: (x.name.lower(), x.price_eur))


def scrape_coop(query: str = "sai", category_url: str = COOP_SAI_CATEGORY, max_pages: int = 3) -> List[Product]:
    """Entry point for Coop: fast API first, then category HTML fallback, then Playwright fallback."""
    products = scrape_coop_api(query=query, max_pages=max_pages)
    if not products:
        products = scrape_coop_with_requests(category_url=category_url, max_pages=max_pages)
    if not products:
        products = scrape_coop_with_playwright(category_url=category_url, max_pages=max_pages)
    return products


# Coop category map for the UI dropdown
COOP_CATEGORIES: dict = {
    "Saiad, sepikud": COOP_BASE + "/tootekategooria/pagaritooted/saiad/",
    "Leivad": COOP_BASE + "/tootekategooria/pagaritooted/leivad/",
    "Saiakesed, pirukad": COOP_BASE + "/tootekategooria/pagaritooted/saiakesed-pirukad-stritslid-kupsised/",
    "Koogid, tordid": COOP_BASE + "/tootekategooria/pagaritooted/koogid-tordid/",
    "Kuivikud, galetid": COOP_BASE + "/tootekategooria/pagaritooted/kuivikud-galetid/",
    "Pagaritooted (kõik)": COOP_BASE + "/tootekategooria/pagaritooted/",
}


def _query_filter(products: List[Product], query: str) -> List[Product]:
    q = query.strip().lower()
    if not q:
        return products
    return [p for p in products if q in p.name.lower()]


def compare_selver_vs_coop(
    query: str = "sai",
    max_pages: int = 3,
    coop_category_url: str = COOP_SAI_CATEGORY,
    engine: str = "auto",
) -> dict:
    """Compare cheapest product by query between Selver and Coop.

    Returns winner and percentage difference:
      price_diff_pct = abs(selver - coop) / max(selver, coop) * 100
    """
    if engine == "playwright":
        selver_products = scrape_with_playwright(query=query, max_pages=max_pages)
        coop_products = scrape_coop_with_playwright(category_url=coop_category_url, max_pages=max_pages)
    else:
        # Run stores in parallel for faster compare in auto/requests mode.
        with ThreadPoolExecutor(max_workers=2) as ex:
            selver_future = ex.submit(scrape, query=query, max_pages=max_pages)
            coop_future = ex.submit(scrape_coop, query=query, category_url=coop_category_url, max_pages=max_pages)
            selver_products = selver_future.result()
            coop_products = coop_future.result()

    coop_products = _query_filter(coop_products, query=query)

    selver_valid = [p for p in selver_products if p.price_eur > 0]
    coop_valid = [p for p in coop_products if p.price_eur > 0]

    selver_cheapest = min(selver_valid, key=lambda p: p.price_eur) if selver_valid else None
    coop_cheapest = min(coop_valid, key=lambda p: p.price_eur) if coop_valid else None

    if not selver_cheapest and not coop_cheapest:
        return {
            "query": query,
            "selver_count": len(selver_products),
            "coop_count": len(coop_products),
            "winner_store": "no-data",
            "price_diff_eur": None,
            "price_diff_pct": None,
            "selver_cheapest": None,
            "coop_cheapest": None,
            "summary": "Mõlemast poest ei leitud sobivaid tooteid.",
        }

    if selver_cheapest and not coop_cheapest:
        return {
            "query": query,
            "selver_count": len(selver_products),
            "coop_count": len(coop_products),
            "winner_store": "selver",
            "price_diff_eur": None,
            "price_diff_pct": None,
            "selver_cheapest": selver_cheapest,
            "coop_cheapest": None,
            "summary": "Coopis ei leitud sobivaid tooteid, Selveris leiti.",
        }

    if coop_cheapest and not selver_cheapest:
        return {
            "query": query,
            "selver_count": len(selver_products),
            "coop_count": len(coop_products),
            "winner_store": "coop",
            "price_diff_eur": None,
            "price_diff_pct": None,
            "selver_cheapest": None,
            "coop_cheapest": coop_cheapest,
            "summary": "Selveris ei leitud sobivaid tooteid, Coopis leiti.",
        }

    selver_price = selver_cheapest.price_eur
    coop_price = coop_cheapest.price_eur
    diff_eur = abs(selver_price - coop_price)
    base = max(selver_price, coop_price)
    diff_pct = (diff_eur / base * 100) if base else 0.0

    if selver_price < coop_price:
        winner = "selver"
        summary = f"Selver on odavam {diff_pct:.2f}% (vahe {diff_eur:.2f} EUR)."
    elif coop_price < selver_price:
        winner = "coop"
        summary = f"Coop on odavam {diff_pct:.2f}% (vahe {diff_eur:.2f} EUR)."
    else:
        winner = "equal"
        summary = "Mõlemas poes on odavaim hind sama."

    return {
        "query": query,
        "selver_count": len(selver_products),
        "coop_count": len(coop_products),
        "winner_store": winner,
        "price_diff_eur": round(diff_eur, 2),
        "price_diff_pct": round(diff_pct, 2),
        "selver_cheapest": selver_cheapest,
        "coop_cheapest": coop_cheapest,
        "summary": summary,
    }
