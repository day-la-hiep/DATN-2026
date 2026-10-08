import psycopg

conn = psycopg.connect("postgresql://postgres:postgres@localhost:5432/derma_hospital_db")
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")
print("Users table columns:")
for row in cur.fetchall():
    print(" -", row)

cur.execute("SELECT id, name, email FROM users")
print("\nExisting rows:")
for row in cur.fetchall():
    print(" -", row)
