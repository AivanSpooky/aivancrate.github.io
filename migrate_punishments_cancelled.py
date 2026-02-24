"""Migration: add cancelled_at to punishments."""
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
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='punishments'")
    if cur.fetchone() is None:
        conn.close()
        return
    cur.execute("PRAGMA table_info(punishments)")
    cols = {r[1] for r in cur.fetchall()}
    if 'cancelled_at' not in cols:
        cur.execute("ALTER TABLE punishments ADD COLUMN cancelled_at DATETIME")
        print("Added punishments.cancelled_at")
    conn.commit()
    conn.close()


if __name__ == '__main__':
    migrate()
