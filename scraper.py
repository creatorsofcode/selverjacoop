from flask import Flask, render_template, request
from scraper import compare_selver_vs_coop

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/search")
def search():
    query = request.args.get("q", "sai")

    data = compare_selver_vs_coop(query=query)

    return jsonify(data)


@app.route("/selver")
def selver():
    query = request.args.get("q", "sai")

    data = compare_selver_vs_coop(query=query)["selver_cheapest"]

    if data:
        return jsonify({
            "name": data.name,
            "price": data.price_eur,
            "url": data.url
        })

    return jsonify({"error": "no data"})


@app.route("/coop")
def coop():
    query = request.args.get("q", "sai")

    data = compare_selver_vs_coop(query=query)["coop_cheapest"]

    if data:
        return jsonify({
            "name": data.name,
            "price": data.price_eur,
            "url": data.url
        })

    return jsonify({"error": "no data"})


if __name__ == "__main__":
    app.run()
