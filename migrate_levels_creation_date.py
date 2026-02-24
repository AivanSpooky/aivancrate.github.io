"""Migration: AivanLevels - add creation_date for yearly stats."""
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

    cur.execute("PRAGMA table_info(aivanlevels)")
    cols = {r[1] for r in cur.fetchall()}

    if 'creation_date' not in cols:
        cur.execute("ALTER TABLE aivanlevels ADD COLUMN creation_date DATE")
        print("Added aivanlevels.creation_date")
    else:
        print("aivanlevels.creation_date already exists")

    conn.commit()
    conn.close()


if __name__ == '__main__':
    migrate()
