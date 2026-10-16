"""Seed demo data into the three service databases (idempotent: skips rows that already exist).
Run:  docker compose --profile tools run --rm seed      (after `docker compose up -d` so migrations have run)
User ids are deterministic (uuid5) so users_db.users.id matches payments_db.accounts.user_id."""
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
STUDENTS = [  # mssv, name, term, amount  (one row per unpaid term; MSSVs may contain letters, always 8 chars)
    ("52100001", "Pham Minh D", "2025-HK1", Decimal("15000000")),
    ("52100002", "Hoang Thu E", "2025-HK1", Decimal("18500000")),
    ("52100003", "Vo Quoc F",   "2025-HK1", Decimal("12000000")),
    ("52100004", "Dang Mai G",  "2025-HK1", Decimal("40000000")),  # larger than bob's balance -> insufficient-funds demo
    # --- payment-test pool (all UNPAID) ---
    ("521H0081", "Nguyen Thanh Long", "2025-HK1", Decimal("16500000")),
    ("521E0001", "Tran Ngoc Anh",     "2025-HK1", Decimal("22000000")),
    ("E2400001", "Le Hoang Nam",      "2025-HK1", Decimal("9800000")),
    ("521H0102", "Pham Thu Trang",    "2025-HK1", Decimal("14200000")),
    ("522H0045", "Bui Duc Huy",       "2025-HK1", Decimal("17300000")),
    ("520K0123", "Do Minh Chau",      "2025-HK1", Decimal("11750000")),
    ("523C0007", "Ngo Gia Bao",       "2025-HK1", Decimal("4500000")),    # bob (5M) can afford
    ("E2300112", "Vu Khanh Linh",     "2025-HK1", Decimal("3200000")),    # bob (5M) can afford
    ("E2400050", "Dinh Cong Thanh",   "2025-HK1", Decimal("5000000")),    # exactly bob's balance -> boundary case
    ("521V0042", "Huynh Tan Phat",    "2025-HK1", Decimal("13600000")),
    ("522H0099", "Kieu Anh Thu",      "2024-HK2", Decimal("9500000")),    # two unpaid terms: older term is offered first,
    ("522H0099", "Kieu Anh Thu",      "2025-HK1", Decimal("18000000")),   #   2025-HK1 appears after it is paid
    ("52200011", "Ly Bao Ngoc",       "2025-HK1", Decimal("12500000")),
    ("52200012", "Mai Quoc Viet",     "2025-HK1", Decimal("19900000")),
    ("52200013", "Trinh Hai Yen",     "2025-HK1", Decimal("8750000")),
    ("52300021", "Duong Minh Khoa",   "2025-HK1", Decimal("21400000")),
    ("52300022", "Cao Thi Lan",       "2025-HK1", Decimal("10300000")),
    ("52300023", "Phan Van Tai",      "2025-HK1", Decimal("26800000")),
    ("52400031", "Ta Thu Ha",         "2025-HK1", Decimal("7600000")),
    ("52400032", "Lam Nhat Minh",     "2025-HK1", Decimal("15750000")),
    ("52400033", "Chau Ngoc Tram",    "2025-HK1", Decimal("120000000")),  # more than any demo balance
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

    print(f"Seeded {len({s[0] for s in STUDENTS})} students / {len(STUDENTS)} tuitions. "
          "Demo logins: alice / bob / carol  (password: Password123!)")


if __name__ == "__main__":
    main()
