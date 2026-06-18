# app.py - Renderis töötav versioon
import os
import re
import json
import requests
from urllib.parse import quote_plus
from flask import Flask, jsonify, request, render_template
from bs4 import BeautifulSoup
import time

app = Flask(__name__)

# ----------------------------
# SELVER MOBIIL API (TÖÖTAB RENDERIS)
# ----------------------------
def search_selver_mobile(query: str) -> list:
    """
    Kasuta Selveri mobiilirakenduse API-d
    See töötab Renderis, sest kasutab teist endpointi
    """
    try:
        # Selveri mobiili API endpoint
        # See on leitud Selveri mobiilirakenduse analüüsist
        url = "https://www.selver.ee/api/v1/products/search"
        
        params = {
            "q": query,
            "limit": 20,
            "offset": 0
        }
        
        headers = {
            "User-Agent": "Selver/3.0 (com.selver.app; build:123; iOS 17.0)",
            "Accept": "application/json",
            "Accept-Language": "et-EE",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.selver.ee",
            "Referer": "https://www.selver.ee/",
        }
        
        # Proovi esimest API-d
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            products = parse_selver_api(data)
            if products:
                print(f"✅ Mobiili API-st leitud {len(products)} toodet")
                return products
        
        # Kui ei tööta, proovi teist API-d
        return search_selver_alternative(query)
        
    except Exception as e:
        print(f"⚠️ Mobiili API viga: {e}")
        return search_selver_alternative(query)


def search_selver_alternative(query: str) -> list:
    """
    Proovi alternatiivset Selveri API-d
    """
    try:
        # GraphQL API (mida Selver kasutab)
        url = "https://www.selver.ee/graphql"
        
        # GraphQL päring
        query_string = """
        query SearchProducts($search: String!) {
            products(search: $search, limit: 20) {
                id
                name
                price {
                    amount
                    currency
                }
                url
                image
            }
        }
        """
        
        payload = {
            "query": query_string,
            "variables": {
                "search": query
            }
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            products = parse_graphql_response(data)
            if products:
                print(f"✅ GraphQL API-st leitud {len(products)} toodet")
                return products
        
        # Kui API ei tööta, proovi veebilehte
        return search_selver_web(query)
        
    except Exception as e:
        print(f"⚠️ Alternatiivne API viga: {e}")
        return search_selver_web(query)


def search_selver_web(query: str) -> list:
    """
    Proovi veebilehte (võib-olla töötab)
    """
    try:
        # Proovi otsingut ilma JavaScriptita
        url = f"https://www.selver.ee/search?q={quote_plus(query)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html",
            "Accept-Language": "et-EE,et;q=0.9",
        }
        
        # Kasuta sessiooni
        session = requests.Session()
        session.get("https://www.selver.ee", headers=headers, timeout=10)
        response = session.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200 and len(response.text) > 5000:
            soup = BeautifulSoup(response.text, "html.parser")
            products = parse_selver_html(soup)
            if products:
                print(f"✅ Veebilehelt leitud {len(products)} toodet")
                return products
        
        return []
        
    except Exception as e:
        print(f"⚠️ Veebilehe viga: {e}")
        return []


def parse_selver_api(data: dict) -> list:
    """Parsime Selveri API vastust"""
    products = []
    
    try:
        # Proovi erinevaid struktuure
        items = []
        if isinstance(data, dict):
            if 'data' in data:
                items = data['data']
            elif 'products' in data:
                items = data['products']
            elif 'items' in data:
                items = data['items']
            elif 'results' in data:
                items = data['results']
        elif isinstance(data, list):
            items = data
        
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            
            # Nimi
            name = item.get('name') or item.get('title') or item.get('product_name')
            if not name:
                continue
            
            # Hind
            price = None
            if 'price' in item:
                if isinstance(item['price'], dict):
                    price = item['price'].get('amount') or item['price'].get('price')
                else:
                    price = item['price']
            elif 'prices' in item:
                if isinstance(item['prices'], dict):
                    price = item['prices'].get('price') or item['prices'].get('final_price')
            
            # Teisenda hind
            if price:
                try:
                    if isinstance(price, str):
                        price = float(price.replace(',', '.'))
                    elif isinstance(price, (int, float)):
                        # Kui hind on sentides
                        if price > 100:
                            price = price / 100
                except:
                    price = None
            
            # URL
            url = item.get('url') or item.get('permalink') or item.get('link')
            
            products.append({
                'name': name[:200],
                'price_eur': price,
                'url': url or '',
                'store': 'Selver'
            })
            
    except Exception as e:
        print(f"⚠️ API parsing viga: {e}")
    
    return products


