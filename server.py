from flask import Flask, render_template, jsonify

app = Flask(__name__)

# Exemple de route qui sert la page HTML (templates/index.html)
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/harvester/<int:harvester_id>")
def harvester_detail(harvester_id):
    # Récupérer les données des harvesters
    data = api_data().json['harvesters']
    harvester = next((h for h in data if h['id'] == harvester_id), None)

    if harvester:
        return render_template("harvester.html", harvester=harvester)
    else:
        return "Harvester non trouvé", 404
    
@app.route("/stats")
def stats():
    return render_template("stats.html")

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
            },
            {
                "id": 3,
                "name": "Harvester #3",
                "ip": "192.168.15.10",
                "state": "connected",
                "version": "1.1.5",
                "num_machines": 8,
                "latence_wan": "12ms"
            }
        ]
    }
    return jsonify(fake_data)

@app.route("/api/stats")
def api_stats():
    data = api_data().json['harvesters']

    # Transformer la latence en nombre (remplacer "N/A" par 0)
    stats_data = {
        "labels": [h["name"] for h in data],
        "num_machines": [h["num_machines"] for h in data],
        "latence": [
            int(h["latence_wan"].replace("ms", "")) if h["latence_wan"] != "N/A" else 0
            for h in data
        ]
    }

    return jsonify(stats_data)


if __name__ == "__main__":
    app.run(debug=True)
