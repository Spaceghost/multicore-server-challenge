#!/usr/bin/env bash
# Local mixed-workload check. No official score: loadgen shares this machine.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$(cd ../.. && pwd)"
template="${TEMPLATE:-conduit_dev}"
articles="${ARTICLES:-10000}"
users="${USERS:-5000}"
seconds="${MEASURE:-20s}"
think="${THINK_SCALE:-0.1}"
label="${LABEL:-nelua}"
server_binary="${SERVER_BINARY:-$PWD/bin/conduit}"
loadgen="${LOADGEN:-$PWD/build/loadgen}"
if [ ! -x "$loadgen" ]; then
  (cd "$root/bench" && go build -o "$loadgen" ./cmd/loadgen)
fi
mkdir -p results
db="nc_load_$$"
pid=''
createdb -T "$template" "$db"
cleanup() {
  if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi
  dropdb --if-exists --force "$db"
}
trap cleanup EXIT
export DATABASE_URL="postgres://conduit:conduit@127.0.0.1:${PGPORT:-5432}/$db"
export JWT_SECRET=multicore-server-challenge HOST=127.0.0.1 PORT="${PORT:-3110}"
"$server_binary" > "results/$label-server.log" 2>&1 &
pid=$!
for attempt in $(seq 60); do
  curl -sf -o /dev/null "http://$HOST:$PORT/api/tags" && break
  kill -0 "$pid" 2>/dev/null || { cat "results/$label-server.log"; exit 1; }
  sleep 1
done
curl -sf -o /dev/null "http://$HOST:$PORT/api/tags"
"$loadgen" run -target "http://$HOST:$PORT" -users "$users" \
  -ramp 5s -measure "$seconds" -tail 3s -secret "$JWT_SECRET" \
  -articles "$articles" -think-scale "$think" -run-id "$label-$(date +%s)" \
  -out "results/$label-box.json"
"$loadgen" merge -o "results/$label-merged.json" "results/$label-box.json" \
  > "results/$label-summary.txt"
cat "results/$label-summary.txt"
