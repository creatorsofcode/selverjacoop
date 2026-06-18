import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# -------------------------
# SELVER
# -------------------------
def search_selver(query):
    url = f"https://www.selver.ee/search?q={query}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        products = []

        for a in soup.select("a[href*='/toode/']")[:20]:
            name = a.get_text(" ", strip=True)

            if not name or len(name) < 3:
                continue

            products.append({
                "name": name,
                "url": "https://www.selver.ee" + a.get("href")
            })

        return products

    except Exception as e:
        return [{"error": str(e)}]


# -------------------------
# COOP
# -------------------------
def search_coop(query):
    url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"

    try:
        r = requests.get(url, params={"search": query, "per_page": 20}, timeout=15)
        data = r.json()

        products = []

        for item in data:
            products.append({
                "name": item.get("name"),
                "price": item.get("prices", {}).get("price"),
                "url": item.get("permalink")
            })

        return products

    except Exception as e:
        return [{"error": str(e)}]
