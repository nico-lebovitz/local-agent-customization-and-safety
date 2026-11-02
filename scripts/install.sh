#!/usr/bin/env bash
# Install participant Python environments; external model services are separate.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
profile=demo
profile_set=false
dry_run=false
for arg in "$@"; do
  case "$arg" in
    demo|course|all)
      if "$profile_set"; then echo 'Choose one profile: demo, course, or all.' >&2; exit 2; fi
      profile=$arg; profile_set=true ;;
    --dry-run) dry_run=true ;;
    -h|--help)
      echo 'Usage: bash scripts/install.sh [demo|course|all] [--dry-run]'
      echo 'demo (default): UI on 7861. course: course, Jupyter, and Gym. all: both.'
      echo 'Syncs local virtual environments to the checked-in locks; requires uv.'
      exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done
cd "$ROOT"
if ! "$dry_run" && ! command -v uv >/dev/null 2>&1; then
  echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2
  exit 1
fi
run() {
  printf '  '; printf '%q ' "$@"; printf '\n'
  if ! "$dry_run"; then "$@"; fi
}
environment() {
  local folder=$1 version=$2 lock=$3
  shift 3
  if [[ ! -x "$folder/bin/python" ]]; then
    run uv venv "$folder" --python "$version"
  else
    run "$folder/bin/python" -c "import sys; assert '.'.join(map(str, sys.version_info[:2])) == '$version', 'Wrong Python version in $folder; use a fresh checkout or move that environment aside.'"
  fi
  run uv pip sync --python "$folder/bin/python" "$lock" "$@"
  run uv pip check --python "$folder/bin/python"
}
echo "Installing $profile environments in $ROOT"
echo 'Tested platform: Linux ARM64. Other platforms may lack matching package wheels.'
if [[ "$profile" == demo || "$profile" == all ]]; then
  environment run/workshop/.venv 3.12 requirements.txt
  run run/workshop/.venv/bin/python -c 'import sys; sys.path.insert(0,"run/workshop"); import workshop_agent.server'
fi
if [[ "$profile" == course || "$profile" == all ]]; then
  environment course/.venv 3.14 course/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu
  environment .workshop/jupyter 3.12 scripts/jupyter-requirements.lock
  environment run/workshop/gym/.venv 3.14 run/workshop/gym/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu
  run course/.venv/bin/python -m ipykernel install --prefix "$ROOT/.workshop/jupyter" --name nato-course --display-name 'NATO course (PyTorch + PEFT)'
  run course/.venv/bin/python course/scripts/validate_notebooks.py --offline
fi
if "$dry_run"; then
  echo 'Preview complete; no commands executed.'
else
  echo 'Installation complete. See README.md for startup commands and live-service prerequisites.'
fi
