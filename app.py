import os, json, requests
from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, flash, session, g
)
from flask_talisman import Talisman
from flask_babel import Babel, _
from babel.numbers import format_currency
from functools import wraps
import mysql.connector
from PIL import Image
import uuid
from werkzeug.utils import secure_filename


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
ALLOWED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
ALLOWED_VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov')

app.secret_key = "secret123"
Talisman(app, content_security_policy=None)

UPLOAD_FOLDER = os.path.join(app.static_folder, "images")
THUMB_FOLDER = os.path.join(app.static_folder, "images", "thumbs")
THUMB_SIZE = (400, 400)  # adjust as needed
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMB_FOLDER, exist_ok=True)
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

def delete_image_by_id(image_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM item_images WHERE id=%s", (image_id,))
    image = cur.fetchone()
    if not image:
        cur.close()
        conn.close()
        return False

    item_id = image["item_id"]
    filename = image["filename"]
    thumb = image.get("thumb")

    # Delete physical files
    full_path = os.path.join(app.static_folder, "images", "full", filename)
    thumb_path = os.path.join(app.static_folder, "images", "thumbs", thumb) if thumb else None
    for path in [full_path, thumb_path]:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"⚠️ Could not remove file {path}: {e}")

    # Delete DB row
    cur.execute("DELETE FROM item_images WHERE id=%s", (image_id,))

    # Update main image if necessary
    cur.execute("SELECT main_image FROM items WHERE id=%s", (item_id,))
    item = cur.fetchone()
    if item and item["main_image"] and os.path.basename(item["main_image"]) == filename:
        cur.execute("""
            SELECT filename FROM item_images WHERE item_id=%s ORDER BY id ASC LIMIT 1
        """, (item_id,))
        new_main = cur.fetchone()
        new_main_path = f"images/full/{new_main['filename']}" if new_main else None
        cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (new_main_path, item_id))

    conn.commit()
    cur.close()
    conn.close()
    return True

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

import shutil

def save_file(file):
    """Save an uploaded file and create a thumbnail. Returns dict with filename and thumb."""
    # Ensure folders exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(THUMB_FOLDER, exist_ok=True)

    # --- Normalize filename ---
    ext = os.path.splitext(file.filename)[1].lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_name)

    # --- Save file ---
    file.save(file_path)

    # --- Generate thumbnail ---
    thumb_path = os.path.join(THUMB_FOLDER, unique_name)
    try:
        # Try to open as image
        with Image.open(file_path) as img:
            img.thumbnail(THUMB_SIZE)
            img.save(thumb_path)
    except Exception:
        # If not an image (e.g., video), just copy the file placeholder
        shutil.copy(file_path, thumb_path)

    # Return only filenames (relative paths are handled in templates)
    return {
        "filename": unique_name,
        "thumb": os.path.relpath(thumb_path, UPLOAD_FOLDER)
    }



def save_image_with_thumbnail(file):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    full_path = os.path.join('static', 'images', 'full', filename)
    thumb_path = os.path.join('static', 'images', 'thumbs', filename)

    # Save original file
    file.save(full_path)

    # Only create thumbnail for images
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        img = Image.open(full_path)
        img.thumbnail((300, 300))
        img.save(thumb_path)
        return full_path, thumb_path
    elif ext in ALLOWED_VIDEO_EXTENSIONS:
        # For videos, thumbnail can be optional or skipped
        return full_path, None
    else:
        raise ValueError(f"Unsupported file type: {ext}")

def create_thumbnail(file_path):
    """Create thumbnail and return thumbnail path"""
    thumb_path = os.path.join(THUMB_FOLDER, os.path.basename(file_path))
    try:
        with Image.open(file_path) as img:
            img.thumbnail(THUMB_SIZE)
            img.save(thumb_path)
    except Exception as e:
        print("Thumbnail generation error:", e)
    return thumb_path

def add_images(cur, conn, item_id, files, main_index=None):
    """Add new images and optionally set main image"""
    saved_ids = []
    main_image_filename = None

    if main_index is not None and files:
        cur.execute("UPDATE item_images SET is_main=0 WHERE item_id=%s", (item_id,))

    for idx, file in enumerate(files):
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        thumb_path = create_thumbnail(file_path)

        is_main = 1 if idx == main_index else 0
        if is_main:
            main_image_filename = filename

        cur.execute("""
            INSERT INTO item_images (item_id, filename, thumb, is_main)
            VALUES (%s, %s, %s, %s)
        """, (item_id, filename, thumb_path, is_main))
        saved_ids.append(cur.lastrowid)

    if main_image_filename:
        cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (main_image_filename, item_id))

    conn.commit()
    return saved_ids

