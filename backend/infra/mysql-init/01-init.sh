#!/bin/bash
# Runs once on first MySQL start (empty data volume). Creates one DB + one user per service.
set -e
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS users_db    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS tuition_db  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS payments_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'user_svc'@'%'    IDENTIFIED BY '${USER_DB_PASSWORD}';
CREATE USER IF NOT EXISTS 'tuition_svc'@'%' IDENTIFIED BY '${TUITION_DB_PASSWORD}';
CREATE USER IF NOT EXISTS 'payment_svc'@'%' IDENTIFIED BY '${PAYMENT_DB_PASSWORD}';

GRANT ALL PRIVILEGES ON users_db.*    TO 'user_svc'@'%';
GRANT ALL PRIVILEGES ON tuition_db.*  TO 'tuition_svc'@'%';
GRANT ALL PRIVILEGES ON payments_db.* TO 'payment_svc'@'%';
FLUSH PRIVILEGES;
SQL
