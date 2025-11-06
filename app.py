import os, json, time, requests
from flask import (
    Flask, render_template, Response, jsonify, request,
    redirect, url_for, flash, session, g
)
from flask_talisman import Talisman
from flask_babel import Babel, _
from babel.numbers import parse_decimal, format_currency
from werkzeug.utils import secure_filename
from functools import wraps
import mysql.connector
from PIL import Image
import uuid

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1410304352803098867/Cuj8e6ovn8Tj6AdXDlZ9bLmPuIRWo-GmsSf-F-S8l2fmgWQuiegWDeuidGBlNtHN-rCu"
ITEMS_FILE = "items.json"
app = Flask(__name__)

app.config["MYSQL_HOST"] = "localhost"
app.config["MYSQL_USER"] = "root"
app.config["MYSQL_PASSWORD"] = "j301052"
app.config["MYSQL_DATABASE"] = "farmshop"

app.secret_key = "secret123"
Talisman(app, content_security_policy=None)

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "images")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ADMIN_PASSWORD = "admin123"

# -----------------------------------------------------------------------------
# MySQL Setup
# -----------------------------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "j301052",
    "database": "farmshop"
}

def get_db():
    conn = mysql.connector.connect(
        host=app.config["MYSQL_HOST"],
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        database=app.config["MYSQL_DATABASE"]
    )
    return conn

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            price DECIMAL(10,2) NOT NULL,
            category VARCHAR(100),
            image VARCHAR(255),
            available BOOLEAN DEFAULT TRUE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS item_images (
            id INT AUTO_INCREMENT PRIMARY KEY,
            item_id INT NOT NULL,
            filename VARCHAR(255) NOT NULL,
            is_main BOOLEAN DEFAULT FALSE,
            sort_order INT DEFAULT 0,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    cur.close()

def ensure_display_order_column():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SHOW COLUMNS FROM item_images LIKE 'sort_order'")
    if not cur.fetchone():
        print("Adding missing column: sort_order")
        cur.execute("ALTER TABLE item_images ADD COLUMN sort_order INT DEFAULT 0")
        conn.commit()
    cur.close()

init_db()

UPLOAD_FOLDER = "static/uploads/items"

from utils.images import save_image_with_thumbnail  # using the helper we created

def save_item_images(cur, conn, item_id, files, image_order_json, main_image_id):
    """
    Handles:
    - Saving new uploaded images (full + thumbnail)
    - Reordering all images
    - Correct main image assignment
    """

    # Parse drag/drop ordering from frontend
    try:
        requested_order = json.loads(image_order_json) if image_order_json else []
    except:
        requested_order = []

    # Fetch existing images
    cur.execute("""
        SELECT id, filename, thumb, display_order
        FROM item_images
        WHERE item_id=%s
        ORDER BY display_order, id
    """, (item_id,))
    existing = {str(row["id"]): row for row in cur.fetchall()}

    # --- 1) Save new images
    new_id_map = {}   # preview_id → DB id

    for file in files:
        if file.filename:
            full_name, thumb_name = save_image_with_thumbnail(file)

            # Insert
            cur.execute("""
                INSERT INTO item_images (item_id, filename, thumb, display_order)
                VALUES (%s, %s, %s, 9999)
            """, (item_id, full_name, thumb_name))

            real_db_id = str(cur.lastrowid)

            # The frontend uses preview_id = "new-UUID"
            preview_id = "new-" + file.filename.replace(" ", "_")
            new_id_map[preview_id] = real_db_id

    conn.commit()

    # --- 2) Build final order list
    final_order = []

    for preview_id in requested_order:
        if preview_id.startswith("new-") and preview_id in new_id_map:
            final_order.append(new_id_map[preview_id])
        elif preview_id in existing:
            final_order.append(preview_id)

    # Fallback: if no order, use DB order
    if not final_order:
        final_order = list(existing.keys()) + list(new_id_map.values())

    # --- 3) Apply display_order
    for idx, img_id in enumerate(final_order):
        cur.execute("UPDATE item_images SET display_order=%s WHERE id=%s",
                    (idx, img_id))

    # --- 4) Assign main image
    main_image_path = None
    if main_image_id:
        # If selected image is existing:
        if main_image_id in existing:
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s",
                        (existing[main_image_id]["id"], item_id))
            main_image_path = existing[main_image_id]["filename"]
        # If selected image was newly uploaded
        elif main_image_id in new_id_map:
            real_id = new_id_map[main_image_id]
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s",
                        (real_id, item_id))

            cur.execute("SELECT filename FROM item_images WHERE id=%s", (real_id,))
            row = cur.fetchone()
            if row:
                main_image_path = row["filename"]

    conn.commit()
    return main_image_path

from pathlib import Path

FULL_DIR = Path("static/images/full")
THUMB_DIR = Path("static/images/thumbs")
THUMB_SIZE = (300, 300)

