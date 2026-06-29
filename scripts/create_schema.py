"""
create_schema.py
================
Applies schema.sql to create (or recreate) the SQLite database.
"""
import os
import sqlite3

BASE = os.path.join(os.path.dirname(__file__), "..")
SCHEMA_FILE = os.path.join(BASE, "database", "schema.sql")
DB_FILE     = os.path.join(BASE, "database", "bluestock_mf.db")

def create_schema():
    print(f"Creating database at: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    with open(SCHEMA_FILE, "r") as f:
        sql = f.read()
    conn.executescript(sql)
    conn.commit()

    # List created tables
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables created ({len(tables)}):")
    for t in tables:
        print(f"  • {t}")

    conn.close()
    print("\nSchema created successfully.")

if __name__ == "__main__":
    create_schema()
