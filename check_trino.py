import trino
conn = trino.dbapi.connect(
    host='dar-trino',
    port=8080,
    user='admin',
    catalog='iceberg',
    schema='bronze'
)
cur = conn.cursor()
cur.execute('SHOW TABLES')
tables = cur.fetchall()
if not tables:
    print("No tables found in bronze.")
else:
    for row in tables:
        print(f"Table: {row[0]}")
