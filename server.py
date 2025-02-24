from flask import Flask, render_template, jsonify

app = Flask(__name__)

# Exemple de route qui sert la page HTML (templates/index.html)
@app.route("/")
def index():
    return render_template("index.html")

# Exemple de route API qui renvoie du JSON
@app.route("/api/data")
def api_data():
    # Dans la vraie application, vous récupéreriez ici
    # les infos remontées par le Harvester (scan, latence, etc.)
    # Pour la démo, on renvoie un JSON bidon :
    fake_data = {
        "harvesters": [
            {
                "id": 1,
                "name": "Harvester #1",
                "ip": "192.168.10.5",
                "state": "connected",
                "version": "1.2.0",
                "num_machines": 12,
                "latence_wan": "28ms"
            },
            {
                "id": 2,
                "name": "Harvester #2",
                "ip": "192.168.15.10",
                "state": "disconnected",
                "version": "1.1.5",
                "num_machines": 8,
                "latence_wan": "N/A"
            }
        ]
    }
    return jsonify(fake_data)


if __name__ == "__main__":
    app.run(debug=True)
