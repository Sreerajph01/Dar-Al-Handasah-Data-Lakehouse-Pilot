import psycopg2
import os
db = os.environ.get("LAKEKEEPER_DB", "lakekeeper")
user = os.environ.get("LAKEKEEPER_DB_USER", "lakekeeper")
pw = os.environ.get("LAKEKEEPER_DB_PASSWORD", "lakekeeper")
conn = psycopg2.connect(f"host=dar-postgres-meta port=5432 dbname={db} user={user} password={pw}")
cur = conn.cursor()
cur.execute("SELECT * FROM warehouse")
print("Warehouses:")
for row in cur.fetchall():
    print(row)
cur.execute("SELECT * FROM project")
print("Projects:")
for row in cur.fetchall():
    print(row)
