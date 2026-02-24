"""Проверка, подходит ли пароль к хешу. Хеш нельзя обратить в пароль — только проверить кандидат.
Запуск: python check_password.py <password_hash> <candidate_password>
Вернёт OK если пароль совпадает, иначе FAIL."""
import sys
from werkzeug.security import check_password_hash

def main():
    if len(sys.argv) < 3:
        print("Usage: python check_password.py <password_hash> <candidate_password>")
        print("Note: Hash cannot be reversed to password; this only checks if the candidate matches.")
        sys.exit(1)
    hash_str = sys.argv[1]
    password = sys.argv[2]
    if check_password_hash(hash_str, password):
        print("OK")
    else:
        print("FAIL")

if __name__ == '__main__':
    main()
