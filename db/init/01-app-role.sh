#!/bin/bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Connor Bailey

set -e

psql -v ON_ERROR_STOP=1 \
     -v app_pw="$APP_DB_PASSWORD" \
     -v dbname="$POSTGRES_DB" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
CREATE ROLE athena_app LOGIN PASSWORD :'app_pw';
GRANT CONNECT ON DATABASE :"dbname" TO athena_app;
GRANT USAGE ON SCHEMA public TO athena_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO athena_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO athena_app;
EOSQL