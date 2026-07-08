"""
Hard reset: Drop and recreate all Slancio tables in Neon via psycopg2 (sync).
"""
import os
import psycopg2

RAW_URL = "postgresql://neondb_owner:npg_9Yn2OWpAegBw@ep-fragrant-sky-aogk3l4j.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

DROPS = [
    "DROP TABLE IF EXISTS otp_records CASCADE",
    "DROP TABLE IF EXISTS api_keys CASCADE",
    "DROP TABLE IF EXISTS trade_logs CASCADE",
    "DROP TABLE IF EXISTS user_settings CASCADE",
    "DROP TABLE IF EXISTS system_state CASCADE",
    "DROP TABLE IF EXISTS users CASCADE",
]

try:
    conn = psycopg2.connect(RAW_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DROPS:
        cur.execute(stmt)
        print(f"OK: {stmt}")
    cur.close()
    conn.close()
    print("\n✅ All tables dropped successfully in Neon!")
    print("The next deploy on Render will recreate them fresh.")
    print("You can now register as admin with any credentials!")
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nInstall psycopg2 first: pip install psycopg2-binary")
