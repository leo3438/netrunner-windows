import csv
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, jsonify, Response, request
import threading
from datetime import datetime
import mysql.connector  # <-- Connecteur MySQL
import os

app = Flask(__name__)

# ======================== #
# 🔹 CONFIG BDD
# ======================== #
DB_CONFIG = {
    'host': 'localhost',       # ou l'IP de votre serveur MySQL
    'user': 'root',            # votre user
    'password': '',
    'database': 'api'
}

def get_connection():
    """Retourne une connexion MySQL."""
    return mysql.connector.connect(**DB_CONFIG)


# ======================== #
# 🔹 ROUTES HTML
# ======================== #
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/harvester/<int:harvester_id>")
def harvester_detail(harvester_id):
    # Récupérer la liste depuis la DB
    data = get_harvesters_data()["harvesters"]
    harvester = next((h for h in data if h["id"] == harvester_id), None)

    if harvester:
        return render_template("harvester.html", harvester=harvester)
    else:
        return "Harvester non trouvé", 404

@app.route("/stats")
def stats():
    return render_template("stats.html")

@app.route("/alerts")
def view_alerts():
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as log:
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

# ======================== #
# 🔹 FONCTIONS DES DONNÉES
# ======================== #
def get_harvesters_data():
    """
    Récupère la liste des 'Harvesters' depuis la table reseau.
    On simule l'état, la version et la latence selon l'ID_reseau pour l'exemple.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Récupérer tous les réseaux
    cursor.execute("SELECT ID_reseau, subnet, nombre_machine, dateheure FROM reseau ORDER BY ID_reseau")
    rows = cursor.fetchall()

    data = {"harvesters": []}
    for row in rows:
        # Déterminer un 'Harvester' :
        # - name, ip => row["subnet"]
        # - state => "connected" / "disconnected"
        # - latence_wan => "28ms", "N/A", "120ms", etc.
        # - version => "1.2.0", "1.1.5", etc.
        
        # EXEMPLE : on fait un switch sur l'ID_reseau
        if row["ID_reseau"] == 1:
            state = "connected"
            version = "1.2.0"
            latence_wan = "28ms"
        elif row["ID_reseau"] == 2:
            state = "disconnected"
            version = "1.1.5"
            latence_wan = "N/A"
        else:
            state = "connected"
            version = "1.1.5"
            latence_wan = "120ms"
        
        data["harvesters"].append({
            "id": row["ID_reseau"],
            "name": f"Harvester #{row['ID_reseau']}",
            "ip": row["subnet"],
            "state": state,
            "version": version,
            "num_machines": row["nombre_machine"] or 0,
            "latence_wan": latence_wan
        })
    
    cursor.close()
    conn.close()
    return data

def get_stats_data():
    """
    Retourne la structure attendue par stats.html :
      {
        "labels": [...],
        "num_machines": [...],
        "latence": [...]
      }
    On fait un left join sur reseau + statistique
    pour récupérer par ex. la moyenne 'temps_moyen' comme latence,
    et le nombre_machine comme 'num_machines'.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT r.ID_reseau, r.subnet, r.nombre_machine, 
           COALESCE(s.temps_moyen, 0) AS temps_moyen
    FROM reseau r
    LEFT JOIN statistique s ON r.ID_reseau = s.ID_reseau
    ORDER BY r.ID_reseau
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    labels = []
    num_machines = []
    latences = []
    for row in rows:
        labels.append(f"Harvester #{row['ID_reseau']}")
        num_machines.append(row["nombre_machine"] or 0)
        latences.append(row["temps_moyen"] or 0)

    return {
        "labels": labels,
        "num_machines": num_machines,
        "latence": latences
    }


# ======================== #
# 🔹 ROUTE API : DONNÉES AVEC ALERTES
# ======================== #
@app.route("/api/data")
def api_data():
    data = get_harvesters_data()

    # Vérifier les problèmes et envoyer des alertes (une seule fois)
    for harvester in data["harvesters"]:
        if harvester["state"] == "disconnected":
            send_alert("🚨 Harvester Déconnecté",
                       f"Le harvester {harvester['name']} ({harvester['ip']}) est hors ligne !")
        
        # latence_wan est de forme "28ms" ou "N/A" ou "120ms"
        if harvester["latence_wan"] != "N/A":
            latence_int = int(harvester["latence_wan"].replace("ms", "")) if "ms" in harvester["latence_wan"] else 0
            if latence_int > 100:
                send_alert("⚠️ Latence Élevée",
                           f"Le harvester {harvester['name']} a une latence élevée de {latence_int}ms.")

    return jsonify(data)

# ======================== #
# 🔹 ROUTE API : STATISTIQUES
# ======================== #
@app.route("/api/stats")
def api_stats():
    data = get_stats_data()  # Récupère les stats depuis la BDD
    return jsonify(data)

# ======================== #
# 🔹 ROUTES API : EXPORT JSON / CSV
# ======================== #
@app.route("/api/export/json")
def export_json():
    data = get_harvesters_data()  # Récupération des données
    return jsonify(data)

@app.route("/api/export/csv")
def export_csv():
    data = get_harvesters_data()["harvesters"]  # Récupération des données

    def generate():
        yield "ID,Nom,IP,État,Version,Machines,Latence WAN\n"
        for h in data:
            yield f"{h['id']},{h['name']},{h['ip']},{h['state']},{h['version']},{h['num_machines']},{h['latence_wan']}\n"

    return Response(generate(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=harvesters.csv"})


# ======================== #
# 🔹 CONFIGURATION EMAIL (ALERTES) + LOGS
# ======================== #
ALERT_EMAIL = "bourlleo@gmail.com"  # Mettez ici votre email
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "bourlleo@gmail.com"
SMTP_PASSWORD = "aqxrrqfjqphxqgaz"  # Gmail = mdp d'application
LOG_FILE = "alerts.log"

alertes_envoyees = set()  # Stocke les alertes déjà envoyées

def send_alert(subject, message):
    global alertes_envoyees
    alert_id = f"{subject}:{message}"
    if alert_id in alertes_envoyees:
        return  # Ne pas renvoyer une alerte déjà envoyée

    alertes_envoyees.add(alert_id)

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

    # Enregistrer l'alerte dans le fichier .log
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {subject}: {message}\n")

    # Envoi d'e-mail en arrière-plan
    email_thread = threading.Thread(target=send_email)
    email_thread.start()


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
