#!/usr/bin/env bash
# Docker stale-backend watchdog.
#
# THE FAILURE SHAPE IT EXISTS FOR (seen five times: 2026-07-06, 07-12, 07-19,
# 08-04, 08-26): the Docker backend goes stale — `docker ps` hangs or errors
# while the app looks fine — and every Postgres-backed path dies until a human
# runs the drill. This encodes the drill: detect → kill → relaunch → verify →
# notify either way.
#
# ── THE 2026-08-27 INCIDENT, and why this script is now three-valued ────────
# Installed as a launch agent, this watchdog killed and relaunched a HEALTHY
# Docker Desktop every ~15 minutes for hours.
#
# ROOT CAUSE, verified not assumed: launchd runs agents with a minimal PATH
# (/usr/bin:/bin:/usr/sbin:/sbin) and the plist sets no EnvironmentVariables.
# `docker` lives in /usr/local/bin and `timeout` in /opt/homebrew/bin — NEITHER
# is on that PATH, and `timeout` is not on stock macOS at all. Under launchd,
# `docker ps` therefore returned **rc 127, command not found**, and probe()
# treated *any* nonzero rc as "the backend is stale". The watchdog was reading
# "I cannot find docker" as "docker is broken" and firing the full drill —
# including, after the P5-T2 hardening, an unconditional SIGKILL of a perfectly
# healthy backend. RunAtLoad + StartInterval 900 made it a 15-minute cycle.
#
# THE RULING, and the rule it establishes: a PATH patch alone would fix this
# instance and leave the reasoning error in place. The scanner's three-valued
# contract applied here too —
#
#     HEALTHY      → log OK, do nothing
#     STALE        → run the drill
#     CANNOT PROBE → log loudly, notify, and RUN NOTHING
#
# **A MONITOR THAT CANNOT PROBE MUST NOT CONCLUDE FAILURE.** Second instrument
# under the same rule as the leak scanner's CANNOT VERIFY: an instrument that
# collapses "no signal" into "bad signal" will eventually act — destructively —
# on its own blindness.
#
# ── THE 2026-08-29 RULING: deliberate downtime is a state, not a fault ─────
# The three states above still collapsed two different meanings of a failed
# `docker ps`: a live backend that stopped answering and Docker Desktop being
# deliberately quit. The latter caused launchd to reopen Docker every fifteen
# minutes. Process presence is now checked BEFORE the CLI probe, producing a
# fourth state:
#
#     NOT RUNNING → log "docker down (not started)", exit 0, RUN NOTHING
#
# Only a present Docker Desktop/backend process plus a failed or timed-out
# `docker ps` is STALE. Deliberate downtime is a state, not a fault — the same
# family as decline-counts-as-served: the instrument must not punish the safe,
# intentional behaviour it is supposed to preserve.
set -uo pipefail
set +m                      # no job-control chatter from the fallback probe

HEALTHY=0
STALE=1
CANNOT_PROBE=2
NOT_RUNNING=3

LOG="${HOME}/Library/Logs/groundwork/docker-watchdog.log"
mkdir -p "$(dirname "$LOG")"
say() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" >> "$LOG"; }
notify() {  # macOS notification; never fails the script
  osascript -e "display notification \"$2\" with title \"$1\"" 2>/dev/null || true
}

PROBE_TIMEOUT="${GROUNDWORK_PROBE_TIMEOUT:-20}"
PROBE_FAILURE_REASON=""

# Drill command overrides make the no-action contract spyable offline. The
# production defaults are the same commands the original drill used.
DRILL_PKILL_BIN="${GROUNDWORK_PKILL_BIN:-pkill}"
DRILL_OPEN_BIN="${GROUNDWORK_OPEN_BIN:-open}"
DRILL_KILL_BIN="${GROUNDWORK_DRILL_KILL_BIN:-/bin/kill}"

# ── binary resolution: explicit, because PATH is not ours to assume ─────────
# Resolved by absolute path rather than trusting PATH, so the same script
# behaves identically in a login shell and under launchd. GROUNDWORK_DOCKER_BIN
# overrides for tests and for installs that keep docker somewhere else.
resolve_docker() {
  local c
  # "none" = deliberately pretend docker is absent. Symmetric with the timeout
  # override below, and the only way to exercise the CANNOT_PROBE verdict on a
  # machine that HAS docker installed — the test must not depend on the test
  # machine lacking the thing under test.
  [ "${GROUNDWORK_DOCKER_BIN:-}" = "none" ] && return 1
  for c in "${GROUNDWORK_DOCKER_BIN:-}" "$(command -v docker 2>/dev/null)" \
           /usr/local/bin/docker /opt/homebrew/bin/docker \
           "${HOME}/.docker/bin/docker"; do
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  return 1
}

