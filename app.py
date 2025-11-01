import os, sqlite3
from flask import (
    Flask, render_template, Response, jsonify, request, redirect, url_for,
    flash, session
)
from flask_talisman import Talisman
from werkzeug.utils import secure_filename
from flask_babel import Babel, _
from babel.numbers import parse_decimal
import json
import time
import os
import requests

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1410304352803098867/Cuj8e6ovn8Tj6AdXDlZ9bLmPuIRWo-GmsSf-F-S8l2fmgWQuiegWDeuidGBlNtHN-rCu"  # replace with your webhook URL

# --- App setup -------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "secret123"

Talisman(app, content_security_policy=None)

UPLOAD_FOLDER = "static/images"
DB_FILE = "farmshop.db"
ADMIN_PASSWORD = "admin123"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

import sqlite3
from flask import g

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row  # 👈 ensures dictionary-style access
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# --- Babel setup -----------------------------------------------------------
# Babel configuration
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"

babel = Babel(app)

# Define supported languages
LANGUAGES = ['en', 'pt']

def get_locale():
    # Use ?lang=xx or session['lang'] or default
    lang = request.args.get('lang')
    if lang:
        session['lang'] = lang
    return session.get('lang', 'en')

babel = Babel(app, locale_selector=get_locale)

LOCALE_MAP = {
    'en': 'en_US',
    'pt': 'pt_PT'
}

# @babel.localeselector
def get_user_locale():
    """Choose locale from session or browser preference."""
    # 1️⃣ If user has manually chosen a language, use it
    if 'lang' in session:
        return session['lang']

    # 2️⃣ Otherwise, detect from browser (Accept-Language header)
    browser_lang = request.accept_languages.best_match(LANGUAGES)

    # 3️⃣ Save it in session so next requests use the same
    session['lang'] = browser_lang or 'en'

    # 4️⃣ Return the selected locale
    return session['lang']

# Make get_locale available in all templates
from babel.numbers import format_currency

@app.context_processor
def inject_locale():
    """Make get_locale and format_currency available in all templates"""
    return dict(
        get_locale=get_user_locale,
        format_currency=format_currency  # <- this makes it usable in templates
    )

@app.route('/set_language/<lang>')
def set_language(lang):
    """Manually change app language."""
    if lang in LANGUAGES:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))

# --- Database setup -------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_display_order_column():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(item_images)")
    columns = [row[1] for row in cur.fetchall()]
    if "display_order" not in columns:
        cur.execute("ALTER TABLE item_images ADD COLUMN display_order INTEGER DEFAULT 0")
        conn.commit()

def ensure_display_order_column():
    conn = get_db()
    cursor = conn.cursor()

    # Check if the column already exists
    cursor.execute("PRAGMA table_info(item_images)")
    columns = [row["name"] for row in cursor.fetchall()]

    if "display_order" not in columns:
        print("Adding missing column: display_order")
        cursor.execute("ALTER TABLE item_images ADD COLUMN display_order INTEGER DEFAULT 0")

        # Initialize display_order based on current id order
        cursor.execute("""
            UPDATE item_images
            SET display_order = id
        """)
        conn.commit()
    conn.close()

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT,
            image TEXT,
            available INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            is_main INTEGER DEFAULT 0,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Login required decorator --------------------------------------------
from functools import wraps
def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            flash(_("Please log in first."))
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped

# --- Routes ---------------------------------------------------------------
db_initialized = False

@app.before_request
def initialize_database():
    global db_initialized
    if not db_initialized:
        ensure_display_order_column()
        db_initialized = True


@app.route("/")
def index():
    """Landing page showing main image + title for each item."""
    conn = get_db()
    items = conn.execute("""
        SELECT i.*, COALESCE(
            (SELECT filename FROM item_images WHERE item_id=i.id AND is_main=1 LIMIT 1),
            i.image
        ) AS main_image
        FROM items i ORDER BY i.id DESC
    """).fetchall()
    conn.close()
    return render_template("index.html", items=items)


