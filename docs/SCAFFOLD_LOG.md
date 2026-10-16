# Scaffold log

Running record of what was generated and why. Newest entries at the bottom.

> Sections 1-6 describe the first scaffold and are kept as history: RabbitMQ was replaced by Redis Streams (section 7),
> the 501 stubs were implemented in Phase 3 (section 10), and migration 0002 changed the ledger key (section 10).
> Current design: `docs/design/services.md`, `docs/api/endpoints.md`, `docs/diagrams/`.

## 1. Infrastructure
- `docker-compose.yml`: mysql:8.0, redis:7, rabbitmq:3-management, 5 services, gateway, web (nginx + React build).
  Optional profiles: `public` (ngrok tunnel to `web:80`), `tools` (seed job).
- `.env.example`: all secrets/config in one template (copy to `.env`).
- `backend/infra/mysql-init/01-init.sh`: creates `users_db`, `tuition_db`, `payments_db` and one DB user per service
  (shell script, not .sql, so passwords come from env vars). Runs only when the MySQL data volume is empty.
- Services get only the env vars they need (no shared `env_file`).

## 2. Backend base
- `backend/requirements.txt`: one dependency list shared by all Python services (simple for a midterm).
- `backend/Dockerfile` + `infra/entrypoint.sh`: one generic image recipe; `SERVICE_DIR` build-arg picks the service.
  Entry point runs `alembic upgrade head` (if the service has `alembic.ini`) then starts uvicorn on port 8000.
- `backend/shared/`: `db.py` (engine/session helpers), `security.py` (bcrypt + JWT), `events.py` (RabbitMQ publish/consume).
- **Decision:** sync SQLAlchemy + PyMySQL (not async `asyncmy`). FastAPI runs `def` endpoints in a threadpool;
  locking semantics (`SELECT ... FOR UPDATE`) are identical and the code is much simpler to reason about.
- Environment note: some `.gitkeep` placeholders could not be deleted (the shell blocks `rm` on your folders); they are harmless.

## 3. Services (backend/services/*)
All expose `GET /health` on port 8000. Business endpoints are **typed stubs returning 501** with a TODO describing the exact logic to implement.
*(Superseded: all stubs implemented in section 10; ledger key now `(transaction_id, type)`, see section 10.)*
- **user_service** (`users_db`): model `users`; stubs `POST /auth/login`, `GET /users/me`; migration 0001.
- **tuition_service** (`tuition_db`): models `students`, `tuitions` (status UNPAID/RESERVED/PAID, `version`, `reserved_until`);
  stubs `GET /tuitions/{mssv}` + internal `reserve / commit / release`; migration 0001.
  *Refinement vs. plan:* one tuition row per (student, term) already guarantees a single liability, so the unique key is
  `(student_id, term)` plus a unique `paid_by_txn` (a transaction can pay only one tuition) instead of the 3-column key.
- **payment_service** (`payments_db`): models `accounts` (CHECK balance >= 0), `transactions` (unique `idempotency_key`),
  `ledger_entries` (unique `transaction_id`), `outbox_events`; stubs `GET /accounts/me`, `GET/POST /transactions`,
  `verify-otp`, `resend-otp`, `cancel`; migration 0001. Saga steps are documented in the route docstrings.
  *Refinement:* balance is served by `GET /accounts/me` (payment-service owns the account), not `/users/me`.
- **otp_service** (Redis): stubs `POST /internal/otp`, `POST /internal/otp/verify` with the Redis strategy noted in TODOs.
- **notification_service**: SMTP mailer + RabbitMQ consumer written; consumer startup is commented out until events are published.
- Internal endpoints (`/internal/...`) are **not** routed by the gateway.

## 4. Gateway and frontend
- **gateway** (`backend/gateway`): FastAPI reverse proxy. Routes `/api/{auth,users}` -> user, `/api/tuitions` -> tuition,
  `/api/{accounts,transactions}` -> payment. Verifies the JWT (except `POST /api/auth/login`), strips any client-sent
  `X-User-Id` and injects the verified one. OTP/notification services are not routed (internal only). Rate limiting is a TODO *(done in section 10)*.
- **frontend** (React + JavaScript + Vite, Tailwind v4, React Query, React Hook Form, React Router):
  routing, auth context (token in sessionStorage), API client with all endpoint helpers, working Login form,
  placeholder Tuition Payment / History pages with TODO notes describing the exact UI flow.
