import os
from PIL import Image
from werkzeug.utils import secure_filename

def save_image_with_thumbnail(upload_folder, file):
    """
    Saves:
    - Full image → /static/images/full/
    - Thumbnail → /static/images/thumbs/ (WebP ~ quality 75)
    Returns (full_path_db, thumb_path_db)
    """

    filename = secure_filename(file.filename)

    # Ensure directories exist
    full_dir = os.path.join(upload_folder, "full")
    thumb_dir = os.path.join(upload_folder, "thumbs")
    os.makedirs(full_dir, exist_ok=True)
    os.makedirs(thumb_dir, exist_ok=True)

    # FULL IMAGE PATH
    full_path = os.path.join(full_dir, filename)
    file.save(full_path)

    # THUMB PATH (.webp)
    thumb_filename = os.path.splitext(filename)[0] + ".webp"
    thumb_path = os.path.join(thumb_dir, thumb_filename)

    # Generate thumbnail
    with Image.open(full_path) as img:
        img.thumbnail((600, 600))  # Nice preview size
        img.save(thumb_path, "WEBP", quality=75)

    # Return paths relative to /static so they work in <img src="/static/...">
    full_path_db = f"images/full/{filename}"
    thumb_path_db = f"images/thumbs/{thumb_filename}"

    return full_path_db, thumb_path_db
