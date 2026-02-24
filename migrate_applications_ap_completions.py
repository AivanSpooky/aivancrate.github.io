"""Migration: applications — только player, type, status, даты, notes; детали прохождений в ap_completions."""
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
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    # 1) ap_completions уже есть?
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ap_completions'")
    if cur.fetchone() is None:
        cur.execute("""
            CREATE TABLE ap_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER NOT NULL UNIQUE REFERENCES applications(id),
                level_id INTEGER NOT NULL REFERENCES aivanlevels(id),
                player_id INTEGER NOT NULL REFERENCES players(id),
                completion_date DATE,
                video_url TEXT NOT NULL DEFAULT '',
                comment TEXT
            )
        """)
        print("Created table ap_completions")
        # 2) Копируем заявки типа 1 из applications (пока ещё с level_id, completion_date)
        cur.execute("""
            INSERT INTO ap_completions (application_id, level_id, player_id, completion_date, video_url, comment)
            SELECT id, level_id, player_id, completion_date, '', ''
            FROM applications WHERE type = 1 AND level_id IS NOT NULL
        """)
        print("Migrated completion applications into ap_completions")
    else:
        print("Table ap_completions already exists")

    # 3) Проверяем, есть ли в applications ещё level_id (старая схема)
    cur.execute("PRAGMA table_info(applications)")
    cols = {r[1] for r in cur.fetchall()}
    if 'level_id' in cols:
        cur.execute("""
            CREATE TABLE applications_new (
                id INTEGER PRIMARY KEY,
                player_id INTEGER NOT NULL REFERENCES players(id),
                type INTEGER NOT NULL,
                status INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME,
                notes TEXT
            )
        """)
        cur.execute("""
            INSERT INTO applications_new (id, player_id, type, status, created_at, updated_at, notes)
            SELECT id, player_id, type, status, created_at, updated_at, notes FROM applications
        """)
        cur.execute("DROP TABLE applications")
        cur.execute("ALTER TABLE applications_new RENAME TO applications")
        print("Recreated applications without level_id, completion_date")
    else:
        print("applications already in new schema")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()


if __name__ == '__main__':
    migrate()