@app.route("/gallery/<item>")
def gallery(item):
    """Show all images for a specific item"""
    item_path = os.path.join(app.static_folder, "images", item)
    if not os.path.exists(item_path):
        return "Item not found", 404

    images = [
        url_for("static", filename=f"images/{item}/{img}")
        for img in os.listdir(item_path)
        if img.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")) and img != "main.jpg"
    ]

    return render_template("gallery.html", item=item.capitalize(), images=images)

@app.route("/load_data")
def load_data():
    # Simulate a large file or dataset load
    products = [
        {"name": "Organic Tomatoes"},
        {"name": "Free-range Eggs"},
        {"name": "Raw Honey"},
        {"name": "Homemade Bread"},
        {"name": "Goat Cheese"},
        {"name": "Fresh Strawberries"},
        {"name": "Farm Milk"}
    ]

    # Stream JSON slowly to show progress
    def generate():
        yield '['
        for i, item in enumerate(products):
            time.sleep(0.3)  # simulate delay
            yield json.dumps(item)
            if i < len(products) - 1:
                yield ','
        yield ']'

    json_data = json.dumps(products)
    headers = {"Content-Length": str(len(json_data))}
    return Response(generate(), mimetype="application/json", headers=headers)

@app.route("/load_images")
def load_images():
    image_folder = os.path.join(app.static_folder, "images")
    images = [
        url_for("static", filename=f"images/{img}")
        for img in os.listdir(image_folder)
        if img.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))
    ]
    return jsonify(images)

