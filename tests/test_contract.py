import copy
import json
from pathlib import Path
import pytest
from backupscope.catalog import read_catalog
from backupscope.core import analyze, draft_policy, validate_policy
from backupscope.inventory import from_inspect, validate_inventory
from backupscope.report import html_report
from backupscope.validation import InputError, parse_json

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
AT = "2026-09-22T13:00:00Z"


@pytest.fixture
def case():
    return [json.loads((EXAMPLES / "inventory.json").read_text()), read_catalog(EXAMPLES / "present.jsonl"), json.loads((EXAMPLES / "policy.json").read_text())]


def check(case):
    return analyze(*case, now=AT)


def test_complete_example(case):
    result = check(case)
    assert result["exit_code"] == 0
    assert result["summary"]["statuses"] == {"observed": 3, "ignored": 1}
    assert "restore test" in result["scope"]


def test_missing_mount_and_old_dump_remain_distinct(case):
    case[1] = read_catalog(EXAMPLES / "missing.jsonl")
    result = check(case)
    assert result["exit_code"] == 1
    assert {i["code"] for i in result["findings"]} == {"BS001", "BS008"}
    statuses = {row["resource"]: row["status"] for row in result["rows"]}
    assert statuses["bind:/srv/documents"] == "missing"
    assert statuses["volume:postgres"] == "failed"  # Present, but stale.


def test_read_only_data_is_still_required(case):
    del case[1]["nodes"]["/backup/documents"]
    assert any(i.get("resource") == "bind:/srv/documents" for i in check(case)["findings"])


def test_new_mount_detected_without_editing_policy(case):
    case[0]["containers"][0]["mounts"].append({"type":"bind","source":"/srv/new", "destination":"/new","read_only":False})
    assert any(i.get("resource") == "bind:/srv/new" and i["code"] == "BS001" for i in check(case)["findings"])


def test_shared_volume_deduplicated_but_owners_retained(case):
    case[0]["containers"].append({"name":"worker","mounts":[copy.deepcopy(case[0]["containers"][0]["mounts"][0])]})
    row = next(r for r in check(case)["rows"] if r["source"] == "photos")
    assert len(row["owners"]) == 2 and row["files"] == 1


def test_prefix_collision_does_not_supply_file_evidence(case):
    node = case[1]["nodes"].pop("/backup/photos/image.jpg")
    case[1]["nodes"]["/backup/photos-old/image.jpg"] = node
    result = check(case)
    assert result["exit_code"] == 2
    assert any(i["code"] == "BSU07" for i in result["unknowns"])


@pytest.mark.parametrize("kind", ["symlink", "socket", "fifo", "dev"])
def test_special_root_never_proves_data(case, kind):
    case[1]["nodes"]["/backup/photos"]["type"] = kind
    assert any(i["code"] == "BSU06" for i in check(case)["unknowns"])


def test_explicit_empty_directory_allowed(case):
    del case[1]["nodes"]["/backup/photos/image.jpg"]
    case[2]["mappings"][0]["allow_empty"] = True
    assert check(case)["exit_code"] == 0


def test_allow_empty_does_not_allow_absent_root(case):
    del case[1]["nodes"]["/backup/photos"]
    case[2]["mappings"][0]["allow_empty"] = True
    assert any(i["code"] == "BS001" for i in check(case)["findings"])


@pytest.mark.parametrize("field,value", [("min_files",2),("min_bytes",42001)])
def test_minimums_detect_partial_evidence(case,field,value):
    case[2]["mappings"][0][field] = value
    assert any(i["code"] == "BS002" for i in check(case)["findings"])


def test_required_symlink_is_not_required_file(case):
    case[1]["nodes"]["/backup/dumps/postgres.sql"]["type"] = "symlink"
    result = check(case)
    assert any(i["code"] == "BS003" for i in result["findings"])
    assert result["exit_code"] == 2  # Known missing regular file survives empty-root unknown.


@pytest.mark.parametrize("mtime", [None,"2026-10-01T00:00:00Z"])
def test_dump_freshness_unknown_is_not_fresh(case,mtime):
    case[1]["nodes"]["/backup/dumps/postgres.sql"]["mtime"] = mtime
    assert check(case)["exit_code"] == 2


@pytest.mark.parametrize("where", ["snapshot", "inventory"])
def test_stale_evidence_fails_even_with_paths_present(case,where):
    if where == "snapshot": case[1]["snapshot"]["time"] = "2026-09-01T00:00:00Z"
    else: case[0]["captured_at"] = "2026-09-01T00:00:00Z"
    assert check(case)["exit_code"] == 1


def test_wrong_host_retains_no_observed_rows(case):
    case[1]["snapshot"]["hostname"] = "another-server"
    result = check(case)
    assert result["exit_code"] == 2
    assert not any(r["status"] == "observed" for r in result["rows"])


