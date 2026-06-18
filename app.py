import requests
import random

# ----------------------------
# TASUTA PROXY-D (TÖÖTAVAD)
# ----------------------------
def get_proxy_list():
    """
    Tagastab nimekirja tasuta proxydest
    Need on testitud ja töötavad
    """
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
    """
    Teeb päringu proxy kaudu
    Proovib erinevaid proxysid, kuni üks töötab
    """
    proxies = get_proxy_list()
    random.shuffle(proxies)  # Sega proxyd
    
    for proxy in proxies:
        try:
            print(f"🔄 Proovin proxyt: {proxy}")
            
            proxy_dict = {
                "http": proxy,
                "https": proxy
            }
            
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
            print(f"❌ Proxy {proxy} ei tööta: {e}")
            continue
    
    # Kui ükski proxy ei tööta, tee ilma proxyta
    print("⚠️ Ükski proxy ei töötanud, proovin ilma proxyta...")
    return requests.get(url, headers=headers or {}, timeout=timeout)

# ----------------------------
# PRISMA PROXYGA
# ----------------------------
def search_prisma_with_proxy(query: str) -> list:
    """Prisma otsing proxyga"""
    try:
        url = f"https://www.prisma.ee/et/otsing?q={quote_plus(query)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
        }
        
        # Tee päring proxyga
        response = search_with_proxy(url, headers)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        products = []
        seen = set()
        
        # Otsi tooteid
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
        
        print(f"✅ Prisma proxyga: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"Prisma proxyga viga: {e}")
        return []

# ----------------------------
# MAXIMA PROXYGA
# ----------------------------
def search_maxima_with_proxy(query: str) -> list:
    """Maxima otsing proxyga"""
    try:
        url = f"https://www.maxima.ee/et/search?q={quote_plus(query)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "Accept-Language": "et-EE,et;q=0.9,en;q=0.8",
        }
        
        response = search_with_proxy(url, headers)
        
        if response.status_code != 200:
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
        
        print(f"✅ Maxima proxyga: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"Maxima proxyga viga: {e}")
        return []

# ----------------------------
# RIMI PROXYGA
# ----------------------------
def search_rimi_with_proxy(query: str) -> list:
    """Rimi otsing proxyga"""
    try:
        url = "https://www.rimi.ee/api/products"
        params = {"search": query, "limit": 20}
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        
        response = search_with_proxy(f"{url}?search={quote_plus(query)}&limit=20", headers)
        
        if response.status_code != 200:
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
        
        print(f"✅ Rimi proxyga: {len(products)} toodet")
        return products
        
    except Exception as e:
        print(f"Rimi proxyga viga: {e}")
        return []
