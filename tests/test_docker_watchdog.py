"""Docker watchdog four-state verdict (D16 unmarked).

THE INCIDENT THESE TESTS EXIST FOR. Installed as a launch agent, the watchdog
killed and relaunched a HEALTHY Docker Desktop every ~15 minutes for hours.
launchd runs agents with a minimal PATH; `docker` (/usr/local/bin) and
`timeout` (/opt/homebrew/bin, and absent from stock macOS) are not on it, so
`docker ps` returned rc 127 — command not found — and the probe read *any*
nonzero rc as "the backend is stale".

The watchdog was acting on its own blindness. A later incident exposed one
more collapsed state: deliberately quitting Docker looked exactly like a stale
backend, so launchd reopened it every fifteen minutes. These tests pin both
fixes:

    HEALTHY      → nothing happens
    STALE        → the drill runs, but only when a process is present
    NOT RUNNING  → "docker down (not started)", success, ZERO drill actions
    CANNOT PROBE → loud log, and ZERO drill actions

`--probe-only` reports a verdict without acting, which is what makes the four
verdicts testable without a real Docker anywhere near them.
"""
import os
import pathlib
import subprocess

import pytest

WATCHDOG = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "docker_watchdog.sh"
INSTALLER = pathlib.Path(__file__).resolve().parent.parent / "ops" / "launchd" / "install.sh"

HEALTHY, STALE, CANNOT_PROBE = 0, 1, 2


def fake_bin(directory: pathlib.Path, name: str, body: str) -> pathlib.Path:
    """A stand-in executable. The tests never touch a real Docker."""
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)
    return p


def run(tmp_path, *args, docker="none", timeout_bin="none", probe_timeout="30",
        process_running=True, extra_path=None, extra_env=None):
    """Run the watchdog hermetically: HOME redirected so its log lands in the
    tmp dir, and both binary resolutions overridden so the result never depends
    on what the test machine happens to have installed.

    The probe budget defaults to 30s — GENEROUS ON PURPOSE. It was 1s, and that
    made every test in this file timing-dependent: under load (a full suite
    run), the budget expired before the stand-in binary had even been forked,
    the fallback's killer fired, and the script correctly reported STALE for a
    test that was asking about something else entirely. One test here is
    genuinely about timing and passes its own short budget; the rest must not
    be able to fail for a reason they are not testing.

    That is this project's own rule turned on its test suite: a check that goes
    red for a reason the reader cannot act on teaches people to ignore it."""
    pgrep = fake_bin(
        tmp_path / "process-bin",
        "pgrep",
        'printf "4242\\n"; exit 0' if process_running else "exit 1",
    )
    env = dict(os.environ)
    env.update({
        "HOME": str(tmp_path),
        "GROUNDWORK_DOCKER_BIN": docker,
        "GROUNDWORK_PGREP_BIN": str(pgrep),
        "GROUNDWORK_TIMEOUT_BIN": timeout_bin,
        "GROUNDWORK_PROBE_TIMEOUT": probe_timeout,
    })
    if extra_env:
        env.update(extra_env)
    if extra_path:
        env["PATH"] = f"{extra_path}:{env['PATH']}"
    return subprocess.run(["bash", str(WATCHDOG), *args], env=env,
                          capture_output=True, text=True, timeout=120)


# ---------- the four verdicts ----------

def test_healthy_when_docker_answers(tmp_path):
    d = fake_bin(tmp_path / "bin", "docker", "exit 0")
    r = run(tmp_path, "--probe-only", docker=str(d))
    assert r.returncode == HEALTHY
    assert r.stdout.strip() == "HEALTHY"


def test_stale_when_docker_runs_but_cannot_reach_the_daemon(tmp_path):
    """`Cannot connect to the Docker daemon` exits 1. The binary was found and
    executed, so this genuinely is the failure the drill exists for."""
    d = fake_bin(tmp_path / "bin", "docker", "exit 1")
    r = run(tmp_path, "--probe-only", docker=str(d))
    assert r.returncode == STALE
    assert r.stdout.strip() == "STALE"


def test_stale_when_docker_hangs_past_the_budget(tmp_path):
    """The original symptom: `docker ps` hangs. Exercised through the FALLBACK
    path (no `timeout` binary), which is what a stock macOS actually runs."""
    d = fake_bin(tmp_path / "bin", "docker", "sleep 60")
    # The ONE test that is about timing, so it names its own short budget.
    r = run(tmp_path, "--probe-only", docker=str(d), probe_timeout="2")
    assert r.returncode == STALE


