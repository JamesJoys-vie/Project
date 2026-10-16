# First-Run Guide

Step-by-step setup for running the Tuition Payment Subsystem (iBanking) on your machine for the first time.
For the project layout and load tests, see [README.md](README.md).

## 1. Prerequisites

| Tool | Needed for | Notes |
|---|---|---|
| Docker Desktop (with Compose v2) | Everything | Must be **running** before any `docker compose` command |
| Git | Cloning the repo | |
| Node.js 18+ | Optional: frontend dev server only | Not needed for the normal Docker run |
| Python 3 | Optional: generating random secrets | Any 3.x works |

Free host ports: **8080** (web UI) and **3307** (MySQL). Both can be changed in `.env`.

## 2. Create `.env`

From the project root (same folder as this file):

```powershell
Copy-Item .env.example .env
```

Then open `.env` and fill in each section. `.env` is git-ignored. **Never commit it or share its values.**

### MySQL
- `MYSQL_ROOT_PASSWORD`, `USER_DB_PASSWORD`, `TUITION_DB_PASSWORD`, `PAYMENT_DB_PASSWORD`: passwords you make up.
  Use four different ones. To generate one:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(24))"
  ```
- `MYSQL_HOST_PORT`: keep `3307` unless that port is taken.

### Auth / timing
- `JWT_SECRET`: a long random string:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- `JWT_EXPIRE_MINUTES` (30), `OTP_TTL_SECONDS` (300), `RESERVATION_TTL_SECONDS` (600): the defaults are fine.

### SMTP (OTP emails), pick one
- **Mailtrap (recommended for dev):** sign up at mailtrap.io → *Email Testing → Inboxes → SMTP Settings*.
  Copy the inbox **Username** to `SMTP_USER` and the **Password** to `SMTP_PASSWORD`. Keep
  `SMTP_HOST=sandbox.smtp.mailtrap.io` and `SMTP_PORT=587`. Emails land in that Mailtrap inbox, not in real mailboxes.
- **Gmail:** turn on 2-Step Verification, create an App Password at myaccount.google.com/apppasswords, then set
  `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` and `SMTP_FROM` = your Gmail address,
  `SMTP_PASSWORD` = the 16-character App Password.
- **No SMTP:** leave `SMTP_USER` and `SMTP_PASSWORD` empty. Emails (including OTPs) are printed to the
  notification-service logs instead (see step 5).

### Web UI
- `WEB_HOST_PORT`: keep `8080` unless that port is taken.

### Ngrok (optional, public demo only)
- `NGROK_AUTHTOKEN`: dashboard.ngrok.com → *Getting Started → Your Authtoken*
- `NGROK_DOMAIN`: dashboard.ngrok.com → *Universal Gateway → Domains* → your free static domain (no `https://`)

## 3. Build and start the stack

```bash
docker compose up -d --build
```

The first build takes a few minutes. Services start in dependency order (MySQL/Redis → user, tuition, otp,
notification → payment → gateway → web), and each service runs its own database migrations on startup.

Check that everything is up:

```bash
docker compose ps
```

All services should show `running` / `healthy`. MySQL and Redis are internal; only the web UI (8080) and MySQL (3307)
are published to your machine.

## 4. Load demo data

```bash
docker compose --profile tools run --rm seed
```

The seed waits for the services to be healthy, and it is safe to run more than once (it skips rows that already exist).

Demo accounts (password `Password123!` for all):

| Username | Balance (VND) | Good for |
|---|---|---|
| `alice` | 30,000,000 | Normal payments |
| `bob` | 5,000,000 | Insufficient-funds demo (try student `52100004`) |
| `carol` | 100,000,000 | Large payments |

Sample unpaid student IDs (MSSV): `52100001`, `52100002`, `52100003`, `52100004`, `521H0081`, `523C0007`.
The full list is in `backend/scripts/seed.py`.

## 5. Use the app

1. Open http://localhost:8080 and log in with a demo account.
2. Look up a student ID, review the tuition, and start the payment.
3. Enter the OTP. You can find it:
   - in your **Mailtrap inbox** (or Gmail) if SMTP is set, or
   - in the logs, if SMTP is empty:
     ```bash
     docker compose logs -f notification-service
     ```
4. Confirm the payment. You also get a receipt email the same way.

## 6. Optional extras

**Public demo through ngrok** (needs the ngrok values in `.env`):

```bash
docker compose --profile public up -d
```

The app is then reachable at `https://<NGROK_DOMAIN>`. Stop it when the demo is over.

**Frontend dev server with hot reload** (needs the Docker stack running, since it proxies `/api` to port 8080):

```bash
npm --prefix frontend install
```

```bash
npm --prefix frontend run dev
```

Then open http://localhost:5173.

## 7. Stop, restart, reset

| Goal | Command |
|---|---|
| Stop (keep data) | `docker compose down` |
| Start again | `docker compose up -d` |
| Rebuild after code changes | `docker compose up -d --build` |
| **Wipe all data** (fresh databases) | `docker compose down -v`, then repeat steps 3–4 |

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `docker` commands fail / "cannot connect to the Docker daemon" | Start Docker Desktop and wait until it says it's running |
| "port is already allocated" for 8080 or 3307 | Change `WEB_HOST_PORT` or `MYSQL_HOST_PORT` in `.env`, then `docker compose up -d` |
| Services restart or stay `unhealthy`, logs show MySQL "Access denied" | MySQL kept the passwords from its **first** start. If you changed DB passwords in `.env` afterwards, run `docker compose down -v` (deletes data) and start again |
| No OTP email arrives | Check `SMTP_USER` / `SMTP_PASSWORD` in `.env`, then look at `docker compose logs notification-service` for SMTP errors |
| Login fails for alice/bob/carol | The seed hasn't run yet: run step 4 |
| A service is unhealthy | Inspect it with `docker compose logs <service-name>` (e.g. `payment-service`) |

## Where to go next
- API reference: [docs/api/endpoints.md](docs/api/endpoints.md)
- Service design: [docs/design/services.md](docs/design/services.md)
- Load and concurrency tests: [README.md](README.md#load-and-concurrency-tests-phase-5)
