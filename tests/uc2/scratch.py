import trino
conn=trino.dbapi.connect(host='dar-trino', port=8080, user='admin')
cur=conn.cursor()
cur.execute('SHOW CATALOGS')
print(cur.fetchall())
