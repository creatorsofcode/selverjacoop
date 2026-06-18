import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# -------------------------
# SELVER (ROBUST)
# -------------------------
def search_selver(query):
    url = f"https://www.selver.ee/search?q={query}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)

        html = r.text.lower()

        # 🔥 kui leht on blokitud või JS shell
        if r.status_code != 200 or "cloudflare" in html or len(r.text) < 1500:
            return [{"error": "Selver blocked or JS-rendered page"}]

        soup = BeautifulSoup(r.text, "html.parser")

        products = []

        # 🔥 tolerantne selector (Selver muudab tihti HTML-i)
        for a in soup.select("a"):
            name = a.get_text(" ", strip=True)

            if not name or len(name) < 3:
                continue

            href = a.get("href", "")

            if not href:
                continue

            # väldi rämpsu
            if "selver" in name.lower():
                continue

            if "/search" in href:
                continue

            products.append({
                "name": name,
                "url": "https://www.selver.ee" + href
            })

            if len(products) >= 20:
                break

        if not products:
            return [{"error": "No products found (HTML changed)"}]

        return products

    except Exception as e:
        return [{"error": str(e)}]


# -------------------------
# COOP (OK API)
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
