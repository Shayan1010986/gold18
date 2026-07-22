#!/bin/bash
# SessionStart hook: make sure the gold-signal engine can run in a fresh
# Claude Code (web/mobile) container by installing its Python deps.
set -euo pipefail

# Only needed in the remote (web/mobile) environment; skip on local machines.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Idempotent: pip is a no-op if the packages are already present (cached container).
python3 -m pip install --quiet --disable-pip-version-check \
  -r "${CLAUDE_PROJECT_DIR:-.}/bot/requirements.txt" 1>&2 || true

echo "session-start: python deps ready" 1>&2
