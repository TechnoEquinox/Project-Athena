#!/usr/bin/env bash
# Plain-bash tests for the installer's pure functions.  Run:  bash installer/tests/run.sh
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export LOG_FILE=/dev/null
. "$ROOT/installer/lib/ui.sh"; . "$ROOT/installer/lib/validate.sh"; . "$ROOT/installer/lib/config.sh"; . "$ROOT/installer/lib/firewall.sh"
pass=0; fail=0
t() { local name="$1"; shift; if "$@"; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $name"; fi; }
no() { ! "$@"; }

for h in athena.library.lan 192.168.1.50 athena a-b.c; do t "host ok $h" valid_host "$h"; done
for h in "" "bad host" "-x.com" "999.1.1.1" "a..b" "x_y.com" "1.2.3"; do t "host bad '$h'" no valid_host "$h"; done
t cidr1 valid_cidr 192.168.1.0/24;  t cidr2 no valid_cidr 192.168.1.5/24; t cidr3 no valid_cidr nonsense; t cidr4 no valid_cidr ""
t in1 ip_in_cidr 192.168.1.20 192.168.1.0/24; t in2 no ip_in_cidr 10.0.0.5 192.168.1.0/24; t in3 no ip_in_cidr "" 192.168.1.0/24
t cidr_of [ "$(cidr_of 192.168.1.23/24)" = "192.168.1.0/24" ]
for m in 1 7 12; do t "month $m" valid_month "$m"; done
for m in 0 13 "" a 07 -1; do t "month bad '$m'" no valid_month "$m"; done
t tz1 valid_timezone America/New_York; t tz2 no valid_timezone Mars/Base; t tz3 no valid_timezone ""
t ssh [ "$(ssh_client_ip '10.1.2.3 5555 22')" = "10.1.2.3" ]

# firewall plan
t fw_ok   plan_firewall 192.168.1.0/24 192.168.1.9 >/dev/null
t fw_lock no plan_firewall 192.168.1.0/24 10.9.9.9
t fw_rules bash -c ". '$ROOT/installer/lib/validate.sh'; . '$ROOT/installer/lib/firewall.sh'; plan_firewall 192.168.1.0/24 '' | grep -q 'allow from 192.168.1.0/24 to any port 80,443 proto tcp'"

# env generation
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
cat >"$D/.env.example" <<'X'
POSTGRES_USER=athena
POSTGRES_PASSWORD=change-me
APP_DB_PASSWORD=change-me
TOTP_ENCRYPTION_KEY=change-me
ATHENA_HOST=athena.example.lan
RETENTION_DAYS=30
# comment line stays
X
write_env "$D/.env.example" "$D/.env" athena.test America/New_York 7
t env_perm [ "$(stat -c %a "$D/.env")" = "600" ]
t env_host [ "$(env_get "$D/.env" ATHENA_HOST)" = "athena.test" ]
t env_tz   [ "$(env_get "$D/.env" LIBRARY_TIMEZONE)" = "America/New_York" ]
t env_fy   [ "$(env_get "$D/.env" FISCAL_YEAR_START_MONTH)" = "7" ]
t env_kept [ "$(env_get "$D/.env" RETENTION_DAYS)" = "30" ]
t env_pw2  [ "$(env_get "$D/.env" POSTGRES_PASSWORD)" != "change-me" ]
t env_pw3  [ "$(env_get "$D/.env" POSTGRES_PASSWORD)" != "$(env_get "$D/.env" APP_DB_PASSWORD)" ]
t env_key  [ "$(env_get "$D/.env" TOTP_ENCRYPTION_KEY | wc -c)" -ge 44 ]
t env_cmt  grep -q '^# comment line stays' "$D/.env"
t env_nooverwrite no write_env "$D/.env.example" "$D/.env" x.y UTC 1 2>/dev/null

echo "passed: $pass  failed: $fail"; [ "$fail" -eq 0 ]
