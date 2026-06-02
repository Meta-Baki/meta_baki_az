from flask import Flask, request, jsonify

app = Flask(__name__)

latest_data = {}

@app.route("/update", methods=["POST"])
def update():
    global latest_data
    latest_data = request.json
    return "OK"

@app.route("/data")
def data():
    return jsonify(latest_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
