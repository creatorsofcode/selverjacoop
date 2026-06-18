import re
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
from typing import List, Dict, Optional
import time

# ----------------------------
# SELVER SKRAPER (PARANDATUD)
# ----------------------------

class SelverScraper:
    """Selver.ee skraper klassina"""
    
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
        }
        self.init_session()
    
    def init_session(self):
        """Initsialiseeri sessioon avalehega"""
        try:
            self.session.get("https://www.selver.ee", headers=self.headers, timeout=10)
            print("✅ Selver sessioon loodud")
        except:
            print("⚠️ Avalehe laadimine ebaõnnestus")
    
    def extract_product_id(self, element) -> Optional[str]:
        """Tõmba toote ID elementidest"""
        # Proovi erinevaid ID atribuute
        id_attrs = ['data-product-id', 'data-id', 'data-sku', 'id']
        for attr in id_attrs:
            product_id = element.get(attr)
            if product_id:
                return product_id
        
        # Proovi URList
        link = element.select_one("a[href]")
        if link:
            href = link.get('href', '')
            # Otsi /toode/123456 või /product/123456
            match = re.search(r'/(?:toode|product)/(\d+)', href)
            if match:
                return match.group(1)
        
        return None
    
    def search_products(self, query: str, max_results: int = 20) -> List[Dict]:
        """
        Põhiline otsingumeetod
        """
        encoded_query = quote_plus(query)
        url = f"https://www.selver.ee/search?q={encoded_query}"
        
        try:
            print(f"🔍 Otsin: {query}")
            response = self.session.get(url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                return [{"error": f"HTTP {response.status_code}"}]
            
            html = response.text
            
            # Kontrolli blokeeringut
            if "cloudflare" in html.lower() or "captcha" in html.lower():
                # Proovi API kaudu
                return self.search_via_api(query)
            
            if len(html) < 5000:
                # Proovi API kaudu
                return self.search_via_api(query)
            
            # Parsimine
            soup = BeautifulSoup(html, "html.parser")
            products = []
            seen_ids = set()
            
            # 1. Proovi leida tooted data-product-id järgi
            product_elements = soup.select("[data-product-id]")
            
            # 2. Kui ei leia, proovi teisi selektoreid
            if not product_elements:
                selectors = [
                    ".product-item",
                    ".product-tile", 
                    ".product-list__item",
                    "li.product",
                    ".search-results .item",
                    "article.product",
                    ".product-card",
                    ".product-box"
                ]
                
                for selector in selectors:
                    elements = soup.select(selector)
                    if elements:
                        product_elements = elements
                        break
            
            # 3. Kui ikka ei leia, proovi linke
            if not product_elements:
                product_elements = soup.select("a[href*='/toode/'], a[href*='/product/']")
            
            print(f"📦 Leitud {len(product_elements)} toodet")
            
            for element in product_elements[:max_results]:
                try:
                    # Kontrolli, kas see on juba käsitletud
                    product_id = self.extract_product_id(element)
                    if product_id and product_id in seen_ids:
                        continue
                    if product_id:
                        seen_ids.add(product_id)
                    
                    # Toote nimi
                    name = self.extract_name(element)
                    if not name or len(name) < 3:
                        continue
                    
                    # Toote hind
                    price_eur = self.extract_price(element, product_id)
                    
                    # Toote URL
                    url = self.extract_url(element)
                    
                    # Lisa toode
                    product = {
                        "name": name[:200],
                        "price_eur": price_eur,
                        "url": url,
                        "product_id": product_id,
                        "store": "Selver"
                    }
                    products.append(product)
                    print(f"  ✅ {name[:50]}... {price_eur}€" if price_eur else f"  ✅ {name[:50]}...")
                    
                except Exception as e:
                    print(f"  ❌ Viga: {e}")
                    continue
            
            # Kui HTML-ist ei leitud tooteid, proovi API
            if not products:
                return self.search_via_api(query)
            
            print(f"✅ Leitud {len(products)} toodet")
            return products
            
        except Exception as e:
            # Proovi API kaudu
            return self.search_via_api(query)
    
    def extract_name(self, element) -> Optional[str]:
        """Tõmba toote nimi"""
        name_selectors = [
            ".product-name",
            ".name",
            ".product-title",
            "[data-testid='product-name']",
            "h2",
            "h3",
            ".title",
            ".product-name a",
            ".product-title a"
        ]
        
        for selector in name_selectors:
            name_elem = element.select_one(selector)
            if name_elem:
                name = name_elem.get_text(" ", strip=True)
                if name and len(name) > 2:
                    return name
        
        # Kui ei leia, võta kogu tekst
        text = element.get_text(" ", strip=True)
        if text and len(text) > 2:
            # Proovi eraldada nimi (esimene osa)
            parts = text.split('€')
            if parts:
                return parts[0].strip()
        
        return None
    
    def extract_price(self, element, product_id: Optional[str] = None) -> Optional[float]:
        """Tõmba toote hind"""
        # 1. Proovi otseseid hinnaselektoreid
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
            ".product-price__price"
        ]
        
        for selector in price_selectors:
            price_elem = element.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text(" ", strip=True)
                match = re.search(r"(\d+[.,]\d{2})\s*€?", price_text)
                if match:
                    try:
                        return float(match.group(1).replace(",", "."))
                    except:
                        pass
        
        # 2. Proovi kogu elemendi tekstist
        full_text = element.get_text(" ", strip=True)
        matches = re.findall(r"(\d+[.,]\d{2})\s*€?", full_text)
        if matches:
            try:
                return float(matches[0].replace(",", "."))
            except:
                pass
        
        # 3. Proovi API kaudu, kui product_id on teada
        if product_id:
            return self.get_price_via_api(product_id)
        
        return None
    
    def extract_url(self, element) -> str:
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
    
    def search_via_api(self, query: str) -> List[Dict]:
        """
        Proovi andmeid API kaudu
        """
        print("🔄 Proovin API kaudu...")
        
        # Selver kasutab erinevaid API endpoint'e
        api_urls = [
            f"https://www.selver.ee/rest/V1/search?q={quote_plus(query)}",
            f"https://www.selver.ee/api/search?q={quote_plus(query)}",
            f"https://www.selver.ee/graphql"
        ]
        
        for api_url in api_urls:
            try:
                response = self.session.get(api_url, headers={
                    **self.headers,
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                }, timeout=10)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        products = self.parse_api_response(data)
                        if products:
                            print(f"✅ API-st leitud {len(products)} toodet")
                            return products
                    except:
                        continue
            except:
                continue
        
        return [{"error": "Tooteid ei leitud (proovitud HTML ja API)"}]
    
    def parse_api_response(self, data: dict) -> List[Dict]:
        """Parsime API vastust"""
        products = []
        
        # Proovi erinevaid API vastuse struktuure
        possible_arrays = ['items', 'data', 'results', 'products', 'hits']
        
        items = []
        for key in possible_arrays:
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        
        if not items and isinstance(data, list):
            items = data
        
        for item in items[:20]:
            try:
                if isinstance(item, dict):
                    # Toote nimi
                    name = item.get('name') or item.get('title') or item.get('product_name')
                    
                    # Hind
                    price = None
                    price_data = item.get('price') or item.get('prices')
                    if isinstance(price_data, dict):
                        price = price_data.get('price') or price_data.get('final_price')
                    elif isinstance(price_data, (int, float)):
                        price = price_data
                    elif isinstance(price_data, str):
                        price = price_data
                    
                    # Teisenda hind ujukomaarvuks
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
                    url = item.get('url') or item.get('permalink')
                    if url and not url.startswith('http'):
                        url = urljoin('https://www.selver.ee', url)
                    
                    if name:
                        products.append({
                            'name': name[:200],
                            'price_eur': price,
                            'url': url or '',
                            'product_id': item.get('id') or item.get('sku'),
                            'store': 'Selver'
                        })
            except:
                continue
        
        return products
    
    def get_price_via_api(self, product_id: str) -> Optional[float]:
        """Proovi toote hinda API kaudu"""
        try:
            url = f"https://www.selver.ee/rest/V1/products/{product_id}"
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                price = data.get('price', {}).get('final_price')
                if price:
                    return float(price)
        except:
            pass
        return None


