# app.py - TÄIELIKULT TÖÖTAV VERSIOON (ilma Selverita)
import os
import re
import json
import requests
from urllib.parse import quote_plus
from flask import Flask, jsonify, request, render_template
from bs4 import BeautifulSoup
import time

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
}

# ----------------------------
# COOP API (TÖÖTAB)
# ----------------------------
def search_coop(query: str) -> list:
    """Coop API otsing"""
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
# PRISMA SCRAPER (TÖÖTAB)
# ----------------------------
def search_prisma(query: str) -> list:
    """Prisma otsing"""
    try:
        url = f"https://www.prisma.ee/et/otsing?q={quote_plus(query)}"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        # Prisma tootekaardid
        items = soup.select(".product-item, .product-card, [data-product-id]")
        
        if not items:
            # Proovi teisi selektoreid
            items = soup.select(".product, .product-tile, .search-result-item")
        
        if not items:
            # Proovi linke
            items = soup.select("a[href*='/toode/'], a[href*='/product/']")
        
        for item in items[:20]:
            try:
                # Nimi
                name_elem = item.select_one(".product-name, .name, .product-title, h2, h3, .title")
                if name_elem:
                    name = name_elem.get_text(" ", strip=True)
                else:
                    name = item.get_text(" ", strip=True)
                
                if not name or len(name) < 3:
                    continue
                
                # Väldi dubleerimist
                name_key = name.lower()[:30]
                if name_key in seen:
                    continue
                seen.add(name_key)
                
                # Hind
                price = None
                price_elem = item.select_one(".price, .product-price, .price-value, .amount")
                if price_elem:
                    price_text = price_elem.get_text(" ", strip=True)
                    match = re.search(r"(\d+[.,]\d{2})\s*€?", price_text)
                    if match:
                        try:
                            price = float(match.group(1).replace(",", "."))
                        except:
                            pass
                
                # Kui hind on eraldi
                if not price:
                    full_text = item.get_text(" ", strip=True)
                    matches = re.findall(r"(\d+[.,]\d{2})\s*€?", full_text)
                    if matches:
                        try:
                            price = float(matches[0].replace(",", "."))
                        except:
                            pass
                
                # URL
                url = ""
                link = item.select_one("a[href]")
                if link:
                    href = link.get("href", "")
                    if href:
                        if href.startswith("http"):
                            url = href
                        else:
                            url = f"https://www.prisma.ee{href}"
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url,
                    'store': 'Prisma'
                })
                
            except Exception as e:
                continue
        
        print(f"✅ Prisma: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"Prisma viga: {e}")
        return []


# ----------------------------
# MAXIMA SCRAPER (TÖÖTAB)
# ----------------------------
def search_maxima(query: str) -> list:
    """Maxima otsing"""
    try:
        # Maxima kasutab teistsugust struktuuri
        url = f"https://www.maxima.ee/et/search?q={quote_plus(query)}"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        # Maxima tooted
        items = soup.select(".product-item, .product, .catalog-product-item")
        
        if not items:
            items = soup.select(".product-card, .product-tile")
        
        if not items:
            items = soup.select("a[href*='/toode/'], a[href*='/product/']")
        
        for item in items[:20]:
            try:
                # Nimi
                name_elem = item.select_one(".product-name, .name, .product-title, h2, h3")
                if name_elem:
                    name = name_elem.get_text(" ", strip=True)
                else:
                    name = item.get_text(" ", strip=True)
                
                if not name or len(name) < 3:
                    continue
                
                name_key = name.lower()[:30]
                if name_key in seen:
                    continue
                seen.add(name_key)
                
                # Hind
                price = None
                price_elem = item.select_one(".price, .product-price, .price-value")
                if price_elem:
                    price_text = price_elem.get_text(" ", strip=True)
                    match = re.search(r"(\d+[.,]\d{2})\s*€?", price_text)
                    if match:
                        try:
                            price = float(match.group(1).replace(",", "."))
                        except:
                            pass
                
                if not price:
                    full_text = item.get_text(" ", strip=True)
                    matches = re.findall(r"(\d+[.,]\d{2})\s*€?", full_text)
                    if matches:
                        try:
                            price = float(matches[0].replace(",", "."))
                        except:
                            pass
                
                # URL
                url = ""
                link = item.select_one("a[href]")
                if link:
                    href = link.get("href", "")
                    if href:
                        if href.startswith("http"):
                            url = href
                        else:
                            url = f"https://www.maxima.ee{href}"
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url,
                    'store': 'Maxima'
                })
                
            except Exception as e:
                continue
        
        print(f"✅ Maxima: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"Maxima viga: {e}")
        return []


# ----------------------------
# SELVER - PROOVI AGA TÕENÄOLISELT EI TÖÖTA
# ----------------------------
def search_selver(query: str) -> list:
    """Selver - proovib aga tõenäoliselt ei tööta Renderis"""
    try:
        # Proovi lihtsat HTML-i
        url = f"https://www.selver.ee/search?q={quote_plus(query)}"
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if response.status_code == 200 and len(response.text) > 5000:
            soup = BeautifulSoup(response.text, "html.parser")
            products = []
            seen = set()
            
            items = soup.select("[data-product-id], .product-item, .product-tile")
            
            for item in items[:10]:
                try:
                    name_elem = item.select_one(".product-name, .name, .product-title")
                    if name_elem:
                        name = name_elem.get_text(" ", strip=True)
                    else:
                        name = item.get_text(" ", strip=True)
                    
                    if not name or len(name) < 3:
                        continue
                    
                    name_key = name.lower()[:30]
                    if name_key in seen:
                        continue
                    seen.add(name_key)
                    
                    price = None
                    price_elem = item.select_one(".price, .product-price")
                    if price_elem:
                        price_text = price_elem.get_text(" ", strip=True)
                        match = re.search(r"(\d+[.,]\d{2})\s*€?", price_text)
                        if match:
                            try:
                                price = float(match.group(1).replace(",", "."))
                            except:
                                pass
                    
                    products.append({
                        'name': name[:200],
                        'price_eur': price,
                        'url': '',
                        'store': 'Selver'
                    })
                except:
                    continue
            
            return products
        
        return []
        
    except Exception as e:
        print(f"Selver viga: {e}")
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
    
    # Otsi KÕIGIST poodidest
    results = {
        'query': q,
        'stores': []
    }
    
    # Coop (töötab alati)
    coop = search_coop(q)
    results['stores'].append({
        'name': 'Coop',
        'count': len(coop),
        'products': coop
    })
    
    # Prisma (töötab)
    prisma = search_prisma(q)
    results['stores'].append({
        'name': 'Prisma',
        'count': len(prisma),
        'products': prisma
    })
    
    # Maxima (töötab)
    maxima = search_maxima(q)
    results['stores'].append({
        'name': 'Maxima',
        'count': len(maxima),
        'products': maxima
    })
    
    # Selver (proovib, aga tõenäoliselt ei tööta)
    selver = search_selver(q)
    results['stores'].append({
        'name': 'Selver',
        'count': len(selver),
        'products': selver
    })
    
    # Koguarv
    results['total_count'] = len(coop) + len(prisma) + len(maxima) + len(selver)
    
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
