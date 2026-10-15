# Tuition Payment Subsystem (iBanking) - Midterm SOA

## Layout
- `backend/gateway`           API gateway (JWT check, routing)
- `backend/services/*`        user, tuition, payment, otp, notification (each: `app/{api,core,domain,repositories,schemas}`, `migrations/`, `tests/`)
- `backend/shared`            JWT/bcrypt, DB helpers, Redis client, Redis Streams event bus (`events.py`)
- `backend/infra`             MySQL init script, container entrypoint
- `backend/scripts/seed.py`   demo data
- `frontend`                  React + JavaScript (Vite) client, served by nginx
- `docs`                      diagrams, API table, `SCAFFOLD_LOG.md`
- `tests`                     load/concurrency (`load/`) and e2e (`e2e/`) - empty for now

## Infrastructure
MySQL 8 (one database per service) + Redis 7 only. Redis is both the OTP store (keys with TTL) and the
event bus (Redis Streams + consumer groups, AOF persistence). No separate message broker.

## Run
1. `.env` already exists (git-ignored, holds your Ngrok values). Replace the `change_me` passwords before the first run.
   On a fresh clone: `Copy-Item .env.example .env`.
2. `docker compose up -d --build`
3. `docker compose --profile tools run --rm seed`
4. Open http://localhost:8080 (demo logins alice/bob/carol, password `Password123!`)
   Demo top-up (developer only): `docker compose --profile tools run --rm seed topup bob 50000000`
5. Public demo: set `NGROK_AUTHTOKEN` + `NGROK_DOMAIN` in `.env`, then `docker compose --profile public up -d`.

Status: scaffold only - business endpoints return 501. See `docs/SCAFFOLD_LOG.md`.
