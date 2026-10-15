# Scaffold log

Running record of what was generated and why. Newest entries at the bottom.

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
  `X-User-Id` and injects the verified one. OTP/notification services are not routed (internal only). Rate limiting is a TODO.
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

## 9. Developer top-up
- `backend/scripts/seed.py topup <username> <amount>`: adds to a demo balance (bumps `version`). Developer/demo tool only;
  account top-up is deliberately not a user feature (future work). Run: `docker compose --profile tools run --rm seed topup bob 50000000`.
