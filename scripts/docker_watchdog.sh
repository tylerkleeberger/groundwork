#!/usr/bin/env bash
# P4-T4 Docker stale-backend watchdog (director ruling 2026-07-20: the
# P2-T2 "update-first" bet is FALSIFIED — occurrence #4 arrived AFTER the
# Docker update, so the held watchdog becomes a scheduled task).
#
# The failure shape, seen four times (2026-07-06, 07-12, 07-19, and the
# July-14 proposal's motivating case): the Docker backend goes stale —
# `docker ps` hangs or errors while the app looks fine — and every
# Postgres-backed path dies until a human runs the drill.
#
# This encodes the drill: detect → kill Docker → relaunch → verify →
# notify EITHER WAY. When automated recovery fails it says so loudly
# rather than retrying forever (honest escalation, D9).
set -uo pipefail

LOG="${HOME}/Library/Logs/groundwork/docker-watchdog.log"
mkdir -p "$(dirname "$LOG")"
say() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" >> "$LOG"; }
notify() {  # macOS notification; never fails the script
  osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null || true
}

PROBE_TIMEOUT=20
probe() {  # 0 = healthy, 1 = stale/unreachable
  # `docker ps` hanging IS the symptom, so the probe is time-boxed.
  if command -v timeout >/dev/null 2>&1; then
    timeout "$PROBE_TIMEOUT" docker ps >/dev/null 2>&1
  else
    docker ps >/dev/null 2>&1 &
    local pid=$!
    ( sleep "$PROBE_TIMEOUT"; kill -9 $pid 2>/dev/null ) &
    local killer=$!
    wait $pid 2>/dev/null
    local rc=$?
    kill $killer 2>/dev/null
    return $rc
  fi
}

if probe; then
  say "OK: docker responsive"
  exit 0
fi

say "STALE: docker unresponsive after ${PROBE_TIMEOUT}s — running the drill"
notify "Groundwork watchdog" "Docker backend stale — attempting recovery"

pkill -f "Docker Desktop" 2>/dev/null || true
pkill -x com.docker.backend 2>/dev/null || true
sleep 10

# P5-T2 FIX, from occurrence #5 (2026-08-26) and confirmed against the
# 2026-08-04 escalations in this log: the drill above sends SIGTERM, and a
# STALE backend is by definition a process that has stopped responding — so
# it ignores the polite signal and survives. Observed directly: after the
# drill "failed", the backend pid was still alive; SIGKILL on it plus
# `open -a Docker` recovered the daemon in 15 seconds.
#
# So escalate. The drill's own symptom (unresponsive) is the reason its own
# remedy has to be unconditional: asking nicely is what already failed.
survivors=$(pgrep -x com.docker.backend 2>/dev/null || true)
if [ -n "$survivors" ]; then
  say "SIGTERM ignored by backend pid(s): $(echo "$survivors" | tr '\n' ' ')— escalating to SIGKILL"
  # shellcheck disable=SC2086
  kill -9 $survivors 2>/dev/null || true
  sleep 5
fi

open -a Docker 2>/dev/null || say "WARN: could not 'open -a Docker'"

# Give the backend up to ~3 minutes to come back.
for i in $(seq 1 18); do
  sleep 10
  if probe; then
    say "RECOVERED after $((i * 10))s"
    # The app stack's DB connections are stale too — bounce the app.
    launchctl kickstart -k "gui/$(id -u)/com.groundwork.app" 2>/dev/null \
      && say "app agent kickstarted" || say "WARN: app kickstart failed"
    notify "Groundwork watchdog" "Docker recovered; app restarted"
    exit 0
  fi
done

say "ESCALATION: automated recovery FAILED — human required (run the drill manually)"
notify "Groundwork watchdog ⚠️" "Docker recovery FAILED — manual drill needed"
exit 1
