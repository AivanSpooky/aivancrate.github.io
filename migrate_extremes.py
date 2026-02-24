"""Migration: AivanExtremes - remove difficulty, add completion, enjoyment, compl_date."""
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
        print("DB not found, skip migration (tables will be created on first run)")
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(aivanextremes)")
    cols = {r[1] for r in cur.fetchall()}

    if 'difficulty' in cols and ('completion' not in cols or 'enjoyment' not in cols or 'compl_date' not in cols):
        # Create new table with updated schema
        cur.execute("""
            CREATE TABLE aivanextremes_new (
                id INTEGER PRIMARY KEY,
                top INTEGER,
                level_name VARCHAR,
                creator_name VARCHAR,
                img VARCHAR,
                attempts VARCHAR,
                device VARCHAR,
                fps VARCHAR,
                opinion TEXT,
                completion VARCHAR,
                enjoyment NUMERIC(4,2),
                compl_date DATE
            )
        """)
        cur.execute("""
            INSERT INTO aivanextremes_new (id, top, level_name, creator_name, img, attempts, device, fps, opinion)
            SELECT id, top, level_name, creator_name, img, attempts, device, fps, opinion
            FROM aivanextremes
        """)
        cur.execute("DROP TABLE aivanextremes")
        cur.execute("ALTER TABLE aivanextremes_new RENAME TO aivanextremes")
        print("Migrated: removed difficulty, added completion, enjoyment, compl_date")
    elif 'completion' not in cols:
        # Add new columns if they don't exist (older schema without difficulty)
        for col, typ in [('completion', 'VARCHAR'), ('enjoyment', 'NUMERIC(4,2)'), ('compl_date', 'DATE')]:
            if col not in cols:
                cur.execute(f"ALTER TABLE aivanextremes ADD COLUMN {col} {typ}")
        if 'difficulty' in cols:
            # SQLite doesn't support DROP COLUMN easily in older versions - skip or use table recreation
            print("Note: difficulty column still exists. Use SQLite 3.35+ for DROP COLUMN.")
        print("Added columns: completion, enjoyment, compl_date")
    else:
        print("Schema already up to date.")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    migrate()
