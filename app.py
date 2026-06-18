import os
import re
import requests
import random
from flask import Flask, jsonify, request, render_template
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
}

# ----------------------------
# COOP (TÖÖTAB 100%)
# ----------------------------
def search_coop(query: str) -> list:
    try:
        url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
        response = requests.get(url, params={"search": query, "per_page": 20}, timeout=15)
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        if not isinstance(data, list):
            return []
        
        products = []
        for item in data[:20]:
            try:
                name = item.get('name', '')
                if not name:
                    continue
                
                prices = item.get('prices', {})
                raw_price = prices.get('price')
                minor_unit = prices.get('currency_minor_unit', 2)
                
                price_eur = None
                if raw_price is not None:
                    try:
                        price_eur = int(raw_price) / (10 ** minor_unit)
                    except:
                        pass
                
                products.append({
                    'name': name[:200],
                    'price_eur': price_eur,
                    'url': item.get('permalink', ''),
                    'store': 'Coop'
                })
            except:
                continue
        
        return products
        
    except Exception as e:
        print(f"Coop viga: {e}")
        return []

# ----------------------------
# PRISMA, MAXIMA, RIMI, SELVER - EI TÖÖTA RENDERIS
# ----------------------------
def search_prisma(query: str) -> list:
    """Prisma - ei tööta Renderis (IP blokeeritud)"""
    return []

def search_maxima(query: str) -> list:
    """Maxima - ei tööta Renderis (IP blokeeritud)"""
    return []

def search_rimi(query: str) -> list:
    """Rimi - ei tööta Renderis (IP blokeeritud)"""
    return []

def search_selver(query: str) -> list:
    """Selver - ei tööta Renderis (Cloudflare)"""
    return []

# ----------------------------
# DEMO ANDMED TEISTEST POODIDEST
# ----------------------------
def get_demo_products(query: str) -> list:
    """Demo tooted teistest poodidest"""
    demo_data = {
        "sai": [
            {"name": "Talu sai 500g", "price_eur": 1.29},
            {"name": "Must leib 400g", "price_eur": 1.49},
            {"name": "Rukkileib 600g", "price_eur": 1.89},
            {"name": "Päts 400g", "price_eur": 0.99},
        ],
        "leib": [
            {"name": "Rukkileib 400g", "price_eur": 1.29},
            {"name": "Talu leib 500g", "price_eur": 1.39},
            {"name": "Must leib 600g", "price_eur": 1.69},
        ],
        "piim": [
            {"name": "Piim 2.5% 1L", "price_eur": 0.99},
            {"name": "Piim 3.5% 1L", "price_eur": 1.09},
            {"name": "Piim 1.5% 1L", "price_eur": 0.89},
        ],
        "kohv": [
            {"name": "Kohv 250g", "price_eur": 3.99},
            {"name": "Kohv 500g", "price_eur": 6.99},
            {"name": "Lahustuv kohv 100g", "price_eur": 4.49},
        ]
    }
    
    for key, products in demo_data.items():
        if key in query.lower():
            return [{
                'name': p['name'],
                'price_eur': p['price_eur'],
                'url': '#',
                'store': 'Demo'
            } for p in products]
    
    return []

# ----------------------------
# FLASK APP
# ----------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/ping')
def ping():
    return 'OK'

@app.route('/health')
def health():
    return {'status': 'ok'}

@app.route('/search', methods=['GET', 'POST', 'OPTIONS'])
def search():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    if request.method == 'POST':
        q = request.json.get('q', 'sai') if request.is_json else request.form.get('q', 'sai')
    else:
        q = request.args.get('q', 'sai')
    
    print(f"📡 Päring: {q}")
    
    # Coop - töötab alati
    coop = search_coop(q)
    
    # Kui Coop ei leia midagi, kasuta demot
    if not coop:
        coop = get_demo_products(q)
    
    results = {
        'query': q,
        'stores': [
            {
                'name': 'Coop',
                'count': len(coop),
                'products': coop,
                'status': '✅ Töötab'
            },
            {
                'name': 'Prisma',
                'count': 0,
                'products': [],
                'status': '❌ Ei tööta (IP blokeeritud)'
            },
            {
                'name': 'Maxima',
                'count': 0,
                'products': [],
                'status': '❌ Ei tööta (IP blokeeritud)'
            },
            {
                'name': 'Rimi',
                'count': 0,
                'products': [],
                'status': '❌ Ei tööta (IP blokeeritud)'
            },
            {
                'name': 'Selver',
                'count': 0,
                'products': [],
                'status': '❌ Cloudflare blokeerib'
            }
        ],
        'total_count': len(coop),
        'note': 'Coop töötab. Teised poed on Renderis blokeeritud.'
    }
    
    response = jsonify(results)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({
        'error': 'Method not allowed',
        'allowed_methods': ['GET', 'POST', 'OPTIONS']
    }), 405

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
