import os
from urllib.parse import quote_plus, urljoin
from flask import Flask, jsonify, request, render_template
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
}


@app.route("/ping")
def ping():
    return "OK"


# -------------------------
# SELVER SCRAPER
# -------------------------
def search_selver(query):
    encoded_query = quote_plus(query)  # fix: korralik URL-encoding (õ,ä,ö,ü, tühikud jne)
    url = f"https://www.selver.ee/search?q={encoded_query}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        html = r.text.lower()

        # block detection
        if r.status_code != 200 or "cloudflare" in html or len(r.text) < 1500:
            return [{"error": "Selver blocked or JS-rendered page"}]

        soup = BeautifulSoup(r.text, "html.parser")
        products = []

        # ainult realistlikud toote linkid
        for a in soup.select("a[href*='toode'], a[href*='product']"):
            name = a.get_text(" ", strip=True)
            href = a.get("href", "")

            if not name or len(name) < 3 or not href:
                continue
            if "selver" in name.lower():
                continue

            # fix: urljoin käsitleb korrektselt nii suhtelisi kui absoluutseid linke
            full_url = urljoin("https://www.selver.ee", href)

            products.append({
                "name": name,
                "url": full_url
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

        if r.status_code != 200:
            return [{"error": f"Coop API returned status {r.status_code}"}]

        data = r.json()

        # fix: kaitse juhuks kui API tagastab dict/veateate, mitte listi
        if not isinstance(data, list):
            return [{"error": "Unexpected Coop API response"}]

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
    # fix: Render annab pordi läbi PORT env-muutuja, kõva 10000 võib põhjustada
    # rakenduse kättesaamatuse jäämist platvormil
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
