from flask import Flask, jsonify, request, render_template
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


# -------------------------
# SELVER (SAFE VERSION)
# -------------------------
def search_selver(query):
    url = f"https://www.selver.ee/search?q={query}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)

        # 🔥 kui Selver blokib või JS page → fallback
        if r.status_code != 200 or len(r.text) < 1000:
            return [{"error": "Selver blocked or JS-rendered page"}]

        soup = BeautifulSoup(r.text, "html.parser")

        products = []

        # 🔥 tolerant selector (Selver muudab tihti HTML-i)
        for a in soup.select("a[href*='toode']"):
            name = a.get_text(" ", strip=True)

            if not name or len(name) < 3:
                continue

            products.append({
                "name": name,
                "url": "https://www.selver.ee" + a.get("href", "")
            })

            if len(products) >= 20:
                break

        return products

    except Exception as e:
        return [{"error": str(e)}]


# -------------------------
# COOP (OK API)
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


# -------------------------
# FRONTEND
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/search", methods=["GET"])
def search():
    q = request.args.get("q", "sai")

    return jsonify({
        "query": q,
        "selver": search_selver(q),
        "coop": search_coop(q)
    })

# -------------------------
# DEBUG (Render test)
# -------------------------
@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
