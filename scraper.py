import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# -------------------------
# SELVER (ROBUST VERSION)
# -------------------------
def search_selver(query):
    url = f"https://www.selver.ee/search?q={query}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)

        # 🔥 kui Selver annab mingi blokeeringu / JS shelli
        if r.status_code != 200:
            return [{"error": f"Selver HTTP {r.status_code}"}]

        html = r.text

        # 🔥 kui page on JS shell / cloudflare / captcha
        if len(html) < 1500 or "cloudflare" in html.lower():
            return [{"error": "Selver blocked or JS-rendered page"}]

        soup = BeautifulSoup(html, "html.parser")

        products = []

        # 🔥 fallback parsing (Selver HTML muutub tihti)
        selectors = [
            "a[href*='/toode']",
            "a[href*='product']",
            "a[href]"
        ]

        for selector in selectors:
            for a in soup.select(selector):
                name = a.get_text(" ", strip=True)

                if not name or len(name) < 3:
                    continue

                href = a.get("href", "")
                if not href:
                    continue

                # väldi rämpslinke
                if "selver" in name.lower():
                    continue

                products.append({
                    "name": name,
                    "url": "https://www.selver.ee" + href
                })

                if len(products) >= 20:
                    break

            if products:
                break

        if not products:
            return [{"error": "No products found (HTML changed)"}]

        return products

    except Exception as e:
        return [{"error": str(e)}]


# -------------------------
# COOP (STABLE API)
# -------------------------
def search_coop(query):
    url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"

    try:
        r = requests.get(
            url,
            params={"search": query, "per_page": 20},
            timeout=15
        )

        r.raise_for_status()
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
