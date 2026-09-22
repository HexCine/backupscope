"""Bounded, read-only capture from an installed, trusted restic executable."""
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Full, Queue
import subprocess
import tempfile
import threading
import time

from .catalog import parse_catalog
from .validation import InputError, need, number, text, utc_now

MAX_BYTES = 128 * 1024 * 1024


@contextmanager
def capture(command, timeout, limit=MAX_BYTES):
    """Spool bounded stdout privately; yield only after exit 0 and complete EOF."""
    number(timeout, "restic timeout", minimum=0.01, maximum=3600)
    chunks = Queue(maxsize=2)
    stopped = threading.Event()
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   shell=False, bufsize=0)
    except OSError as exc:
        raise InputError("Cannot start restic; install it or select a trusted executable with --restic") from exc

    def send(value):
        while not stopped.is_set():
            try:
                chunks.put(value, timeout=0.05)
                return
            except Full:
                pass

    def reader():
        try:
            while not stopped.is_set():
                block = process.stdout.read(65536)
                send(block)
                if not block:
                    break
        except OSError:
            send(None)
        finally:
            process.stdout.close()

    worker = threading.Thread(target=reader, name="backupscope-restic-reader", daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryFile(mode="w+b") as stream:
            size = 0
            while True:
                remaining = deadline - time.monotonic()
                need(remaining > 0, "Restic timed out; no report was produced")
                try:
                    block = chunks.get(timeout=remaining)
                except Empty:
                    raise InputError("Restic timed out; no report was produced") from None
                need(block is not None, "Cannot read restic output; no report was produced")
                if not block:
                    break
                size += len(block)
                need(size <= limit, "Restic listing exceeds the capture size limit; no report was produced")
                stream.write(block)
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise InputError("Restic timed out; no report was produced") from None
            need(code == 0, f"Restic ls failed (exit {code}); output discarded. Check restic authentication and repository access directly; stderr is withheld to protect secrets")
            stream.seek(0)
            yield stream
    finally:
        stopped.set()
        if process.poll() is None:
            process.kill()
        process.wait()
        worker.join(timeout=1)


def collect_catalog(policy, snapshot_id=None, executable="restic", timeout=300):
    """None selects latest for the policy host and all required tags."""
    text(executable, "restic executable")
    need(Path(executable).suffix.lower() not in (".bat", ".cmd"), "Use a native restic executable, not a shell script")
    if snapshot_id is not None:
        need(isinstance(snapshot_id, str) and len(snapshot_id) == 64 and
             all(c in "0123456789abcdef" for c in snapshot_id),
             "--snapshot-id requires a full lowercase 64-character ID; use --latest for automatic selection")
    command = [executable, "--no-lock", "--no-cache", "ls", "--json"]
    if snapshot_id is None:
        text(policy["host"], "policy host", 256)
        # One restic tag list means AND; repeated --tag arguments mean OR.
        tags = policy.get("required_tags", [])
        for tag in tags:
            text(tag, "policy tag", 256)
            need("," not in tag, "--latest cannot select a literal comma in a tag; use --snapshot-id")
            need(tag == tag.strip(), "--latest cannot select tags with surrounding whitespace; use --snapshot-id")
        command.append("--host=" + policy["host"])
        if tags:
            command.append("--tag=" + ",".join(tags))
    command.extend(["--", snapshot_id or "latest"])
    with capture(command, timeout) as stream:
        catalog = parse_catalog(stream)
    if snapshot_id:
        need(catalog["snapshot"]["id"] == snapshot_id, "Restic returned a different snapshot ID; no report was produced")
    catalog["capture"] = {"method": "restic", "completion_confirmed": True,
                          "restic_exit_code": 0, "finished_at": utc_now(),
                          "selection": "snapshot_id" if snapshot_id else "latest_for_policy"}
    return catalog
