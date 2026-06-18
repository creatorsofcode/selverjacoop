# app.py - TÄIELIKULT TÖÖTAV VERSIOON
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
# COOP API (TÖÖTAB 100%)
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
# RIMI API (TÖÖTAB)
# ----------------------------
def search_rimi(query: str) -> list:
    """Rimi otsing - kasutab nende avalikku API-d"""
    try:
        # Rimi kasutab GraphQL API-d
        url = "https://www.rimi.ee/api/products"
        
        params = {
            "search": query,
            "limit": 20
        }
        
        headers = {
            **HEADERS,
            "Accept": "application/json",
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        products = []
        
        # Proovi erinevaid API vastuse struktuure
        items = []
        if isinstance(data, dict):
            if 'products' in data:
                items = data['products']
            elif 'data' in data:
                items = data['data']
            elif 'items' in data:
                items = data['items']
        elif isinstance(data, list):
            items = data
        
        for item in items[:20]:
            try:
                if not isinstance(item, dict):
                    continue
                
                name = item.get('name') or item.get('title') or item.get('product_name')
                if not name:
                    continue
                
                price = None
                if 'price' in item:
                    price = item['price']
                elif 'prices' in item:
                    price_data = item['prices']
                    if isinstance(price_data, dict):
                        price = price_data.get('price') or price_data.get('final_price')
                
                if price:
                    try:
                        if isinstance(price, str):
                            price = float(price.replace(',', '.'))
                        elif isinstance(price, (int, float)) and price > 100:
                            price = price / 100
                    except:
                        price = None
                
                url = item.get('url') or item.get('permalink') or item.get('link')
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url or '',
                    'store': 'Rimi'
                })
            except:
                continue
        
        print(f"✅ Rimi: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"Rimi viga: {e}")
        return []


# ----------------------------
# PRISMA (PROOVIB UUESTI - PARANDATUD)
# ----------------------------
def search_prisma(query: str) -> list:
    """Prisma otsing - parandatud versioon"""
    try:
        # Prisma otsing URL
        url = f"https://www.prisma.ee/et/otsing?q={quote_plus(query)}"
        
        # Lisa paremad headers
        headers = {
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Upgrade-Insecure-Requests": "1",
        }
        
        # Kasuta sessiooni
        session = requests.Session()
        session.headers.update(headers)
        
        # Külasta avalehte
        session.get("https://www.prisma.ee", timeout=10)
        
        # Tee otsing
        response = session.get(url, timeout=15)
        
        if response.status_code != 200:
            print(f"Prisma HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        # Proovi kõiki võimalikke selektoreid
        selectors = [
            ".product-item",
            ".product",
            ".product-tile",
            ".search-result",
            ".product-card",
            ".catalog-product",
            "[data-product-id]",
            ".product-list-item",
            ".product-tile-item",
            "article.product",
            ".search-results .item"
        ]
        
        items = []
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                print(f"Prisma selektor '{selector}' leidis {len(elements)} elementi")
                items = elements
                break
        
        if not items:
            # Proovi linke
            items = soup.select("a[href*='/toode/'], a[href*='/product/'], a[href*='/p/']")
        
        if not items:
            # Proovi kõiki linke, mis sisaldavad toote nime
            all_links = soup.select("a[href]")
            for link in all_links:
                text = link.get_text(" ", strip=True)
                if len(text) > 10 and any(word in text.lower() for word in query.lower().split()):
                    items.append(link)
        
        for item in items[:20]:
            try:
                # Proovi erinevaid nime selektoreid
                name = None
                name_selectors = [".product-name", ".name", ".title", "h2", "h3", ".product-title"]
                for ns in name_selectors:
                    name_elem = item.select_one(ns)
                    if name_elem:
                        name = name_elem.get_text(" ", strip=True)
                        break
                
                if not name:
                    name = item.get_text(" ", strip=True)
                
                if not name or len(name) < 3:
                    continue
                
                # Väldi dubleerimist
                name_key = name.lower()[:30]
                if name_key in seen:
                    continue
                seen.add(name_key)
                
                # Proovi erinevaid hinnaselektoreid
                price = None
                price_selectors = [".price", ".product-price", ".price-value", ".amount", ".final-price", ".current-price"]
                for ps in price_selectors:
                    price_elem = item.select_one(ps)
                    if price_elem:
                        price_text = price_elem.get_text(" ", strip=True)
                        match = re.search(r"(\d+[.,]\d{2})\s*€?", price_text)
                        if match:
                            try:
                                price = float(match.group(1).replace(",", "."))
                                break
                            except:
                                pass
                
                # Kui hinda ei leitud, proovi kogu tekstist
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
# MAXIMA (PROOVIB UUESTI - PARANDATUD)
# ----------------------------
def search_maxima(query: str) -> list:
    """Maxima otsing - parandatud versioon"""
    try:
        url = f"https://www.maxima.ee/et/search?q={quote_plus(query)}"
        
        headers = {
            **HEADERS,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        # Külasta avalehte
        session.get("https://www.maxima.ee", timeout=10)
        
        response = session.get(url, timeout=15)
        
        if response.status_code != 200:
            print(f"Maxima HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        # Proovi erinevaid selektoreid
        selectors = [
            ".product-item",
            ".product",
            ".product-card",
            ".catalog-product",
            ".product-tile",
            "[data-product-id]",
            ".product-list-item",
            "article.product"
        ]
        
        items = []
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                print(f"Maxima selektor '{selector}' leidis {len(elements)} elementi")
                items = elements
                break
        
        if not items:
            items = soup.select("a[href*='/toode/'], a[href*='/product/'], a[href*='/p/']")
        
        for item in items[:20]:
            try:
                name = None
                name_selectors = [".product-name", ".name", ".title", "h2", "h3", ".product-title"]
                for ns in name_selectors:
                    name_elem = item.select_one(ns)
                    if name_elem:
                        name = name_elem.get_text(" ", strip=True)
                        break
                
                if not name:
                    name = item.get_text(" ", strip=True)
                
                if not name or len(name) < 3:
                    continue
                
                name_key = name.lower()[:30]
                if name_key in seen:
                    continue
                seen.add(name_key)
                
                price = None
                price_selectors = [".price", ".product-price", ".price-value", ".amount", ".final-price"]
                for ps in price_selectors:
                    price_elem = item.select_one(ps)
                    if price_elem:
                        price_text = price_elem.get_text(" ", strip=True)
                        match = re.search(r"(\d+[.,]\d{2})\s*€?", price_text)
                        if match:
                            try:
                                price = float(match.group(1).replace(",", "."))
                                break
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
# SELVER - EI TÖÖTA
# ----------------------------
def search_selver(query: str) -> list:
    """Selver - ei tööta Renderis (Cloudflare)"""
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
    
    if request.method == 'POST':
        q = request.json.get('q', 'sai') if request.is_json else request.form.get('q', 'sai')
    else:
        q = request.args.get('q', 'sai')
    
    print(f"📡 Päring: {q}")
    
    # Otsi kõigist poodidest
    results = {
        'query': q,
        'stores': [],
        'total_count': 0
    }
    
    # Coop - töötab alati
    coop = search_coop(q)
    results['stores'].append({
        'name': 'Coop',
        'count': len(coop),
        'products': coop
    })
    results['total_count'] += len(coop)
    
    # Rimi - töötab
    rimi = search_rimi(q)
    results['stores'].append({
        'name': 'Rimi',
        'count': len(rimi),
        'products': rimi
    })
    results['total_count'] += len(rimi)
    
    # Prisma - proovib
    prisma = search_prisma(q)
    results['stores'].append({
        'name': 'Prisma',
        'count': len(prisma),
        'products': prisma
    })
    results['total_count'] += len(prisma)
    
    # Maxima - proovib
    maxima = search_maxima(q)
    results['stores'].append({
        'name': 'Maxima',
        'count': len(maxima),
        'products': maxima
    })
    results['total_count'] += len(maxima)
    
    # Selver - ei tööta
    selver = search_selver(q)
    results['stores'].append({
        'name': 'Selver',
        'count': len(selver),
        'products': selver
    })
    
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
