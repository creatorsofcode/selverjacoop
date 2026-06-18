import os
import re
import json
import time
from urllib.parse import quote_plus, urljoin
from flask import Flask, jsonify, request, render_template, send_from_directory
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

app = Flask(__name__)

# ----------------------------
# KONFIGURATSIOON
# ----------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}

PRICE_RE = re.compile(r"(\d+[.,]\d{2})\s*€?")

# ----------------------------
# SELVER SKRAPER (TÄIELIKULT PARANDATUD)
# ----------------------------
class SelverScraper:
    """Selver.ee skraper API ja HTML tugiga"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.cookies.set('language', 'et')
        self.products_cache = {}
        self.last_cache_update = 0
    
    def search(self, query: str, max_results: int = 20) -> List[Dict]:
        """Põhiline otsingumeetod"""
        print(f"🔍 Otsin Selverist: {query}")
        
        # Proovi API kaudu
        api_results = self._search_via_api(query, max_results)
        if api_results and len(api_results) > 0:
            print(f"✅ API-st leitud {len(api_results)} toodet")
            return api_results
        
        # Kui API ei tööta, proovi HTML
        html_results = self._search_via_html(query, max_results)
        if html_results and len(html_results) > 0:
            print(f"✅ HTML-ist leitud {len(html_results)} toodet")
            return html_results
        
        # Kui midagi ei leitud
        return [{"error": "Tooteid ei leitud"}]
    
    def _search_via_api(self, query: str, max_results: int) -> List[Dict]:
        """Otsi Selveri API kaudu"""
        try:
            # Proovi erinevaid API endpoint'e
            api_endpoints = [
                f"https://www.selver.ee/rest/V1/search?q={quote_plus(query)}",
                f"https://www.selver.ee/api/search?q={quote_plus(query)}",
                f"https://www.selver.ee/graphql?query={{products(search:\"{query}\"){{id,name,price,url}}}}"
            ]
            
            for api_url in api_endpoints:
                try:
                    headers = {
                        **HEADERS,
                        "Accept": "application/json",
                        "X-Requested-With": "XMLHttpRequest"
                    }
                    
                    response = self.session.get(api_url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            products = self._parse_api_response(data, max_results)
                            if products:
                                return products
                        except:
                            continue
                except:
                    continue
            
            # Proovi Coop API stiilis endpointi
            try:
                url = "https://www.selver.ee/wp-json/wc/store/v1/products"
                response = self.session.get(url, params={"search": query, "per_page": max_results}, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return self._parse_api_response(data, max_results)
            except:
                pass
            
            return []
            
        except Exception as e:
            print(f"⚠️ API viga: {e}")
            return []
    
    def _search_via_html(self, query: str, max_results: int) -> List[Dict]:
        """Otsi HTML-i kaudu"""
        try:
            # 1. Külasta avalehte
            self.session.get("https://www.selver.ee", timeout=10)
            
            # 2. Tee otsing
            url = f"https://www.selver.ee/search?q={quote_plus(query)}"
            response = self.session.get(url, timeout=15)
            
            if response.status_code != 200:
                return []
            
            html = response.text
            
            # Kontrolli blokeeringut
            if "cloudflare" in html.lower() or "captcha" in html.lower() or len(html) < 3000:
                return []
            
            soup = BeautifulSoup(html, "html.parser")
            products = []
            seen_names = set()
            
            # Leia tooted erinevate selektoritega
            product_elements = self._find_product_elements(soup)
            
            for element in product_elements[:max_results]:
                try:
                    # Toote nimi
                    name = self._extract_name(element)
                    if not name or len(name) < 3 or name.lower() in seen_names:
                        continue
                    seen_names.add(name.lower())
                    
                    # Toote hind
                    price = self._extract_price(element)
                    
                    # Toote URL
                    url = self._extract_url(element)
                    
                    # Toote ID
                    product_id = self._extract_product_id(element)
                    
                    products.append({
                        "name": name[:200],
                        "price_eur": price,
                        "url": url,
                        "product_id": product_id,
                        "store": "Selver"
                    })
                except Exception as e:
                    continue
            
            return products
            
        except Exception as e:
            print(f"⚠️ HTML viga: {e}")
            return []
    
    def _find_product_elements(self, soup) -> List:
        """Leia toote elemendid"""
        selectors = [
            "[data-product-id]",
            ".product-item",
            ".product-tile",
            ".product-list__item",
            "li.product",
            ".search-results .item",
            "article.product",
            ".product-card",
            ".product-box",
            ".product-list-item",
            ".product-tile-item"
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                print(f"  📍 Selektor '{selector}' leidis {len(elements)} elementi")
                return elements
        
        # Proovi linke
        links = soup.select("a[href*='/toode/'], a[href*='/product/']")
        if links:
            print(f"  📍 Linkide selektor leidis {len(links)} elementi")
            return links
        
        return []
    
    def _extract_name(self, element) -> Optional[str]:
        """Tõmba toote nimi"""
        name_selectors = [
            ".product-name",
            ".name",
            ".product-title",
            "[data-testid='product-name']",
            ".product-name a",
            ".product-title a",
            ".title",
            "h2",
            "h3",
            "h4"
        ]
        
        for selector in name_selectors:
            name_elem = element.select_one(selector)
            if name_elem:
                name = name_elem.get_text(" ", strip=True)
                if name and len(name) > 2:
                    return name
        
        # Kui on link, võta linkide tekst
        link = element.select_one("a[href]")
        if link:
            name = link.get_text(" ", strip=True)
            if name and len(name) > 2:
                return name
        
        # Kogu tekst
        text = element.get_text(" ", strip=True)
        if text and len(text) > 2:
            # Eemalda hind
            parts = re.split(r'\d+[.,]\d{2}\s*€', text)
            if parts:
                return parts[0].strip()
        
        return None
    
    def _extract_price(self, element) -> Optional[float]:
        """Tõmba toote hind"""
        price_selectors = [
            ".price",
            ".product-price",
            ".price span",
            ".price-value",
            ".final-price",
            "[data-testid='product-price']",
            ".amount",
            ".discounted-price",
            ".current-price",
            ".product-price__price",
            ".price-wrapper",
            ".product-price-wrapper"
        ]
        
        # 1. Otsi hinnaselektoritega
        for selector in price_selectors:
            price_elem = element.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(" ", strip=True)
                match = PRICE_RE.search(price_text)
                if match:
                    try:
                        return float(match.group(1).replace(",", "."))
                    except:
                        pass
        
        # 2. Otsi kogu tekstist
        full_text = element.get_text(" ", strip=True)
        matches = PRICE_RE.findall(full_text)
        if matches:
            try:
                return float(matches[0].replace(",", "."))
            except:
                pass
        
        return None
    
    def _extract_url(self, element) -> str:
        """Tõmba toote URL"""
        link = element.select_one("a[href]")
        if link:
            href = link.get("href", "")
            if href:
                if href.startswith("http"):
                    return href
                else:
                    return urljoin("https://www.selver.ee", href)
        return ""
    
    def _extract_product_id(self, element) -> Optional[str]:
        """Tõmba toote ID"""
        # 1. Otsi atribuutidest
        id_attrs = ['data-product-id', 'data-id', 'data-sku', 'id']
        for attr in id_attrs:
            product_id = element.get(attr)
            if product_id:
                return product_id
        
        # 2. Otsi URList
        link = element.select_one("a[href]")
        if link:
            href = link.get('href', '')
            match = re.search(r'/(?:toode|product)/(\d+)', href)
            if match:
                return match.group(1)
        
        return None
    
    def _parse_api_response(self, data: dict, max_results: int) -> List[Dict]:
        """Parsime API vastust"""
        products = []
        
        # Proovi erinevaid struktuure
        possible_keys = ['items', 'data', 'results', 'products', 'hits', 'product']
        
        items = []
        for key in possible_keys:
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        
        if not items and isinstance(data, list):
            items = data
        
        if not items and isinstance(data, dict):
            # Proovi võtmeid
            for key, value in data.items():
                if isinstance(value, list) and len(value) > 0:
                    items = value
                    break
        
        for item in items[:max_results]:
            try:
                if not isinstance(item, dict):
                    continue
                
                # Nimi
                name = item.get('name') or item.get('title') or item.get('product_name')
                if not name:
                    continue
                
                # Hind
                price = None
                if 'price' in item:
                    price = item['price']
                elif 'prices' in item:
                    price_data = item['prices']
                    if isinstance(price_data, dict):
                        price = price_data.get('price') or price_data.get('final_price') or price_data.get('regular_price')
                elif 'price_eur' in item:
                    price = item['price_eur']
                
                # Teisenda hind
                if price is not None:
                    try:
                        if isinstance(price, str):
                            price = float(price.replace(',', '.'))
                        elif isinstance(price, (int, float)):
                            # Kui hind on sentides (nt 1990)
                            if price > 1000 and isinstance(price, int):
                                price = price / 100
                    except:
                        price = None
                
                # URL
                url = item.get('url') or item.get('permalink') or item.get('link')
                if url and not url.startswith('http'):
                    url = urljoin('https://www.selver.ee', url)
                
                # ID
                product_id = item.get('id') or item.get('sku') or item.get('product_id')
                
                products.append({
                    'name': name[:200],
                    'price_eur': price,
                    'url': url or '',
                    'product_id': product_id,
                    'store': 'Selver'
                })
            except:
                continue
        
        return products


# ----------------------------
# COOP SCRAPER (TÖÖTAB)
# ----------------------------
def search_coop(query: str) -> List[Dict]:
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
                
                url = item.get('permalink', '')
                product_id = item.get('id')
                
                products.append({
                    'name': name[:200],
                    'price_eur': price_eur,
                    'url': url,
                    'product_id': product_id,
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

# Loo skraper
selver_scraper = SelverScraper()

@app.route('/')
def home():
    """Avaleht"""
    return render_template('index.html')

@app.route('/ping')
def ping():
    """Lihtne health check"""
    return 'OK'

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        'status': 'ok',
        'timestamp': time.time()
    })

@app.route('/api/search', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/search', methods=['GET', 'POST', 'OPTIONS'])
def search():
    """Otsing API"""
    # CORS preflight
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        return response
    
    # Võta query
    if request.method == 'POST':
        if request.is_json:
            q = request.json.get('q', 'sai')
        else:
            q = request.form.get('q', 'sai')
    else:
        q = request.args.get('q', 'sai')
    
    # Otsi
    print(f"📡 Päring: {q}")
    
    selver_results = selver_scraper.search(q)
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

@app.route('/api/stores')
def stores():
    """Tagasta kõik poed"""
    return jsonify({
        'stores': ['Selver', 'Coop'],
        'status': 'active'
    })

# ----------------------------
# VEATEATED
# ----------------------------
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

# ----------------------------
# KÄIVITUS
# ----------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