def delete_image_by_id(cur, conn, image_id):
    """Delete image and update main image if needed"""
    cur.execute("SELECT item_id, filename, is_main FROM item_images WHERE id=%s", (image_id,))
    row = cur.fetchone()
    if not row:
        return False
    item_id, filename, is_main = row

    # Remove files
    for folder in [UPLOAD_FOLDER, THUMB_FOLDER]:
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            os.remove(path)

    cur.execute("DELETE FROM item_images WHERE id=%s", (image_id,))

    if is_main:
        cur.execute("SELECT id, filename FROM item_images WHERE item_id=%s ORDER BY id ASC LIMIT 1", (item_id,))
        new_main = cur.fetchone()
        if new_main:
            new_id, new_filename = new_main
            cur.execute("UPDATE item_images SET is_main=1 WHERE id=%s", (new_id,))
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (new_filename, item_id))
        else:
            cur.execute("UPDATE items SET main_image=NULL WHERE id=%s", (item_id,))

    conn.commit()
    return True

def set_main_image(cur, conn, item_id, image_id):
    cur.execute("SELECT filename FROM item_images WHERE id=%s AND item_id=%s", (image_id, item_id))
    row = cur.fetchone()
    if not row:
        return False
    filename = row[0]
    cur.execute("UPDATE item_images SET is_main=0 WHERE item_id=%s", (item_id,))
    cur.execute("UPDATE item_images SET is_main=1 WHERE id=%s", (image_id,))
    cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (filename, item_id))
    conn.commit()
    return True

def delete_image_by_id(image_id):
    """
    Delete an image (and its thumbnail) from both disk and database.
    Automatically updates main_image if needed.
    Returns True if deleted, False if not found.
    """
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # --- Find the image ---
    cur.execute("SELECT id, item_id, filename, thumb FROM item_images WHERE id=%s", (image_id,))
    image = cur.fetchone()
    if not image:
        cur.close()
        conn.close()
        return False

    item_id = image["item_id"]
    filename = image["filename"]
    thumb = image.get("thumb")

    # --- Delete files from disk ---
    paths = [
        os.path.join(app.static_folder, "images", "full", filename),
        os.path.join(app.static_folder, "images", "thumbs", thumb) if thumb else None
    ]
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"⚠️ Could not remove file {path}: {e}")

    # --- Remove from DB ---
    cur.execute("DELETE FROM item_images WHERE id=%s", (image_id,))

    # --- If it was the main image, assign a new one ---
    cur.execute("SELECT main_image FROM items WHERE id=%s", (item_id,))
    item = cur.fetchone()
    if item and item["main_image"]:
        current_main = os.path.basename(item["main_image"])
        if current_main == filename:
            cur.execute("""
                SELECT filename FROM item_images
                WHERE item_id=%s LIMIT 1
            """, (item_id,))
            next_img = cur.fetchone()
            if next_img:
                new_main = f"images/full/{next_img['filename']}"
                cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (new_main, item_id))
            else:
                cur.execute("UPDATE items SET main_image=NULL WHERE id=%s", (item_id,))

    conn.commit()
    cur.close()
    conn.close()
    return True

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