# ----------------------------
# LIIDES FUNKTSIOONID
# ----------------------------

# Loo globaalne skraper
scraper = SelverScraper()

def search_selver_improved(query: str) -> List[Dict]:
    """Liides funktsioon skraperile"""
    return scraper.search_products(query)


def search_selver_for_app(query: str) -> List[Dict]:
    """App.py jaoks wrapper"""
    results = search_selver_improved(query)
    
    # Kui tulemus on error, tagasta tühi list
    if results and isinstance(results, list) and results and "error" in results[0]:
        return []
    
    return results


# ----------------------------
# TESTIMINE
# ----------------------------
def test_selver_scraper():
    """Testi skraperit"""
    test_queries = ["sai", "leib", "piim"]
    
    for query in test_queries:
        print(f"\n{'='*50}")
        print(f"TEST: {query}")
        print('='*50)
        
        results = search_selver_improved(query)
        
        if results and "error" in results[0]:
            print(f"❌ Viga: {results[0]['error']}")
        else:
            print(f"✅ Leitud {len(results)} toodet:")
            for i, product in enumerate(results[:5], 1):
                price_str = f"{product['price_eur']}€" if product['price_eur'] else "Hind puudub"
                print(f"  {i}. {product['name']} - {price_str}")
            if len(results) > 5:
                print(f"  ... ja {len(results) - 5} veel")


if __name__ == "__main__":
    test_selver_scraper()
