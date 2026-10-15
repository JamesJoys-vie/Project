"""Concurrency checks against the running stack (through nginx -> gateway).

Needs: a FRESHLY seeded stack and SMTP NOT configured (OTPs are then read from the notification-service log).
    docker compose down -v; SMTP_USER= docker compose up -d --build; docker compose --profile tools run --rm seed
    (`SMTP_USER=` blanks SMTP for this run only, so OTP emails go to the notification-service log)
    python tests/load/race_check.py            (only needs `httpx`)

Scenarios (seed data: alice 30M, carol 100M; students 52100001=15M, 52100002=18.5M, 52100003=12M):
  A  same student, many payers at once   -> exactly one reservation wins, the rest get 409
  B  same account, two payments that together exceed the balance, OTPs confirmed at the same time
                                          -> one SUCCESS, one FAILED "Insufficient balance", balance never < 0
  C  same Idempotency-Key sent 8x in parallel -> one transaction
  D  same OTP submitted 5x in parallel   -> money debited once
"""
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import httpx

BASE = "http://localhost:8080/api"
PASSWORD = "Password123!"
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {info}")


def login(username: str) -> httpx.Client:
    c = httpx.Client(base_url=BASE, timeout=30)
    r = c.post("/auth/login", json={"username": username, "password": PASSWORD})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


def balance(c: httpx.Client) -> Decimal:
    return Decimal(str(c.get("/accounts/me").json()["balance"]))


def initiate(c: httpx.Client, mssv: str, key: str | None = None) -> httpx.Response:
    return c.post("/transactions", json={"student_id": mssv}, headers={"Idempotency-Key": key or str(uuid.uuid4())})


def otp_for(txn_id: str, timeout_s: float = 20) -> str:
    """Latest OTP emailed for the transaction, scraped from the notification-service log (dev SMTP fallback)."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        log = subprocess.run(["docker", "compose", "logs", "--no-log-prefix", "notification-service"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        codes = re.findall(r"one-time password is (\d{6})\.\s*\n.*\n\s*Transaction: " + re.escape(txn_id), log)
        if codes:
            return codes[-1]
        time.sleep(0.5)
    raise RuntimeError(f"no OTP found in logs for {txn_id}")


def scenario_a():
    payers = [login("alice"), login("carol")] * 4  # 8 concurrent attempts, 2 users
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda c: initiate(c, "52100003").status_code, payers))
    check("A same student: one winner", codes.count(201) == 1 and codes.count(409) == 7, str(sorted(codes)))
    for c in payers[:2]:  # cancel the winner so the student is free again
        for t in c.get("/transactions").json():
            if t["status"] == "PENDING_OTP":
                c.post(f"/transactions/{t['id']}/cancel")


def scenario_b():
    alice = login("alice")
    before = balance(alice)
    t1, t2 = initiate(alice, "52100001").json(), initiate(alice, "52100002").json()
    otps = [otp_for(t1["id"]), otp_for(t2["id"])]
    with ThreadPoolExecutor(2) as ex:
        res = list(ex.map(lambda p: alice.post(f"/transactions/{p[0]['id']}/verify-otp", json={"otp": p[1]}),
                          [(t1, otps[0]), (t2, otps[1])]))
    statuses = sorted(r.json()["transaction"]["status"] for r in res)
    after = balance(alice)
    paid = sum(Decimal(str(t["amount"])) for t, r in zip((t1, t2), res) if r.json()["transaction"]["status"] == "SUCCESS")
    check("B same account: one SUCCESS one FAILED", statuses == ["FAILED", "SUCCESS"], str(statuses))
    check("B balance consistent and >= 0", after >= 0 and after == before - paid, f"{before} -> {after}")


def scenario_c():
    carol, key = login("carol"), str(uuid.uuid4())
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda _: initiate(carol, "52100003", key), range(8)))
    ids = {r.json().get("id") for r in res if r.status_code == 201}
    check("C idempotency: one transaction", len(ids) == 1 and all(r.status_code == 201 for r in res),
          str([r.status_code for r in res]))
    return carol, ids.pop() if ids else None


def scenario_d(carol: httpx.Client, txn_id: str):
    before, otp = balance(carol), otp_for(txn_id)
    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(lambda _: carol.post(f"/transactions/{txn_id}/verify-otp", json={"otp": otp}), range(5)))
    after = balance(carol)
    check("D double submit: debited once", before - after == Decimal("12000000"),
          f"{before} -> {after}, codes {[r.status_code for r in res]}")


if __name__ == "__main__":
    scenario_a()
    scenario_b()
    carol, txn = scenario_c()
    if txn:
        scenario_d(carol, txn)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    sys.exit(1 if failed else 0)
