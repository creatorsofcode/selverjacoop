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
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        products = []

        for a in soup.select("a[href*='/toode/']")[:20]:
            name = a.get_text(" ", strip=True)

            if len(name) < 3:
                continue

            products.append({
                "name": name,
                "url": "https://www.selver.ee" + a["href"]
            })

        return products

    except Exception as e:
        return [{"error": str(e)}]


def search_coop(query):
    url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"

    try:
        r = requests.get(
            url,
            params={"search": query, "per_page": 20},
            timeout=15
        )

        r.raise_for_status()

        products = []

        for item in r.json():
            products.append({
                "name": item.get("name"),
                "price": item.get("prices", {}).get("price"),
                "url": item.get("permalink")
            })

        return products

    except Exception as e:
        return [{"error": str(e)}]

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/search")
def search():
    q = request.args.get("q", "sai")

    return jsonify({
        "query": q,
        "selver": search_selver(q),
        "coop": search_coop(q)
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
