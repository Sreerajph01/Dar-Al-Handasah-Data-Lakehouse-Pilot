import psycopg2

conn = psycopg2.connect(
    host="dar-postgres-meta",
    port=5432,
    dbname="lakekeeper",
    user="lakekeeper",
    password="F5nEWFfHpaS_8qYJSJXHlg"
)
cur = conn.cursor()
cur.execute('TRUNCATE TABLE tabular, "table", namespace, secret, warehouse CASCADE;')
conn.commit()
print("TRUNCATE LAKEKEEPER OK")
conn.close()
