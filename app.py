# -*- coding: utf-8 -*-
"""
LHP AKPOL — free version.

Design decisions (see Devnotes.md for the full reasoning trail from the
previous paid iteration of this project):
  - No tokens, no payment, no gating. Anyone with an account can generate
    unlimited documents.
  - Login exists ONLY so usage can be attributed to a person for the admin
    activity log. Registration is instant self-serve (username + password),
    no email/Google verification required.
  - Every request that creates a document is logged to activity_log.json.
  - users.json / activity_log.json / visitors.json live under data/ and are
    written atomically (temp file + os.replace) to survive a crash mid-write.
"""
import os
import io
import json
import uuid
import threading
import tempfile
from datetime import datetime, date

from flask import (
    Flask, request, redirect, url_for, session, render_template,
    send_file, jsonify, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

import lhp_core as lc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "tmp_uploads")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

USERS_PATH = os.path.join(DATA_DIR, "users.json")
ACTIVITY_PATH = os.path.join(DATA_DIR, "activity_log.json")
VISITORS_PATH = os.path.join(DATA_DIR, "visitors.json")

_lock = threading.Lock()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
# Reject oversized uploads before they exhaust memory; surfaced as a clean
# message via the 413 handler rather than a dropped connection.
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # 40 MB total per request

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

MAX_ACTIVITY_ENTRIES = 5000  # trim old entries so the file doesn't grow forever


# ---------------------------------------------------------------------------
# Atomic JSON read/write helpers
# ---------------------------------------------------------------------------
def _atomic_write(path, data):
    with _lock:
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def load_users():
    return _read_json(USERS_PATH, {})


def save_users(users):
    _atomic_write(USERS_PATH, users)


def load_activity():
    return _read_json(ACTIVITY_PATH, [])


