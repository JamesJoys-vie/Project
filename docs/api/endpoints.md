# REST API (via gateway, prefix `/api`). All except login need `Authorization: Bearer <jwt>`.

| Method & path | Request | Success | Errors |
|---|---|---|---|
| POST /auth/login | `{username, password}` | 200 `{access_token, token_type, expires_in}` | 401 |
| GET /users/me | - | 200 `{id, username, full_name, phone, email}` | 401 |
| GET /accounts/me | - | 200 `{balance}` | 401 |
| GET /tuitions/{mssv} | - | 200 `{tuition_id, student_id, student_name, term, amount, status}` | 404 |
| POST /transactions (header `Idempotency-Key`) | `{student_id}` | 201 transaction `PENDING_OTP` + `otp_expires_in` | 400, 409 (paid/reserved), 422 (insufficient balance) |
| POST /transactions/{id}/verify-otp | `{otp}` | 200 `{transaction, balance_after}` | 400 (bad/expired OTP), 409, 410 |
| POST /transactions/{id}/resend-otp | - | 200 | 429 |
| POST /transactions/{id}/cancel | - | 200 | 404, 409 |
| GET /transactions | - | 200 list (history) | 401 |

Internal only (not routed by gateway): tuition `POST /internal/tuitions/{id}/{reserve|commit|release}`, otp `POST /internal/otp`, `POST /internal/otp/verify`.
Live OpenAPI docs per service: `/docs` (reachable only inside the compose network, or temporarily publish a port).