- **web container**: multi-stage Dockerfile (node build -> nginx). nginx serves the SPA and proxies `/api/` to the gateway,
  so the browser only ever talks to one origin (no CORS; Ngrok tunnels just `web:80`).

## 5. Seed, diagrams, docs
- `backend/scripts/seed.py`: 3 demo users (alice/bob/carol, password `Password123!`) with balances, 4 students with UNPAID tuition
  (one larger than bob's balance for the insufficient-funds case). Idempotent; deterministic uuid5 ids link users to accounts.
- `docs/diagrams/`: architecture, ERD, class (Mermaid) and use case (PlantUML).
- `docs/api/endpoints.md`: endpoint table (methods, payloads, status codes).
- Root `README.md` rewritten with layout and run steps.

## 6. Verification (what was and was not checked)
Checked (static): all 69 Python files parse/compile; `docker-compose.yml` is valid YAML with 12 services and every
`depends_on` target exists; `package.json` is valid JSON; `entrypoint.sh` and `01-init.sh` pass shell syntax checks;
no CRLF line endings in scripts/config.
**Not checked** (package installs were blocked in the sandbox, and Docker is not available there):
`docker compose build/up`, the FastAPI apps actually starting, Alembic migrations against a real MySQL, and `npm install` / `vite build`.
First real run is on your machine: see README "Run". If a build fails, send me the error output.

## Next phase (not started)
1. user-service login + `/users/me`; tuition lookup; `/accounts/me`
2. OTP service (Redis) + notification consumer enabled
3. Payment saga (initiate / verify-otp), outbox relay, expiry job, deadlock retry
4. Frontend payment flow + OTP modal
5. Locust/k6 concurrency tests (same account; same student)

## 7. Switch to "MySQL + Redis only" (RabbitMQ removed)
Why: fewer containers; Redis was already required for OTPs, and Redis Streams provide durable, acknowledged,
asynchronous messaging (consumer groups), which still satisfies the async-communication objective.
- `docker-compose.yml`: `rabbitmq` service removed. Redis now runs with AOF (`--appendonly yes`) on a `redis_data`
  volume so stream events survive restarts. otp/payment/notification get `REDIS_URL`; `RABBITMQ_URL` removed everywhere.
- `.env.example`: RabbitMQ variables removed; Ngrok values reset to placeholders (the template is meant to be committed).
  Your real Ngrok token/domain were moved into a new git-ignored `.env`.
- `backend/requirements.txt`: `pika` removed.
- `backend/shared/events.py`: rewritten for Redis Streams - `publish` (XADD to `events:<type>`, trimmed ~10k),
  `consume` (XREADGROUP + XACK after success, XAUTOCLAIM re-delivers messages stuck > 60s). At-least-once -> idempotent handlers.
- `backend/shared/redis_client.py`: new cached Redis client helper.
- payment_service: config `rabbitmq_url` -> `redis_url`; new `app/workers/outbox_relay.py` (MySQL outbox -> Redis Streams)
  and `app/workers/expiry_job.py` (expire stale PENDING_OTP, release reservations) as documented stubs.
- notification_service: consumer moved from `app/domain/consumer.py` to `app/workers/stream_consumer.py` (group `notification`);
  empty `api/`, `schemas/`, `repositories/`, `migrations/` removed (it has no HTTP API besides /health and no storage).
- otp_service: `rabbitmq_url` removed; empty `migrations/` removed (no SQL DB); new `app/repositories/otp_store.py`
  documents the Redis key layout (`otp:txn:<id>` hash with TTL, `otp:code:<code>` NX for uniqueness, Lua single-use verify).
- Docstrings in otp/payment routes and the outbox model updated; `docs/diagrams/architecture.mmd` redrawn; README updated.
- Cleanup: removed `__pycache__` folders left by earlier checks and `.gitkeep` files in folders that now contain code.
Note: entries in sections 1-6 above that mention RabbitMQ describe the earlier state and are superseded by this section.

## 8. Phase 4 - frontend wireframes
- `docs/wireframes/wireframes.html`: self-contained low-fidelity wireframes (open in a browser, no build step).
  Screens: Login (`/login`), Tuition payment (`/pay`) with lookup states (404 / already paid / insufficient balance),
  OTP verification modal, Result (success / failed), Transaction history (`/history`, incl. empty state).
  Each screen has numbered notes mapping UI pieces to API calls and enable/disable rules; ends with a component inventory.
- Layout decisions: one shared app shell (header nav + centered column ~920px); `/pay` = Payer | Tuition cards side by side,
  full-width Confirm card below; errors shown inline in the card that caused them; Result replaces the form (no new route).
- Added **Home (`/home`)**: new landing page after login and first nav item. Balance tile, success / not-completed counts,
  "Waiting for OTP" card (Resume reopens the OTP modal on `/pay`, Cancel calls `/cancel`), last 5 transactions.
  Uses only existing endpoints (`/accounts/me`, `/transactions`). Screens renumbered (Pay = 3 ... History = 6).
  Deliberately out of scope: tuition due dates and payment-method management (no data for them; listed as future work).
  Implementation note: `App.jsx` will need a `/home` route and the catch-all redirect changed from `/pay` to `/home`.
- **Hide / show amounts** (standing requirement): every ₫ value (balances, amounts, totals) can be masked as `•••••••• ₫`.
  Eye button in every app header + next to each balance; one global state remembered in `localStorage`, hidden by default;
  applies on Home, Pay (incl. Confirm card and OTP recap), Result and History. Components: `Money` (renders the mask) and an
  `AmountVisibility` context + `EyeToggle`. Visual privacy only, values are still in API responses. The wireframe page has a
  working preview switch in its top bar.

## 10. Phase 3 - backend business logic
All 501 stubs replaced. Branch `phase-3-backend`.
- **user-service**: `POST /auth/login` (bcrypt; unknown usernames still pay one bcrypt check so timing does not leak
  which usernames exist), `GET /users/me`, new internal `GET /internal/users/{id}` (payer email/name for emails).
- **tuition-service**: `GET /tuitions/{mssv}` (oldest unpaid term, else latest PAID; a hold past `reserved_until`
  is reported as UNPAID). `reserve / commit / release` are each ONE conditional `UPDATE ... WHERE status=...`
  (compare-and-set), idempotent for the same transaction. Times are Python UTC, never MySQL `NOW()`.
  `reserve` also extends the hold when called again by the same txn (used by resend-otp).
  `commit` ignores `reserved_until` on purpose: once money moved, the commit must not lose to the clock.
- **otp-service**: Lua scripts for save (code-uniqueness key `SET NX`, old code dropped on resend) and verify
  (compare-and-delete = single-use; 5 wrong codes burn the OTP). Only SHA-256 of the code is stored.
  Issue limits per transaction: 30 s cooldown, max 4 OTPs. Publishes `otp.requested`.
- **notification-service**: consumer enabled (auto-restarts on Redis errors); dedupe `notif:sent:<type>:<id> NX`
  (OTP dedupe id includes the code hash so a resend still mails). **Without SMTP settings the email is written to
  the container log instead** (dev fallback: `docker compose logs notification-service`).
- **payment-service** (`app/domain/saga.py`, routes are thin):
  - initiate: idempotency key replay -> tuition lookup + unlocked balance pre-check (422) -> insert PENDING_OTP
    -> reserve (409 / compensation FAILED) -> OTP (compensation: release + FAILED).
  - verify: OTP -> ONE MySQL txn (lock txn row, lock account row, re-check balance, debit, DEBIT ledger,
    PROCESSING) -> tuition commit -> ONE MySQL txn (SUCCESS + outbox `payment.completed`).
    Commit 409 -> refund (CREDIT ledger entry, FAILED). Commit unreachable -> stays PROCESSING, the reconciler retries.
  - Business outcomes of verify are 200 with `status` SUCCESS / FAILED (+`failure_reason`) / PROCESSING.
  - Lock order always transaction -> account; MySQL 1213/1205 retried up to 3x (`run_in_tx`).
  - resend-otp extends the tuition hold, issues a new OTP, restarts `expires_at`. cancel is idempotent.
  - New `GET /transactions/{id}` (poll PROCESSING / resume PENDING_OTP).
  - Workers started on app startup: outbox relay (`FOR UPDATE SKIP LOCKED`), expiry + reconcile job (every 15 s).
  - Migration **0002**: `transactions.expires_at` (+ index with status); ledger unique key `(transaction_id, type)`
    replaces `unique(transaction_id)` so one refund is possible but a double charge still is not.
  - *Refinement vs. plan*: the outbox event is written with the SUCCESS status change (after the tuition commit),
    not with the debit, so a receipt is never mailed for a payment that ends up refunded.
- **gateway**: Redis fixed-window rate limits (see `docs/api/endpoints.md`), fails open if Redis is down;
  `Retry-After` from upstream is passed through. Compose: gateway gets `REDIS_URL`, payment-service gets
  `USER_SERVICE_URL` + `OTP_TTL_SECONDS`.
- **Tests**: `services/otp_service/tests/test_otp_store.py` (real Redis), `tests/load/race_check.py`
  (same student / same account / idempotency / double submit, against the running stack).
- **Fix found while testing**: redis-py 8 defaults `socket_timeout` to 5 s = the blocking `XREADGROUP` wait, so the
  notification consumer crashed every few seconds. `shared/redis_client.py` now sets `socket_timeout=30` explicitly.
- **Verified on the real stack** (fresh volumes + seed, emails to the log via `SMTP_USER=` override):
  migrations 0001 + 0002 apply; every endpoint and error path (401/404/409/410/422/429, other user's txn -> 404);
  OTP + receipt emails; outbox row published; ledger DEBIT; `race_check.py` 5/5; OTP store unit tests 8/8;
  reconciler (tuition-service stopped during verify -> PROCESSING -> SUCCESS after restart);
  expiry (`OTP_TTL_SECONDS=20`: PENDING_OTP -> EXPIRED, tuition back to UNPAID, verify -> 410);
  login rate limit (11th attempt -> 429 + Retry-After).

## 11. Phase 4 - frontend payment flow
Phase 3 committed first (`d45c50a`). All placeholder pages replaced, following `docs/wireframes/wireframes.html`.
- **Shell / routing**: `AppLayout` (logo, Home / Pay tuition / History nav, eye toggle, user name, Sign out) wraps every
  protected route; new `/home` is the landing page and the catch-all target. A 401 on any call except login signs the
  user out (and clears the React Query cache so the next user never sees old data).
- **Hide / show amounts**: `AmountVisibility` context (localStorage, hidden by default) + `Money` / `EyeToggle` in
  `components/ui.jsx`; every ₫ value goes through `Money`.
- **Home**: balance tile, successful / not-completed counts and last 5 rows, all from one cached `GET /transactions`;
  "Waiting for OTP" card with live countdown, Cancel (confirm) and Resume (`/pay?resume=<id>` reopens the OTP modal).
- **/pay**: Payer card (read-only), Tuition card (MSSV debounced 400 ms, 404 / PAID / RESERVED states inline), Confirm card
  (enable rule: UNPAID + balance >= amount + terms; reason shown above the button, incl. "you need X more").
  One Idempotency-Key per attempt: reused when the same attempt is retried after a network/5xx error, replaced after
  409/422/404, after any outcome, or when the MSSV changes.
- **OTP modal**: 6 boxes (auto-advance, paste/autofill, Backspace), expiry countdown, 30 s resend cooldown (429 uses
  `Retry-After`), inline 400 errors, 410/409 hand over to the result view, ✕ / Cancel ask before `POST /cancel`,
  no backdrop close. PROCESSING is polled via `GET /transactions/{id}` for up to ~30 s.
- **Result**: success (new balance from `balance_after`), processing, or failed / expired / cancelled with the reason.
- **History**: client-side MSSV + status filters, 10 rows per page, empty / loading / error states, horizontal scroll on mobile.
- Dev: `npm --prefix frontend run dev` (Vite on :5173, proxies `/api` to :8080).
- **Verified in the browser** against the running stack (OTP read from the log with `SMTP_USER=` override, restored after):
  login, Home, 404 / paid / insufficient lookup states, wrong OTP (attempts left), cancel (tuition back to UNPAID),
  full success (balance 73M -> 72M), resume from Home, resend 429 + cooldown, History filters, mobile width, `vite build`,
  rebuilt `web` container on :8080. Two test tuitions were added to the dev DB for this (MSSV 52100098 / 52100099);
  a fresh volume + seed removes them.
- Not done: row-click details in History (optional in the wireframe), automated frontend tests.

## 11. More seed students (payment-test pool)
- `backend/scripts/seed.py`: 20 more UNPAID students (24 students / 25 tuitions in total). MSSVs are 8 characters and may
  contain letters (`521H0081`, `521E0001`, `E2400001`, `522H0045`, `520K0123`, `523C0007`, `E2300112`, `E2400050`,
  `521V0042`, `521H0102`, `522H0099`) alongside numeric ones (`522000xx`, `523000xx`, `524000xx`).
  Built-in cases: `523C0007` / `E2300112` are affordable for bob (5M); `E2400050` = exactly 5M (boundary);
  `522H0099` has two unpaid terms (2024-HK2 offered first, then 2025-HK1); `52400033` = 120M (more than any balance).
  Re-running the seed on an existing database only adds missing rows (`INSERT IGNORE`).
- Lookup is case-insensitive (`521h0081` finds `521H0081`) via the MySQL `utf8mb4_unicode_ci` collation.
- Frontend: MSSV inputs no longer force a numeric phone keyboard (`inputMode="numeric"` -> `autoCapitalize`),
  hint text mentions letters, history search by MSSV is case-insensitive.

## 12. Phase 5 - load and concurrency tests
Branch `phase-5-load-tests`. Full results and analysis: `docs/reports/LOAD_TEST_REPORT.md`.
- **Test-only hooks**, enabled only by `docker-compose.loadtest.yml` (layered on the normal compose file):
  otp-service `OTP_TEST_ECHO` keeps the plain code in Redis (`otp:test:<txn>`, same TTL) and mounts
  `GET /internal/test/otp/{id}` (route absent otherwise); gateway `RATE_LIMIT_MULTIPLIER` (x1000 there);
  OTP 60 s / hold 120 s; SMTP blanked so load never reaches a real inbox.
- **`tests/` toolbox image** (profile `loadtest`, `./tests` mounted, results in `docs/reports/<run>/`):
  - `lt_data.py`: seed / reset of separate load-test data (`lt-` users, `LT` students, 30k tuitions; a student with many
    terms is a queue because lookup offers the oldest unpaid term). Reset restores balances and tuitions.
  - `locustfile.py`: Payer / HotStudent / SharedAccount users, misbehaving flows, business outcomes tallied in `outcomes.json`.
  - `verify_invariants.py`: waits for the background jobs, then checks I1-I8 (money, ledger, tuition, outbox, stuck) from
    the databases.
  - `test_races.py`: the old `race_check.py` as pytest (5 scenarios x 5 rounds, own small data pool, OTP from the hook);
    adds cancel-vs-verify. `race_check.py` removed.
  - `run_level.sh`: reset -> Locust headless -> invariants.
- **Bugs found by the load test and fixed** (details and before/after numbers in the report):
  1. payment-service held DB connections across HTTP calls -> pool exhausted at 150 users. `saga.end_read()` before every
     remote call; `_release` takes ids (re-reading an expired object would take a connection again); expiry job too.
  2. Sync endpoints: FastAPI validates the response in a second threadpool step while the request-scoped session still
     holds its connection -> circular wait, service frozen for minutes (seen in user-service). All DB routes now use
     `Depends(get_db, scope="function")` (requires FastAPI >= 0.121, requirements bumped).
  3. Pool wait 30 s > gateway timeout 20 s let dead requests pile up. `shared/db.py`: `pool_timeout=5`, pool sizes from
     `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`, `add_busy_handler(app)` -> 503 + Retry-After. `/health` is `async` everywhere so a
     busy threadpool does not make Docker report the service unhealthy.
  4. Parallel duplicates of one Idempotency-Key could get 409 (tuition RESERVED by their own twin). `initiate` re-checks
     the key before answering 409.
  5. payment-service CPU-bound (one GIL): `entrypoint.sh` honours `UVICORN_WORKERS`; payment-service runs 4
     (`PAYMENT_WORKERS`, pool 5+10 each, `THREADPOOL_SIZE` 100 per process); MySQL `--max-connections=300`.
     Its background workers were already replica-safe (SKIP LOCKED relay, conditional transitions).
- **Final results**: small 50 / medium 150 / stress 300 users, 3 min each: 0 failed requests and all invariants pass
  (a repeated stress run had 14 transient 502s out of 23,620 during the login ramp, self-healing). ~150 req/s ceiling;
  gateway and tuition-service (one process each) are the next limits.
- Not done: frontend e2e tests (`tests/e2e/` still empty); workers for gateway / tuition-service (recommended in the report).
