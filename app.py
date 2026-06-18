import os
import re
import requests
import random
import time
from flask import Flask, jsonify, request, render_template
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# ----------------------------
# PROXY LIST (VÄRSKENDATUD)
# ----------------------------
def get_proxy_list():
    """Tagastab töötavate proxyde nimekirja - Eesti ja Soome proxyd"""
    return [
        # Eesti proxyd (kõige paremad)
        "http://37.49.224.15:3128",
        "http://5.45.126.128:8080",
        "http://85.192.61.93:7443",
        "http://85.214.204.79:80",
        
        # Soome proxyd
        "http://85.192.61.93:7443",
        "http://65.108.159.129:8081",
        "http://2.26.87.216:1080",
        "http://84.19.3.208:3128",
        
        # Saksa proxyd (töökindlad)
        "http://91.107.182.124:82",
        "http://138.124.114.42:7443",
        "http://89.169.53.40:7443",
        "http://85.192.28.62:7443",
        "http://213.165.42.185:7443",
        "http://46.249.100.124:80",
        "http://91.107.163.9:82",
        "http://194.59.204.87:9080",
        
        # Hollandi proxyd
        "http://79.137.205.130:7443",
        "http://138.124.113.102:7443",
        "http://64.188.77.26:3128",
        "http://88.210.21.224:1080",
        
        # USA proxyd (varuvariant)
        "http://207.246.234.115:4669",
        "http://72.56.238.99:9090",
        "http://209.141.46.220:9091",
        "http://198.89.96.148:808",
        "http://174.138.119.88:80",
        "http://104.239.105.25:6555",
        
        # Prantsuse proxyd
        "http://92.119.56.37:5555",
        "http://202.133.88.173:80",
        "http://37.187.74.125:80",
        "http://62.133.62.3:1082",
        "http://195.25.20.155:3128",
        
        # Briti proxyd
        "http://217.174.244.117:3129",
        "http://81.168.119.85:443",
        
        # Rootsi proxyd
        "http://62.60.149.161:3128",
    ]

def get_working_proxy(url, headers=None, timeout=15):
    """
    Proovib kõiki proxysid, kuni leiab töötava
    """
    proxies = get_proxy_list()
    random.shuffle(proxies)
    
    for proxy in proxies:
        try:
            proxy_dict = {"http": proxy, "https": proxy}
            
            # Lühike timeout, et mitte liiga kaua oodata
            response = requests.get(
                url,
                headers=headers or HEADERS,
                proxies=proxy_dict,
                timeout=timeout
            )
            
            # Kui vastus on 200 ja leht pole liiga väike
            if response.status_code == 200 and len(response.text) > 5000:
                print(f"✅ Töötav proxy: {proxy}")
                return response, proxy
                
        except Exception as e:
            print(f"❌ Proxy ei tööta: {proxy}")
            continue
    
    # Kui ükski proxy ei tööta, proovi ilma proxyta
    print("⚠️ Ükski proxy ei töötanud, proovin ilma proxyta...")
    try:
        response = requests.get(url, headers=headers or HEADERS, timeout=timeout)
        if response.status_code == 200 and len(response.text) > 5000:
            return response, None
    except:
        pass
    
    return None, None

