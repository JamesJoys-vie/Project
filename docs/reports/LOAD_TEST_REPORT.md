# Load and concurrency test report (Phase 5)

Date: 2026-10-16. Tool: Locust 2.44.4 (+ pytest race tests and a database invariant checker).
Raw results per run: `docs/reports/<run>/` (`report.html` = Locust charts, `stats_*.csv`, `outcomes.json` =
business outcomes, `invariants.json` = database checks, `container_cpu.txt` = `docker stats` sample at ~100 s).

## 1. Verdict
- **Money is always correct.** Across ~100k requests and ~21k completed payments in the final runs, no balance
  went below 0, every balance change is explained by a ledger entry, every tuition was paid at most once, and the
  money taken from accounts equals the tuition marked paid (to the đồng). This also held in the run where the
  service collapsed (section 5): the failures were about availability, never about money.
- **Concurrency rules hold under load**: one winner per contested tuition, no overdraft from parallel payments on one
  account, one transaction per Idempotency-Key, one debit per double-submitted OTP, cancel/expiry/verify never
  both win.
- **Load testing found 4 real bugs and 1 capacity limit, all fixed** (section 5). Before the fixes, 150 users brought
  payment-service down (38% errors, still down minutes after the load stopped). After: 0 errors at 150 and 300 users.
- **Capacity on this machine:** ~150 requests/s (~35 completed payments/s). Beyond that, latency grows rather than
  errors (300 users: median 1.4 s, p99 2.5 s). Next limits: gateway and tuition-service, each one process (section 6).

## 2. Setup
- Machine: Docker Desktop on Windows 11, 12 CPUs / 7.6 GiB for Docker. Everything (stack + Locust) on one host.
- Stack as in `docker-compose.yml`, payment-service with 4 uvicorn processes, all other services 1 process.
- Load-test mode (`docker-compose.loadtest.yml`) changes only what a test client needs:
  OTP readable through an internal test endpoint (`OTP_TEST_ECHO`), gateway rate limits x1000 (all virtual users share
  one IP), OTP window 60 s / tuition hold 120 s (so abandoned payments expire during a run), SMTP off.
- Traffic goes through nginx -> gateway like the browser. Each run starts from `lt_data.py reset`
  (347 users, 653 students, 30,003 unpaid tuitions; separate from the demo data).
- Levels: 3 minutes each, users ramped at 10 % of the target per second.

## 3. What the virtual users do
| User type (share) | Behaviour | Expected |
|---|---|---|
| Payer (80 %) | own account + own student: lookup -> initiate -> OTP -> verify; balance and history views | SUCCESS |
| | sometimes on a spare student: wrong OTP then right one, cancel, abandon (left to expire), same OTP 3x at once, same Idempotency-Key 3x at once, resend right away | 400 then SUCCESS, CANCELLED, EXPIRED, one debit, one transaction, 429 then SUCCESS |
| Hot student (10 %) | 40 accounts fight for the same 10 students (100 terms each) | one reservation per term wins, others 409 |
| Shared account (10 %) | several users on 5 accounts of 150M, often confirming two payments at the same moment | balance runs out: 422 at initiate or FAILED "Insufficient balance" at verify, never below 0 |

Checks after every run (`verify_invariants.py`, straight from the three databases, after waiting for the background
jobs): **I1** no negative balance; **I2** balance = seed - debits + refunds; **I3** ledger matches each transaction status
and amount; **I4** SUCCESS <-> PAID tuition one-to-one; **I5** no tuition paid twice; **I6** money out = tuition paid;
**I7** one published `payment.completed` event per SUCCESS; **I8** nothing left PROCESSING / PENDING_OTP.

`pytest` race suite (`test_races.py`, 5 scenarios x 5 rounds = 25 tests, passed after every change): same student
from 8 requests, two payments over the balance confirmed together, same Idempotency-Key 8x, same OTP 5x,
cancel racing verify.

## 4. Results (final code)
| Run | Users | Requests | Failed | Req/s | p50 | p95 | p99 | Payments SUCCESS | Invariants |
|---|---|---|---|---|---|---|---|---|---|
| small | 50 | 18,799 | 0 | 105 | 28 ms | 120 ms | 190 ms | 3,786 | pass |
| medium | 150 | 27,019 | 0 | 150 | 500 ms | 1.2 s | 1.7 s | 6,081 | pass |
| stress | 300 | 28,332 | 0 | 156 | 1.4 s | 2.3 s | 2.5 s | 6,272 | pass |
| stress (repeat) | 300 | 23,620 | 14 (0.06 %) | 130 | 1.7 s | 2.8 s | 6.6 s | 5,229 | pass |

