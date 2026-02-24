"""Migration: applicant_token, player_id nullable, table ap_registrations."""
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

    cur.execute("PRAGMA table_info(applications)")
    cols = {r[1] for r in cur.fetchall()}
    if 'applicant_token' not in cols:
        cur.execute("ALTER TABLE applications ADD COLUMN applicant_token VARCHAR(64)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_applications_applicant_token ON applications(applicant_token)")
        print("Added applications.applicant_token")

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ap_registrations'")
    if cur.fetchone() is None:
        cur.execute("""
            CREATE TABLE ap_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER NOT NULL UNIQUE REFERENCES applications(id),
                nickname VARCHAR(64) NOT NULL,
                version VARCHAR(32) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                icon_filename VARCHAR(255) NOT NULL
            )
        """)
        print("Created table ap_registrations")

    # Пересоздать applications с player_id nullable (для заявок на регистрацию до принятия)
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_mig_reg_done'")
    if cur.fetchone() is None:
        cur.execute("CREATE TABLE applications_reg_new (id INTEGER PRIMARY KEY, player_id INTEGER REFERENCES players(id), applicant_token VARCHAR(64), type INTEGER NOT NULL, status INTEGER NOT NULL DEFAULT 1, created_at DATETIME NOT NULL, updated_at DATETIME, notes TEXT)")
        cur.execute("""
            INSERT INTO applications_reg_new (id, player_id, applicant_token, type, status, created_at, updated_at, notes)
            SELECT id, player_id, applicant_token, type, status, created_at, updated_at, notes FROM applications
        """)
        cur.execute("DROP TABLE applications")
        cur.execute("ALTER TABLE applications_reg_new RENAME TO applications")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_applications_applicant_token ON applications(applicant_token)")
        cur.execute("CREATE TABLE _mig_reg_done (x INT)")
        print("Recreated applications with nullable player_id")
    else:
        print("applications already nullable")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()


if __name__ == '__main__':
    migrate()
