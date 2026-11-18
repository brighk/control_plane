"""Create a user: uv run create_user.py <username>"""

import argparse
import getpass
import sys

from sqlmodel import Session, select

from auth import hash_password
from db import engine, init_db
from models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a control-plane user.")
    parser.add_argument("username")
    args = parser.parse_args()

    init_db()
    with Session(engine) as session:
        if session.exec(select(User).where(User.username == args.username)).first():
            sys.exit(f"User '{args.username}' already exists.")

        password = getpass.getpass("Password: ")
        if len(password) < 8:
            sys.exit("Password must be at least 8 characters.")
        if getpass.getpass("Repeat password: ") != password:
            sys.exit("Passwords do not match.")

        session.add(User(username=args.username, password_hash=hash_password(password)))
        session.commit()
    print(f"Created user '{args.username}'.")


if __name__ == "__main__":
    main()
