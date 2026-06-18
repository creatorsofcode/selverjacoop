import os
from urllib.parse import quote_plus, urljoin
from flask import Flask, jsonify, request, render_template
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
}

# Definitsioonid hindade leidmiseks
PRICE_RE = re.compile(r"(\d+[,.]\d{2})\s*€?")
EXCLUDE_WORDS = ["sushi", "supp", "magus"]
INCLUDE_PATTERNS = [
    r"sai",
    r"kukkel",
    r"leib",
    r"ciabatta",
    r"brioche",
    r"baguette",
]

@app.route("/ping")
def ping():
    return "OK"

@app.route("/health")
def health():
    return {"status": "ok"}

def looks_like_sai(name: str) -> bool:
    """Kontrollib, kas toode on sai või saiatoit"""
    n = name.lower()
    if any(w in n for w in EXCLUDE_WORDS):
        return False
    return any(re.search(p, n) for p in INCLUDE_PATTERNS)

def eur_text_to_float(value: str) -> float:
    """Teisendab teksti ujukomaarvuks"""
    try:
        return float(value.replace(",", ".").strip())
    except (ValueError, AttributeError):
        return None

def extract_price_from_text(text: str) -> float:
    """Otsib hinda tekstist"""
    if not text:
        return None
    match = PRICE_RE.search(text)
    if match:
        return eur_text_to_float(match.group(1))
    return None

# -------------------------
# SELVER SCRAPER (PARANDATUD)
# -------------------------
def search_selver(query):
    encoded_query = quote_plus(query)
    url = f"https://www.selver.ee/search?q={encoded_query}"
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        
        if r.status_code != 200:
            return [{"error": f"Selver HTTP {r.status_code}"}]
        
        html = r.text.lower()
        
        # Cloudflare tuvastamine
        if "cloudflare" in html or "captcha" in html or len(r.text) < 1500:
            return [{"error": "Selver blocked or JS-rendered page"}]
        
        soup = BeautifulSoup(r.text, "html.parser")
        products = []
        seen_urls = set()
        
        # Otsi kõiki linke, mis võivad olla tooted
        for a in soup.select("a[href]"):
            name = a.get_text(" ", strip=True)
            href = a.get("href", "")
            
            if not name or len(name) < 5 or not href:
                continue
            
            # Filtr
            if not looks_like_sai(name):
                continue
            
            # Duplikaatide vältimine
            if href in seen_urls:
                continue
            seen_urls.add(href)
            
            # URL parandamine
            if href.startswith("http"):
                full_url = href
            else:
                full_url = urljoin("https://www.selver.ee", href)
            
            # Hind
            price = extract_price_from_text(parent.get_text(" ", strip=True)) if (parent := a.find_parent(["li", "div", "article"])) else None
            
            products.append({
                "name": name[:100],  # Piira pikkust
                "price_eur": price,
                "url": full_url
            })
            
            if len(products) >= 10:
                break
        
        return products if products else [{"error": "No products found"}]
        
    except requests.exceptions.Timeout:
        return [{"error": "Selver timeout"}]
    except Exception as e:
        return [{"error": f"Selver error: {str(e)}"}]

# -------------------------
# COOP API (PARANDATUD)
# -------------------------
def search_coop(query):
    url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
    
    try:
        r = requests.get(url, params={"search": query, "per_page": 20}, timeout=15)
        
        if r.status_code != 200:
            return [{"error": f"Coop API returned status {r.status_code}"}]
        
        data = r.json()
        
        if not isinstance(data, list):
            return [{"error": "Unexpected Coop API response"}]
        
        results = []
        for item in data:
            prices = item.get("prices", {}) or {}
            raw_price = prices.get("price")
            minor_unit = prices.get("currency_minor_unit", 2)
            
            price_eur = None
            if raw_price is not None:
                try:
                    # Paranda: int(raw_price) / (10 ** minor_unit)
                    price_eur = int(raw_price) / (10 ** minor_unit)
                except (ValueError, TypeError):
                    price_eur = None
            
            results.append({
                "name": item.get("name", ""),
                "price_eur": price_eur,
                "url": item.get("permalink", ""),
            })
        
        return results
        
    except requests.exceptions.Timeout:
        return [{"error": "Coop timeout"}]
    except Exception as e:
        return [{"error": f"Coop error: {str(e)}"}]

# -------------------------
# FRONTEND
# -------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -------------------------
# API - OLULINE: TOETAB KÕIKI MEETODEID
# -------------------------
@app.route("/search", methods=["GET", "POST", "OPTIONS"])
def search():
    if request.method == "OPTIONS":
        # CORS preflight request
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    # Võta query kas GET või POST andmetest
    if request.method == "POST":
        q = request.json.get("q", "sai") if request.is_json else request.form.get("q", "sai")
    else:
        q = request.args.get("q", "sai")
    
    selver_results = search_selver(q)
    coop_results = search_coop(q)
    
    response = jsonify({
        "query": q,
        "selver": selver_results,
        "coop": coop_results
    })
    
    # Lisa CORS headerid
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

# -------------------------
# KÕIK VEATEED SUUNA /
# -------------------------
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    """Käsitle Method Not Allowed vigu"""
    return jsonify({
        "error": "Method not allowed",
        "allowed_methods": ["GET", "POST", "OPTIONS"]
    }), 405

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500

# -------------------------
# KÄIVITUS
# -------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
