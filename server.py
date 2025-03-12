import csv
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, jsonify, Response, request
import threading
from datetime import datetime, timedelta
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
from datetime import datetime, timedelta

def get_harvesters_data():
    conn = get_connection()  # fonction qui retourne la connexion MySQL
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT ID_reseau, subnet, nombre_machine, dateheure FROM reseau ORDER BY ID_reseau")
    rows = cursor.fetchall()

    data = {"harvesters": []}
    now = datetime.now()

    for row in rows:
        # Extraire la date/heure du dernier scan
        last_scan = row["dateheure"]  # type: datetime ou None

        if last_scan is not None:
            elapsed_seconds = (now - last_scan).total_seconds()
            # 30 secondes après le scan => disconnected
            if elapsed_seconds <= 120 :
                state = "connected"
            else:
                state = "disconnected"
        else:
            # Si on n'a pas de date de scan, on considère "disconnected"
            state = "disconnected"

        data["harvesters"].append({
            "id": row["ID_reseau"],
            "name": f"Harvester #{row['ID_reseau']}",
            "ip": row["subnet"],
            "state": state,
            "num_machines": row["nombre_machine"] or 0,
            # Exemple : si vous n'avez pas de vraie colonne latence en BDD,
            # mettez "N/A" ou une valeur par défaut
            "latence_wan": "N/A"
        })
    
    cursor.close()
    conn.close()
    return data
def get_harvester_details(harvester_id):
    """
    Récupère toutes les infos (reseau + client + stats + hote + machine) liées
    à un ID_reseau donné, et renvoie un dict complet exploitable par la page 'harvester'.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 1) Récupérer le reseau + le client
    #    (on suppose qu'un harvester correspond à un reseau)
    query_reseau = """
        SELECT 
            r.ID_reseau,
            r.subnet,
            r.nombre_machine,
            r.dateheure,
            c.ID_client,
            c.nom AS client_nom
        FROM reseau r
        JOIN client c ON r.ID_client = c.ID_client
        WHERE r.ID_reseau = %s
    """
    cursor.execute(query_reseau, (harvester_id,))
    row_reseau = cursor.fetchone()

    if not row_reseau:
        # Si on ne trouve pas ce réseau, on renvoie None
        cursor.close()
        conn.close()
        return None

    # 2) Récupérer la liste des statistiques
    #    (nombre_scan, temps_moyen, dateheure, etc.)
    query_stats = """
        SELECT 
            ID_statistique,
            dateheure,
            nombre_scan,
            temps_moyen
        FROM statistique
        WHERE ID_reseau = %s
        ORDER BY dateheure DESC
    """
    cursor.execute(query_stats, (harvester_id,))
    stats_rows = cursor.fetchall()

    # 3) Récupérer la liste des hôtes
    query_hote = """
        SELECT 
            ID_hote,
            nom,
            OS,
            version_os,
            ip_adress
        FROM hote
        WHERE ID_reseau = %s
    """
    cursor.execute(query_hote, (harvester_id,))
    hotes_rows = cursor.fetchall()

    # 4) Récupérer la liste des machines
    #    (ip_adress, port, service, vulnerabilite, etc.)
    query_machine = """
        SELECT
            ID_machine,
            ip_adress,
            port,
            service,
            vulnerabilite
        FROM machine
        WHERE ID_reseau = %s
    """
    cursor.execute(query_machine, (harvester_id,))
    machine_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    # Construire l'objet final harvester
    # On reprend la même logique de "connected"/"disconnected" sur 30s, si besoin
    from datetime import datetime
    now = datetime.now()
    state = "disconnected"
    if row_reseau["dateheure"]:
        elapsed = (now - row_reseau["dateheure"]).total_seconds()
        if elapsed <= 30:
            state = "connected"

    harvester_details = {
        "id": row_reseau["ID_reseau"],
        "ip": row_reseau["subnet"],
        "nombre_machine": row_reseau["nombre_machine"],
        "dateheure_scan": row_reseau["dateheure"],
        "state": state,
        "client": {
            "id_client": row_reseau["ID_client"],
            "nom": row_reseau["client_nom"]
        },
        "stats": stats_rows,       # liste de dict
        "hotes": hotes_rows,       # liste de dict
        "machines": machine_rows   # liste de dict
    }
    return harvester_details


@app.route("/harvester/<int:harvester_id>")
def harvester_detail(harvester_id):
    """
    Page détaillée pour un 'harvester' (reseau).
    On va y afficher tout ce qu'on sait : reseau, client, stats, hotes, machines...
    """
    harvester = get_harvester_details(harvester_id)
    if not harvester:
        return "Harvester non trouvé", 404

    # Pour l'affichage, on veut un 'name' par cohérence avec index.html
    # ex: "Harvester #1"
    harvester["name"] = f"Harvester #{harvester_id}"

    return render_template("harvester.html", harvester=harvester)


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