def normalize_image_id(val):
    if val and val.startswith("item_"):
        return int(val.replace("item_", ""))
    return val

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
                'no-image.png'
            ) AS main_image
        FROM items i
        ORDER BY i.id DESC
    """)
    items = cur.fetchall()
    cur.close()

    # Ensure main_image is filename-only
    for item in items:
        item['main_image'] = os.path.basename(item['main_image'] or 'no-image.png')
        print(f"--> {item['id']} - {item['main_image']}")
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
        # --- Item data ---
        title = request.form["title"].strip()
        description = request.form.get("description", "").strip()
        price = float(request.form["price"].strip().replace(",", "."))
        stock = int(request.form.get("stock", 0))
        category = request.form.get("category", "").strip()
        category_new = request.form.get("category_new", "").strip()
        if not category:
            category = category_new
        available = 1 if request.form.get("available") else 0

        # --- Insert item ---
        cur.execute("""
            INSERT INTO items (title, description, price, stock, category, available)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, description, price, stock, category, available))
        item_id = cur.lastrowid

        # --- Handle uploaded files ---
        files = request.files.getlist("new_images")
        image_order_json = request.form.get("image_order", "[]")
        delete_list = json.loads(request.form.get("delete_list", "[]"))

        try:
            image_order = json.loads(image_order_json)
        except Exception:
            image_order = []

        # Save new files
        new_ids_map = {}
        for f in files:
            if not f or f.filename == "":
                continue
            # Save main image
            filename = secure_filename(f.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(file_path)

            # Create thumbnail
            thumb_path = create_thumbnail(file_path)

            # Insert into DB
            cur.execute("""
                INSERT INTO item_images (item_id, filename, thumb, is_main)
                VALUES (%s, %s, %s, 0)
            """, (item_id, os.path.basename(file_path), os.path.basename(thumb_path)))
            db_id = cur.lastrowid
            new_ids_map[f.filename] = db_id

        # --- Delete unwanted images (from delete_list) ---
        for del_id in delete_list:
            if str(del_id).isdigit():
                cur.execute("SELECT filename, thumb FROM item_images WHERE id=%s", (int(del_id),))
                row = cur.fetchone()
                if row:
                    # Remove files from disk
                    for path in [
                        os.path.join(UPLOAD_FOLDER, row["filename"]),
                        os.path.join(THUMB_FOLDER, row["thumb"])
                    ]:
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                        except Exception as e:
                            print("File deletion error:", e)
                    # Delete from DB
                    cur.execute("DELETE FROM item_images WHERE id=%s", (int(del_id),))

        # --- Apply image order ---
        for pos, img_id in enumerate(image_order):
            if img_id.startswith("new_"):
                original_name = img_id.replace("new_", "")
                db_id = new_ids_map.get(original_name)
            else:
                db_id = int(img_id) if str(img_id).isdigit() else None
            if db_id:
                cur.execute("UPDATE item_images SET sort_order=%s WHERE id=%s", (pos, db_id))

        # --- Determine main image: always the first remaining one ---
        cur.execute("SELECT id, filename FROM item_images WHERE item_id=%s ORDER BY sort_order ASC, id ASC", (item_id,))
        images = cur.fetchall()

        if images:
            main_image = images[0]
            main_image_id = main_image["id"]
            # Set this one as main
            cur.execute("UPDATE item_images SET is_main=0 WHERE item_id=%s", (item_id,))
            cur.execute("UPDATE item_images SET is_main=1 WHERE id=%s", (main_image_id,))
            main_image_path = os.path.join(UPLOAD_FOLDER, main_image["filename"])
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (main_image_path, item_id))

        conn.commit()
        cur.close()
        conn.close()

        flash("Item added successfully!", "success")
        return redirect(url_for("admin_panel"))

    # --- GET ---
    cur.execute("SELECT DISTINCT category FROM items WHERE category <> '' ORDER BY category ASC")
    categories = [row['category'] for row in cur.fetchall()]
    cur.close()
    conn.close()

    return render_template("edit_item.html", item=None, gallery=[], categories=categories)



