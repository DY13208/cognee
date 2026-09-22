#!/usr/bin/env bash
# Smart compose up: only rebuild images whose build inputs changed.
#
# Usage (from repo root, Git Bash / Linux / macOS):
#   ./scripts/compose-up.sh
#   ./scripts/compose-up.sh --force
#   ./scripts/compose-up.sh --force-services frontend,cognee-mcp
#   ./scripts/compose-up.sh --no-build
#
# Do NOT run compose-up.ps1 inside Git Bash — use this script or:
#   powershell.exe -File ./scripts/compose-up.ps1

set -euo pipefail

FORCE_BUILD=0
NO_BUILD=0
FORCE_SERVICES=""
COMPOSE_EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force|-f) FORCE_BUILD=1; shift ;;
    --no-build) NO_BUILD=1; shift ;;
    --force-services)
      FORCE_SERVICES="${2:-}"
      shift 2
      ;;
    *)
      COMPOSE_EXTRA+=("$1")
      shift
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STAMP_DIR="$ROOT/.compose-build-stamps"
mkdir -p "$STAMP_DIR"

fingerprint() {
  # Stable hash of listed files/dirs (content), ignoring node_modules / .next / .git
  local paths=("$@")
  local tmp
  tmp="$(mktemp)"
  for path in "${paths[@]}"; do
    [[ -e "$path" ]] || continue
    if [[ -d "$path" ]]; then
      # shellcheck disable=SC2016
      find "$path" -type f \
        ! -path '*/node_modules/*' ! -path '*/.next/*' ! -path '*/.git/*' \
        -print0 2>/dev/null |
        sort -z |
        xargs -0 sha256sum 2>/dev/null |
        awk '{print $1"  "$2}' >>"$tmp" || true
    else
      sha256sum "$path" >>"$tmp" 2>/dev/null || shasum -a 256 "$path" >>"$tmp"
    fi
  done
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$tmp" | awk '{print $1}'
  else
    shasum -a 256 "$tmp" | awk '{print $1}'
  fi
  rm -f "$tmp"
}

image_exists() {
  docker image inspect "$1" >/dev/null 2>&1
}

profiles_raw=""
if [[ -f "$ROOT/.env" ]]; then
  profiles_raw="$(grep -E '^\s*COMPOSE_PROFILES\s*=' "$ROOT/.env" | head -1 | cut -d= -f2- | tr -d '\"' | tr -d "'" | xargs || true)"
fi

has_profile() {
  local want="$1"
  IFS=',' read -r -a arr <<<"$profiles_raw"
  for p in "${arr[@]}"; do
    [[ "$(echo "$p" | xargs)" == "$want" ]] && return 0
  done
  return 1
}

declare -a CANDIDATES=(cognee)
has_profile mcp && CANDIDATES+=(cognee-mcp)
has_profile ui && CANDIDATES+=(frontend)

declare -A WATCHES=(
  [cognee]="$ROOT/Dockerfile $ROOT/pyproject.toml $ROOT/uv.lock $ROOT/entrypoint.sh $ROOT/README.md"
  [cognee-mcp]="$ROOT/cognee-mcp/Dockerfile $ROOT/cognee-mcp/pyproject.toml $ROOT/cognee-mcp/uv.lock $ROOT/cognee-mcp/entrypoint.sh $ROOT/cognee-mcp/src"
  [frontend]="$ROOT/cognee-frontend/Dockerfile $ROOT/cognee-frontend/package.json $ROOT/cognee-frontend/package-lock.json $ROOT/cognee-frontend/next.config.ts $ROOT/cognee-frontend/tsconfig.json $ROOT/cognee-frontend/src $ROOT/cognee-frontend/public"
)
declare -A IMAGE_HINT=(
  [cognee]=cognee-cognee
  [cognee-mcp]=cognee-cognee-mcp
  [frontend]=cognee-ui-local
)

IFS=',' read -r -a FORCED <<<"$FORCE_SERVICES"
if [[ "$FORCE_BUILD" -eq 1 && ${#FORCED[@]} -eq 1 && -z "${FORCED[0]:-}" ]]; then
  FORCED=("${CANDIDATES[@]}")
fi

is_forced() {
  local name="$1"
  for f in "${FORCED[@]:-}"; do
    [[ "$(echo "$f" | xargs)" == "$name" ]] && return 0
  done
  return 1
}

TO_BUILD=()
declare -A NEW_FP
for name in "${CANDIDATES[@]}"; do
  # shellcheck disable=SC2206
  paths=(${WATCHES[$name]})
  fp="$(fingerprint "${paths[@]}")"
  stamp="$STAMP_DIR/${name}.sha256"
  prev=""
  [[ -f "$stamp" ]] && prev="$(tr -d '[:space:]' <"$stamp")"
  hint="${IMAGE_HINT[$name]}"
  img_ok=0
  image_exists "$hint" && img_ok=1
  image_exists "${hint}:latest" && img_ok=1

  reason=""
  if [[ "$NO_BUILD" -eq 1 ]]; then
    :
  elif is_forced "$name"; then
    reason="forced"
  elif [[ "$img_ok" -eq 0 ]]; then
    reason="image missing"
  elif [[ "$prev" != "$fp" ]]; then
    reason="inputs changed"
  fi

  if [[ -n "$reason" ]]; then
    echo "[compose-up] build $name ($reason)"
    TO_BUILD+=("$name")
    NEW_FP[$name]="$fp"
  else
    echo "[compose-up] skip build $name"
  fi
done

if [[ ${#TO_BUILD[@]} -gt 0 && "$NO_BUILD" -eq 0 ]]; then
  docker compose build "${TO_BUILD[@]}"
  for name in "${TO_BUILD[@]}"; do
    printf '%s' "${NEW_FP[$name]}" >"$STAMP_DIR/${name}.sha256"
  done
else
  echo "[compose-up] no image rebuild needed"
fi

docker compose up -d "${COMPOSE_EXTRA[@]+"${COMPOSE_EXTRA[@]}"}"
