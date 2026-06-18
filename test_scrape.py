import sys
sys.path.insert(0, '/var/www/creatorsofcode.com/selverjacoop')
from scraper import scrape_with_requests
try:
    r = scrape_with_requests('sai', 1)
    print('OK:', len(r), 'toodet')
    if r:
        print('Esimene:', r[0])
except Exception as e:
    print('VIGA:', type(e).__name__, str(e)[:200])