# `timeout` is GNU coreutils and is NOT present on stock macOS. Its absence is
# normal and must never look like a fault; the fallback below covers it.
resolve_timeout() {
  local c
  [ "${GROUNDWORK_TIMEOUT_BIN:-}" = "none" ] && return 1
  for c in "${GROUNDWORK_TIMEOUT_BIN:-}" "$(command -v timeout 2>/dev/null)" \
           "$(command -v gtimeout 2>/dev/null)" \
           /opt/homebrew/bin/timeout /usr/local/bin/timeout; do
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  return 1
}

# Process presence is a different instrument from `docker ps`. A clean pgrep
# miss means Docker is not started; inability to run pgrep means CANNOT PROBE.
resolve_pgrep() {
  local c
  [ "${GROUNDWORK_PGREP_BIN:-}" = "none" ] && return 1
  for c in "${GROUNDWORK_PGREP_BIN:-}" "$(command -v pgrep 2>/dev/null)" \
           /usr/bin/pgrep; do
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  return 1
}

docker_process_state() {
  local pgrep_bin desktop_rc backend_rc
  pgrep_bin="$(resolve_pgrep)" || {
    PROBE_FAILURE_REASON="no usable pgrep binary found"
    return 2
  }

  "$pgrep_bin" -x "Docker Desktop" >/dev/null 2>&1
  desktop_rc=$?
  "$pgrep_bin" -x com.docker.backend >/dev/null 2>&1
  backend_rc=$?

  if [ "$desktop_rc" -eq 0 ] || [ "$backend_rc" -eq 0 ]; then
    return 0
  fi
  if [ "$desktop_rc" -eq 1 ] && [ "$backend_rc" -eq 1 ]; then
    return 1
  fi

  PROBE_FAILURE_REASON="could not inspect Docker Desktop/backend processes"
  return 2
}

# ── the probe: returns one of the four verdicts ─────────────────────────────
probe() {
  local docker_bin timeout_bin rc

  # This MUST precede docker binary resolution and `docker ps`. No process is
  # deliberate/not-started downtime, even if the CLI is installed or absent.
  docker_process_state
  rc=$?
  case "$rc" in
    0) ;;
    1) return $NOT_RUNNING ;;
    *) return $CANNOT_PROBE ;;
  esac

  docker_bin="$(resolve_docker)" || {
    PROBE_FAILURE_REASON="no usable docker binary found"
    return $CANNOT_PROBE
  }

  if timeout_bin="$(resolve_timeout)"; then
    "$timeout_bin" "$PROBE_TIMEOUT" "$docker_bin" ps >/dev/null 2>&1
    rc=$?
  else
    # Fallback for a stock macOS with no coreutils: run the probe in the
    # background and kill it if it outlives the budget. A SUCCESSFUL fast
    # probe must return HEALTHY here — pinned by test, because this path is
    # the one a default machine actually takes.
    "$docker_bin" ps >/dev/null 2>&1 &
    local pid=$!
    # The killer's stdout/stderr go to /dev/null, NOT inherited. Found by the
    # test suite hanging for the full budget on probes that finished
    # instantly: killing the subshell orphans its `sleep`, and an orphan that
    # inherited the caller's pipe holds that pipe open until it exits. Under
    # launchd that orphan holds the agent's log pipe for the whole budget on
    # every single run.
    ( sleep "$PROBE_TIMEOUT"; kill -9 "$pid" 2>/dev/null ) >/dev/null 2>&1 &
    local killer=$!
    wait "$pid" 2>/dev/null
    rc=$?
    kill "$killer" 2>/dev/null
    wait "$killer" 2>/dev/null
  fi

  # THE DISTINCTION THAT WAS MISSING, and that caused the incident: a nonzero
  # rc is not one thing.
  case "$rc" in
    0)   return $HEALTHY ;;
    127) return $CANNOT_PROBE ;;   # binary vanished between resolve and run
    124) return $STALE ;;          # GNU timeout: the probe outlived its budget
    137) return $STALE ;;          # fallback SIGKILL: same meaning, our signal
    *)   return $STALE ;;          # docker RAN and could not reach the daemon
  esac
}

