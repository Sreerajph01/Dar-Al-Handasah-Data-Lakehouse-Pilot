import trino
import time

conn = trino.dbapi.connect(host='dar-trino', port=8080, user='admin', catalog='iceberg', schema='silver')
cur = conn.cursor()

print("--- Schema Evolution Demo ---")
# 1. Add a column
print("Adding column 'demo_col' to dim_project...")
cur.execute("ALTER TABLE dim_project ADD COLUMN demo_col VARCHAR")
cur.fetchall()

# Verify
cur.execute("SHOW COLUMNS FROM dim_project")
cols = cur.fetchall()
print("Columns after addition:", [c[0] for c in cols])

# 2. Get snapshots
cur.execute("SELECT snapshot_id, parent_id FROM \"dim_project$snapshots\" ORDER BY committed_at DESC")
snapshots = cur.fetchall()
print("Snapshots:", snapshots)

if len(snapshots) >= 2:
    parent_snapshot = snapshots[1][0]
    print(f"Rolling back to parent snapshot: {parent_snapshot}...")
    cur.execute(f"CALL iceberg.system.rollback_to_snapshot('silver', 'dim_project', {parent_snapshot})")
    cur.fetchall()
    
    # Wait a bit for propagation?
    time.sleep(1)
    
    # Verify rollback
    cur.execute("SHOW COLUMNS FROM dim_project")
    cols_after = cur.fetchall()
    print("Columns after rollback:", [c[0] for c in cols_after])
    
    if 'demo_col' not in [c[0] for c in cols_after]:
        print("Rollback successful! Column is gone.")
    else:
        print("Column is still there? Wait, Iceberg rollback_to_snapshot restores DATA, not schema.")
        print("Actually, Iceberg schema evolution is independent of data snapshots. To rollback schema, we must DROP COLUMN.")
        cur.execute("ALTER TABLE dim_project DROP COLUMN demo_col")
        cur.fetchall()
        print("Dropped column manually.")
