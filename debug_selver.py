"""
DEBUG SKRIPT — käivita see LOKAALSELT (arvutis, kus on internetiühendus).

Eesmärk: näha, mida Selveri leht tegelikult JS-renderduse järel sisaldab,
et saaksin kirjutada täpse ja töötava parseri.

KÄIVITAMINE:
    pip install playwright
    playwright install chromium
    python3 debug_selver.py

Skript:
1. Avab Selveri lehe päris (headless) brauseriga
2. Ootab, kuni leht on JS-i täis laadinud
3. Salvestab täisrenderdatud HTML faili "selver_rendered.html"
4. Prindib välja kõik elemendid, mis sisaldavad sõna "sai" (toote nimed)
5. Prindib välja kõik lingid, mis viitavad tooteleheküljele

Saada mulle:
- "selver_rendered.html" fail (või vähemalt esimesed 200 rida)
- Terminali väljund (mis prinditi)
"""

from playwright.sync_api import sync_playwright

# Proovime mitut võimalikku URL-i, et leida, mis tegelikult töötab
CANDIDATE_URLS = [
    "https://www.selver.ee/search?q=sai",
    "https://www.selver.ee/otsing?q=sai",
    "https://www.selver.ee/leivad-saiad-kondiitritooted",
    "https://www.selver.ee/tooted?search=sai",
]


def debug_url(page, url):
    print(f"\n{'='*70}")
    print(f"PROOVIN: {url}")
    print(f"{'='*70}")

    try:
        response = page.goto(url, timeout=20000, wait_until="networkidle")
        print(f"HTTP staatus: {response.status if response else 'N/A'}")
    except Exception as e:
        print(f"VIGA lehe laadimisel: {e}")
        return

    # Anna JS-ile veidi rohkem aega renderdada
    page.wait_for_timeout(3000)

    html = page.content()
    print(f"HTML pikkus: {len(html)} märki")

    # Otsi, kas leheküljel on üldse mingeid hindu (€ märk)
    euro_count = html.count("€")
    print(f"'€' sümboli esinemiskordi HTML-is: {euro_count}")

    # Otsi sõna "sai" (case-insensitive) esinemist
    sai_count = html.lower().count("sai")
    print(f"'sai' esinemiskordi HTML-is: {sai_count}")

    # Proovime levinumaid toote-kaardi selektoreid
    selectors_to_try = [
        "h3 a[href]",
        "article a[href]",
        "[class*='product'] a[href]",
        "[class*='Product'] a[href]",
        "[data-testid*='product']",
        "a[href*='/toode/']",
        "a[href*='/p/']",
    ]

    for sel in selectors_to_try:
        try:
            count = page.locator(sel).count()
            print(f"Selektor '{sel}': {count} vastet")
            if count > 0 and count <= 3:
                for i in range(min(count, 3)):
                    text = page.locator(sel).nth(i).inner_text()[:80]
                    href = page.locator(sel).nth(i).get_attribute("href")
                    print(f"    [{i}] text={text!r} href={href!r}")
        except Exception as e:
            print(f"Selektor '{sel}': viga ({e})")

    return html


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        )

        last_html = None
        for url in CANDIDATE_URLS:
            html = debug_url(page, url)
            if html:
                last_html = (url, html)

        browser.close()

        if last_html:
            url, html = last_html
            with open("selver_rendered.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\n\nViimase URL-i ({url}) täis-HTML salvestatud faili: selver_rendered.html")
            print("Saada see fail mulle, et saaksin kirjutada täpse parseri.")


if __name__ == "__main__":
    main()
