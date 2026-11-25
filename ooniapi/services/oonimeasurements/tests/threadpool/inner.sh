# Runs inside the test container (see run.sh). /src = ooni/backend's ooniapi dir
# (read-only), /chimg = the ClickHouse image, /harness = this directory.
set -eu
SCENARIOS=${SCENARIOS:-all}
export PYTHONDONTWRITEBYTECODE=1 PATH=/venv/bin:$PATH
CH=/chimg/usr/bin/clickhouse

# Postgres 15 on 127.0.0.1 (TCP, so iptables can cut it off)
install -d -o postgres /tmp/pg /run/postgresql
su postgres -c "/usr/lib/postgresql/15/bin/initdb -D /tmp/pg -A trust -U oonidb" >/dev/null
su postgres -c "/usr/lib/postgresql/15/bin/pg_ctl -D /tmp/pg -l /tmp/pg.log -w \
    -o '-c listen_addresses=127.0.0.1' start" >/dev/null
createdb -h 127.0.0.1 -U oonidb oonidb

# ClickHouse with its built-in default config, and the API's test schema
mkdir -p /tmp/ch && (cd /tmp/ch && $CH server -- --listen_host=127.0.0.1 --path=/tmp/ch/ \
    >/tmp/ch.log 2>&1 &)
for i in $(seq 60); do $CH client -q 'SELECT 1' >/dev/null 2>&1 && break; sleep 1; done
$CH client --multiquery --ignore-error < /src/common/fixtures/initdb/01-scheme.sql 2>/dev/null || true
$CH client -q "EXISTS TABLE default.api_token_usage" | grep -q 1

# The apitoken table, and valid tokens: ooni_valid, ooni_valid_0 .. ooni_valid_1999
cd /src/services/oonimeasurements
PYTHONPATH=src python3 - <<'PY'
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from oonimeasurements.common.apiauth.models import ApiToken
from oonimeasurements.common.apiauth.tokens import hash_token
e = create_engine("postgresql://oonidb@127.0.0.1/oonidb")
ApiToken.__table__.create(e)
with Session(e) as s:
    s.add(ApiToken(token_hash=hash_token("ooni_valid"), user_id="tester"))
    for i in range(2000):  # see load.py's "token" victim
        s.add(ApiToken(token_hash=hash_token(f"ooni_valid_{i}"), user_id=f"tester{i}"))
    s.commit()
PY

export CLICKHOUSE_URL=clickhouse://127.0.0.1 POSTGRESQL_URL=postgresql://oonidb@127.0.0.1/oonidb \
    VALKEY_URL=memory JWT_ENCRYPTION_KEY=test PROMETHEUS_METRICS_PASSWORD=test \
    ACCOUNT_ID_HASHING_KEY=test
# prod's settings (devops tf/environments/prod/main.tf)
export RATE_LIMITS="4000/hour;400000/day;200000/7day" RATE_LIMITS_UNMETERED_PAGES='["/metrics", "/health"]'

run() {  # $1 = name, rest = load.py args
    local name=$1; shift
    PYTHONPATH=src uvicorn oonimeasurements.main:app --host 127.0.0.1 --port 8000 \
        --log-level warning >/tmp/app-$name.log 2>&1 &
    local pid=$!
    for i in $(seq 60); do curl -sf http://127.0.0.1:8000/ >/dev/null && break; sleep 0.5; done
    echo "{\"scenario\": \"$name\", \"result\": $(python3 /harness/load.py --pid $pid "$@")}"
    kill $pid; wait $pid 2>/dev/null || true
}

want() { [ "$SCENARIOS" = all ] || [[ " $SCENARIOS " == *" $1 "* ]]; }
want baseline      && run baseline
want health-stop   && run health-stop   --fault stop --health-every 2
want health-drop   && run health-drop   --fault drop --health-every 2
want flood-ok      && run flood-ok      --attack 200 --attack-ip spoof
want flood-1ip-stop && run flood-1ip-stop --fault stop --attack 200 --attack-ip single
want flood-stop    && run flood-stop    --fault stop --attack 200 --attack-ip spoof
want flood-drop    && run flood-drop    --fault drop --attack 200 --attack-ip spoof
want valid-burst   && run valid-burst --attack 30 --attack-token valid --warm 0 --fault-for 20 --recover 5
want flood-notoken  && run flood-notoken --fault stop --attack 200 --attack-ip spoof --attack-token none
want flood-stop-10 && run flood-stop-10 --fault stop --attack 10 --attack-ip spoof
want flood-stop-40 && run flood-stop-40 --fault stop --attack 40 --attack-ip spoof
exit 0
