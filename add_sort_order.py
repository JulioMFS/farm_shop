import sqlite3

DB_PATH = "farm_shop.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Check if column exists
c.execute("PRAGMA table_info(item_images)")
columns = [row[1] for row in c.fetchall()]
if "sort_order" not in columns:
    c.execute("ALTER TABLE item_images ADD COLUMN sort_order INTEGER DEFAULT 0")
    print("Added sort_order column.")
else:
    print("sort_order column already exists.")

# Optional: populate existing images with sequential sort_order
c.execute("SELECT id FROM item_images ORDER BY id ASC")
for idx, row in enumerate(c.fetchall()):
    c.execute("UPDATE item_images SET sort_order=? WHERE id=?", (idx, row[0]))

conn.commit()
conn.close()
print("Database updated successfully.")