def save_image_with_thumbnail(file_storage):
    """Save original + thumbnail. Returns (full_path, thumb_path)."""

    # Generate unique filename
    ext = os.path.splitext(file_storage.filename)[1].lower()
    uid = str(uuid.uuid4())
    filename = f"{uid}{ext}"
    full_path = os.path.join(FULL_DIR, filename)

    # Save original full resolution
    file_storage.save(full_path)

    # Generate WebP thumbnail (max width = 420px)
    img = Image.open(full_path)
    img.thumbnail((420, 420))
    thumb_filename = f"{uid}.webp"
    thumb_path = os.path.join(THUMB_DIR, thumb_filename)
    img.save(thumb_path, "WEBP", quality=80)

    return filename, thumb_filename

# -----------------------------------------------------------------------------
# Babel setup
# -----------------------------------------------------------------------------
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_TRANSLATION_DIRECTORIES"] = "translations"
babel = Babel(app)

LANGUAGES = ["en", "pt"]
LANG_FLAGS = {"en": "gb", "pt": "pt", "es": "es", "fr": "fr"}

def get_locale():
    lang = request.args.get("lang")
    if lang:
        session["lang"] = lang
    return session.get("lang", "en")

babel = Babel(app, locale_selector=get_locale)

def create_thumbnail(full_path, thumb_path):
    try:
        img = Image.open(full_path)
        img.thumbnail(THUMB_SIZE)
        img.save(thumb_path, optimize=True, quality=85)
    except Exception as e:
        print("Thumbnail generation error:", e)

@app.context_processor
def inject_globals():
    return dict(get_locale=get_locale, format_currency=format_currency, lang_flags=LANG_FLAGS)

@app.route("/set_language/<lang>")
def set_language(lang):
    if lang in LANGUAGES:
        session["lang"] = lang
    return redirect(request.referrer or url_for("index"))

# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            flash(_("Please log in first."))
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT i.*,
            COALESCE(
                (SELECT filename FROM item_images WHERE item_id=i.id AND is_main=1 LIMIT 1),
                i.image,
                'images/no-image.png'
            ) AS main_image
        FROM items i
        ORDER BY i.id DESC
    """)

    items = cur.fetchall()
    cur.close()
    return render_template("index.html", items=items)

@app.route("/item/<int:item_id>")
def item(item_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM items WHERE id=%s", (item_id,))
    item = cur.fetchone()
    if not item:
        cur.close()
        return "Item not found", 404

    cur.execute("""
        SELECT * FROM item_images WHERE item_id=%s ORDER BY sort_order ASC, id ASC
    """, (item_id,))
    gallery = cur.fetchall()
    cur.close()
    return render_template("item.html", item=item, gallery=gallery)

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

@app.route("/contact/<int:item_id>", methods=["GET", "POST"])
def contact(item_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items WHERE id=%s", (item_id,))
    item = cursor.fetchone()
    conn.close()
    if not item:
        flash("Item not found.")
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name")
        message = request.form.get("message")
        payload = {
            "content": f"📩 **New Inquiry:**\n"
                       f"**Item:** {item['title']}\n"
                       f"**From:** {name}\n"
                       f"**Message:** {message}"
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
            flash("Your message has been sent successfully!")
        except Exception as e:
            flash(f"Failed to send message: {e}")
        return redirect(url_for("item", item_id=item_id))

    return render_template("contact.html", item=item)

@app.route("/admin")
@login_required
def admin_panel():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM items ORDER BY id DESC")
    items = cur.fetchall()
    cur.close()
    return render_template("admin.html", items=items)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add_item():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    if request.method == "POST":
        # User selects either an existing category OR a new custom one
        new_category = request.form.get("category_new", "").strip()

        if new_category:
            category = new_category  # override with new category if provided
        title = request.form["title"].strip()
        description = request.form.get("description", "").strip()
        price = float(request.form["price"].strip().replace(",", "."))
        stock = int(request.form.get("stock", 0))
        category = request.form.get("category", "").strip()
        available = 1 if request.form.get("available") else 0

        # Insert item
        cur.execute("""
            INSERT INTO items (title, description, price, category, stock, available)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, description, price, category, stock, available))
        conn.commit()

        # Retrieve ID of inserted item
        item_id = cur.lastrowid

        # Handle image upload
        files = request.files.getlist("images[]")
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)

                full_path = os.path.join(FULL_DIR, filename)
                thumb_path = os.path.join(THUMB_DIR, filename)

                file.save(full_path)
                create_thumbnail(full_path, thumb_path)

                cur.execute("""
                    INSERT INTO gallery (item_id, filename)
                    VALUES (%s, %s)
                """, (item_id, filename))
                conn.commit()

        cur.close()
        conn.close()

        flash("Item added successfully.", "success")
        return redirect(url_for("edit_item", item_id=item_id))

    # GET request: show form
    cur.execute("SELECT DISTINCT category FROM items WHERE category <> '' ORDER BY category ASC")
    categories = [row['category'] for row in cur.fetchall()]
    cur.close()
    conn.close()

    return render_template(
        "edit_item.html",
        item=None,
        gallery=[],
        categories=categories
    )

