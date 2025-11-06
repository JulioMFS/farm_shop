import sqlite3
import mysql.connector
from mysql.connector import errorcode

# --- CONFIG ---
SQLITE_DB = "farmshop.db"
MYSQL_CONFIG = {
    "user": "root",
    "password": "j301052",
    "host": "localhost",
    "database": "farmshop",
}

# --- CONNECT TO BOTH DATABASES ---
sqlite_conn = sqlite3.connect(SQLITE_DB)
sqlite_cur = sqlite_conn.cursor()

try:
    mysql_conn = mysql.connector.connect(**MYSQL_CONFIG)
    mysql_cur = mysql_conn.cursor()
    print("✅ Connected to MySQL database:", MYSQL_CONFIG["database"])
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print("❌ Access denied: wrong user/password")
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        print("❌ Database does not exist — create it first in MySQL.")
    else:
        print(err)
    exit(1)

# --- FETCH ALL TABLES FROM SQLITE ---
sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in sqlite_cur.fetchall() if t[0] != 'sqlite_sequence']

print(f"📦 Found {len(tables)} tables in SQLite:", tables)

for table in tables:
    print(f"\n➡️ Migrating table: {table}")

    # Get table schema
    sqlite_cur.execute(f"PRAGMA table_info({table});")
    columns = sqlite_cur.fetchall()
    column_defs = []
    column_names = []

    for col in columns:
        name, ctype = col[1], col[2].upper()
        column_names.append(name)

        # Basic SQLite→MySQL type mapping
        if "INT" in ctype:
            mysql_type = "INT"
        elif "CHAR" in ctype or "TEXT" in ctype:
            mysql_type = "VARCHAR(255)"
        elif "REAL" in ctype or "FLOAT" in ctype or "DOUBLE" in ctype:
            mysql_type = "FLOAT"
        else:
            mysql_type = "VARCHAR(255)"

        if col[5] == 1:  # primary key
            mysql_type += " PRIMARY KEY"

        column_defs.append(f"`{name}` {mysql_type}")

    create_stmt = f"CREATE TABLE IF NOT EXISTS `{table}` ({', '.join(column_defs)});"
    mysql_cur.execute(create_stmt)

    # Fetch data from SQLite
    sqlite_cur.execute(f"SELECT * FROM {table}")
    rows = sqlite_cur.fetchall()
    if not rows:
        print(f"   ⚠️ No rows in {table}, skipping...")
        continue

    placeholders = ", ".join(["%s"] * len(column_names))
    insert_stmt = f"REPLACE INTO `{table}` ({', '.join(column_names)}) VALUES ({placeholders})"

    for row in rows:
        mysql_cur.execute(insert_stmt, row)

    mysql_conn.commit()
    print(f"   ✅ {len(rows)} rows migrated.")

# --- CLOSE CONNECTIONS ---
sqlite_conn.close()
mysql_conn.close()
print("\n🎉 Migration completed successfully!")
