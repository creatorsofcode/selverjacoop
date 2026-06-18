from flask import Flask, jsonify, render_template, request
from contextlib import contextmanager
import signal

from scraper import (
    COOP_CATEGORIES,
    SelverBlockedError,
    compare_selver_vs_coop,
    scrape,
    scrape_coop,
    scrape_coop_with_playwright,
    scrape_with_playwright,
)

app = Flask(__name__)


# ----------------------------
# Timeout helper (Render-safe)
# ----------------------------
@contextmanager
def request_timeout(seconds: int):
    if seconds <= 0:
        yield
        return

    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def handler(signum, frame):
        raise TimeoutError("Request timeout")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# ----------------------------
# Default context
# ----------------------------
def default_context():
    return {
        "products": None,
        "error": None,
        "compare_result": None,
        "query": "sai",
        "max_pages": 2,
        "engine": "auto",
        "store": "selver",
        "coop_categories": COOP_CATEGORIES,
        "coop_category": list(COOP_CATEGORIES.keys())[0],
    }


# ----------------------------
# MAIN PAGE
# ----------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    context = default_context()

    if request.method == "GET":
        return render_template("index.html", **context)

    store = request.form.get("store", "selver")
    action = request.form.get("action", "search")
    engine = request.form.get("engine", "auto")

    try:
        max_pages = min(max(int(request.form.get("max_pages", 2)), 1), 5)
    except:
        max_pages = 2

    query = (request.form.get("query", "sai") or "sai").strip()

    coop_category_name = request.form.get("coop_category", context["coop_category"])
    coop_url = COOP_CATEGORIES.get(coop_category_name, list(COOP_CATEGORIES.values())[0])

    context.update({
        "store": store,
        "engine": engine,
        "max_pages": max_pages,
        "query": query,
        "coop_category": coop_category_name,
    })

    try:
        with request_timeout(40):

            if action == "compare":
                context["store"] = "compare"
                context["compare_result"] = compare_selver_vs_coop(
                    query=query,
                    max_pages=max_pages,
                    coop_category_url=coop_url,
                    engine=engine,
                )
            else:
                if store == "coop":
                    if engine == "playwright":
                        products = scrape_coop_with_playwright(coop_url, max_pages)
                    else:
                        products = scrape_coop(query, coop_url, max_pages)
                else:
                    if engine == "playwright":
                        products = scrape_with_playwright(query, max_pages)
                    else:
                        products = scrape(query, max_pages)

                context["products"] = products

    except SelverBlockedError as e:
        context["error"] = str(e)
        context["products"] = []

    except Exception as e:
        context["error"] = str(e)
        context["products"] = []

    return render_template("index.html", **context)


# ----------------------------
# API SEARCH
# ----------------------------
@app.route("/api/search")
def api_search():
    store = request.args.get("store", "selver")
    engine = request.args.get("engine", "auto")

    try:
        max_pages = min(max(int(request.args.get("max_pages", 2)), 1), 5)
    except:
        max_pages = 2

    try:
        with request_timeout(40):

            if store == "coop":
                cat_name = request.args.get("coop_category", list(COOP_CATEGORIES.keys())[0])
                cat_url = COOP_CATEGORIES.get(cat_name, list(COOP_CATEGORIES.values())[0])

                products = scrape_coop_with_playwright(cat_url, max_pages) if engine == "playwright" else scrape_coop("sai", cat_url, max_pages)

            else:
                query = (request.args.get("q", "sai") or "sai").strip()

                if engine == "playwright":
                    products = scrape_with_playwright(query, max_pages)
                else:
                    products = scrape(query, max_pages)

        return jsonify({
            "store": store,
            "count": len(products),
            "products": [
                {"name": p.name, "price_eur": p.price_eur, "url": p.url}
                for p in products
            ]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------
# API COMPARE
# ----------------------------
@app.route("/api/compare")
def api_compare():
    query = (request.args.get("q", "sai") or "sai").strip()
    engine = request.args.get("engine", "auto")

    try:
        max_pages = min(max(int(request.args.get("max_pages", 2)), 1), 5)
    except:
        max_pages = 2

    coop_category_name = request.args.get("coop_category", list(COOP_CATEGORIES.keys())[0])
    coop_url = COOP_CATEGORIES.get(coop_category_name, list(COOP_CATEGORIES.values())[0])

    try:
        with request_timeout(40):
            result = compare_selver_vs_coop(
                query=query,
                max_pages=max_pages,
                coop_category_url=coop_url,
                engine=engine,
            )
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------
# ENTRY
# ----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)