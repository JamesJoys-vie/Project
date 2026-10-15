# REST API (via gateway, prefix `/api`). All except login need `Authorization: Bearer <jwt>`.

| Method & path | Request | Success | Errors |
|---|---|---|---|
| POST /auth/login | `{username, password}` | 200 `{access_token, token_type, expires_in}` | 401, 429 |
| GET /users/me | - | 200 `{id, username, full_name, phone, email}` | 401 |
| GET /accounts/me | - | 200 `{balance}` | 401, 404 |
| GET /tuitions/{mssv} | - | 200 `{tuition_id, student_id, student_name, term, amount, status}` | 404 |
| POST /transactions (header `Idempotency-Key`, 8-64 chars, e.g. a UUID) | `{student_id}` | 201 transaction `PENDING_OTP` + `otp_expires_in` (same key again -> the same transaction) | 400, 404, 409 (paid/reserved), 422 (insufficient balance), 429, 502 |
| POST /transactions/{id}/verify-otp | `{otp}` | 200 `{transaction, balance_after}`; `transaction.status` = `SUCCESS`, `FAILED` (see `failure_reason`, e.g. insufficient balance) or `PROCESSING` (still finishing, poll GET) | 400 (wrong / expired / locked OTP, message says which), 404, 409, 410 (transaction expired), 429 |
| POST /transactions/{id}/resend-otp | - | 200 `{otp_expires_in}` (old OTP stops working, window restarts) | 404, 409, 410, 429 (`Retry-After`) |
| POST /transactions/{id}/cancel | - | 200 transaction `CANCELLED` | 404, 409 |
| GET /transactions | - | 200 list, newest first (max 100) | 401 |
| GET /transactions/{id} | - | 200 transaction | 404 |

Transaction `status`: `PENDING_OTP` -> `PROCESSING` -> `SUCCESS`, or `FAILED` / `CANCELLED` / `EXPIRED`.
Other users' transactions answer 404 (never 403), so ids cannot be probed.

Rate limits (gateway, Redis fixed window, 429 + `Retry-After`): login 10/min per IP; create transaction 20/min,
verify-otp 10/min, resend-otp 5/min per user. otp-service adds: 30 s between OTPs of one transaction, max 4 OTPs
(initial + 3 resends) per transaction, OTP burned after 5 wrong codes.

Internal only (not routed by gateway): user `GET /internal/users/{id}`;
tuition `POST /internal/tuitions/{id}/{reserve|commit|release}`; otp `POST /internal/otp`, `POST /internal/otp/verify`.
Live OpenAPI docs per service: `/docs` (reachable only inside the compose network, or temporarily publish a port).
