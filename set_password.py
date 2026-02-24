"""Установка пароля игрока по никнейму. Запуск: python set_password.py <nickname> <password>"""
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from main import app
from models import db, Players
from werkzeug.security import generate_password_hash

def main():
    if len(sys.argv) < 3:
        print("Usage: python set_password.py <nickname> <password>")
        sys.exit(1)
    nickname = sys.argv[1]
    password = sys.argv[2]
    if len(password) < 6:
        print("Password must be at least 6 characters")
        sys.exit(1)
    with app.app_context():
        player = Players.query.filter(Players.nickname.ilike(nickname)).first()
        if not player:
            print(f"Player '{nickname}' not found")
            sys.exit(1)
        player.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        db.session.commit()
        print(f"Password set for {player.nickname} (id={player.id})")

if __name__ == '__main__':
    main()
