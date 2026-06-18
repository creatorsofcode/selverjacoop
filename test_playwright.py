import sys
sys.path.insert(0, '/var/www/creatorsofcode.com/selverjacoop')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://www.selver.ee/search?q=sai&page=1&limit=48', wait_until='domcontentloaded', timeout=30000)
    try:
        page.wait_for_selector('h3', timeout=10000)
    except:
        pass
    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')
h3s = soup.select('h3')
print('h3 count:', len(h3s))
print('h3 first 3:', [h.get_text()[:50] for h in h3s[:3]])
h3_links = soup.select('h3 a[href]')
print('h3 a[href] count:', len(h3_links))
arts = soup.select('article')
print('article count:', len(arts))
divs = soup.select('[class*="product"]')
print('product class divs:', len(divs))
with open('/tmp/selver_html.txt', 'w') as f:
    f.write(html[:8000])
print('HTML snippet saved to /tmp/selver_html.txt')
