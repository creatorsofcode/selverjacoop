import concurrent.futures

SCRAPE_TIMEOUT = 25


@app.route("/", methods=["GET", "POST"])
def index():
    context = _default_context()

    if request.method == "GET":
        return render_template("index.html", **context)

    store = request.form.get("store", "selver")
    action = request.form.get("action", "search")
    engine = request.form.get("engine", "auto")
    max_pages = min(max(int(request.form.get("max_pages", 2)), 1), 10)
    query = request.form.get("query", "sai").strip() or "sai"

    context.update({
        "store": store,
        "engine": engine,
        "max_pages": max_pages,
        "query": query,
    })

    def run_scrape():
        if action == "compare":
            return compare_selver_vs_coop(
                query=query,
                max_pages=max_pages,
                engine=engine,
            )

        if store == "coop":
            return scrape_coop(query=query, max_pages=max_pages)
        return scrape(query=query, max_pages=max_pages)

    try:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            future = ex.submit(run_scrape)
            result = future.result(timeout=SCRAPE_TIMEOUT)

        if action == "compare":
            context["compare_result"] = result
        else:
            context["products"] = result

    except Exception as exc:
        context["error"] = f"Timeout / error: {str(exc)}"
        context["products"] = []
        context["compare_result"] = None

    return render_template("index.html", **context)