verdict_name() {
  case "$1" in
    "$HEALTHY") printf 'HEALTHY' ;;
    "$STALE")   printf 'STALE' ;;
    "$CANNOT_PROBE") printf 'CANNOT_PROBE' ;;
    *) printf 'NOT_RUNNING' ;;
  esac
}

# --probe-only: report the verdict and TAKE NO ACTION. Used by the installer
# to tell "loaded" apart from "loaded and able to see its subject", and by the
# offline tests to pin all three verdicts without a drill running.
if [ "${1:-}" = "--probe-only" ]; then
  probe; v=$?
  printf '%s\n' "$(verdict_name $v)"
  [ "$v" -eq "$NOT_RUNNING" ] && exit 0
  exit $v
fi

probe; verdict=$?

if [ "$verdict" -eq "$HEALTHY" ]; then
  say "OK: docker responsive"
  exit 0
fi

if [ "$verdict" -eq "$NOT_RUNNING" ]; then
  say "docker down (not started)"
  exit 0
fi

if [ "$verdict" -eq "$CANNOT_PROBE" ]; then
  # The whole point of the incident. Say everything a human needs, change
  # nothing, and exit non-zero so the failure is visible rather than silent.
  say "CANNOT PROBE: ${PROBE_FAILURE_REASON:-probe unavailable}. TAKING NO \
ACTION — a monitor that cannot find its subject must not conclude the subject \
is broken. Under launchd the PATH is minimal; set GROUNDWORK_DOCKER_BIN if the \
Docker CLI is installed somewhere this script does not search."
  notify "Groundwork watchdog" "Cannot probe Docker — no action taken"
  exit 2
fi

say "STALE: docker unresponsive after ${PROBE_TIMEOUT}s — running the drill"
notify "Groundwork watchdog" "Docker backend stale — attempting recovery"

"$DRILL_PKILL_BIN" -f "Docker Desktop" 2>/dev/null || true
"$DRILL_PKILL_BIN" -x com.docker.backend 2>/dev/null || true
sleep 10

# P5-T2 hardening, from occurrence #5: the drill above sends SIGTERM, and a
# STALE backend is by definition a process that has stopped responding — so it
# ignores the polite signal and survives. Observed directly: after the drill
# "failed", the backend pid was still alive; SIGKILL plus `open -a Docker`
# recovered the daemon in 15 seconds.
#
# THIS IS ALSO WHY THE VERDICT ABOVE MATTERS SO MUCH. During the 08-27
# incident this escalation hard-killed a HEALTHY backend, because the code
# above had already decided "stale" on a rc-127 that meant "command not
# found". A correct remedy behind an incorrect verdict is a more destructive
# bug, not a safer one.
pgrep_bin="$(resolve_pgrep 2>/dev/null || true)"
survivors=$([ -n "$pgrep_bin" ] && "$pgrep_bin" -x com.docker.backend 2>/dev/null || true)
if [ -n "$survivors" ]; then
  say "SIGTERM ignored by backend pid(s): $(echo "$survivors" | tr '\n' ' ')— escalating to SIGKILL"
  # shellcheck disable=SC2086
  "$DRILL_KILL_BIN" -9 $survivors 2>/dev/null || true
  sleep 5
fi

"$DRILL_OPEN_BIN" -a Docker 2>/dev/null || say "WARN: could not 'open -a Docker'"

# Give the backend up to ~3 minutes to come back.
for i in $(seq 1 18); do
  sleep 10
  probe; v=$?
  if [ "$v" -eq "$HEALTHY" ]; then
    say "RECOVERED after $((i * 10))s"
    # The app stack's DB connections are stale too — bounce the app.
    launchctl kickstart -k "gui/$(id -u)/com.groundwork.app" 2>/dev/null \
      && say "app agent kickstarted" || say "WARN: app kickstart failed"
    notify "Groundwork watchdog" "Docker recovered after $((i * 10))s"
    exit 0
  fi
  if [ "$v" -eq "$CANNOT_PROBE" ]; then
    say "CANNOT PROBE during recovery wait — stopping, taking no further action"
    notify "Groundwork watchdog" "Cannot probe Docker — recovery abandoned"
    exit 2
  fi
  if [ "$v" -eq "$NOT_RUNNING" ]; then
    say "docker down (not started) during recovery wait"
  fi
done

say "ESCALATION: automated recovery FAILED — human required (run the drill manually)"
notify "Groundwork watchdog" "Docker recovery FAILED — human required"
exit 1
