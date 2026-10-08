import os
import trino

TRINO_HOST   = "dar-trino"
TRINO_PORT   = 8080
TRINO_USER   = "admin"
CATALOG      = "iceberg"
SCHEMA       = "bronze"
TABLE        = "m1_masked_test"

def conn():
    return trino.dbapi.connect(host=TRINO_HOST, port=TRINO_PORT, user=TRINO_USER, catalog=CATALOG, schema=SCHEMA)

def main():
    c = conn()
    cur = c.cursor()
    
    # 1. Create table
    cur.execute(f"CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{TABLE} (id BIGINT, description VARCHAR(255), amount DECIMAL(15,2))")
    cur.fetchall()
    
    # 2. Insert data (amount > 1,000,000 should be filtered, description should be masked)
    cur.execute(f"INSERT INTO {CATALOG}.{SCHEMA}.{TABLE} VALUES (1, 'Secret Project', 500000.00), (2, 'Super Secret', 2000000.00)")
    cur.fetchall()
    
    # 3. Query data
    cur.execute(f"SELECT * FROM {CATALOG}.{SCHEMA}.{TABLE}")
    rows = cur.fetchall()
    
    # 4. Clean up
    cur.execute(f"DROP TABLE {CATALOG}.{SCHEMA}.{TABLE}")
    cur.fetchall()
    
    print("OPA Masking & Filtering Results:")
    for row in rows:
        print(f"Row: {row}")
        assert "MASKED" in row[1], "Description was not masked!"
        assert float(row[2]) < 1000000, "Row filter failed!"

    assert len(rows) == 1, f"Expected 1 row due to filter, got {len(rows)}"
    print("✅ OPA Row Filter & Column Mask test passed!")

if __name__ == "__main__":
    main()
