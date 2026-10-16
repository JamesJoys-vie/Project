# Tuition Payment Subsystem (iBanking) - Midterm SOA

## Layout
- `backend/gateway`           API gateway (JWT check, routing)
- `backend/services/*`        user, tuition, payment, otp, notification (each: `app/{api,core,domain,repositories,schemas}`, `migrations/`, `tests/`)
- `backend/shared`            JWT/bcrypt, DB helpers, Redis client, Redis Streams event bus (`events.py`)
- `backend/infra`             MySQL init script, container entrypoint
- `backend/scripts/seed.py`   demo data
- `frontend`                  React + JavaScript (Vite) client, served by nginx
- `docs`                      design (`design/services.md`), diagrams, API reference (`api/endpoints.md` + `api/openapi/`), `SCAFFOLD_LOG.md`
- `tests`                     load/concurrency suite (`load/`: Locust, pytest races, invariant checker); e2e (`e2e/`) empty

## Infrastructure
MySQL 8 (one database per service) + Redis 7 only. Redis is both the OTP store (keys with TTL) and the
event bus (Redis Streams + consumer groups, AOF persistence). No separate message broker.

## Run
1. `.env` already exists (git-ignored, holds your Ngrok values). Replace the `change_me` passwords before the first run.
   On a fresh clone: `Copy-Item .env.example .env`.
2. `docker compose up -d --build`
3. `docker compose --profile tools run --rm seed`
4. Open http://localhost:8080 (demo logins alice/bob/carol, password `Password123!`)
5. Public demo: set `NGROK_AUTHTOKEN` + `NGROK_DOMAIN` in `.env`, then `docker compose --profile public up -d`.

Status: backend (Phase 3), frontend payment flow (Phase 4) and load / concurrency tests (Phase 5) implemented.
See `docs/SCAFFOLD_LOG.md` sections 10-12. Frontend dev server: `npm --prefix frontend run dev` (http://localhost:5173).
Without SMTP settings in `.env`, emails (incl. OTPs) are printed by `docker compose logs notification-service`.

## Load and concurrency tests (Phase 5)
Runs on the same stack switched into load-test mode by `docker-compose.loadtest.yml` (test-only OTP hook, gateway
limits x1000, short OTP window, SMTP off). Results of the last runs: `docs/reports/LOAD_TEST_REPORT.md`.
```
docker compose -f docker-compose.yml -f docker-compose.loadtest.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.loadtest.yml --profile loadtest run --rm loadtest python lt_data.py seed
docker compose -f docker-compose.yml -f docker-compose.loadtest.yml --profile loadtest run --rm loadtest pytest -v
docker compose -f docker-compose.yml -f docker-compose.loadtest.yml --profile loadtest run --rm loadtest sh run_level.sh medium 150 15 3m
```
`run_level.sh` = reset load-test data -> Locust (headless) -> `verify_invariants.py`; output in `docs/reports/<name>/`.
Interactive Locust UI: `... run --rm --service-ports loadtest locust -f locustfile.py`, then http://localhost:8089.
Afterwards return to normal mode: `docker compose up -d` (recreates the services without the test settings).
