"""Seed demo data into the three service databases (idempotent: skips rows that already exist).
Run:  docker compose --profile tools run --rm seed      (after `docker compose up -d` so migrations have run)
Developer top-up (demo only, not a user feature):
      docker compose --profile tools run --rm seed topup bob 50000000
User ids are deterministic (uuid5) so users_db.users.id matches payments_db.accounts.user_id."""
import argparse
import os
import uuid
from decimal import Decimal
from sqlalchemy import create_engine, text
from shared.security import hash_password

NS = uuid.UUID("11111111-1111-1111-1111-111111111111")
uid = lambda name: str(uuid.uuid5(NS, name))

USERS = [  # username, password, full name, phone, email, balance
    ("alice", "Password123!", "Nguyen Van A", "0900000001", "alice@example.com", Decimal("30000000")),
    ("bob",   "Password123!", "Tran Thi B",   "0900000002", "bob@example.com",   Decimal("5000000")),
    ("carol", "Password123!", "Le Van C",     "0900000003", "carol@example.com", Decimal("100000000")),
]
STUDENTS = [  # mssv, name, term, amount
    ("52100001", "Pham Minh D", "2025-HK1", Decimal("15000000")),
    ("52100002", "Hoang Thu E", "2025-HK1", Decimal("18500000")),
    ("52100003", "Vo Quoc F",   "2025-HK1", Decimal("12000000")),
    ("52100004", "Dang Mai G",  "2025-HK1", Decimal("40000000")),  # larger than bob's balance -> insufficient-funds demo
]


def main():
    users = create_engine(os.environ["USERS_DB_URL"])
    tuition = create_engine(os.environ["TUITION_DB_URL"])
    pay = create_engine(os.environ["PAYMENTS_DB_URL"])

    with users.begin() as c:
        for username, pw, name, phone, email, _ in USERS:
            if c.execute(text("SELECT 1 FROM users WHERE username=:u"), {"u": username}).first():
                continue
            c.execute(text("INSERT INTO users (id, username, password_hash, full_name, phone, email) "
                           "VALUES (:id,:u,:h,:n,:p,:e)"),
                      {"id": uid(username), "u": username, "h": hash_password(pw), "n": name, "p": phone, "e": email})

    with pay.begin() as c:
        for username, *_, balance in USERS:
            c.execute(text("INSERT IGNORE INTO accounts (id, user_id, balance, version) VALUES (:id,:u,:b,0)"),
                      {"id": uid("acc-" + username), "u": uid(username), "b": balance})

    with tuition.begin() as c:
        for mssv, name, term, amount in STUDENTS:
            c.execute(text("INSERT IGNORE INTO students (student_id, full_name) VALUES (:s,:n)"), {"s": mssv, "n": name})
            c.execute(text("INSERT IGNORE INTO tuitions (id, student_id, term, amount, status, version) "
                           "VALUES (:id,:s,:t,:a,'UNPAID',0)"),
                      {"id": uid("tuition-" + mssv + term), "s": mssv, "t": term, "a": amount})

    print("Seeded. Demo logins: alice / bob / carol  (password: Password123!)")


def topup(username, amount):
    """Add `amount` to a user's balance. Bumps `version` so in-flight optimistic-lock updates see the change."""
    if amount <= 0:
        raise SystemExit("amount must be > 0")
    users = create_engine(os.environ["USERS_DB_URL"])
    pay = create_engine(os.environ["PAYMENTS_DB_URL"])

    with users.connect() as c:
        row = c.execute(text("SELECT id FROM users WHERE username=:u"), {"u": username}).first()
    if not row:
        raise SystemExit(f"unknown user: {username}")

    with pay.begin() as c:
        updated = c.execute(text("UPDATE accounts SET balance = balance + :a, version = version + 1 WHERE user_id = :u"),
                            {"a": amount, "u": row.id}).rowcount
        if not updated:
            raise SystemExit(f"no account for {username} (run the seed first)")
        balance = c.execute(text("SELECT balance FROM accounts WHERE user_id = :u"), {"u": row.id}).scalar_one()

    print(f"Topped up {username} by {amount:,}. New balance: {balance:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data, or top up a demo account.")
    sub = parser.add_subparsers(dest="cmd")
    p_top = sub.add_parser("topup", help="add money to a user's balance (developer/demo use only)")
    p_top.add_argument("username")
    p_top.add_argument("amount", type=Decimal)
    args = parser.parse_args()

    if args.cmd == "topup":
        topup(args.username, args.amount)
    else:
        main()