def test_cannot_probe_when_the_binary_is_missing(tmp_path):
    """With a live process, no docker binary is CANNOT PROBE, not staleness."""
    r = run(tmp_path, "--probe-only", docker="none")
    assert r.returncode == CANNOT_PROBE
    assert r.stdout.strip() == "CANNOT_PROBE"


def test_not_running_is_success_before_docker_binary_resolution(tmp_path):
    """No process is deliberate downtime even when the CLI is also absent."""
    r = run(tmp_path, "--probe-only", docker="none", process_running=False)
    assert r.returncode == HEALTHY
    assert r.stdout.strip() == "NOT_RUNNING"


def test_rc_127_from_the_probe_is_cannot_probe_not_stale(tmp_path):
    """The precise reading error that caused the incident: a resolved binary
    that answers 127 means 'command not found', never 'daemon broken'."""
    d = fake_bin(tmp_path / "bin", "docker", "exit 127")
    r = run(tmp_path, "--probe-only", docker=str(d))
    assert r.returncode == CANNOT_PROBE


# ---------- the property that matters most ----------

def test_cannot_probe_takes_ZERO_actions(tmp_path):
    """A monitor that cannot probe must not conclude failure — and must not
    ACT. Every command the drill would use is replaced by a spy that records
    being called; the run must leave no trace of any of them."""
    spy_dir = tmp_path / "spy"
    trace = tmp_path / "actions.log"
    spies = {
        name: fake_bin(spy_dir, name, f'echo "{name} $*" >> "{trace}"; exit 0')
        for name in ("pkill", "open", "osascript", "launchctl", "kill")
    }

    r = run(
        tmp_path,
        docker="none",
        extra_path=str(spy_dir),
        extra_env={
            "GROUNDWORK_PKILL_BIN": str(spies["pkill"]),
            "GROUNDWORK_OPEN_BIN": str(spies["open"]),
            "GROUNDWORK_DRILL_KILL_BIN": str(spies["kill"]),
        },
    )

    assert r.returncode == CANNOT_PROBE
    drill = [ln for ln in (trace.read_text().splitlines() if trace.exists() else [])
             if ln.split()[0] in {"pkill", "open", "launchctl", "kill"}]
    assert drill == [], f"CANNOT_PROBE ran drill actions: {drill}"

    log = (tmp_path / "Library" / "Logs" / "groundwork"
           / "docker-watchdog.log").read_text()
    assert "CANNOT PROBE" in log
    assert "TAKING NO ACTION" in log
    assert "STALE" not in log, "must not describe itself as a staleness finding"


def test_not_running_logs_and_takes_ZERO_drill_actions(tmp_path):
    """Deliberate downtime is a state, not a fault."""
    spy_dir = tmp_path / "spy"
    trace = tmp_path / "actions.log"
    spies = {
        name: fake_bin(spy_dir, name, f'echo "{name} $*" >> "{trace}"; exit 0')
        for name in ("pkill", "open", "kill")
    }

    r = run(
        tmp_path,
        docker="none",
        process_running=False,
        extra_path=str(spy_dir),
        extra_env={
            "GROUNDWORK_PKILL_BIN": str(spies["pkill"]),
            "GROUNDWORK_OPEN_BIN": str(spies["open"]),
            "GROUNDWORK_DRILL_KILL_BIN": str(spies["kill"]),
        },
    )

    assert r.returncode == HEALTHY
    assert not trace.exists(), "not-running state must take zero drill actions"
    log = (tmp_path / "Library" / "Logs" / "groundwork"
           / "docker-watchdog.log").read_text()
    assert "docker down (not started)" in log
    assert "STALE" not in log