def log_activity(username, action, detail=None):
    with _lock:
        entries = _read_json(ACTIVITY_PATH, [])
        entries.append({
            "username": username,
            "action": action,
            "detail": detail or {},
            "ip": request.remote_addr,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        entries = entries[-MAX_ACTIVITY_ENTRIES:]
    _atomic_write(ACTIVITY_PATH, entries)


def load_visitors():
    return _read_json(VISITORS_PATH, {"total": 0, "by_day": {}})


def record_visit():
    with _lock:
        v = _read_json(VISITORS_PATH, {"total": 0, "by_day": {}})
        today = date.today().isoformat()
        v["total"] = v.get("total", 0) + 1
        v.setdefault("by_day", {})
        v["by_day"][today] = v["by_day"].get(today, 0) + 1
    _atomic_write(VISITORS_PATH, v)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    users = load_users()
    return users.get(uid)


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "uid" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Sesi habis, silakan login ulang.", "redirect": "/login"}), 401
            return redirect(url_for("login"))

        # A session cookie can outlive the account it points at -- after a
        # redeploy without a persistent volume, or if an admin deleted the
        # user. Treat that as logged out instead of letting the view crash on
        # a None user.
        if current_user() is None:
            session.clear()
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Sesi tidak berlaku lagi, silakan login ulang.",
                                "redirect": "/login"}), 401
            return redirect(url_for("login"))

        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("login_admin"))
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# Public / auth routes
# ---------------------------------------------------------------------------
@app.route("/")
def root():
    if "uid" in session:
        return redirect(url_for("index"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    nama = (request.form.get("nama") or "").strip()
    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""

    if not nama or not username or not password:
        return render_template("register.html", error="Semua field wajib diisi.")
    if len(username) < 3 or not username.replace("_", "").replace(".", "").isalnum():
        return render_template("register.html", error="Username minimal 3 karakter, huruf/angka/._ saja.")
    if len(password) < 6:
        return render_template("register.html", error="Password minimal 6 karakter.")
    if password != confirm:
        return render_template("register.html", error="Konfirmasi password tidak cocok.")

    users = load_users()
    if username in users:
        return render_template("register.html", error="Username sudah dipakai, pilih yang lain.")

    uid = username
    users[uid] = {
        "uid": uid,
        "username": username,
        "nama": nama,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "role": "user",
    }
    save_users(users)
    session["uid"] = uid
    session["role"] = "user"
    log_activity(username, "register")
    return redirect(url_for("index"))


@app.route("/check-username")
def check_username():
    username = (request.args.get("username") or "").strip().lower()
    users = load_users()
    available = bool(username) and username not in users and len(username) >= 3
    return jsonify({"available": available})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "uid" in session:
            return redirect(url_for("index"))
        return render_template("login.html")

    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    users = load_users()
    user = users.get(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Username atau password salah.")

    session["uid"] = user["uid"]
    session["role"] = user.get("role", "user")
    log_activity(username, "login")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    user = current_user()
    if user:
        log_activity(user["username"], "logout")
    session.clear()
    return redirect(url_for("login"))


@app.route("/login-admin", methods=["GET", "POST"])
def login_admin():
    if request.method == "GET":
        return render_template("admin_login.html")
    username = request.form.get("username") or ""
    password = request.form.get("password") or ""
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session["uid"] = "__admin__"
        session["role"] = "admin"
        return redirect(url_for("admin_panel"))
    return render_template("admin_login.html", error="Username atau password admin salah.")


# ---------------------------------------------------------------------------
# Main form
# ---------------------------------------------------------------------------
@app.route("/health")
def health():
    """Diagnostic endpoint -- open this in the browser if something breaks."""
    tingkat_loaded = lc.available_tingkat()   # must run before reading ROSTER_ERROR
    checks = {
        "excel_roster": os.path.exists(lc.EXCEL_PATH),
        "word_template": os.path.exists(lc.TEMPLATE_PATH),
        "logo": os.path.exists(os.path.join(BASE_DIR, "static", "logo_akpol.png")),
        "data_dir_writable": os.access(DATA_DIR, os.W_OK),
        "tingkat_loaded": tingkat_loaded,
        "roster_error": lc.ROSTER_ERROR,
        "users_registered": len(load_users()),
    }
    checks["ok"] = all([
        checks["excel_roster"], checks["word_template"],
        checks["data_dir_writable"], tingkat_loaded,
    ])
    return jsonify(checks), (200 if checks["ok"] else 503)


@app.route("/app")
@login_required
def index():
    user = current_user()
    record_visit()
    # Load the roster FIRST -- lc.ROSTER_ERROR is only set as a side effect of
    # reading the workbook, so reading it earlier would always give None.
    tingkat_list = [
        {"value": t, **lc.TINGKAT_CONFIG[t]} for t in lc.available_tingkat()
    ]
    return render_template(
        "index.html",
        user=user,
        defaults=user.get("defaults", {}),
        roster_error=lc.ROSTER_ERROR,
        tingkat_list=tingkat_list,
        kompi_list=lc.kompi_letters("2"),
        peleton_list=lc.peleton_numbers(),
        pangkat_list=lc.PANGKAT_LIST,
    )


@app.route("/api/lookup")
@login_required
def api_lookup():
    tingkat = request.args.get("tingkat", "")
    kompi = (request.args.get("kompi", "") or "").upper()
    peleton = request.args.get("peleton", "")
    if tingkat not in lc.TINGKAT_CONFIG or not kompi:
        return jsonify({"error": "Parameter tidak lengkap"}), 400
    danton = lc.lookup_danton(tingkat, peleton, kompi) if peleton else None
    danki = lc.lookup_danki(tingkat, kompi)
    return jsonify({"danton": danton, "danki": danki})


REQUIRED_FIELDS = [
    "tingkat", "kompi", "peleton", "nama_taruna", "no_akademi", "pangkat",
    "nama_kegiatan", "tanggal", "waktu", "tempat",
]


@app.route("/api/generate", methods=["POST"])
@login_required
def api_generate():
    user = current_user()
    form = {k: (request.form.get(k) or "").strip() for k in REQUIRED_FIELDS}
    form["lokasi_ttd"] = (request.form.get("lokasi_ttd") or "Semarang").strip()

    missing = [f for f in REQUIRED_FIELDS if not form[f]]
    if missing:
        return jsonify({"error": f"Field wajib belum diisi: {', '.join(missing)}"}), 400
    if form["tingkat"] not in lc.TINGKAT_CONFIG:
        return jsonify({"error": "Tingkat tidak valid"}), 400

    # Manual override support: if the client marked komando as manually
    # edited, use what they typed instead of the roster lookup.
    if request.form.get("danton_manual") == "1":
        form["danton_override"] = {
            "nama": request.form.get("danton_nama", ""),
            "pangkat": request.form.get("danton_pangkat", ""),
            "nrp": request.form.get("danton_nrp", ""),
        }
    if request.form.get("danki_manual") == "1":
        form["danki_override"] = {
            "nama": request.form.get("danki_nama", ""),
            "pangkat": request.form.get("danki_pangkat", ""),
            "nrp": request.form.get("danki_nrp", ""),
            "signature_kompi": form["kompi"].upper(),
        }

    photos = request.files.getlist("foto")
    photo_paths = []
    job_id = uuid.uuid4().hex
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    try:
        for i, f in enumerate(photos):
            if not f or not f.filename:
                continue
            path = os.path.join(job_dir, f"foto_{i}{os.path.splitext(f.filename)[1] or '.jpg'}")
            f.save(path)
            photo_paths.append(path)

        safe_name = "".join(c for c in form["nama_taruna"] if c.isalnum() or c in " _-").strip().replace(" ", "_")
        safe_kegiatan = "".join(c for c in form["nama_kegiatan"] if c.isalnum() or c in " _-").strip().replace(" ", "_")
        out_name = f"LHP_{safe_name}_{safe_kegiatan}.docx"
        out_path = os.path.join(job_dir, out_name)

        lc.generate_document(form, photo_paths, out_path)

        log_activity(user["username"], "generate", {
            "nama_taruna": form["nama_taruna"],
            "kegiatan": form["nama_kegiatan"],
            "tingkat": form["tingkat"],
            "kompi": form["kompi"],
            "peleton": form["peleton"],
            "tanggal": form["tanggal"],
        })

        # Remember the parts that don't change between reports, so the next
        # document starts mostly filled in. Kegiatan/tanggal/waktu/tempat are
        # deliberately NOT remembered -- they differ every time.
        users = load_users()
        if user["uid"] in users:
            users[user["uid"]]["defaults"] = {
                "nama_taruna": form["nama_taruna"],
                "no_akademi": form["no_akademi"],
                "pangkat": form["pangkat"],
                "tingkat": form["tingkat"],
                "kompi": form["kompi"],
                "peleton": form["peleton"],
                "lokasi_ttd": form["lokasi_ttd"],
            }
            save_users(users)

        return send_file(out_path, as_attachment=True, download_name=out_name)
    except Exception as e:
        app.logger.exception("generate failed")
        return jsonify({"error": f"Gagal membuat dokumen: {e}"}), 500


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_panel():
    users = load_users()
    activity = load_activity()
    visitors = load_visitors()

    # per-user generate counts and last activity
    gen_counts = {}
    last_seen = {}
    for entry in activity:
        u = entry["username"]
        if entry["action"] == "generate":
            gen_counts[u] = gen_counts.get(u, 0) + 1
        last_seen[u] = entry["timestamp"]

    user_rows = []
    for uid, u in users.items():
        user_rows.append({
            "uid": uid,
            "username": u["username"],
            "nama": u.get("nama", ""),
            "created_at": u.get("created_at", ""),
            "last_seen": last_seen.get(u["username"], ""),
            "generate_count": gen_counts.get(u["username"], 0),
        })
    user_rows.sort(key=lambda r: (r["generate_count"], r["created_at"]), reverse=True)

    recent_activity = list(reversed(activity[-200:]))
    today_str = date.today().isoformat()
    generated_today = sum(
        1 for e in activity
        if e["action"] == "generate" and e["timestamp"].startswith(today_str)
    )

    return render_template(
        "admin.html",
        users=user_rows,
        activity=recent_activity,
        visitors=visitors,
        total_users=len(users),
        total_generated=sum(gen_counts.values()),
        generated_today=generated_today,
    )


@app.route("/api/admin/delete-user", methods=["POST"])
@admin_required
def admin_delete_user():
    uid = request.json.get("uid")
    users = load_users()
    if uid in users:
        del users[uid]
        save_users(users)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/api/admin/reset-password", methods=["POST"])
@admin_required
def admin_reset_password():
    uid = request.json.get("uid")
    new_password = request.json.get("password") or ""
    if len(new_password) < 6:
        return jsonify({"ok": False, "error": "Password minimal 6 karakter"}), 400
    users = load_users()
    if uid not in users:
        return jsonify({"ok": False, "error": "not found"}), 404
    users[uid]["password_hash"] = generate_password_hash(new_password)
    save_users(users)
    return jsonify({"ok": True})


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("login_admin"))


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html",
                           code="404",
                           title="Halaman tidak ditemukan",
                           message="Alamat yang kamu buka tidak ada. Periksa kembali tautannya."), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.exception("unhandled server error")
    return render_template("error.html",
                           code="500",
                           title="Terjadi gangguan di server",
                           message="Coba muat ulang halaman. Kalau masih bermasalah, hubungi admin."), 500


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "Total ukuran foto terlalu besar. Kurangi jumlah atau ukuran foto."}), 413


@app.errorhandler(404)
def page_not_found(e):
    logged_in = "uid" in session
    return render_template(
        "error.html",
        code="404",
        title="Halaman tidak ditemukan",
        message="Alamat yang Anda buka tidak ada. Periksa kembali tautannya.",
        back_url="/app" if logged_in else "/login",
        back_label="Kembali ke formulir" if logged_in else "Ke halaman masuk",
    ), 404


@app.errorhandler(500)
def server_error(e):
    app.logger.exception("unhandled server error")
    logged_in = "uid" in session
    return render_template(
        "error.html",
        code="500",
        title="Terjadi kesalahan di server",
        message="Kesalahan sudah dicatat. Coba ulangi beberapa saat lagi.",
        back_url="/app" if logged_in else "/login",
        back_label="Kembali ke formulir" if logged_in else "Ke halaman masuk",
    ), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
