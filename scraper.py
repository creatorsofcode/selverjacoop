from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}


def search_selver(query):
    url = f"https://www.selver.ee/search?q={query}"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        products = []

        links = soup.select("a[href]")

        for link in links:
            href = link.get("href", "")
            text = link.get_text(" ", strip=True)

            if len(text) < 3:
                continue

            if "/toode/" in href or "/product/" in href:
                products.append({
                    "name": text,
                    "url": "https://www.selver.ee" + href
                    if href.startswith("/")
                    else href
                })

        return products[:50]

    except Exception as e:
        return [{"error": str(e)}]


def search_coop(query):
    try:
        url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"

        response = requests.get(
            url,
            params={
                "search": query,
                "per_page": 50
            },
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        products = []

        for item in response.json():
            price = item.get("prices", {}).get("price")

            if price:
                try:
                    price = float(price) / 100
                except:
                    pass

            products.append({
                "name": item.get("name"),
                "price": price,
                "url": item.get("permalink")
            })

        return products

    except Exception as e:
        return [{"error": str(e)}]


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Selver + Coop API",
        "usage": {
            "search": "/search?q=sai",
            "examples": [
                "/search?q=piim",
                "/search?q=leib",
                "/search?q=sai"
            ]
        }
    })


@app.route("/search")
def search():
    query = request.args.get("q", "sai")

    return jsonify({
        "query": query,
        "selver_count": len(search_selver(query)),
        "coop_count": len(search_coop(query)),
        "selver": search_selver(query),
        "coop": search_coop(query)
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
    )