@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # --- GET: load item and gallery ---
    if request.method == "GET":
        cur.execute("SELECT * FROM items WHERE id=%s", (item_id,))
        item = cur.fetchone()

        cur.execute("""
            SELECT id, filename, thumb, is_main
            FROM item_images
            WHERE item_id=%s
            ORDER BY sort_order ASC
        """, (item_id,))
        gallery = cur.fetchall()

        cur.execute("SELECT DISTINCT category FROM items WHERE category <> '' ORDER BY category ASC")
        categories = [row['category'] for row in cur.fetchall()]

        cur.close()
        conn.close()

        return render_template(
            "edit_item.html",
            item=item,
            gallery=gallery,
            categories=categories
        )

    # --- POST: update item details ---
    title = request.form["title"].strip()
    description = request.form.get("description", "").strip()
    price = float(request.form["price"].strip().replace(",", "."))
    stock = int(request.form.get("stock", 0))
    category = request.form.get("category", "").strip()
    category_new = request.form.get("category_new", "").strip()
    if not category:
        category = category_new
    available = 1 if request.form.get("available") else 0

    cur.execute("""
        UPDATE items
        SET title=%s, description=%s, price=%s, stock=%s, category=%s, available=%s
        WHERE id=%s
    """, (title, description, price, stock, category, available, item_id))

    # --- Process uploads/deletions/reorder ---
    files = request.files.getlist("new_images")
    image_order_json = request.form.get("image_order", "[]")
    delete_list_json = request.form.get("delete_list", "[]")

    try:
        image_order = json.loads(image_order_json)
        delete_list = json.loads(delete_list_json)
    except json.JSONDecodeError:
        image_order, delete_list = [], []

    # --- Delete removed images ---
    for img_id in delete_list:
        cur.execute("SELECT filename, thumb FROM item_images WHERE id=%s AND item_id=%s", (img_id, item_id))
        row = cur.fetchone()
        if row:
            for path in [row["filename"], row["thumb"]]:
                if path:
                    try:
                        os.remove(os.path.join(UPLOAD_FOLDER, path))
                    except FileNotFoundError:
                        pass
        cur.execute("DELETE FROM item_images WHERE id=%s AND item_id=%s", (img_id, item_id))

    # --- Save new uploads ---
    new_ids_map = {}
    for f in files:
        if not f.filename:
            continue
        saved = save_file(f)  # your existing file save + thumbnail generator
        cur.execute("""
            INSERT INTO item_images (item_id, filename, thumb, is_main)
            VALUES (%s, %s, %s, 0)
        """, (item_id, saved["filename"], saved["thumb"]))
        db_id = cur.lastrowid
        new_ids_map[f.filename] = db_id

    # --- Apply new order + main image ---
    for sort_index, img_id in enumerate(image_order):
        # Map new_ filenames to DB IDs
        if img_id.startswith("new_"):
            fname = img_id.replace("new_", "")
            db_id = new_ids_map.get(fname)
            if not db_id:
                continue
        else:
            db_id = int(img_id)

        is_main = 1 if sort_index == 0 else 0
        cur.execute("""
            UPDATE item_images
            SET sort_order=%s, is_main=%s
            WHERE id=%s AND item_id=%s
        """, (sort_index, is_main, db_id, item_id))

        # Update main image path in items table
        if is_main:
            cur.execute("SELECT filename FROM item_images WHERE id=%s", (db_id,))
            row = cur.fetchone()
            if row:
                main_image_path = os.path.join("images", row["filename"])
                cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (main_image_path, item_id))

    conn.commit()
    cur.close()
    conn.close()

    flash("Item updated successfully!", "success")
    return redirect(url_for("admin_panel"))



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

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/delete_image/<int:image_id>", methods=["DELETE"])
def delete_image_route(image_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    success = delete_image_by_id(cur, conn, image_id)
    cur.close()
    conn.close()

    if not success:
        return jsonify({"error": "Image not found"}), 404
    return jsonify({"success": True})

@app.route("/delete_images_bulk", methods=["POST"])
def delete_images_bulk():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 403

    ids = request.json.get("ids", [])
    if not ids:
        return jsonify({"error": "No image IDs provided"}), 400

    deleted = 0
    for img_id in ids:
        if delete_image_by_id(img_id):
            deleted += 1

    return jsonify({"success": True, "deleted": deleted})

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

@app.route("/delete_image/<image_id>", methods=["DELETE"])
def delete_image(image_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 403

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Get image record
    cur.execute("SELECT * FROM item_images WHERE id_ui = %s", (image_id,))
    image = cur.fetchone()
    if not image:
        cur.close()
        return jsonify({"error": "Image not found"}), 404

    # Delete from DB
    cur.execute("DELETE FROM item_images WHERE id_ui = %s", (image_id,))
    conn.commit()
    cur.close()

    # Delete image files from disk (if exist)
    full_path = os.path.join(app.static_folder, "images", "full", image["filename"])
    thumb_path = os.path.join(app.static_folder, "images", "thumbs", image.get("thumb") or image["filename"])

    for path in [full_path, thumb_path]:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"Warning: Could not remove file {path}: {e}")

    return jsonify({"success": True})


# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=443, ssl_context=("cert.pem", "key.pem"))