@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Fetch existing item
    cur.execute("SELECT * FROM items WHERE id=%s", (item_id,))
    item = cur.fetchone()
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("admin_panel"))

    # Fetch images for gallery
    cur.execute("""
        SELECT * FROM item_images
        WHERE item_id=%s
        ORDER BY sort_order ASC, id ASC
    """, (item_id,))
    rows = cur.fetchall()

    gallery = [
        {
            "id": str(row["id"]),
            "thumb": url_for('static', filename=f'images/thumbs/{row["thumb"]}') if row["thumb"] else url_for('static',
                                                                                                              filename='no-image.png'),
            "full": url_for('static', filename=f'images/full/{row["filename"]}') if row["filename"] else url_for(
                'static', filename='no-image.png'),
            "is_main": bool(row["is_main"])
        }
        for row in rows
    ]

    # Auto-assign first image as main if none set
    if not item.get('main_image') and gallery:
        item['main_image'] = gallery[0]['id']
        cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (item['main_image'], item_id))
        conn.commit()

    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form.get("description", "").strip()
        price = float(request.form["price"].strip().replace(",", "."))
        stock = int(request.form.get("stock", 0))
        category = request.form.get("category", "").strip()
        available = 1 if request.form.get("available") else 0

        image_order_json = request.form.get("image_order")
        main_image_id = request.form.get("main_image")
        files = request.files.getlist("new_images")

        # Update item
        cur.execute("""
            UPDATE items
            SET title=%s, description=%s, price=%s, stock=%s, category=%s, available=%s
            WHERE id=%s
        """, (title, description, price, stock, category, available, item_id))

        # Handle images
        main_image_path = save_item_images(cur, conn, item_id, files, image_order_json, main_image_id)
        if main_image_path:
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (main_image_path, item_id))

        conn.commit()
        cur.close()
        flash("Item updated successfully!", "success")
        return redirect(url_for("admin_panel"))

    # ✅ Fetch distinct non-empty categories BEFORE rendering
    cur.execute("SELECT DISTINCT category FROM items WHERE category <> '' ORDER BY category ASC")
    categories = [row['category'] for row in cur.fetchall()]

    cur.close()
    return render_template("edit_item.html", item=item, gallery=gallery, categories=categories)


@app.route("/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT image FROM items WHERE id=%s", (item_id,))
    item = cur.fetchone()
    if item and item["image"]:
        image_path = os.path.join("static", item["image"])
        if os.path.exists(image_path):
            os.remove(image_path)
    cur.execute("DELETE FROM items WHERE id=%s", (item_id,))
    conn.commit()
    cur.close()
    flash(_("Item deleted."))
    return redirect(url_for("admin_panel"))

from flask import send_from_directory

UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/delete_image/<int:image_id>", methods=["DELETE"])
def delete_image(image_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # --- Find the image first ---
    cur.execute("SELECT id, item_id, filename FROM item_images WHERE id=%s", (image_id,))
    image = cur.fetchone()
    if not image:
        return jsonify({"error": "Image not found"}), 404

    item_id = image["item_id"]
    filename = image["filename"]

    # --- Delete file from disk ---
    file_path = os.path.join(app.static_folder, "images", filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"⚠️ Could not remove file {file_path}: {e}")

    # --- Delete DB record ---
    cur.execute("DELETE FROM item_images WHERE id=%s", (image_id,))

    # --- Check if it was the main image ---
    cur.execute("SELECT main_image FROM items WHERE id=%s", (item_id,))
    item = cur.fetchone()
    was_main = False
    if item and item["main_image"]:
        # Compare with stored path (normalize)
        normalized_main = item["main_image"].split("/")[-1]
        if normalized_main == filename:
            was_main = True

    # --- If it was the main image, pick the next available one ---
    if was_main:
        cur.execute("""
            SELECT filename FROM item_images
            WHERE item_id=%s
            ORDER BY sort_order ASC LIMIT 1
        """, (item_id,))
        next_img = cur.fetchone()

        if next_img:
            new_main = f"images/{next_img['filename']}"
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (new_main, item_id))
        else:
            # No remaining images → clear main_image
            cur.execute("UPDATE items SET main_image=NULL WHERE id=%s", (item_id,))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"success": True})

# --- Update order route ---
@app.route("/update_order/<int:item_id>", methods=["POST"])
def update_order(item_id):
    data = request.get_json()
    order_list = data.get("order", [])

    conn = get_db()
    cur = conn.cursor()

    for position, image_id in enumerate(order_list):
        # Only update real DB images (skip new previews like 'new-abc123')
        if not str(image_id).startswith("new-"):
            cur.execute("UPDATE item_images SET sort_order=%s WHERE id=%s", (position, image_id))

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})


# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=443, ssl_context=("cert.pem", "key.pem"))
