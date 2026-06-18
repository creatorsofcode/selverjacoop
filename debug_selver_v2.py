"""
DEBUG SKRIPT v2 — käivita LOKAALSELT.

Nüüd kui me teame, et https://www.selver.ee/search?q=sai TÖÖTAB,
vajan täpset HTML struktuuri ühe tootekaardi kohta (nimi, hind, link),
et kirjutada korrektne parser.

KÄIVITAMINE:
    python3 debug_selver_v2.py

Saada mulle TERVE terminali väljund (copy-paste).
"""

from playwright.sync_api import sync_playwright

URL = "https://www.selver.ee/search?q=sai"


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

        page.goto(URL, timeout=20000, wait_until="networkidle")
        page.wait_for_timeout(3000)

        print(f"\n{'='*80}")
        print("1) NÄITED: [data-testid*='product'] (kõige rohkem vasteid - 24)")
        print(f"{'='*80}")
        loc = page.locator("[data-testid*='product']")
        count = loc.count()
        print(f"Kokku: {count} vastet\n")
        for i in range(min(count, 3)):
            el = loc.nth(i)
            try:
                testid = el.get_attribute("data-testid")
                tag = el.evaluate("e => e.tagName")
                outer = el.evaluate("e => e.outerHTML")
                print(f"--- Element [{i}] (tag={tag}, data-testid={testid}) ---")
                print(outer[:1500])
                print()
            except Exception as e:
                print(f"Viga elemendil [{i}]: {e}")

        print(f"\n{'='*80}")
        print("2) NÄITED: h3 a[href] (vana selektor - 8 vastet)")
        print(f"{'='*80}")
        loc2 = page.locator("h3 a[href]")
        count2 = loc2.count()
        print(f"Kokku: {count2} vastet\n")
        for i in range(min(count2, 3)):
            el = loc2.nth(i)
            try:
                text = el.inner_text()
                href = el.get_attribute("href")
                # Get the wider card container (going up a few parents)
                card_html = el.evaluate(
                    "e => { let p = e; for (let j=0;j<4;j++){ if(p.parentElement) p = p.parentElement; } return p.outerHTML; }"
                )
                print(f"--- Element [{i}] text={text!r} href={href!r} ---")
                print("Laiem kaart (4 taset üles):")
                print(card_html[:1500])
                print()
            except Exception as e:
                print(f"Viga elemendil [{i}]: {e}")

        print(f"\n{'='*80}")
        print("3) NÄITED: [class*='product'] a[href] (16 vastet)")
        print(f"{'='*80}")
        loc3 = page.locator("[class*='product'] a[href]")
        count3 = loc3.count()
        print(f"Kokku: {count3} vastet\n")
        for i in range(min(count3, 3)):
            el = loc3.nth(i)
            try:
                text = el.inner_text()
                href = el.get_attribute("href")
                print(f"--- Element [{i}] text={text!r} href={href!r} ---")
            except Exception as e:
                print(f"Viga elemendil [{i}]: {e}")

        browser.close()


if __name__ == "__main__":
    main()