def test_running_process_with_timed_out_probe_runs_the_drill(tmp_path):
    """A live pid that ignores the probe is still the real stale failure."""
    spy_dir = tmp_path / "spy"
    trace = tmp_path / "actions.log"
    spies = {
        name: fake_bin(spy_dir, name, f'echo "{name} $*" >> "{trace}"; exit 0')
        for name in ("pkill", "open", "kill", "osascript")
    }
    fake_bin(spy_dir, "sleep", "exit 0")
    d = fake_bin(tmp_path / "bin", "docker", "exit 0")
    timed_out = fake_bin(tmp_path / "bin", "timeout", "exit 124")

    r = run(
        tmp_path,
        docker=str(d),
        timeout_bin=str(timed_out),
        process_running=True,
        extra_path=str(spy_dir),
        extra_env={
            "GROUNDWORK_PKILL_BIN": str(spies["pkill"]),
            "GROUNDWORK_OPEN_BIN": str(spies["open"]),
            "GROUNDWORK_DRILL_KILL_BIN": str(spies["kill"]),
        },
    )

    assert r.returncode == STALE
    actions = trace.read_text().splitlines()
    assert any(line.startswith("pkill ") for line in actions)
    assert any(line.startswith("kill ") for line in actions)
    assert any(line.startswith("open -a Docker") for line in actions)


def test_healthy_run_takes_zero_actions_either(tmp_path):
    spy_dir = tmp_path / "spy"
    trace = tmp_path / "actions.log"
    spies = {
        name: fake_bin(spy_dir, name, f'echo "{name} $*" >> "{trace}"; exit 0')
        for name in ("pkill", "open", "launchctl", "kill")
    }
    d = fake_bin(tmp_path / "bin", "docker", "exit 0")

    r = run(
        tmp_path,
        docker=str(d),
        extra_path=str(spy_dir),
        extra_env={
            "GROUNDWORK_PKILL_BIN": str(spies["pkill"]),
            "GROUNDWORK_OPEN_BIN": str(spies["open"]),
            "GROUNDWORK_DRILL_KILL_BIN": str(spies["kill"]),
        },
    )

    assert r.returncode == HEALTHY
    assert not trace.exists(), "a healthy check must touch nothing"
    log = (tmp_path / "Library" / "Logs" / "groundwork"
           / "docker-watchdog.log").read_text()
    assert "OK: docker responsive" in log


# ---------- the fallback path, proven rather than assumed ----------

def test_fallback_without_timeout_returns_healthy_for_a_fast_probe(tmp_path):
    """`timeout` is GNU coreutils and is NOT on stock macOS, so the fallback is
    the path a default machine takes. Its absence must never read as a fault —
    which is precisely the mistake that produced the incident."""
    d = fake_bin(tmp_path / "bin", "docker", "exit 0")
    r = run(tmp_path, "--probe-only", docker=str(d), timeout_bin="none")
    assert r.returncode == HEALTHY, "the fallback must resolve a fast success"
    assert r.stdout.strip() == "HEALTHY"
    assert "Terminated" not in r.stderr, "job-control chatter leaked into stderr"


def test_timeout_path_and_fallback_agree_on_a_healthy_probe(tmp_path):
    """Two implementations of one probe must not disagree about the same
    docker. The incident's cost came from a disagreement nobody was checking."""
    d = fake_bin(tmp_path / "bin", "docker", "exit 0")
    # A stand-in for GNU timeout: drop the budget argument, exec the rest.
    # Written rather than borrowed so the test exercises the timeout BRANCH on
    # a machine that may not have coreutils at all.
    fake_timeout = fake_bin(tmp_path / "bin", "timeout", 'shift; exec "$@"')

    with_timeout = run(tmp_path, "--probe-only", docker=str(d),
                       timeout_bin=str(fake_timeout))
    without = run(tmp_path, "--probe-only", docker=str(d), timeout_bin="none")

    assert with_timeout.returncode == HEALTHY
    assert without.returncode == HEALTHY
    assert with_timeout.stdout.strip() == without.stdout.strip() == "HEALTHY"


def test_probe_only_never_writes_a_verdict_to_the_log(tmp_path):
    """The installer calls --probe-only. A dry run that logged 'STALE' would
    put a finding in the record that no monitor ever made."""
    d = fake_bin(tmp_path / "bin", "docker", "exit 1")
    run(tmp_path, "--probe-only", docker=str(d))
    log = tmp_path / "Library" / "Logs" / "groundwork" / "docker-watchdog.log"
    assert not log.exists() or log.read_text().strip() == ""


def test_installer_tells_owner_how_to_disarm_the_watchdog():
    if not INSTALLER.is_file():
        pytest.skip("install.sh absent — launch-agent operations stay private")
    installer = INSTALLER.read_text()
    assert "Disarm watchdog: launchctl bootout gui/$(id -u)/com.groundwork.docker-watchdog" in installer
