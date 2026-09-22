"""Shared strict input validation. Never interpolate raw input in errors."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path


class InputError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise InputError(message)


def fields(value, allowed, required, label):
    need(isinstance(value, dict), f"{label}: expected an object")
    need(set(value) <= set(allowed) and set(required) <= set(value), f"{label}: missing or unsupported fields")


def text(value, label, limit=4096):
    need(isinstance(value, str) and 0 < len(value) <= limit, f"{label}: expected nonempty text")
    need(all(ord(c) >= 32 and ord(c) != 127 and not 0xD800 <= ord(c) <= 0xDFFF for c in value), f"{label}: control characters are unsupported")
    return value


def number(value, label, minimum=0, maximum=87600, integer=False):
    need(type(value) in (int, float) and minimum <= value <= maximum and math.isfinite(value), f"{label}: number out of range")
    need(not integer or type(value) is int, f"{label}: expected an integer")
    return value


def timestamp(value, label="timestamp"):
    text(value, label, 100)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        need(result.tzinfo is not None, f"{label}: timezone is required")
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise InputError(f"{label}: expected an ISO-8601 timestamp with timezone") from exc


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def absolute(value, label="path"):
    text(value, label)
    need(value.startswith("/") and not value.startswith("//") and "\\" not in value, f"{label}: expected an absolute POSIX path")
    parts = value.split("/")[1:]
    need(len(parts) <= 64, f"{label}: at most 64 path segments")
    need(all(p not in (".", "..") for p in parts), f"{label}: dot segments are unsupported")
    need("//" not in value, f"{label}: repeated separators are unsupported")
    return value.rstrip("/") or "/"


def relative(value):
    text(value, "required path")
    need(not value.startswith("/") and "\\" not in value and all(p not in ("", ".", "..") for p in value.split("/")), "required path: expected a relative POSIX file path")
    return value


def pairs(items):
    value = {}
    for key, item in items:
        need(key not in value, "JSON: duplicate object key")
        value[key] = item
    return value


def parse_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(InputError("JSON: nonfinite number")))
    except (ValueError, RecursionError) as exc:
        raise InputError("Invalid JSON (including duplicate keys or excessive nesting)") from exc


def read_json(path):
    target = Path(path)
    need(not target.is_symlink(), "Input symlinks are not accepted")
    with target.open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    need(len(raw) <= 8 * 1024 * 1024, "JSON input exceeds 8 MiB")
    try:
        return parse_json(raw.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise InputError("Input must be UTF-8") from exc
