import psycopg
conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/derma_hospital_db")
cur = conn.cursor()
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
print("Tables:")
for r in cur.fetchall():
    print(" -", r[0])
