"""Migration: Completions - add completion_time for ordering same-day completions."""
import sqlite3
import os

for p in [
    os.path.join(os.path.dirname(__file__), 'aivancrate.db'),
    os.path.join(os.path.dirname(__file__), 'instance', 'aivancrate.db'),
]:
    if os.path.exists(p):
        DB_PATH = p
        break
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), 'aivancrate.db')


def migrate():
    if not os.path.exists(DB_PATH):
        print("DB not found, skip migration")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(completions)")
    cols = {r[1] for r in cur.fetchall()}

    if 'completion_time' not in cols:
        cur.execute("ALTER TABLE completions ADD COLUMN completion_time TIME")
        print("Added completions.completion_time")
    else:
        print("completions.completion_time already exists")

    conn.commit()
    conn.close()


if __name__ == '__main__':
    migrate()
