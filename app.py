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
# PROXY FUNKTSIOONID
# ----------------------------
def get_proxy_list():
    """Tagastab töötavate proxyde nimekirja"""
    return [
        "http://94.131.38.176:8080",
        "http://195.123.225.121:8080",
        "http://185.217.131.67:8080",
        "http://51.15.127.183:3128",
        "http://94.130.157.233:3128",
        "http://46.105.196.194:3128",
        "http://163.172.151.122:3128",
        "http://94.130.182.38:3128",
        "http://163.172.222.133:3128",
        "http://51.15.76.89:3128",
    ]

def search_with_proxy(url, headers=None, timeout=15):
    """Teeb päringu proxy kaudu"""
    proxies = get_proxy_list()
    random.shuffle(proxies)
    
    for proxy in proxies:
        try:
            proxy_dict = {"http": proxy, "https": proxy}
            response = requests.get(
                url,
                headers=headers or {},
                proxies=proxy_dict,
                timeout=timeout
            )
            if response.status_code == 200:
                print(f"✅ Proxy töötab: {proxy}")
                return response
        except Exception as e:
            print(f"❌ Proxy ei tööta: {proxy}")
            continue
    
    print("⚠️ Ükski proxy ei tööta, proovin ilma proxyta...")
    try:
        return requests.get(url, headers=headers or {}, timeout=timeout)
    except:
        return None

# ----------------------------
# COOP (TÖÖTAB ILMA PROXYTA)
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
# PRISMA PROXYGA
# ----------------------------
def search_prisma(query: str) -> list:
    try:
        url = f"https://www.prisma.ee/et/otsing?q={quote_plus(query)}"
        response = search_with_proxy(url, HEADERS)
        
        if not response or response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        items = soup.select(".product-item, .product, .product-tile, [data-product-id]")
        if not items:
            items = soup.select("a[href*='/toode/'], a[href*='/product/']")
        
        for item in items[:20]:
            try:
                name = None
                for selector in [".product-name", ".name", ".title", "h2", "h3"]:
                    name_elem = item.select_one(selector)
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
                for selector in [".price", ".product-price", ".price-value", ".amount"]:
                    price_elem = item.select_one(selector)
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
                            url = f"https://www.prisma.ee{href}"
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url,
                    'store': 'Prisma'
                })
                
            except Exception as e:
                continue
        
        return products
        
    except Exception as e:
        print(f"Prisma viga: {e}")
        return []

# ----------------------------
# MAXIMA PROXYGA
# ----------------------------
def search_maxima(query: str) -> list:
    try:
        url = f"https://www.maxima.ee/et/search?q={quote_plus(query)}"
        response = search_with_proxy(url, HEADERS)
        
        if not response or response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        items = soup.select(".product-item, .product, .product-card, [data-product-id]")
        if not items:
            items = soup.select("a[href*='/toode/'], a[href*='/product/']")
        
        for item in items[:20]:
            try:
                name = None
                for selector in [".product-name", ".name", ".title", "h2", "h3"]:
                    name_elem = item.select_one(selector)
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
                for selector in [".price", ".product-price", ".price-value", ".amount"]:
                    price_elem = item.select_one(selector)
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
        
        return products
        
    except Exception as e:
        print(f"Maxima viga: {e}")
        return []

# ----------------------------
# RIMI PROXYGA
# ----------------------------
def search_rimi(query: str) -> list:
    try:
        url = f"https://www.rimi.ee/api/products?search={quote_plus(query)}&limit=20"
        headers = {
            **HEADERS,
            "Accept": "application/json",
        }
        response = search_with_proxy(url, headers)
        
        if not response or response.status_code != 200:
            return []
        
        data = response.json()
        products = []
        
        items = []
        if isinstance(data, dict):
            items = data.get('products', data.get('data', data.get('items', [])))
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
                elif 'prices' in item and isinstance(item['prices'], dict):
                    price = item['prices'].get('price') or item['prices'].get('final_price')
                
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
        
        return products
        
    except Exception as e:
        print(f"Rimi viga: {e}")
        return []

# ----------------------------
# SELVER - PROOVIB AGA TÕENÄOLISELT EI TÖÖTA
# ----------------------------
def search_selver(query: str) -> list:
    try:
        url = f"https://www.selver.ee/search?q={quote_plus(query)}"
        response = search_with_proxy(url, HEADERS)
        
        if not response or response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        items = soup.select("[data-product-id], .product-item, .product-tile")
        
        for item in items[:20]:
            try:
                name = None
                for selector in [".product-name", ".name", ".product-title", "h2", "h3"]:
                    name_elem = item.select_one(selector)
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
                for selector in [".price", ".product-price", ".price-value"]:
                    price_elem = item.select_one(selector)
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
                            url = f"https://www.selver.ee{href}"
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url,
                    'store': 'Selver'
                })
                
            except Exception as e:
                continue
        
        return products
        
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
        'products': coop,
        'working': True
    })
    results['total_count'] += len(coop)
    
    # Prisma - proxyga
    prisma = search_prisma(q)
    results['stores'].append({
        'name': 'Prisma',
        'count': len(prisma),
        'products': prisma,
        'working': len(prisma) > 0
    })
    results['total_count'] += len(prisma)
    
    # Maxima - proxyga
    maxima = search_maxima(q)
    results['stores'].append({
        'name': 'Maxima',
        'count': len(maxima),
        'products': maxima,
        'working': len(maxima) > 0
    })
    results['total_count'] += len(maxima)
    
    # Rimi - proxyga
    rimi = search_rimi(q)
    results['stores'].append({
        'name': 'Rimi',
        'count': len(rimi),
        'products': rimi,
        'working': len(rimi) > 0
    })
    results['total_count'] += len(rimi)
    
    # Selver - proovib
    selver = search_selver(q)
    results['stores'].append({
        'name': 'Selver',
        'count': len(selver),
        'products': selver,
        'working': len(selver) > 0
    })
    results['total_count'] += len(selver)
    
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

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
