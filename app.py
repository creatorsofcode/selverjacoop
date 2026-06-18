from flask import Flask, jsonify, render_template, request
import signal
from contextlib import contextmanager

from scraper import (
    COOP_CATEGORIES,
    SelverBlockedError,
    compare_selver_vs_coop,
    scrape,
    scrape_coop,
    scrape_coop_with_playwright,
    scrape_with_requests,
    scrape_with_playwright,
)

app = Flask(__name__)


@contextmanager
def _request_timeout(seconds: int):
    """Abort long-running scraper calls so one blocked upstream does not hang the API."""
    if seconds <= 0:
        yield
        return

    # SIGALRM is not available on Windows; fall back to no-op timeout there.
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise TimeoutError(f"Request timed out after {seconds}s")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def _default_context() -> dict:
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


@app.route("/", methods=["GET", "POST"])
def index():
    context = _default_context()

    if request.method == "GET":
        return "OK WORKS"

    store = request.form.get("store", "selver")
    action = request.form.get("action", "search")
    engine = request.form.get("engine", "auto")
    max_pages = min(max(int(request.form.get("max_pages", 2)), 1), 10)
    query = request.form.get("query", "sai").strip() or "sai"
    coop_category_name = request.form.get("coop_category", context["coop_category"])
    coop_url = COOP_CATEGORIES.get(coop_category_name, list(COOP_CATEGORIES.values())[0])

    context.update(
        {
            "store": store,
            "engine": engine,
            "max_pages": max_pages,
            "query": query,
            "coop_category": coop_category_name,
        }
    )

    try:
        with _request_timeout(45):
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
                        products = scrape_coop_with_playwright(category_url=coop_url, max_pages=max_pages)
                    else:
                        products = scrape_coop(query=query, category_url=coop_url, max_pages=max_pages)
                else:
                    if engine == "playwright":
                        products = scrape_with_playwright(query=query, max_pages=max_pages)
                    elif engine == "auto":
                        products = scrape(query=query, max_pages=max_pages)
                    else:
                        products = scrape(query=query, max_pages=max_pages)
                context["products"] = products
    except SelverBlockedError as exc:
        if store == "selver" and action != "compare":
            context["products"] = []
            context["error"] = f"Selver blocked request on current IP: {exc}"
        else:
            context["error"] = str(exc)
            context["products"] = []
    except Exception as exc:
        context["error"] = str(exc)
        context["products"] = []

    return render_template("index.html", **context)


@app.route("/api/search")
def api_search():
    store = request.args.get("store", "selver")
    engine = request.args.get("engine", "auto")
    max_pages = min(max(int(request.args.get("max_pages", 2)), 1), 10)

    try:
        with _request_timeout(45):
            if store == "coop":
                cat_name = request.args.get("coop_category", list(COOP_CATEGORIES.keys())[0])
                cat_url = COOP_CATEGORIES.get(cat_name, list(COOP_CATEGORIES.values())[0])
                if engine == "playwright":
                    products = scrape_coop_with_playwright(category_url=cat_url, max_pages=max_pages)
                else:
                    products = scrape_coop(query=request.args.get("q", "sai"), category_url=cat_url, max_pages=max_pages)
            else:
                query = request.args.get("q", "sai").strip() or "sai"
                if engine == "playwright":
                    products = scrape_with_playwright(query=query, max_pages=max_pages)
                elif engine == "auto":
                    products = scrape(query=query, max_pages=max_pages)
                else:
                    products = scrape(query=query, max_pages=max_pages)

        return jsonify(
            {
                "store": store,
                "count": len(products),
                "products": [
                    {"name": p.name, "price_eur": p.price_eur, "url": p.url}
                    for p in products
                ],
            }
        )
    except SelverBlockedError as exc:
        if store == "selver":
            return jsonify(
                {
                    "store": store,
                    "count": 0,
                    "products": [],
                    "blocked": True,
                    "error": str(exc),
                }
            )
        return jsonify({"error": str(exc)}), 500
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/compare")
def api_compare():
    query = request.args.get("q", "sai").strip() or "sai"
    engine = request.args.get("engine", "auto")
    max_pages = min(max(int(request.args.get("max_pages", 2)), 1), 10)
    coop_category_name = request.args.get("coop_category", list(COOP_CATEGORIES.keys())[0])
    coop_url = COOP_CATEGORIES.get(coop_category_name, list(COOP_CATEGORIES.values())[0])

    try:
        with _request_timeout(45):
            result = compare_selver_vs_coop(
                query=query,
                max_pages=max_pages,
                coop_category_url=coop_url,
                engine=engine,
            )

        def _product_json(p):
            if not p:
                return None
            return {"name": p.name, "price_eur": p.price_eur, "url": p.url}

        return jsonify(
            {
                "query": result.get("query"),
                "selver_count": result.get("selver_count"),
                "coop_count": result.get("coop_count"),
                "winner_store": result.get("winner_store"),
                "price_diff_eur": result.get("price_diff_eur"),
                "price_diff_pct": result.get("price_diff_pct"),
                "selver_cheapest": _product_json(result.get("selver_cheapest")),
                "coop_cheapest": _product_json(result.get("coop_cheapest")),
            }
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
