# Microservices design

Diagram: `docs/diagrams/architecture.mmd`. API details: `docs/api/endpoints.md`.

## 1. Services and responsibilities

Each service owns its data: no service reads another service's database. Data owned elsewhere is reached through
that service's API, and cross-service ids (e.g. `transactions.tuition_id`) are plain columns without a FOREIGN KEY.

| Service | Responsibility | Owns (data) | Public API (via gateway) | Internal API | Calls |
|---|---|---|---|---|---|
| web (nginx + React) | UI: login, home (balance, pending payments), tuition payment with OTP, history | - | serves the SPA, proxies `/api/*` | - | gateway |
| gateway | Single entry point: verifies the JWT, sets `X-User-Id`, routes by path prefix, rate limits, hides `/internal/*` | rate-limit counters (Redis) | `/api/*` | - | user, tuition, payment |
| user-service | Login (bcrypt, issues JWT), user profile | `users_db.users` | `POST /auth/login`, `GET /users/me` | `GET /internal/users/{id}` | - |
| tuition-service | Student and tuition lookup by MSSV; reservation state machine UNPAID -> RESERVED -> PAID so one tuition is paid once | `tuition_db.students`, `tuitions` | `GET /tuitions/{mssv}` | `reserve`, `commit`, `release` | - |
| payment-service | Payment account and balance; transactions; orchestrates the payment saga; ledger; outbox; expiry / reconcile job | `payments_db.accounts`, `transactions`, `ledger_entries`, `outbox_events` | `GET /accounts/me`, `/transactions*` | - | user, tuition, otp; Redis Streams (outbox relay) |
| otp-service | Generates 6-digit OTPs, stores them hashed with a 5-min TTL, verifies single-use, limits resends and wrong attempts | OTP keys (Redis) | - | `POST /internal/otp`, `POST /internal/otp/verify` | Redis Streams (`otp.requested`) |
| notification-service | Sends the OTP email and the payment receipt (SMTP; printed to the log if SMTP is not set) | email dedupe keys (Redis) | - | - | Redis Streams (consumer), SMTP |

Infrastructure: MySQL 8 (one database and one DB user per service) and Redis 7 (OTP store, rate-limit counters,
event streams; AOF persistence). No separate message broker.

## 2. Communication

**Synchronous REST (HTTP/JSON)**, used when the caller needs the answer to continue:
- Browser -> nginx -> gateway -> user / tuition / payment-service.
- payment-service -> user-service (payer email and name), tuition-service (lookup, reserve, commit, release),
  otp-service (issue, verify). Timeout 5 s; no DB connection is held while waiting.

**Asynchronous events (Redis Streams, consumer group `notification`)**, used for side effects the user does not wait on:
- `otp.requested`: published by otp-service when an OTP is issued.
- `payment.completed`: written to `outbox_events` in the same MySQL transaction that sets SUCCESS, then
  published by the outbox relay.
- notification-service reads both and sends the emails. At-least-once delivery, duplicates skipped.

## 3. Payment flow (saga orchestrated by payment-service)

| Step | Action | On failure (compensation) |
|---|---|---|
| 1 | Idempotency-Key check: same key -> return the existing transaction | - |
| 2 | Look up tuition (tuition-service), pre-check balance | 404 / 409 / 422, nothing created |
| 3 | Insert transaction `PENDING_OTP` (expires with the OTP) | - |
| 4 | Reserve tuition for this transaction (tuition-service) | mark FAILED |
| 5 | Issue OTP (otp-service), email via `otp.requested` | release the reservation, mark FAILED |
| 6 | User sends the OTP; otp-service verifies and consumes it | 400, user may retry or resend |
| 7 | One MySQL transaction: lock transaction row, lock account row, re-check balance, debit, DEBIT ledger entry, `PROCESSING` | insufficient balance -> FAILED, release the reservation |
| 8 | Commit tuition -> PAID (tuition-service) | 409 -> refund (CREDIT ledger entry), FAILED; no answer -> stays PROCESSING, the job retries |
| 9 | One MySQL transaction: `SUCCESS` + outbox event `payment.completed` -> receipt email | - |

Cancel (user) and expiry (job, every 15 s) move `PENDING_OTP` to CANCELLED / EXPIRED and release the reservation.

## 4. Consistency and concurrency

| Situation | Mechanism |
|---|---|
| Two payers pay the same tuition | tuition-service changes status with one conditional `UPDATE ... WHERE status=...`; only one reservation wins, the other gets 409. Unique `paid_by_txn`. |
| Two payments from one account confirmed together | `SELECT ... FOR UPDATE` on the account row; balance re-checked under the lock; `CHECK (balance >= 0)` |
| Double click / client retry on "Pay" | `Idempotency-Key` header, unique index on `transactions.idempotency_key` |
| Same OTP submitted several times | Atomic Lua verify-and-delete in Redis (single use); unique `(transaction_id, type)` on ledger entries (one DEBIT) |
| Cancel, expiry and verify at the same moment | Every status change is conditional on the current status under a row lock; only one wins |
| Deadlock / lock wait timeout | Fixed lock order (transaction row, then account row); the MySQL transaction is retried up to 3 times |
| Crash between steps | Expiry job releases stale holds; reconcile job finishes `PROCESSING`; tuition holds also expire on their own (`reserved_until`) |
| Event lost or sent twice | Transactional outbox (no lost events); consumer dedupe (no duplicate emails) |

Tested by `tests/load/test_races.py` (race scenarios) and the Locust runs with database invariant checks
(`docs/reports/LOAD_TEST_REPORT.md`).

## 5. Redis data

| Key | Type, TTL | Owner | Purpose |
|---|---|---|---|
| `otp:txn:<transaction_id>` | HASH `{code_hash, attempts}`, 300 s | otp-service | The one active OTP of a transaction (SHA-256 only) |
| `otp:code:<code_hash>` | STRING -> transaction id, 300 s | otp-service | No two active OTPs share a code |
| `otp:issued:<transaction_id>` | counter, OTP window x 4 | otp-service | Max 4 OTPs per transaction |
| `otp:cooldown:<transaction_id>` | flag, 30 s | otp-service | Min gap between OTPs |
| `rl:<rule>:<ip or user>` | counter, 60 s | gateway | Rate limits |
| `events:otp.requested`, `events:payment.completed` | STREAM (~10,000 entries) | otp / payment, read by notification | Event bus |
| `notif:sent:<type>:<id>` | flag, 24 h | notification-service | Email dedupe |
