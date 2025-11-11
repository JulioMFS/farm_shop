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


UPLOAD_FOLDER = "static/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
THUMB_FOLDER = "static/images/thumbs"
os.makedirs(THUMB_FOLDER, exist_ok=True)
THUMB_SIZE = (300, 300)
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

def save_file(file_storage):
    """
    Save uploaded file.
    - Images: generate thumbnail (WebP)
    - Videos: just save the file
    Returns: dict with keys: type ('image'/'video'), filename, thumb (None for videos)
    """
    ext = os.path.splitext(file_storage.filename)[1].lower()
    uid = str(uuid.uuid4())
    filename = f"{uid}{ext}"
    full_path = os.path.join(UPLOAD_FOLDER, filename)

    file_storage.save(full_path)

    if ext in ALLOWED_IMAGE_EXTENSIONS:
        # Generate thumbnail
        img = Image.open(full_path)
        img.thumbnail((420, 420))
        thumb_filename = f"{uid}.webp"
        thumb_path = os.path.join(THUMB_FOLDER, thumb_filename)
        img.save(thumb_path, "WEBP", quality=80)
        return {"type": "image", "filename": filename, "thumb": thumb_filename}

    elif ext in ALLOWED_VIDEO_EXTENSIONS:
        # Videos: no thumbnail for now
        return {"type": "video", "filename": filename, "thumb": None}

    else:
        raise ValueError(f"Unsupported file type: {ext}")

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


def save_item_images(cur, conn, item_id, files, image_order_json, main_image_id):
    """
    Save uploaded images/videos to disk and update DB.
    Works with new uploads (IDs starting with 'new_') and existing images in DB.
    """

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(THUMB_FOLDER, exist_ok=True)

    main_path = None

    try:
        order = json.loads(image_order_json)
    except Exception:
        order = []

    # Convert files list to a dict by filename for easier lookup
    files_dict = {f.filename: f for f in files}

    for idx, media_id in enumerate(order):
        # New file uploaded
        if media_id.startswith("new_"):
            # Find uploaded file by matching filename in files_dict
            # In your JS, filename is stored in window.existingImages as `filename`
            # So we can match by the end of media_id, or simply pop one file at a time
            if not files:
                continue
            file_obj = files.pop(0)  # take the first remaining file

            filename = f"{media_id}_{file_obj.filename}"
            full_path = os.path.join(UPLOAD_FOLDER, filename)
            file_obj.save(full_path)

            # Thumbnail for images
            is_video = file_obj.content_type.startswith("video/")
            thumb_name = ""
            if not is_video:
                thumb_name = f"{media_id}_{file_obj.filename}"
                thumb_path = os.path.join(THUMB_FOLDER, thumb_name)
                try:
                    img = Image.open(full_path)
                    img.thumbnail((300, 300))
                    img.save(thumb_path)
                except Exception as e:
                    print("Error creating thumbnail:", e)
                    thumb_name = ""

            # Determine main
            is_main = 1 if media_id == main_image_id or idx == 0 else 0
            if is_main:
                main_path = full_path

            # Insert into DB
            sql = """
                INSERT INTO item_images (item_id, filename, thumb, is_main, sort_order, display_order)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cur.execute(sql, (item_id, filename, thumb_name, is_main, idx, idx))

        else:
            # Existing DB image: just update is_main and order
            is_main = 1 if media_id == main_image_id or idx == 0 else 0
            if is_main:
                cur.execute("SELECT filename FROM item_images WHERE id=%s", (media_id,))
                row = cur.fetchone()
                if row:
                    main_path = os.path.join(UPLOAD_FOLDER, row['filename'])

            cur.execute(
                "UPDATE item_images SET is_main=%s, sort_order=%s, display_order=%s WHERE id=%s",
                (is_main, idx, idx, media_id)
            )

    conn.commit()
    return main_path


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
        if category == "":
            category = category_new
        available = 1 if request.form.get("available") else 0

        image_order_json = request.form.get("image_order", "[]")
        main_image_id = request.form.get("main_image", "")
        delete_list_json = request.form.get("delete_list", "[]")
        files = request.files.getlist("new_images")

        # --- Insert new item ---
        cur.execute("""
            INSERT INTO items (title, description, price, stock, category, available)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, description, price, stock, category, available))
        conn.commit()
        item_id = cur.lastrowid

        # --- Delete any images if provided (for consistency, usually empty on add) ---
        try:
            delete_ids = json.loads(delete_list_json)
        except Exception:
            delete_ids = []

            THUMB_FOLDER = "static/images/thumbs"

        for img_id in delete_ids:
            cur.execute("SELECT filename, thumb FROM item_images WHERE id=%s", (img_id,))
            row = cur.fetchone()
            if row:
                for path in [os.path.join(UPLOAD_FOLDER, row['filename']),
                             os.path.join(THUMB_FOLDER, row['thumb'])]:
                    if path and os.path.exists(path):
                        os.remove(path)
                cur.execute("DELETE FROM item_images WHERE id=%s", (img_id,))

        # --- Process uploaded images/videos ---
        main_image_path = save_item_images(cur, conn, item_id, files, image_order_json, main_image_id)
        if main_image_path:
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (main_image_path, item_id))
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
        cur.close()
        conn.close()
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
            "id": f"item_{row['id']}",
            "filename": row['filename'],
            "thumb": row['thumb'],
            "type": "video" if row['filename'].endswith(('.mp4', '.webm', '.mov')) else "image"
        }
        for row in rows
    ]

    # Auto-assign first image as main if none set
    if not item.get('main_image') and gallery:
        item['main_image'] = gallery[0]['id']
        cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (item['main_image'], item_id))
        conn.commit()

    if request.method == "POST":
        # ... handle POST as you already have ...
        title = request.form["title"].strip()
        description = request.form.get("description", "").strip()
        price = float(request.form["price"].strip().replace(",", "."))
        stock = int(request.form.get("stock", 0))
        category = request.form.get("category", "").strip()
        category_new = request.form.get("category_new", "").strip()
        if category == "":
            category = category_new
        available = 1 if request.form.get("available") else 0

        image_order_json = request.form.get("image_order")
        main_image_id = request.form.get("main_image")
        files = request.files.getlist("new_images")

        # --- Update item info ---
        cur.execute("""
            UPDATE items
            SET title=%s, description=%s, price=%s, stock=%s, category=%s, available=%s
            WHERE id=%s
        """, (title, description, price, stock, category, available, item_id))

        # Handle deletions & new uploads
        main_image_path = save_item_images(cur, conn, item_id, files, image_order_json, main_image_id)
        if main_image_path:
            cur.execute("UPDATE items SET main_image=%s WHERE id=%s", (main_image_path, item_id))

        conn.commit()
        cur.close()
        conn.close()

        flash("Item updated successfully!", "success")
        return redirect(url_for("admin_panel"))

    # --- Return template on GET ---
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