The 14 failures in the repeat were 502s during the first seconds, while 300 logins arrived within 10 s (bcrypt is
slow on purpose) and payment-service's 5 s timeout to user-service ran out. The run recovered by itself and finished
clean: that is the difference from the collapse in section 5.

Per endpoint, medium run: p50 / p95
| Endpoint | p50 | p95 |
|---|---|---|
| GET /accounts/me | 33 ms | 110 ms |
| GET /tuitions/{mssv} | 530 ms | 870 ms |
| POST /transactions (initiate) | 580 ms | 1.6 s |
| POST /transactions/{id}/verify-otp | 440 ms | 890 ms |
| POST /auth/login | 510 ms | 770 ms |

Contention outcomes, stress run (`stress/outcomes.json`):
- **Same student:** 465 payments succeeded; 665 lost the reservation race (409) and 500 saw the student RESERVED at
  lookup. Each term was paid exactly once (I4, I5).
- **Same account:** 1,220 payments were stopped by the balance pre-check (422) and 15 by the re-check under the account
  lock at verify ("Insufficient balance", nothing debited). Balances never went below 0 (I1).
- **Duplicates:** 106 triplets with one Idempotency-Key each gave one transaction. 156 OTP triplets each debited
  once (some extra copies got 200 with the already-final result, the rest 400 "already used").
- **Background jobs:** 102 abandoned payments expired and released their hold, 123 were cancelled, and 0 stayed stuck.

## 5. Problems found and fixed
| # | Found by | Problem | Fix |
|---|---|---|---|
| 1 | medium run: 38 % 502s, service unhealthy | payment-service kept its DB connection while waiting on other services (tuition, user, OTP), so 30 pooled connections ran out | `saga.end_read()` finishes the read transaction before every remote call. Connections are now held for milliseconds (pool peak 30/30 -> under 10) |
| 2 | stress run: user-service frozen for minutes with idle CPU | For sync endpoints FastAPI validates the response in a **second** threadpool step while the `get_db` session still holds its connection. Under load, finished requests waited for a thread and all threads waited for a connection, so the queue never drained | `Depends(get_db, scope="function")` in all DB services: the session closes when the endpoint returns (FastAPI >= 0.121) |
| 3 | both of the above lasted long after the load | a pool wait (30 s) longer than the gateway timeout (20 s) let requests nobody waited for pile up. `/health` ran in the same busy threadpool, so Docker reported "unhealthy" | pool timeout 5 s -> `503 Service busy` + `Retry-After`. `/health` is `async` in every service |
| 4 | Locust duplicate-key flow at 150+ users | same Idempotency-Key in parallel: a late duplicate saw the tuition RESERVED by its own twin and got 409 instead of the original transaction | before answering 409, check the key again and return the existing transaction |
| 5 | CPU sampling: payment-service at ~117 % = one core | one Python process (GIL) | 4 uvicorn processes (`PAYMENT_WORKERS`), DB pool configurable (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`), MySQL `max_connections` 300 |

Medium (150 users) before -> after: 2,505 -> 27,019 requests, **37.9 % -> 0 % failed**, 12 -> 150 req/s,
p95 37 s -> 1.2 s. The before-run (`medium-before-fix/`) also failed I4/I7/I8: 13 payments stuck PROCESSING and 25
never expired, because the expiry and reconcile jobs could not get a DB connection either. Its money checks (I1-I3,
I5, I6) still passed.

How #1 and #2 were found: `py-spy dump` showed every thread waiting for a pool connection at its first query.
A temporary pool tracer (stack trace at checkout) showed which code held the connections. It was removed afterwards.

## 6. Limits and next steps
- Throughput levels off at ~150 req/s between 150 and 300 users. At 300 users, gateway (~105 %) and
  tuition-service (~113 %) each run at one full core: each is one process. Both are stateless (rate limits live in
  Redis; tuition changes are conditional UPDATEs), so `--workers` would raise the ceiling the same way as for
  payment-service.
- Login is CPU-heavy (bcrypt) and was the trigger of the short 502 burst. More user-service processes, or one
  retry with backoff for `get_user` in payment-service, would remove it.
- One machine runs both the stack and Locust (Locust used ~35 % of a core), so the absolute numbers are a lower bound.

## 7. Reproduce
See README "Load and concurrency tests". One level:
`docker compose -f docker-compose.yml -f docker-compose.loadtest.yml --profile loadtest run --rm loadtest sh run_level.sh medium 150 15 3m`