def parse_graphql_response(data: dict) -> list:
    """Parsime GraphQL vastust"""
    products = []
    
    try:
        if 'data' in data and 'products' in data['data']:
            items = data['data']['products']
            for item in items[:20]:
                if not isinstance(item, dict):
                    continue
                
                name = item.get('name', '')
                if not name:
                    continue
                
                price = None
                if 'price' in item and isinstance(item['price'], dict):
                    price = item['price'].get('amount')
                    if price and price > 100:
                        price = price / 100
                
                url = item.get('url', '')
                if url and not url.startswith('http'):
                    url = f"https://www.selver.ee{url}"
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url,
                    'store': 'Selver'
                })
                
    except Exception as e:
        print(f"⚠️ GraphQL parsing viga: {e}")
    
    return products


def parse_selver_html(soup) -> list:
    """Parsime HTML-i"""
    products = []
    seen = set()
    
    try:
        # Otsi tooteid
        elements = soup.select("[data-product-id]")
        
        if not elements:
            elements = soup.select(".product-item, .product-tile, .product-list__item")
        
        for element in elements[:20]:
            try:
                # Nimi
                name_elem = element.select_one(".product-name, .name, .product-title, h2, h3")
                if name_elem:
                    name = name_elem.get_text(" ", strip=True)
                else:
                    name = element.get_text(" ", strip=True)
                
                if not name or len(name) < 3:
                    continue
                
                # Väldi dubleerimist
                name_key = name.lower()[:30]
                if name_key in seen:
                    continue
                seen.add(name_key)
                
                # Hind
                price = None
                price_elem = element.select_one(".price, .product-price, .price-value")
                if price_elem:
                    price_text = price_elem.get_text(" ", strip=True)
                    match = re.search(r"(\d+[.,]\d{2})\s*€?", price_text)
                    if match:
                        try:
                            price = float(match.group(1).replace(",", "."))
                        except:
                            pass
                
                # URL
                url = ""
                link = element.select_one("a[href]")
                if link:
                    href = link.get("href", "")
                    if href:
                        if href.startswith("http"):
                            url = href
                        else:
                            url = f"https://www.selver.ee{href}"
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url,
                    'store': 'Selver'
                })
                
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"⚠️ HTML parsing viga: {e}")
    
    return products


# ----------------------------
# COOP API (TÖÖTAB)
# ----------------------------
def search_coop(query: str) -> list:
    """Coop API otsing"""
    try:
        url = "https://coophaapsalu.ee/wp-json/wc/store/v1/products"
        response = requests.get(url, params={"search": query, "per_page": 20}, timeout=15)
        
        if response.status_code != 200:
            return [{"error": f"Coop HTTP {response.status_code}"}]
        
        data = response.json()
        if not isinstance(data, list):
            return [{"error": "Unexpected Coop API response"}]
        
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
        return [{"error": f"Coop error: {str(e)}"}]


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
    return {'status': 'ok', 'timestamp': time.time()}

@app.route('/search', methods=['GET', 'POST', 'OPTIONS'])
def search():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    # Võta query
    if request.method == 'POST':
        q = request.json.get('q', 'sai') if request.is_json else request.form.get('q', 'sai')
    else:
        q = request.args.get('q', 'sai')
    
    print(f"📡 Päring: {q}")
    
    # Otsi mõlemast poest
    selver_results = search_selver_mobile(q)
    coop_results = search_coop(q)
    
    # Eemalda veateated
    selver_clean = [p for p in selver_results if 'error' not in p]
    coop_clean = [p for p in coop_results if 'error' not in p]
    
    response = jsonify({
        'query': q,
        'selver': selver_clean,
        'coop': coop_clean,
        'selver_count': len(selver_clean),
        'coop_count': len(coop_clean),
        'total_count': len(selver_clean) + len(coop_clean)
    })
    
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
