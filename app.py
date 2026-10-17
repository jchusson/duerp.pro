import io
import os
import sys

from flask import (
    Flask, abort, flash, g, redirect, render_template,
    request, session, send_file, url_for,
)
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database
import exports

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

FREQ = [1, 2, 3, 4]
SEV = [1, 2, 4, 8]
MASTERY = [0.5, 1, 2]


@app.before_request
def before_request():
    database.init_db()
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = database.get_user(user_id)


def login_required(f):
    def wrapper(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


def admin_required(f):
    def wrapper(*args, **kwargs):
        if not g.get("user") or g.user["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


def current_client():
    user = g.get("user")
    if not user:
        return None
    client_id = session.get("client_id")
    clients = database.user_clients(user)
    if not clients:
        return None
    if client_id:
        for c in clients:
            if c["id"] == client_id:
                return c
    session["client_id"] = clients[0]["id"]
    return clients[0]


# ---------------- Auth ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = database.verify_user(request.form.get("email", "").strip().lower(), request.form.get("password", ""))
        if not user:
            flash("Identifiants incorrects.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _load_units(client_id):
    """Charge les UT avec risques, mesures et actions de prévention."""
    conn = database.get_db()
    units = [dict(u) for u in conn.execute(
        "SELECT * FROM work_units WHERE client_id = ? ORDER BY position, id", (client_id,)
    ).fetchall()]
    for u in units:
        u["risks"] = [dict(r) for r in conn.execute(
            "SELECT * FROM risks WHERE work_unit_id = ? ORDER BY id", (u["id"],)
        ).fetchall()]
        for r in u["risks"]:
            r["measures"] = [dict(m) for m in conn.execute(
                "SELECT * FROM measures WHERE risk_id = ? ORDER BY id", (r["id"],)
            ).fetchall()]
            r["actions"] = [dict(m) for m in conn.execute(
                "SELECT * FROM actions WHERE risk_id = ? ORDER BY id", (r["id"],)
            ).fetchall()]
    conn.close()
    return units


def crit_value(r):
    return r["frequency"] * r["severity"] * r["mastery"]


@app.route("/")
@login_required
def home():
    client = current_client()
    if not client:
        if g.user["role"] == "admin":
            return redirect(url_for("admin"))
        return render_template("no_client.html")
    q = request.args.get("q", "").strip().lower()
    crit_level = request.args.get("crit", "")
    unit_filter = request.args.get("unit", "")
    units = _load_units(client["id"])
    count_risks = sum(len(u["risks"]) for u in units)
    conn = database.get_db()
    actions_plan = conn.execute(
        "SELECT a.*, w.name AS work_unit FROM action_items a "
        "LEFT JOIN work_units w ON w.id = a.work_unit_id "
        "WHERE a.client_id = ? ORDER BY a.id DESC", (client["id"],)
    ).fetchall()
    conn.close()

    # --- filtres ---
    units_shown = units
    filters_active = bool(q or crit_level or unit_filter)
    if filters_active:
        try:
            unit_id_int = int(unit_filter) if unit_filter else None
        except ValueError:
            unit_id_int = None
        for u in units_shown:
            if unit_id_int and u["id"] != unit_id_int:
                u["risks"] = []
                continue
            kept = []
            for r in u["risks"]:
                if q:
                    texts = [u["name"], r["hazard"], r["situation"],
                             " ".join(m["text"] for m in r["measures"]),
                             " ".join(a["text"] for a in r["actions"])]
                    if q not in " ".join(texts).lower():
                        continue
                v = crit_value(r)
                if crit_level == "low" and v > 3:
                    continue
                if crit_level == "mid" and not (4 <= v <= 15):
                    continue
                if crit_level == "high" and v < 16:
                    continue
                kept.append(r)
            u["risks"] = kept
        units_shown = [u for u in units_shown if u["risks"]]

    high = sum(1 for u in units for r in u["risks"] if crit_value(r) >= 16)
    from risk_catalog import RISQUE_CATALOG
    return render_template(
        "home.html", client=client, units=units, actions=actions_plan,
        count_risks=count_risks, count_high=high,
        units_shown=units_shown,
        filters_active=filters_active,
        catalog=RISQUE_CATALOG,
        clients=database.user_clients(g.user),
    )


@app.route("/client/select/<int:client_id>", methods=["POST"])
@login_required
def select_client(client_id):
    if not database.user_has_client(g.user, client_id):
        abort(403)
    session["client_id"] = client_id
    return redirect(url_for("home"))


# ---------------- Unités de travail ----------------

@app.route("/work-units/add", methods=["POST"])
@login_required
def add_work_unit():
    client = current_client()
    if not client:
        abort(403)
    name = request.form.get("name", "").strip()
    if name:
        conn = database.get_db()
        conn.execute(
            "INSERT INTO work_units (client_id, name, position) VALUES (?,?,?)",
            (client["id"], name, request.form.get("position", 0) or 0),
        )
        conn.commit()
        conn.close()
    return redirect(url_for("home"))


@app.route("/work-units/<int:uid>/rename", methods=["POST"])
@login_required
def rename_work_unit(uid):
    client = current_client()
    if not client:
        abort(403)
    name = request.form.get("name", "").strip()
    if name:
        conn = database.get_db()
        conn.execute(
            "UPDATE work_units SET name = ? WHERE id = ? AND client_id = ?",
            (name, uid, client["id"]),
        )
        conn.commit()
        conn.close()
    return redirect(url_for("home"))


@app.route("/work-units/duplicate", methods=["POST"])
@login_required
def duplicate_work_unit_selected():
    """Formulaire « Dupliquer une UT » (sélecteur src)."""
    try:
        uid = int(request.form.get("src", ""))
    except (TypeError, ValueError):
        return redirect(url_for("home"))
    return duplicate_work_unit(uid)


@app.route("/work-units/<int:uid>/duplicate", methods=["POST"])
@login_required
def duplicate_work_unit(uid):
    client = current_client()
    if not client:
        abort(403)
    conn = database.get_db()
    src = conn.execute(
        "SELECT * FROM work_units WHERE id = ? AND client_id = ?", (uid, client["id"])
    ).fetchone()
    if not src:
        conn.close()
        abort(403)
    cur = conn.execute(
        "INSERT INTO work_units (client_id, name, position) VALUES (?,?,?)",
        (client["id"], src["name"] + " (copie)", src["position"]),
    )
    new_uid = cur.lastrowid
    risks = conn.execute("SELECT * FROM risks WHERE work_unit_id = ?", (uid,)).fetchall()
    for r in risks:
        cur = conn.execute(
            "INSERT INTO risks (work_unit_id, hazard, situation, frequency, severity, mastery) "
            "VALUES (?,?,?,?,?,?)",
            (new_uid, r["hazard"], r["situation"], r["frequency"], r["severity"], r["mastery"]),
        )
        new_rid = cur.lastrowid
        for m in conn.execute("SELECT * FROM measures WHERE risk_id = ?", (r["id"],)).fetchall():
            conn.execute("INSERT INTO measures (risk_id, text) VALUES (?,?)", (new_rid, m["text"]))
        for a in conn.execute("SELECT * FROM actions WHERE risk_id = ?", (r["id"],)).fetchall():
            conn.execute("INSERT INTO actions (risk_id, text) VALUES (?,?)", (new_rid, a["text"]))
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/work-units/<int:uid>/delete", methods=["POST"])
@login_required
def delete_work_unit(uid):
    client = current_client()
    if not client:
        abort(403)
    conn = database.get_db()
    conn.execute(
        "DELETE FROM work_units WHERE id = ? AND client_id = ?", (uid, client["id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


# ---------------- Risques ----------------

def _valid_risk_params():
    try:
        frequency = int(request.form.get("frequency"))
        severity = int(request.form.get("severity"))
        mastery = float(request.form.get("mastery"))
    except (TypeError, ValueError):
        abort(400)
    if frequency not in FREQ or severity not in SEV or mastery not in MASTERY:
        abort(400)
    return frequency, severity, mastery


@app.route("/risks/add", methods=["POST"])
@login_required
def add_risk():
    client = current_client()
    if not client:
        abort(403)
    try:
        work_unit_id = int(request.form.get("work_unit_id"))
    except (TypeError, ValueError):
        abort(400)
    frequency, severity, mastery = _valid_risk_params()
    conn = database.get_db()
    check = conn.execute(
        "SELECT id FROM work_units WHERE id = ? AND client_id = ?", (work_unit_id, client["id"])
    ).fetchone()
    if not check:
        conn.close()
        abort(403)
    cur = conn.execute(
        "INSERT INTO risks (work_unit_id, hazard, situation, frequency, severity, mastery) "
        "VALUES (?,?,?,?,?,?)",
        (work_unit_id, request.form.get("hazard", "").strip(),
         request.form.get("situation", "").strip(), frequency, severity, mastery),
    )
    new_rid = cur.lastrowid
    for m in request.form.getlist("measures[]"):
        if m.strip():
            conn.execute("INSERT INTO measures (risk_id, text) VALUES (?,?)", (new_rid, m.strip()))
    for a in request.form.getlist("actions[]"):
        if a.strip():
            conn.execute("INSERT INTO actions (risk_id, text) VALUES (?,?)", (new_rid, a.strip()))
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/risks/<int:rid>/update", methods=["POST"])
@login_required
def update_risk(rid):
    client = current_client()
    if not client:
        abort(403)
    frequency, severity, mastery = _valid_risk_params()
    conn = database.get_db()
    row = conn.execute(
        "SELECT id FROM risks WHERE id=? AND work_unit_id IN "
        "(SELECT id FROM work_units WHERE client_id=?)", (rid, client["id"])
    ).fetchone()
    if not row:
        conn.close()
        abort(403)
    conn.execute(
        "UPDATE risks SET hazard=?, situation=?, frequency=?, severity=?, mastery=? WHERE id=?",
        (request.form.get("hazard", "").strip(), request.form.get("situation", "").strip(),
         frequency, severity, mastery, rid),
    )
    if "measures[]" in request.form:
        conn.execute("DELETE FROM measures WHERE risk_id=?", (rid,))
        for m in request.form.getlist("measures[]"):
            if m.strip():
                conn.execute("INSERT INTO measures (risk_id, text) VALUES (?,?)", (rid, m.strip()))
    if "actions[]" in request.form:
        conn.execute("DELETE FROM actions WHERE risk_id=?", (rid,))
        for a in request.form.getlist("actions[]"):
            if a.strip():
                conn.execute("INSERT INTO actions (risk_id, text) VALUES (?,?)", (rid, a.strip()))
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/risks/<int:rid>/delete", methods=["POST"])
@login_required
def delete_risk(rid):
    client = current_client()
    if not client:
        abort(403)
    conn = database.get_db()
    conn.execute(
        "DELETE FROM risks WHERE id=? AND work_unit_id IN (SELECT id FROM work_units WHERE client_id=?)",
        (rid, client["id"]),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


# ---------------- Mesures et actions de prévention (lignes individuelles) ----------------

@app.route("/risks/<int:rid>/measures/add", methods=["POST"])
@login_required
def add_measure(rid):
    return _add_line(rid, "measures")


@app.route("/risks/<int:rid>/actions/add", methods=["POST"])
@login_required
def add_action_line(rid):
    return _add_line(rid, "actions")


def _add_line(rid, table):
    client = current_client()
    if not client:
        abort(403)
    text = request.form.get("text", "").strip()
    if not text:
        return redirect(url_for("home"))
    conn = database.get_db()
    row = conn.execute(
        "SELECT id FROM risks WHERE id=? AND work_unit_id IN "
        "(SELECT id FROM work_units WHERE client_id=?)", (rid, client["id"])
    ).fetchone()
    if row:
        conn.execute("INSERT INTO %s (risk_id, text) VALUES (?,?)" % table, (rid, text))
        conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/measures/<int:mid>/update", methods=["POST"])
@login_required
def update_measure(mid):
    return _update_line(mid, "measures")


@app.route("/actions/<int:aid>/update", methods=["POST"])
@login_required
def update_action_line(aid):
    return _update_line(aid, "actions")


def _update_line(line_id, table):
    client = current_client()
    if not client:
        abort(403)
    text = request.form.get("text", "").strip()
    conn = database.get_db()
    row = conn.execute(
        "SELECT l.id FROM %s l JOIN risks r ON r.id = l.risk_id "
        "JOIN work_units w ON w.id = r.work_unit_id WHERE l.id = ? AND w.client_id = ?" % table,
        (line_id, client["id"]),
    ).fetchone()
    if row:
        conn.execute("UPDATE %s SET text = ? WHERE id = ?" % table, (text, line_id))
        conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/measures/<int:mid>/delete", methods=["POST"])
@login_required
def delete_measure(mid):
    return _delete_line(mid, "measures")


@app.route("/actions/<int:aid>/delete", methods=["POST"])
@login_required
def delete_action_line(aid):
    return _delete_line(aid, "actions")


def _delete_line(line_id, table):
    client = current_client()
    if not client:
        abort(403)
    conn = database.get_db()
    conn.execute(
        "DELETE FROM %s WHERE id = ? AND risk_id IN "
        "(SELECT id FROM risks WHERE work_unit_id IN "
        "(SELECT id FROM work_units WHERE client_id = ?))" % table,
        (line_id, client["id"]),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


# ---------------- Plan d'action ----------------

@app.route("/actions/add", methods=["POST"])
@login_required
def add_action():
    client = current_client()
    if not client:
        abort(403)
    action = request.form.get("action", "").strip()
    if not action:
        return redirect(url_for("home"))
    work_unit_id = request.form.get("work_unit_id") or None
    conn = database.get_db()
    conn.execute(
        "INSERT INTO action_items (client_id, work_unit_id, action, priority, responsible, due_date, status, cost) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (client["id"], work_unit_id, action,
         request.form.get("priority", "Moyenne"), request.form.get("responsible", "").strip(),
         request.form.get("due_date", "").strip(), request.form.get("status", "À faire"),
         request.form.get("cost", "").strip()),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/actions/<int:aid>/update", methods=["POST"])
@login_required
def update_action(aid):
    client = current_client()
    if not client:
        abort(403)
    conn = database.get_db()
    conn.execute(
        "UPDATE action_items SET status=? WHERE id=? AND client_id=?",
        (request.form.get("status", "À faire"), aid, client["id"]),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


@app.route("/actions/<int:aid>/delete", methods=["POST"])
@login_required
def delete_action(aid):
    client = current_client()
    if not client:
        abort(403)
    conn = database.get_db()
    conn.execute("DELETE FROM action_items WHERE id=? AND client_id=?", (aid, client["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


# ---------------- Exports ----------------

def _load_export_data():
    client = current_client()
    if not client:
        abort(403)
    units = _load_units(client["id"])
    conn = database.get_db()
    actions = [dict(a) for a in conn.execute(
        "SELECT a.*, w.name AS work_unit FROM action_items a "
        "LEFT JOIN work_units w ON w.id = a.work_unit_id "
        "WHERE a.client_id = ? ORDER BY a.id", (client["id"],)
    ).fetchall()]
    conn.close()
    return client, units, actions


@app.route("/export/pdf")
@login_required
def export_pdf():
    client, units, actions = _load_export_data()
    buf = io.BytesIO()
    exports.build_pdf(client, units, actions, buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="DUERP_%s.pdf" % client["name"].replace(" ", "_"))


@app.route("/export/excel")
@login_required
def export_excel():
    client, units, actions = _load_export_data()
    buf = io.BytesIO()
    exports.build_excel(client, units, actions, buf)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="DUERP_%s.xlsx" % client["name"].replace(" ", "_"))


@app.route("/export/action-pdf")
@login_required
def export_action_pdf():
    client, _units, actions = _load_export_data()
    buf = io.BytesIO()
    exports.build_action_pdf(client, actions, buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="Plan_action_%s.pdf" % client["name"].replace(" ", "_"))


@app.route("/export/action-excel")
@login_required
def export_action_excel():
    client, _units, actions = _load_export_data()
    buf = io.BytesIO()
    exports.build_action_excel(client, actions, buf)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name="Plan_action_%s.xlsx" % client["name"].replace(" ", "_"))


# ---------------- Administration ----------------

@app.route("/admin")
@login_required
@admin_required
def admin():
    conn = database.get_db()
    clients = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    users = conn.execute("SELECT * FROM users ORDER BY email").fetchall()
    memberships = conn.execute("SELECT * FROM client_members").fetchall()
    conn.close()
    return render_template("admin.html", clients=clients, users=users, memberships=memberships)


@app.route("/admin/clients/add", methods=["POST"])
@login_required
@admin_required
def admin_add_client():
    name = request.form.get("name", "").strip()
    if name:
        conn = database.get_db()
        conn.execute("INSERT OR IGNORE INTO clients (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/users/add", methods=["POST"])
@login_required
@admin_required
def admin_add_user():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "user")
    if email and password and role in ("admin", "user"):
        conn = database.get_db()
        try:
            conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
                (email, generate_password_hash(password), request.form.get("full_name", "").strip(), role),
            )
            conn.commit()
        except Exception:
            flash("Cet email existe déjà.", "error")
        conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/members/add", methods=["POST"])
@login_required
@admin_required
def admin_add_member():
    try:
        user_id = int(request.form.get("user_id"))
        client_id = int(request.form.get("client_id"))
    except (TypeError, ValueError):
        abort(400)
    conn = database.get_db()
    conn.execute("INSERT OR IGNORE INTO client_members (client_id, user_id) VALUES (?,?)", (client_id, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/members/<int:mid>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_member(mid):
    conn = database.get_db()
    conn.execute("DELETE FROM client_members WHERE id = ?", (mid,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


if __name__ == "__main__":
    database.init_db()
    database.create_admin()
    app.run(debug=True, host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
