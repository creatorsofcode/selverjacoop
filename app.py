from flask import Flask, jsonify, request, render_template
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0"}
@app.route("/ping")
def ping():
    return "OK"

# -------------------------
# SELVER SCRAPER
# -------------------------
def search_selver(query):
    url = f"https://www.selver.ee/search?q={query}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=15)

        html = r.text.lower()

        # 🔥 block detection
        if r.status_code != 200 or "cloudflare" in html or len(r.text) < 1500:
            return [{"error": "Selver blocked or JS-rendered page"}]

        soup = BeautifulSoup(r.text, "html.parser")

        products = []

        # 🔥 ainult realistlikud product linkid
        for a in soup.select("a[href*='toode'], a[href*='product']"):
            name = a.get_text(" ", strip=True)
            href = a.get("href", "")

            if not name or len(name) < 3:
                continue

            if not href:
                continue

            if "selver" in name.lower():
                continue

            products.append({
                "name": name,
                "url": "https://www.selver.ee" + href
            })

            if len(products) >= 20:
                break

        return products if products else [{"error": "No products found"}]

    except Exception as e:
        return [{"error": str(e)}]

# -------------------------
# COOP API (stabiilne)
# -------------------------
def search_coop(query):
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


# -------------------------
# FRONTEND
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -------------------------
# API (IMPORTANT: GET ONLY)
# -------------------------
@app.route("/search", methods=["GET"])
def search():
    q = request.args.get("q", "sai")

    return jsonify({
        "query": q,
        "selver": search_selver(q),
        "coop": search_coop(q)
    })


# -------------------------
# HEALTH CHECK (Render jaoks)
# -------------------------
@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