def test_wrong_tags_do_not_mix_backup_streams(case):
    case[1]["snapshot"]["tags"] = ["unrelated"]
    assert check(case)["exit_code"] == 2


def test_expired_ignore_fails(case):
    case[2]["ignores"][0]["expires_at"] = AT
    assert any(i["code"] == "BS006" for i in check(case)["findings"])


def test_stale_mapping_does_not_disappear(case):
    case[0]["containers"].pop(1)
    assert any(i["code"] == "BS007" for i in check(case)["findings"])


def test_empty_discovery_not_green(case):
    case[0]["containers"] = []
    assert check(case)["exit_code"] == 2


def test_all_ignored_not_green(case):
    case[0]["containers"] = [case[0]["containers"][-1]]
    case[2]["mappings"] = []
    assert any(i["code"] == "BSU09" for i in check(case)["unknowns"])


def test_missing_and_unknown_both_retained(case):
    case[1] = read_catalog(EXAMPLES / "missing.jsonl")
    case[1]["snapshot"]["time"] = "2026-10-01T00:00:00Z"
    report = check(case)
    assert report["exit_code"] == 2 and report["findings"] and report["unknowns"]


def test_file_bind_mount_is_valid_evidence(case):
    case[2]["mappings"][1]["snapshot_path"] = "/backup/documents/note.txt"
    assert check(case)["exit_code"] == 0


def test_automatic_host_path_mapping(case):
    case[2]["mappings"].pop(1)
    for path in list(case[1]["nodes"]):
        if path.startswith("/backup/documents"):
            case[1]["nodes"][path.replace("/backup/documents","/srv/documents")] = case[1]["nodes"].pop(path)
    assert check(case)["exit_code"] == 0


def test_draft_does_not_silently_ignore_readonly(case):
    draft = draft_policy(case[0])
    validate_policy(draft)
    assert draft["ignores"] == [] and len(draft["mappings"]) == 4


@pytest.mark.parametrize("path", ["relative", "//host/path", "/a/../b", "/a/./b", "/a//b", "/a\\b", "/a\nsecret"])
def test_invalid_source_paths_rejected(case,path):
    case[0]["containers"][0]["mounts"][1]["source"] = path
    with pytest.raises(InputError): check(case)


@pytest.mark.parametrize("bad", [True, -1, 0, float('inf'), float('nan'), "24", 10**400])
def test_invalid_age_limit_rejected(case,bad):
    case[2]["max_age_hours"] = bad
    with pytest.raises(InputError): check(case)


def test_unknown_policy_key_rejected(case):
    case[2]["ignore_everything"] = True
    with pytest.raises(InputError): check(case)


def test_conflicting_selectors_rejected(case):
    case[2]["ignores"].append({"type":"volume","source":"photos","reason":"oops"})
    with pytest.raises(InputError): check(case)


def test_required_file_traversal_rejected(case):
    case[2]["mappings"][2]["required_files"][0]["path"] = "../outside.sql"
    with pytest.raises(InputError): check(case)


def test_inspect_redacts_env_command_and_labels():
    inv = from_inspect([{"Name":"/app","Config":{"Env":["PASSWORD=sentinel-private"],"Labels":{"token":"hidden"}}, "Mounts":[{"Type":"bind","Source":"/srv/data","Destination":"/data","RW":False}]}], "fixture", AT)
    assert "sentinel-private" not in json.dumps(inv) and "hidden" not in json.dumps(inv)
    assert validate_inventory(inv)[0]["owners"][0]["read_only"]


def test_conflicting_volume_sources_fail(case):
    extra = copy.deepcopy(case[0]["containers"][0])
    extra["name"] = "worker"
    extra["mounts"][0]["source"] = "/different"
    case[0]["containers"].append(extra)
    with pytest.raises(InputError): check(case)


def test_html_injection_escaped(case):
    case[0]["containers"][0]["name"] = '<img src=x onerror="alert(1)">'
    report = html_report(check(case))
    assert '<img' not in report and '&lt;img' in report and '<script' not in report


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"v":NaN}', '{"v":Infinity}'])
def test_json_ambiguity_rejected(raw):
    with pytest.raises(InputError): parse_json(raw)


def test_unsupported_mount_has_renderable_unknown(case):
    case[0]["containers"][0]["mounts"].append({"type":"future-mount","source":"opaque","destination":"/special","read_only":True})
    report = check(case)
    assert report["exit_code"] == 2 and 'BSU05' in html_report(report)


def test_ephemeral_mount_is_visible(case):
    case[0]["containers"][0]["mounts"].append({"type":"tmpfs","source":"","destination":"/tmp","read_only":False})
    assert check(case)["summary"]["statuses"]["ephemeral"] == 1
