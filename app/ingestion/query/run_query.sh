#!/usr/bin/env bash
# Execute a Dune SQL query via Tempo MPP, substituting params from config.yaml
# Usage: ./run_query.sh <query_file.sql> [--dry-run]
# Example: ./run_query.sh whale_transaction_filter.sql
# Example: ./run_query.sh whale_transaction_filter.sql --dry-run

set -e

TEMPO="$HOME/.tempo/bin/tempo"
DUNE_BASE="https://api.dune.com"
QUERY_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$QUERY_DIR/config.yaml"
QUERY_FILE="${1:-}"
DRY_RUN=false
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=true

if [[ -z "$QUERY_FILE" ]]; then
    echo "Usage: $0 <query_file.sql> [--dry-run]"
    echo ""
    echo "Available queries:"
    ls "$QUERY_DIR"/*.sql | xargs -n1 basename
    exit 1
fi

SQL_PATH="$QUERY_DIR/$QUERY_FILE"
[[ ! -f "$SQL_PATH" ]] && SQL_PATH="$QUERY_FILE"
[[ ! -f "$SQL_PATH" ]] && { echo "Error: Query file not found: $QUERY_FILE"; exit 1; }

QUERY_NAME="${QUERY_FILE%.sql}"

# ── Parameter substitution via Python ─────────────────────────────────────────
SQL=$(python3 - "$SQL_PATH" "$CONFIG" "$QUERY_NAME" <<'PYEOF'
import sys, re
try:
    import yaml
except ImportError:
    sys.exit("Error: PyYAML not installed. Run: pip install pyyaml")

sql_path, config_path, query_name = sys.argv[1], sys.argv[2], sys.argv[3]

with open(config_path) as f:
    cfg = yaml.safe_load(f)

# Merge: globals < per-query overrides
params = {**cfg.get("globals", {})}
params.update(cfg.get("queries", {}).get(query_name, {}))

with open(sql_path) as f:
    sql = f.read()

def substitute(sql, params):
    for key, value in params.items():
        sql = re.sub(r"\{\{" + re.escape(str(key)) + r"\}\}", str(value), sql)
    unresolved = re.findall(r"\{\{(\w+)\}\}", sql)
    if unresolved:
        print(f"Warning: unresolved placeholders: {unresolved}", file=sys.stderr)
    return sql

print(substitute(sql, params))
PYEOF
)

echo "Query:  $QUERY_FILE"
echo "Config: $CONFIG"
echo "---"

if $DRY_RUN; then
    echo "[dry-run] Resolved SQL:"
    echo "$SQL"
    exit 0
fi

# ── Submit ─────────────────────────────────────────────────────────────────────
RESPONSE=$("$TEMPO" request -t -X POST \
    --json "{\"query_sql\": $(echo "$SQL" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" \
    "$DUNE_BASE/api/v1/sql/execute" 2>&1)

echo "Submit response: $RESPONSE"

EXECUTION_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('execution_id',''))" 2>/dev/null || echo "")

if [[ -z "$EXECUTION_ID" ]]; then
    echo "Failed to get execution_id. Full response above."
    exit 1
fi

echo "Execution ID: $EXECUTION_ID"
echo "Polling for results..."

# ── Poll ───────────────────────────────────────────────────────────────────────
for i in $(seq 1 30); do
    sleep 3
    RESULT=$("$TEMPO" request -t "$DUNE_BASE/api/v1/execution/$EXECUTION_ID/results" 2>&1)
    STATE=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('state','UNKNOWN'))" 2>/dev/null || echo "PENDING")

    echo "[$i] State: $STATE"

    if [[ "$STATE" == "QUERY_STATE_COMPLETED" ]]; then
        echo ""
        echo "Results:"
        echo "$RESULT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
rows = d.get('result', {}).get('rows', [])
if rows:
    headers = list(rows[0].keys())
    print(' | '.join(headers))
    print('-' * (len(' | '.join(headers)) + 4))
    for row in rows[:50]:
        print(' | '.join(str(row.get(h,'')) for h in headers))
    print(f'\nTotal rows: {len(rows)}')
else:
    print('No rows returned.')
"
        exit 0
    elif [[ "$STATE" == "QUERY_STATE_FAILED" ]]; then
        echo "Query failed."
        echo "$RESULT"
        exit 1
    fi
done

echo "Timed out. Fetch manually:"
echo "  $TEMPO request -t $DUNE_BASE/api/v1/execution/$EXECUTION_ID/results"
