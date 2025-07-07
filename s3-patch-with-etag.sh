#!/usr/bin/env bash
set -euo pipefail

# ─── Parse args ───────────────────────────────────────────────────────────────
ACTION="add"
while [[ $# -gt 0 ]]; do
  case $1 in
    -a|--action)
      ACTION="$2"; shift 2;;
    *)
      echo "Usage: $0 [--action add|remove]"; exit 1;;
  esac
done

if [[ "$ACTION" != "add" && "$ACTION" != "remove" ]]; then
  echo "❌ Invalid action: $ACTION (must be add or remove)"
  exit 1
fi
# ────────────────────────────────────────────────────────────────────────────────

# ─── Required ENV VARS ─────────────────────────────────────────────────────────
: "${BUCKET:?Need to set BUCKET (e.g. my-s3-bucket)}"
: "${HOST:?Need to set HOST}"
: "${PORT:?Need to set PORT}"
: "${LOCATION_NAME:?Need to set LOCATION_NAME}"
# ────────────────────────────────────────────────────────────────────────────────

# ─── Optional ENV VARS ─────────────────────────────────────────────────────────
MAX_RETRIES="${MAX_RETRIES:-5}"
SLEEP_SECONDS="${SLEEP_SECONDS:-3}"
PREFIX="${PREFIX:-}"     # empty = root of bucket
# ────────────────────────────────────────────────────────────────────────────────

# ─── Compute S3 keys ────────────────────────────────────────────────────────────
if [ -z "$PREFIX" ]; then
  SCRIPT_KEY="patch_workspace_cm.py"
  WORKSPACE_KEY="workspace.yaml"
else
  P="$(echo "$PREFIX" | sed 's#^/*##; s#/*$##')"
  SCRIPT_KEY="$P/patch_workspace_cm.py"
  WORKSPACE_KEY="$P/workspace.yaml"
fi

SCRIPT_LOCAL="patch_workspace_cm.py"
WORKSPACE_LOCAL="workspace.yaml"
# ────────────────────────────────────────────────────────────────────────────────

retry=0
while true; do
  echo "► Attempt $((retry+1)) of $MAX_RETRIES (action=$ACTION prefix='$PREFIX')"

  # 1) HEAD to get ETag (or detect first‐time)
  set +e
  HEAD_OUT=$(aws s3api head-object --bucket "$BUCKET" --key "$WORKSPACE_KEY" 2>&1)
  HEAD_RC=$?
  set -e

  if [ $HEAD_RC -eq 0 ]; then
    ETAG=$(printf "%s\n" "$HEAD_OUT" | jq -r .ETag | tr -d '"')
    echo "   Current ETag: $ETAG"
    FIRST_TIME=0
  else
    if echo "$HEAD_OUT" | grep -q "404"; then
      echo "⚠️  workspace.yaml not found; will create it"
      FIRST_TIME=1
    else
      echo "❌ head-object error:"; echo "$HEAD_OUT"; exit 1
    fi
  fi

  # 2) Fetch patcher (fallback to local if missing)
  if ! aws s3 cp "s3://$BUCKET/$SCRIPT_KEY" "$SCRIPT_LOCAL"; then
    echo "⚠️  Could not fetch $SCRIPT_KEY from S3; using local $SCRIPT_LOCAL"
  fi

  # 3) Fetch workspace.yaml if it exists
  if [ $FIRST_TIME -eq 0 ]; then
    aws s3 cp "s3://$BUCKET/$WORKSPACE_KEY" "$WORKSPACE_LOCAL"
  else
    # ensure a blank file exists for the patcher
    printf "" > "$WORKSPACE_LOCAL"
  fi

  # 4) Run Python patcher with action
  python3 "$SCRIPT_LOCAL" \
    --action "$ACTION" \
    --host "$HOST" \
    --port "$PORT" \
    --location-name "$LOCATION_NAME"

  # 5) Upload with/without If-Match
  set +e
  if [ $FIRST_TIME -eq 1 ]; then
    aws s3api put-object \
      --bucket "$BUCKET" \
      --key    "$WORKSPACE_KEY" \
      --body   "$WORKSPACE_LOCAL"
  else
    aws s3api put-object \
      --bucket "$BUCKET" \
      --key    "$WORKSPACE_KEY" \
      --body   "$WORKSPACE_LOCAL" \
      --if-match "$ETAG"
  fi
  PUT_RC=$?
  set -e

  # 6) Done or retry?
  if [ $PUT_RC -eq 0 ]; then
    echo "✅ workspace.yaml uploaded successfully"
    break
  fi

  echo "⚠️  ETag mismatch (412). Retrying in $SLEEP_SECONDS…"
  retry=$((retry+1))
  if [ $retry -ge $MAX_RETRIES ]; then
    echo "❌ Exceeded $MAX_RETRIES retries—aborting."
    exit 1
  fi
  sleep "$SLEEP_SECONDS"
done

echo "🎉 Done. You can now: kubectl apply -f $WORKSPACE_LOCAL"
