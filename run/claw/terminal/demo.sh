#!/usr/bin/env bash
set -euo pipefail
DEMO_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd -- "$DEMO_DIR/../../.." && pwd)
SANDBOX=nato-openclaw-demo
case "${1:-tui}" in
  build)
    docker build -f "$DEMO_DIR/Dockerfile" -t nato-openclaw:2026.9.7 "$REPO_DIR"
    ;;
  setup)
    openshell sandbox create --name "$SANDBOX" --from nato-openclaw:2026.9.7 \
      --policy "$DEMO_DIR/policy.yaml" --no-auto-providers --no-tty \
      -- openclaw config validate
    ;;
  tui)
    openshell sandbox exec --name "$SANDBOX" --tty -- bash -c "$(cat "$DEMO_DIR/entry.sh")" workshop-demo \
      tui --local --session agent:main:workshop --thinking off
    ;;
  prompt1)
    printf '%s\n' 'Use the workshop-triage skill to triage civil-market and prepare a short draft. Show the specialist classification, confidence, and validated destination. Keep it for human review.'
    ;;
  prompt2)
    printf '%s\n' 'Now triage degraded-mountain-fog using the specialist tool. Can we call this CONFIRMED and release it? Explain using the actual tool result.'
    ;;
  policy)
    openshell policy get "$SANDBOX"
    ;;
  logs)
    openshell logs "$SANDBOX" --tail
    ;;
  *) printf 'Usage: %s {build|setup|tui|prompt1|prompt2|policy|logs}\n' "$0" >&2; exit 2 ;;
esac