@app.route("/item/<int:item_id>")
def item(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return "Item not found", 404

    # Fetch images (main first)
    gallery = conn.execute(
        "SELECT * FROM item_images WHERE item_id=? ORDER BY is_main DESC, id ASC",
        (item_id,)
    ).fetchall()
    conn.close()

    return render_template("item.html", item=item, gallery=gallery)


@app.route("/contact/<int:item_id>", methods=["GET", "POST"])
def contact(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        flash(_("Item not found."))
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name")
        message = request.form.get("message")

        # Send to Discord
        payload = {
            "content": f"📩 **New Inquiry:**\n"
                       f"**Item:** {item['title']}\n"
                       f"**From:** {name}\n"
                       f"**Message:** {message}"
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
            flash(_("Your message has been sent successfully!"))
        except Exception as e:
            flash(_(f"Failed to send message: {e}"))

        return redirect(url_for("item", item_id=item_id))

    return render_template("contact.html", item=item)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["logged_in"] = True
            flash(_("Logged in successfully!"))
            return redirect(url_for("admin_panel"))
        else:
            flash(_("Invalid password."))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash(_("You have been logged out."))
    return redirect(url_for("index"))

@app.route("/admin")
@login_required
def admin_panel():
    conn = get_db()
    items = conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("admin.html", items=items)

# --- Add Item -------------------------------------------------------------
@app.route("/add", methods=["POST"])
def add_item():
    flash(_("Item added successfully!"))
    return redirect(url_for("index"))

@login_required
def add_item():
    lang = session.get('lang', 'en')
    title = request.form["title"]
    description = request.form["description"]
    price_str = request.form["price"]
    price = float(parse_decimal(price_str, locale=lang))
    category = request.form.get("category", "").strip()
    available = 1 if request.form.get("available") else 0

    image_file = request.files.get("image")
    filename = None
    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        image_file.save(image_path)

    conn = get_db()
    conn.execute(
        "INSERT INTO items (title, description, price, category, image, available) VALUES (?, ?, ?, ?, ?, ?)",
        (title, description, price, category, f"images/{filename}" if filename else None, available),
    )
    conn.commit()
    conn.close()
    flash(_("Item added successfully!"))
    return redirect(url_for("admin_panel"))

# --- Edit Item ------------------------------------------------------------
# --- Edit Item ------------------------------------------------------------
@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    gallery = conn.execute(
        "SELECT * FROM item_images WHERE item_id=? ORDER BY sort_order ASC, id ASC",
        (item_id,)
    ).fetchall()

    if not item:
        flash(_("Item not found."))
        return redirect(url_for("admin_panel"))

    if request.method == "POST":
        locale = get_user_locale()  # e.g., 'en_US' or 'pt_PT'
        title = request.form["title"]
        description = request.form["description"]
        price_str = request.form["price"]

        # --- Locale-aware price parsing ---
        try:
            price = float(parse_decimal(price_str, locale=locale))
        except:
            flash(_("Invalid price format."))
            return redirect(request.url)

        category = request.form.get("category", "").strip()
        available = 1 if request.form.get("available") else 0

        # --- Handle existing images (remove only) ---
        for idx, img in enumerate(gallery):
            remove = request.form.get(f"remove_image_{idx}")
            if remove:
                img_path = os.path.join(UPLOAD_FOLDER, os.path.basename(img["filename"]))
                if os.path.exists(img_path):
                    os.remove(img_path)
                conn.execute("DELETE FROM item_images WHERE id=?", (img["id"],))

        # --- Handle new uploads ---
        new_files = request.files.getlist("new_images")
        if new_files:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) FROM item_images WHERE item_id=?",
                (item_id,)
            ).fetchone()[0]

            for nf in new_files:
                if nf.filename:
                    fn = secure_filename(nf.filename)
                    nf.save(os.path.join(UPLOAD_FOLDER, fn))
                    max_order += 1
                    conn.execute(
                        "INSERT INTO item_images (item_id, filename, is_main, sort_order) VALUES (?, ?, ?, ?)",
                        (item_id, f"images/{fn}", 0, max_order)
                    )

        # --- Update sort order from unified gallery ---
        import json
        raw_order = request.form.get("image_order")
        try:
            image_order = json.loads(raw_order) if raw_order and raw_order.strip() else []
        except json.JSONDecodeError:
            image_order = []

        for order_index, img_info in enumerate(image_order):
            if img_info.get("id"):  # existing image
                conn.execute(
                    "UPDATE item_images SET sort_order=? WHERE id=?",
                    (order_index, img_info["id"])
                )

        # --- Automatically mark first image as main ---
        if image_order:
            first_img_id = image_order[0].get("id")
            if first_img_id:
                conn.execute("UPDATE item_images SET is_main=1 WHERE id=?", (first_img_id,))
                # Reset others
                conn.execute(
                    "UPDATE item_images SET is_main=0 WHERE item_id=? AND id!=?",
                    (item_id, first_img_id)
                )

        # --- Update item record ---
        conn.execute(
            "UPDATE items SET title=?, description=?, price=?, category=?, available=? WHERE id=?",
            (title, description, price, category, available, item_id)
        )

        conn.commit()
        conn.close()

        flash(_("Item updated successfully!"))
        return redirect(url_for("admin_panel"))

    # --- Render template ---
    import json
    gallery_json = json.dumps([{"id": g["id"], "filename": g["filename"]} for g in gallery])
    conn.close()
    return render_template("edit_item.html", item=item, gallery_json=gallery_json)

@app.route("/update_order/<int:item_id>", methods=["POST"])
@login_required
def update_order(item_id):
    data = request.get_json()
    order = data.get("order", [])

    if not isinstance(order, list):
        return jsonify({"error": "Invalid data"}), 400

    conn = get_db()
    for idx, img_id in enumerate(order):
        conn.execute(
            "UPDATE item_images SET display_order=? WHERE id=? AND item_id=?",
            (idx, img_id, item_id)
        )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})

# --- Delete Item ----------------------------------------------------------
@app.route("/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    conn = get_db()
    item = conn.execute("SELECT image FROM items WHERE id=?", (item_id,)).fetchone()
    if item and item["image"]:
        image_path = os.path.join("static", item["image"])
        if os.path.exists(image_path):
            os.remove(image_path)
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    flash(_("Item deleted."))
    return redirect(url_for("admin_panel"))

# --- Run server -----------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=443, ssl_context=("cert.pem", "key.pem"))