# ----------------------------
# SELVER PROXYGA
# ----------------------------
def search_selver(query: str) -> list:
    """Selveri otsing proxydega"""
    try:
        url = f"https://www.selver.ee/search?q={quote_plus(query)}"
        print(f"🔍 Otsin Selverist: {query}")
        
        response, proxy = get_working_proxy(url)
        
        if not response:
            print("❌ Selver - ükski proxy ei töötanud")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        # Proovi erinevaid selektoreid
        items = soup.select("[data-product-id], .product-item, .product-tile, .product-list__item")
        
        if not items:
            items = soup.select("a[href*='/toode/'], a[href*='/product/']")
        
        if not items:
            # Proovi leida kõiki linke, mis sisaldavad toote nime
            all_links = soup.select("a[href]")
            for link in all_links:
                text = link.get_text(" ", strip=True)
                if len(text) > 10 and any(word in text.lower() for word in query.lower().split()):
                    items.append(link)
        
        print(f"📦 Selver: leitud {len(items)} elementi")
        
        for item in items[:20]:
            try:
                # Toote nimi
                name = None
                name_selectors = [".product-name", ".name", ".product-title", "[data-testid='product-name']", "h2", "h3", ".title"]
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
                name_key = name.lower()[:40]
                if name_key in seen:
                    continue
                seen.add(name_key)
                
                # Toote hind
                price = None
                price_selectors = [".price", ".product-price", ".price-value", ".final-price", "[data-testid='product-price']"]
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
                            url = f"https://www.selver.ee{href}"
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url,
                    'store': 'Selver'
                })
                
            except Exception as e:
                continue
        
        print(f"✅ Selver: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"❌ Selver viga: {e}")
        return []

# ----------------------------
# PRISMA PROXYGA
# ----------------------------
def search_prisma(query: str) -> list:
    """Prisma otsing proxydega"""
    try:
        url = f"https://www.prisma.ee/et/otsing?q={quote_plus(query)}"
        print(f"🔍 Otsin Prismast: {query}")
        
        response, proxy = get_working_proxy(url)
        
        if not response:
            print("❌ Prisma - ükski proxy ei töötanud")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        items = soup.select(".product-item, .product, .product-tile, .search-result, [data-product-id]")
        
        if not items:
            items = soup.select("a[href*='/toode/'], a[href*='/product/'], a[href*='/p/']")
        
        print(f"📦 Prisma: leitud {len(items)} elementi")
        
        for item in items[:20]:
            try:
                name = None
                name_selectors = [".product-name", ".name", ".title", ".product-title", "h2", "h3"]
                for ns in name_selectors:
                    name_elem = item.select_one(ns)
                    if name_elem:
                        name = name_elem.get_text(" ", strip=True)
                        break
                
                if not name:
                    name = item.get_text(" ", strip=True)
                
                if not name or len(name) < 3:
                    continue
                
                name_key = name.lower()[:40]
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
        print(f"❌ Prisma viga: {e}")
        return []

# ----------------------------
# MAXIMA PROXYGA
# ----------------------------
def search_maxima(query: str) -> list:
    """Maxima otsing proxydega"""
    try:
        url = f"https://www.maxima.ee/et/search?q={quote_plus(query)}"
        print(f"🔍 Otsin Maximast: {query}")
        
        response, proxy = get_working_proxy(url)
        
        if not response:
            print("❌ Maxima - ükski proxy ei töötanud")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        items = soup.select(".product-item, .product, .product-card, .catalog-product, [data-product-id]")
        
        if not items:
            items = soup.select("a[href*='/toode/'], a[href*='/product/'], a[href*='/p/']")
        
        print(f"📦 Maxima: leitud {len(items)} elementi")
        
        for item in items[:20]:
            try:
                name = None
                name_selectors = [".product-name", ".name", ".title", ".product-title", "h2", "h3"]
                for ns in name_selectors:
                    name_elem = item.select_one(ns)
                    if name_elem:
                        name = name_elem.get_text(" ", strip=True)
                        break
                
                if not name:
                    name = item.get_text(" ", strip=True)
                
                if not name or len(name) < 3:
                    continue
                
                name_key = name.lower()[:40]
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
        print(f"❌ Maxima viga: {e}")
        return []

# ----------------------------
# RIMI PROXYGA
# ----------------------------
def search_rimi(query: str) -> list:
    """Rimi otsing proxydega"""
    try:
        url = f"https://www.rimi.ee/api/products?search={quote_plus(query)}&limit=20"
        print(f"🔍 Otsin Rimist: {query}")
        
        headers = {**HEADERS, "Accept": "application/json"}
        response, proxy = get_working_proxy(url, headers)
        
        if not response:
            print("❌ Rimi - ükski proxy ei töötanud")
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
        
        print(f"✅ Rimi: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"❌ Rimi viga: {e}")
        return []

# ----------------------------
# COOP (TÖÖTAB ILMA PROXYTA)
# ----------------------------
def search_coop(query: str) -> list:
    """Coop API - töötab alati"""
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
    
    print(f"\n{'='*50}")
    print(f"📡 Päring: {q}")
    print('='*50)
    
    results = {
        'query': q,
        'stores': [],
        'total_count': 0
    }
    
    # Kõik poed
    stores = [
        ('Coop', search_coop),
        ('Selver', search_selver),
        ('Prisma', search_prisma),
        ('Maxima', search_maxima),
        ('Rimi', search_rimi),
    ]
    
    for name, search_func in stores:
        try:
            start_time = time.time()
            products = search_func(q)
            elapsed = time.time() - start_time
            
            results['stores'].append({
                'name': name,
                'count': len(products),
                'products': products,
                'time': f"{elapsed:.2f}s"
            })
            results['total_count'] += len(products)
            print(f"⏱️ {name}: {elapsed:.2f}s - {len(products)} toodet")
        except Exception as e:
            results['stores'].append({
                'name': name,
                'count': 0,
                'products': [],
                'error': str(e)
            })
            print(f"❌ {name} viga: {e}")
    
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
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
