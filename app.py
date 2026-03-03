from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import psycopg2
import bcrypt
import os
import secrets
from datetime import datetime
from functools import wraps

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

# ─────────────────────────────────────────
# CONNEXION BASE DE DONNÉES
# ─────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode='require')
    return conn

# ─────────────────────────────────────────
# INITIALISATION DES TABLES
# ─────────────────────────────────────────
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS portails (
            id SERIAL PRIMARY KEY,
            code_unique VARCHAR(20) UNIQUE NOT NULL,
            nom VARCHAR(100) DEFAULT 'Mon Portail',
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id SERIAL PRIMARY KEY,
            identifiant VARCHAR(100) UNIQUE NOT NULL,
            mot_de_passe_hash TEXT NOT NULL,
            portail_id INTEGER REFERENCES portails(id),
            role VARCHAR(50) DEFAULT 'habitant',
            approuve BOOLEAN DEFAULT FALSE,
            date_inscription TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS droits (
            id SERIAL PRIMARY KEY,
            utilisateur_id INTEGER REFERENCES utilisateurs(id),
            portail_id INTEGER REFERENCES portails(id),
            droit VARCHAR(100) NOT NULL,
            accorde_par INTEGER REFERENCES utilisateurs(id),
            date_accord TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(utilisateur_id, portail_id, droit)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS mode_actuel (
            id SERIAL PRIMARY KEY,
            portail_id INTEGER REFERENCES portails(id) UNIQUE,
            mode VARCHAR(100) DEFAULT 'STANDBY',
            date_changement TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS commandes (
            id SERIAL PRIMARY KEY,
            portail_id INTEGER REFERENCES portails(id),
            type VARCHAR(50),
            valeur VARCHAR(255),
            executee BOOLEAN DEFAULT FALSE,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS codes (
            id SERIAL PRIMARY KEY,
            portail_id INTEGER REFERENCES portails(id),
            nom VARCHAR(100),
            contenu TEXT,
            cree_par INTEGER REFERENCES utilisateurs(id),
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS badges (
            id SERIAL PRIMARY KEY,
            portail_id INTEGER REFERENCES portails(id),
            uid VARCHAR(100) NOT NULL,
            nom VARCHAR(100) DEFAULT 'Inconnu',
            autorise BOOLEAN DEFAULT FALSE,
            date_scan TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portail_id, uid)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS empreintes (
            id SERIAL PRIMARY KEY,
            portail_id INTEGER REFERENCES portails(id),
            id_capteur INTEGER NOT NULL,
            nom VARCHAR(100) DEFAULT 'Inconnu',
            date_enregistrement TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(portail_id, id_capteur)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS logs_acces (
            id SERIAL PRIMARY KEY,
            portail_id INTEGER REFERENCES portails(id),
            type VARCHAR(50),
            identifiant VARCHAR(100),
            nom VARCHAR(100),
            acces_accorde BOOLEAN,
            date_acces TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()

# ─────────────────────────────────────────
# DÉCORATEURS
# ─────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Non connecté"}), 401
        return f(*args, **kwargs)
    return decorated

def chef_ou_droit_requis(droit):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({"error": "Non connecté"}), 401
            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT role, portail_id, approuve FROM utilisateurs WHERE id = %s", (session['user_id'],))
            user = cur.fetchone()
            if not user or not user[2]:
                cur.close()
                conn.close()
                return jsonify({"error": "Compte non approuvé"}), 403
            role, portail_id = user[0], user[1]
            if role in ('admin', 'chef'):
                cur.close()
                conn.close()
                return f(*args, **kwargs)
            cur.execute(
                "SELECT id FROM droits WHERE utilisateur_id = %s AND portail_id = %s AND droit = %s",
                (session['user_id'], portail_id, droit)
            )
            if cur.fetchone():
                cur.close()
                conn.close()
                return f(*args, **kwargs)
            cur.close()
            conn.close()
            return jsonify({"error": "Droits insuffisants"}), 403
        return decorated
    return decorator

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Non connecté"}), 401
        if session.get('role') != 'admin':
            return jsonify({"error": "Accès réservé à l'admin"}), 403
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────
# PAGE PRINCIPALE
# ─────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

# ─────────────────────────────────────────
# AUTH — INSCRIPTION
# ─────────────────────────────────────────
@app.route('/api/auth/inscription', methods=['POST'])
def inscription():
    data = request.json
    identifiant  = data.get('identifiant', '').strip()
    mot_de_passe = data.get('mot_de_passe', '')
    code_portail = data.get('code_portail', '').strip().upper()

    if not identifiant or not mot_de_passe or not code_portail:
        return jsonify({"error": "Tous les champs sont obligatoires"}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id FROM portails WHERE code_unique = %s", (code_portail,))
    portail = cur.fetchone()
    if not portail:
        cur.close()
        conn.close()
        return jsonify({"error": "Code portail invalide"}), 404

    portail_id = portail[0]

    cur.execute("SELECT id FROM utilisateurs WHERE identifiant = %s", (identifiant,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "Identifiant déjà utilisé"}), 409

    mdp_hash = bcrypt.hashpw(mot_de_passe.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    cur.execute("SELECT COUNT(*) FROM utilisateurs WHERE portail_id = %s", (portail_id,))
    count = cur.fetchone()[0]
    est_premier = count == 0
    role    = 'chef' if est_premier else 'habitant'
    approuve = True if est_premier else False

    cur.execute(
        "INSERT INTO utilisateurs (identifiant, mot_de_passe_hash, portail_id, role, approuve) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (identifiant, mdp_hash, portail_id, role, approuve)
    )

    if est_premier:
        cur.execute(
            "INSERT INTO mode_actuel (portail_id, mode) VALUES (%s, 'STANDBY') ON CONFLICT (portail_id) DO NOTHING",
            (portail_id,)
        )

    conn.commit()
    cur.close()
    conn.close()

    if est_premier:
        return jsonify({"status": "ok", "message": "Compte créé ! Vous êtes Chef de maison.", "role": "chef"})
    return jsonify({"status": "ok", "message": "Compte créé ! En attente d'approbation du Chef de maison.", "role": "habitant"})

# ─────────────────────────────────────────
# AUTH — CONNEXION
# ─────────────────────────────────────────
@app.route('/api/auth/connexion', methods=['POST'])
def connexion():
    data = request.json
    identifiant  = data.get('identifiant', '').strip()
    mot_de_passe = data.get('mot_de_passe', '')

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, mot_de_passe_hash, role, approuve, portail_id FROM utilisateurs WHERE identifiant = %s",
        (identifiant,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return jsonify({"error": "Identifiant ou mot de passe incorrect"}), 401
    if not bcrypt.checkpw(mot_de_passe.encode('utf-8'), user[1].encode('utf-8')):
        return jsonify({"error": "Identifiant ou mot de passe incorrect"}), 401
    if not user[3] and user[2] != 'admin':
        return jsonify({"error": "Votre compte est en attente d'approbation"}), 403

    session['user_id']   = user[0]
    session['role']      = user[2]
    session['portail_id'] = user[4]

    return jsonify({"status": "ok", "role": user[2], "portail_id": user[4]})

# ─────────────────────────────────────────
# AUTH — DÉCONNEXION
# ─────────────────────────────────────────
@app.route('/api/auth/deconnexion', methods=['POST'])
def deconnexion():
    session.clear()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# AUTH — QUI SUIS-JE ?
# ─────────────────────────────────────────
@app.route('/api/auth/moi', methods=['GET'])
@login_required
def moi():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT identifiant, role, portail_id, date_inscription FROM utilisateurs WHERE id = %s",
        (session['user_id'],)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({"identifiant": user[0], "role": user[1], "portail_id": user[2], "inscription": str(user[3])})

# ─────────────────────────────────────────
# CHEF — GÉRER LES UTILISATEURS
# ─────────────────────────────────────────
@app.route('/api/utilisateurs/en_attente', methods=['GET'])
@login_required
def utilisateurs_en_attente():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, identifiant, date_inscription FROM utilisateurs WHERE portail_id = %s AND approuve = FALSE",
        (session['portail_id'],)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "identifiant": r[1], "inscription": str(r[2])} for r in rows])

@app.route('/api/utilisateurs/<int:user_id>/approuver', methods=['POST'])
@login_required
def approuver_utilisateur(user_id):
    if session.get('role') not in ('chef', 'admin'):
        return jsonify({"error": "Droits insuffisants"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE utilisateurs SET approuve = TRUE WHERE id = %s AND portail_id = %s",
        (user_id, session['portail_id'])
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/utilisateurs/<int:user_id>/refuser', methods=['POST'])
@login_required
def refuser_utilisateur(user_id):
    if session.get('role') not in ('chef', 'admin'):
        return jsonify({"error": "Droits insuffisants"}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM utilisateurs WHERE id = %s AND portail_id = %s",
        (user_id, session['portail_id'])
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/utilisateurs/<int:user_id>/droits', methods=['POST'])
@login_required
def accorder_droit(user_id):
    if session.get('role') not in ('chef', 'admin'):
        return jsonify({"error": "Droits insuffisants"}), 403
    data = request.json
    droit = data.get('droit')
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO droits (utilisateur_id, portail_id, droit, accorde_par) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (user_id, session['portail_id'], droit, session['user_id'])
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# MODE ESP32
# ─────────────────────────────────────────
@app.route('/api/mode', methods=['GET'])
@login_required
def get_mode():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT mode, date_changement FROM mode_actuel WHERE portail_id = %s", (session['portail_id'],))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return jsonify({"mode": "STANDBY", "depuis": ""})
    return jsonify({"mode": row[0], "depuis": str(row[1])})

@app.route('/api/mode', methods=['POST'])
@chef_ou_droit_requis('scan')
def set_mode():
    data = request.json
    mode = data.get('mode', 'STANDBY')
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE mode_actuel SET mode = %s, date_changement = %s WHERE portail_id = %s",
        (mode, datetime.now(), session['portail_id'])
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok", "mode": mode})

# ─────────────────────────────────────────
# PULSE
# ─────────────────────────────────────────
@app.route('/api/pulse', methods=['POST'])
@chef_ou_droit_requis('pulse')
def pulse():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO commandes (portail_id, type, valeur) VALUES (%s, %s, %s)",
        (session['portail_id'], 'PULSE', '500')
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# COMMANDES PENDING (pour l'ESP32)
# ─────────────────────────────────────────
@app.route('/api/commandes/pending', methods=['GET'])
def get_commandes_pending():
    code_portail = request.args.get('portail', '').upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM portails WHERE code_unique = %s", (code_portail,))
    portail = cur.fetchone()
    if not portail:
        return jsonify({"type": "RIEN"})
    cur.execute(
        "SELECT id, type, valeur FROM commandes WHERE portail_id = %s AND executee = FALSE ORDER BY date_creation ASC LIMIT 1",
        (portail[0],)
    )
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE commandes SET executee = TRUE WHERE id = %s", (row[0],))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"id": row[0], "type": row[1], "valeur": row[2]})
    cur.close()
    conn.close()
    return jsonify({"type": "RIEN"})

# ─────────────────────────────────────────
# MODE PENDING (pour l'ESP32)
# ─────────────────────────────────────────
@app.route('/api/mode/pending', methods=['GET'])
def get_mode_pending():
    code_portail = request.args.get('portail', '').upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT m.mode FROM mode_actuel m JOIN portails p ON m.portail_id = p.id WHERE p.code_unique = %s",
        (code_portail,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return jsonify({"mode": row[0]})
    return jsonify({"mode": "STANDBY"})

# ─────────────────────────────────────────
# BADGES
# ─────────────────────────────────────────
@app.route('/api/badges', methods=['GET'])
@login_required
def get_badges():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, uid, nom, autorise, date_scan FROM badges WHERE portail_id = %s ORDER BY date_scan DESC",
        (session['portail_id'],)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "uid": r[1], "nom": r[2], "autorise": r[3], "date": str(r[4])} for r in rows])

@app.route('/api/badges', methods=['POST'])
def add_badge():
    data = request.json
    uid = data.get('uid')
    code_portail = data.get('portail', '').upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM portails WHERE code_unique = %s", (code_portail,))
    portail = cur.fetchone()
    if not portail:
        return jsonify({"error": "Portail inconnu"}), 404
    portail_id = portail[0]
    cur.execute("SELECT id, nom, autorise FROM badges WHERE uid = %s AND portail_id = %s", (uid, portail_id))
    badge = cur.fetchone()
    if badge:
        cur.execute(
            "INSERT INTO logs_acces (portail_id, type, identifiant, nom, acces_accorde) VALUES (%s, %s, %s, %s, %s)",
            (portail_id, 'BADGE', uid, badge[1], badge[2])
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"connu": True, "nom": badge[1], "autorise": badge[2]})
    cur.execute(
        "INSERT INTO badges (portail_id, uid, nom, autorise) VALUES (%s, %s, %s, %s)",
        (portail_id, uid, 'Inconnu', False)
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"connu": False, "message": "Nouveau badge enregistré"})

@app.route('/api/badges/<int:badge_id>', methods=['PUT'])
@chef_ou_droit_requis('badges')
def update_badge(badge_id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE badges SET nom = %s, autorise = %s WHERE id = %s AND portail_id = %s",
        (data.get('nom'), data.get('autorise', False), badge_id, session['portail_id'])
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# EMPREINTES
# ─────────────────────────────────────────
@app.route('/api/empreintes', methods=['GET'])
@login_required
def get_empreintes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, id_capteur, nom, date_enregistrement FROM empreintes WHERE portail_id = %s ORDER BY date_enregistrement DESC",
        (session['portail_id'],)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "id_capteur": r[1], "nom": r[2], "date": str(r[3])} for r in rows])

@app.route('/api/empreintes', methods=['POST'])
def add_empreinte():
    data = request.json
    code_portail = data.get('portail', '').upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM portails WHERE code_unique = %s", (code_portail,))
    portail = cur.fetchone()
    if not portail:
        return jsonify({"error": "Portail inconnu"}), 404
    cur.execute(
        "INSERT INTO empreintes (portail_id, id_capteur, nom) VALUES (%s, %s, %s) ON CONFLICT (portail_id, id_capteur) DO UPDATE SET nom = %s",
        (portail[0], data['id_capteur'], data.get('nom', 'Inconnu'), data.get('nom', 'Inconnu'))
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# CODES
# ─────────────────────────────────────────
@app.route('/api/codes', methods=['GET'])
@login_required
def get_codes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, nom, contenu, date_creation FROM codes WHERE portail_id = %s ORDER BY date_creation DESC",
        (session['portail_id'],)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "nom": r[1], "contenu": r[2], "date": str(r[3])} for r in rows])

@app.route('/api/codes', methods=['POST'])
@chef_ou_droit_requis('codes')
def add_code():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO codes (portail_id, nom, contenu, cree_par) VALUES (%s, %s, %s, %s)",
        (session['portail_id'], data['nom'], data['contenu'], session['user_id'])
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# LOGS
# ─────────────────────────────────────────
@app.route('/api/logs', methods=['GET'])
@login_required
def get_logs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, type, identifiant, nom, acces_accorde, date_acces FROM logs_acces WHERE portail_id = %s ORDER BY date_acces DESC LIMIT 50",
        (session['portail_id'],)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "type": r[1], "identifiant": r[2], "nom": r[3], "acces_accorde": r[4], "date": str(r[5])} for r in rows])

