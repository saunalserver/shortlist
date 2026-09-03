#!/usr/bin/env bash
# One-shot setup: venv, dependencies, folders, user systemd units (Linux).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv venv
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -e ".[dev]"

mkdir -p data output profile
[ -f .env ] || cp .env.example .env
for f in candidate.md resume.tex cover_letter.tex; do
  [ -f "profile/$f" ] || cp "profile.example/$f" "profile/$f"
done

if command -v systemctl >/dev/null && [ "${1:-}" != "--no-systemd" ]; then
  mkdir -p ~/.config/systemd/user
  cp systemd/autojob.service systemd/autojob.timer systemd/autojob-worker.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now autojob.timer autojob-worker.service
  echo "systemd: autojob.timer + autojob-worker.service enabled (systemctl --user list-timers)"
  echo "If this is a headless server, run once: sudo loginctl enable-linger $USER"
fi

echo
echo "Next: edit .env (LLM_API_KEY at minimum), profile/candidate.md, profile/resume.tex, profile/cover_letter.tex,"
echo "then run: ./venv/bin/autojob doctor && ./venv/bin/autojob run --dry-run --max-jobs 20"
