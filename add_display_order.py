from app import get_db


def migrate_add_display_order():
    conn = get_db()
    try:
        conn.execute("ALTER TABLE item_images ADD COLUMN display_order INTEGER DEFAULT 0;")
        conn.commit()
        print("✅ Column 'display_order' added to item_images.")
    except Exception as e:
        print("ℹ️ Possibly already added:", e)
    finally:
        conn.close()