# ─────────────────────────────────────────
# ADMIN — PORTAILS
# ─────────────────────────────────────────
@app.route('/api/admin/portails', methods=['GET'])
@admin_required
def admin_get_portails():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT p.id, p.code_unique, p.nom, p.date_creation,
               COUNT(u.id) as nb_utilisateurs
        FROM portails p
        LEFT JOIN utilisateurs u ON u.portail_id = p.id
        GROUP BY p.id
        ORDER BY p.date_creation DESC
    ''')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{
        "id": r[0], "code_unique": r[1], "nom": r[2],
        "date": str(r[3]), "nb_utilisateurs": r[4]
    } for r in rows])

@app.route('/api/admin/portails', methods=['POST'])
@admin_required
def admin_create_portail():
    data = request.json
    code = data.get('code_unique', '').strip().upper()
    nom  = data.get('nom', 'Nouveau Portail').strip()
    if not code:
        return jsonify({"error": "Code unique obligatoire"}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO portails (code_unique, nom) VALUES (%s, %s) RETURNING id",
            (code, nom)
        )
        portail_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO mode_actuel (portail_id, mode) VALUES (%s, 'STANDBY')",
            (portail_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "id": portail_id})
    except Exception:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({"error": "Code déjà utilisé"}), 409

@app.route('/api/admin/portails/<int:portail_id>', methods=['DELETE'])
@admin_required
def admin_delete_portail(portail_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM logs_acces   WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM empreintes   WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM badges       WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM codes        WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM commandes    WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM mode_actuel  WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM droits       WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM utilisateurs WHERE portail_id = %s", (portail_id,))
    cur.execute("DELETE FROM portails     WHERE id = %s",         (portail_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# ADMIN — UTILISATEURS
# ─────────────────────────────────────────
@app.route('/api/admin/utilisateurs', methods=['GET'])
@admin_required
def admin_get_utilisateurs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT u.id, u.identifiant, u.role, u.approuve,
               u.date_inscription, p.nom, p.code_unique
        FROM utilisateurs u
        LEFT JOIN portails p ON u.portail_id = p.id
        ORDER BY u.date_inscription DESC
    ''')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{
        "id": r[0], "identifiant": r[1], "role": r[2],
        "approuve": r[3], "date": str(r[4]),
        "portail_nom": r[5], "portail_code": r[6]
    } for r in rows])

