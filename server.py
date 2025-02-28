import csv
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, jsonify, Response
import threading
from datetime import datetime
import threading
alertes_envoyees = set()  # Stocke les alertes déjà envoyées

app = Flask(__name__)

# ======================== #
# 🔹 ROUTES HTML
# ======================== #
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/harvester/<int:harvester_id>")
def harvester_detail(harvester_id):
    data = get_harvesters_data()["harvesters"]
    harvester = next((h for h in data if h["id"] == harvester_id), None)

    if harvester:
        return render_template("harvester.html", harvester=harvester)
    else:
        return "Harvester non trouvé", 404

@app.route("/stats")
def stats():
    return render_template("stats.html")

# ======================== #
# 🔹 FONCTIONS DES DONNÉES
# ======================== #
def get_harvesters_data():
    return {
        "harvesters": [
            {"id": 1, "name": "Harvester #1", "ip": "192.168.10.5", "state": "connected", "version": "1.2.0", "num_machines": 12, "latence_wan": "28ms"},
            {"id": 2, "name": "Harvester #2", "ip": "192.168.15.10", "state": "disconnected", "version": "1.1.5", "num_machines": 8, "latence_wan": "N/A"},
            {"id": 3, "name": "Harvester #3", "ip": "192.168.15.20", "state": "connected", "version": "1.1.5", "num_machines": 8, "latence_wan": "120ms"},
        ]
    }

# ======================== #
# 🔹 ROUTE API : DONNÉES AVEC ALERTES
# ======================== #
@app.route("/api/data")
def api_data():
    data = get_harvesters_data()

    # Vérifier les problèmes et envoyer des alertes une seule fois
    for harvester in data["harvesters"]:
        if harvester["state"] == "disconnected":
            send_alert("🚨 Harvester Déconnecté", f"Le harvester {harvester['name']} ({harvester['ip']}) est hors ligne !")
        if harvester["latence_wan"] != "N/A":
            latence = int(harvester["latence_wan"].replace("ms", ""))
            if latence > 100:
                send_alert("⚠️ Latence Élevée", f"Le harvester {harvester['name']} a une latence élevée de {latence}ms.")

    return jsonify(data)

# ======================== #
# 🔹 ROUTE API : STATISTIQUES
# ======================== #
@app.route("/api/stats")
def api_stats():
    data = get_harvesters_data()["harvesters"]  # Récupération sans relancer les alertes

    stats_data = {
        "labels": [h["name"] for h in data],
        "num_machines": [h["num_machines"] for h in data],
        "latence": [
            int(h["latence_wan"].replace("ms", "")) if h["latence_wan"] != "N/A" else 0
            for h in data
        ]
    }

    return jsonify(stats_data)

# ======================== #
# 🔹 ROUTES API : EXPORT JSON / CSV
# ======================== #
@app.route("/api/export/json")
def export_json():
    data = get_harvesters_data()  # Récupération des données sans relancer les alertes
    return jsonify(data)

@app.route("/api/export/csv")
def export_csv():
    data = get_harvesters_data()["harvesters"]  # Récupération des données sans relancer les alertes

    def generate():
        yield "ID,Nom,IP,État,Version,Machines,Latence WAN\n"
        for harvester in data:
            yield f"{harvester['id']},{harvester['name']},{harvester['ip']},{harvester['state']},{harvester['version']},{harvester['num_machines']},{harvester['latence_wan']}\n"

    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=harvesters.csv"})

# ======================== #
# 🔹 CONFIGURATION EMAIL (ALERTES) + LOGS
# ======================== #
ALERT_EMAIL = "bourlleo@gmail.com"  # Remplace par ton adresse
SMTP_SERVER = "smtp.gmail.com"  # Serveur SMTP de ton email (ex: Gmail)
SMTP_PORT = 587
SMTP_USER = "bourlleo@gmail.com"  # Remplace par ton email
SMTP_PASSWORD = "aqxrrqfjqphxqgaz"  # ATTENTION : Pour Gmail, active un mot de passe d’application

# Fonction pour envoyer un email d'alerte

LOG_FILE = "alerts.log"  # Fichier où on stocke les alertes

def send_alert(subject, message):
    global alertes_envoyees

    alert_id = f"{subject}:{message}"  # Identifiant unique pour éviter les doublons
    if alert_id in alertes_envoyees:
        return  # Ne pas renvoyer une alerte déjà envoyée

    alertes_envoyees.add(alert_id)  # Ajouter l'alerte à la liste des alertes envoyées

    def send_email():
        msg = MIMEText(message)
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_EMAIL
        msg["Subject"] = subject

        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, ALERT_EMAIL, msg.as_string())
            server.quit()
            print(f"✅ Alerte envoyée : {subject}")
        except Exception as e:
            print(f"❌ Erreur lors de l'envoi de l'alerte : {e}")

    # 🔹 Enregistrer l'alerte dans le fichier `alerts.log`
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {subject}: {message}\n")

    # Exécuter l'envoi d'e-mail en arrière-plan
    email_thread = threading.Thread(target=send_email)
    email_thread.start()


@app.route("/alerts")
def view_alerts():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as log:  # 🔹 Ajout de encoding="utf-8"
            logs = log.readlines()
    except FileNotFoundError:
        logs = ["Aucune alerte enregistrée pour le moment."]
    except UnicodeDecodeError:
        logs = ["❌ Erreur : Impossible de lire le fichier d'alertes. Vérifiez l'encodage."]
    
    return render_template("alerts.html", logs=logs)


@app.route("/clear_alerts", methods=["POST"])
def clear_alerts():
    open(LOG_FILE, "w").close()  # Efface le contenu du fichier
    return view_alerts()  # Recharge la page après suppression

@app.route("/api/alert_stats")
def alert_stats():
    alert_types = {"🚨 Harvester Déconnecté": 0, "⚠️ Latence Élevée": 0}
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as log:
            logs = log.readlines()

        for line in logs:
            if "🚨 Harvester Déconnecté" in line:
                alert_types["🚨 Harvester Déconnecté"] += 1
            if "⚠️ Latence Élevée" in line:
                alert_types["⚠️ Latence Élevée"] += 1

    except FileNotFoundError:
        return jsonify({"message": "Aucune alerte enregistrée."})

    return jsonify(alert_types)


# ======================== #
# 🔹 LANCEMENT DU SERVEUR
# ======================== #
if __name__ == "__main__":
    app.run(debug=True)
