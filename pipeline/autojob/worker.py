"""Command worker: executes requests written to the ``commands`` table by the dashboard.

Commands: ``run`` (arg "dry" for a dry run), ``docs`` (arg: job id), ``abort``.
Each run/docs command is executed as a fresh ``autojob`` subprocess, so code or config
changes apply to the next command without restarting this service, and a crash in a run
never takes the worker down. The daily timer calls ``autojob run`` directly.
"""
from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time

from autojob import db as D
from autojob.pipeline import setup_logging

logger = logging.getLogger("autojob")
_stop = False
_child: subprocess.Popen | None = None


def _handle_stop(*_):
    global _stop
    _stop = True
    if _child and _child.poll() is None:
        _child.terminate()  # the child's own SIGTERM handler turns this into a graceful abort


def _autojob(*args: str) -> subprocess.CompletedProcess:
    global _child
    _child = subprocess.Popen([sys.executable, "-m", "autojob", *args], stdin=subprocess.DEVNULL)
    rc = _child.wait()
    _child = None
    return subprocess.CompletedProcess(args, rc)


def execute(cmd: dict) -> tuple[str, str]:
    """Return (status, result) for a command row."""
    name, arg = cmd["command"], (cmd.get("arg") or "").strip()
    if name == "run":
        rc = _autojob("run", *(["--dry-run"] if arg == "dry" else [])).returncode
        return ("done" if rc == 0 else "error"), f"autojob run exited {rc}"
    if name == "docs":
        if not arg.isdigit():
            return "error", f"bad job id {arg!r}"
        rc = _autojob("docs", arg).returncode
        return ("done" if rc == 0 else "error"), f"autojob docs {arg} exited {rc}"
    if name == "abort":
        with D.db() as conn:
            D.set_pipeline_state(conn, command="abort")
        return "done", "abort flag set"
    return "error", f"unknown command {name}"


def main(poll_seconds: float = 3.0) -> None:
    setup_logging()
    D.init_db()
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    logger.info("worker started (poll %.0fs)", poll_seconds)
    while not _stop:
        with D.db() as conn:
            cmd = D.claim_next_command(conn)
        if not cmd:
            time.sleep(poll_seconds)
            continue
        logger.info("worker: executing %s %s", cmd["command"], cmd.get("arg") or "")
        try:
            status, result = execute(cmd)
        except Exception as e:  # noqa: BLE001
            logger.exception("worker: command %s failed", cmd["id"])
            status, result = "error", str(e)[:500]
        with D.db() as conn:
            D.finish_command(conn, cmd["id"], status, result)
    logger.info("worker stopped")