@app.route('/api/admin/utilisateurs/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_utilisateur(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM droits       WHERE utilisateur_id = %s", (user_id,))
    cur.execute("DELETE FROM utilisateurs WHERE id = %s",             (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/admin/utilisateurs/<int:user_id>/promouvoir', methods=['POST'])
@admin_required
def admin_promouvoir(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE utilisateurs SET role = 'chef' WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/admin/utilisateurs/<int:user_id>/reset-mdp', methods=['POST'])
@admin_required
def admin_reset_mdp(user_id):
    data    = request.json
    nouveau = data.get('mot_de_passe', '')
    if not nouveau:
        return jsonify({"error": "Mot de passe vide"}), 400
    mdp_hash = bcrypt.hashpw(nouveau.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE utilisateurs SET mot_de_passe_hash = %s WHERE id = %s",
        (mdp_hash, user_id)
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "ok"})

# ─────────────────────────────────────────
# ADMIN — LOGS GLOBAUX
# ─────────────────────────────────────────
@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def admin_get_logs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        SELECT l.id, l.type, l.identifiant, l.nom,
               l.acces_accorde, l.date_acces,
               p.nom, p.code_unique
        FROM logs_acces l
        LEFT JOIN portails p ON l.portail_id = p.id
        ORDER BY l.date_acces DESC
        LIMIT 100
    ''')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{
        "id": r[0], "type": r[1], "identifiant": r[2],
        "nom": r[3], "acces_accorde": r[4], "date": str(r[5]),
        "portail_nom": r[6], "portail_code": r[7]
    } for r in rows])

# ─────────────────────────────────────────
# ROUTE SETUP ADMIN — SUPPRIMER APRÈS USAGE
# ─────────────────────────────────────────
@app.route('/setup-admin', methods=['GET'])
def setup_admin():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM utilisateurs WHERE identifiant = 'admin'"
    )
    if cur.fetchone():
        cur.close()
        conn.close()
        return "Compte admin déjà existant !"
    mdp = "AdminPortail2025!"
    mdp_hash = bcrypt.hashpw(mdp.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cur.execute(
        "INSERT INTO utilisateurs (identifiant, mot_de_passe_hash, portail_id, role, approuve) VALUES ('admin', %s, NULL, 'admin', TRUE)",
        (mdp_hash,)
    )
    conn.commit()
    cur.close()
    conn.close()
    return "Compte admin cree ! Identifiant : admin / Mot de passe : AdminPortail2025!"

# ─────────────────────────────────────────
# LANCEMENT
# ─────────────────────────────────────────
with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)
