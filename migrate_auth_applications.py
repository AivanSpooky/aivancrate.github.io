"""Migration: Players.password_hash and applications table."""
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

    cur.execute("PRAGMA table_info(players)")
    cols = {r[1] for r in cur.fetchall()}
    if 'password_hash' not in cols:
        cur.execute("ALTER TABLE players ADD COLUMN password_hash VARCHAR(255)")
        print("Added players.password_hash")
    else:
        print("players.password_hash already exists")

    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='applications'"
    )
    if cur.fetchone() is None:
        cur.execute("""
            CREATE TABLE applications (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL REFERENCES players(id),
                type INTEGER NOT NULL,
                status INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME,
                notes TEXT,
                level_id INTEGER REFERENCES aivanlevels(id),
                completion_date DATE
            )
        """)
        print("Created table applications")
    else:
        print("Table applications already exists")

    conn.commit()
    conn.close()


if __name__ == '__main__':
    migrate()
