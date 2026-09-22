"""Real local restic backup/check/restore on disposable generated fixtures.

Usage: python scripts/restic_integration.py --restic /path/to/restic
No daemon, real user backup, cloud account, or network is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from backupscope.catalog import read_catalog
from backupscope.core import analyze
from backupscope.validation import utc_now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--restic", default="restic")
    args = parser.parse_args()
    # TemporaryDirectory owns precisely its generated directory, never a user path.
    with tempfile.TemporaryDirectory(prefix="backupscope-integration-") as folder:
        root = Path(folder)
        data = root / "data"
        for name, content in [("photos/photo.txt",b"photo fixture"),("documents/note.txt",b"important document")]:
            path = data/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(content)
        env = {**{k:v for k,v in os.environ.items() if not k.startswith('RESTIC_')}, "RESTIC_PASSWORD":"disposable-local-test-password", "RESTIC_REPOSITORY":str(root/'repo')}
        def restic(*commands):
            result = subprocess.run([args.restic,"--cache-dir",str(root/'cache'),*commands],env=env,capture_output=True,timeout=120)
            if result.returncode != 0:
                raise AssertionError(f"restic {commands[0]} failed with exit {result.returncode}: {result.stderr.decode('utf-8',errors='replace')}")
            return result.stdout
        version = restic("version").decode().strip()
        restic("init")
        restic("backup",str(data),"--host","fixture-host","--tag","daily,docker","--exclude",str(data/'documents'))
        restic("check","--read-data")
        listing = root/'listing.jsonl'; listing.write_bytes(restic("ls","--json","latest"))
        missing = read_catalog(listing)
        photo = next(p for p in missing['nodes'] if p.endswith('/photos/photo.txt'))
        snapshot_root = photo.removesuffix('/photos/photo.txt')
        at = utc_now()
        inventory = {"version":1,"host":"fixture-host","captured_at":at,"containers":[{"name":"synthetic-consumer","mounts":[
            {"type":"bind","source":"/srv/photos","destination":"/photos","read_only":False},
            {"type":"bind","source":"/srv/documents","destination":"/documents","read_only":True}]}]}
        policy = {"version":1,"host":"fixture-host","required_tags":["daily", "docker"],"mappings":[
            {"type":"bind","source":"/srv/photos","snapshot_path":snapshot_root+'/photos'},
            {"type":"bind","source":"/srv/documents","snapshot_path":snapshot_root+'/documents',"required_files":[{"path":"note.txt","min_bytes":1}]}]}
        failed = analyze(inventory,missing,policy,at)
        assert failed['exit_code']==1 and any(i['code']=='BS001' and i['resource']=='bind:/srv/documents' for i in failed['findings'])
        inv_file = root/'inventory.json'; inv_file.write_text(json.dumps(inventory), encoding='utf-8')
        policy_file = root/'policy.json'; policy_file.write_text(json.dumps(policy), encoding='utf-8')
        base = [sys.executable, '-m', 'backupscope', 'verify', '--inventory', str(inv_file), '--policy', str(policy_file), '--restic', args.restic]
        def verify(selection, expected, environment=None, extra=None):
            result = subprocess.run([*base, *selection, *(extra or ['--format', 'json'])], env=environment or env, capture_output=True, timeout=120)
            assert result.returncode == expected, (result.returncode, result.stderr)
            return result
        captured_missing = json.loads(verify(['--snapshot-id', missing['snapshot']['id']], 1).stdout)
        assert captured_missing['capture']['completion_confirmed']
        restic("backup",str(data),"--host","fixture-host","--tag","daily,docker")
        listing.write_bytes(restic("ls","--json","latest"))
        present = read_catalog(listing)
        passed = analyze(inventory,present,policy,utc_now())
        assert passed['exit_code']==0, passed
        captured_present = json.loads(verify(['--snapshot-id', present['snapshot']['id']], 0).stdout)
        assert captured_present['capture']['selection'] == 'snapshot_id'
        # Newer snapshots with the wrong host or only one required tag must not win.
        restic('backup', str(data), '--host', 'other-host', '--tag', 'daily,docker')
        restic('backup', str(data), '--host', 'fixture-host', '--tag', 'daily')
        latest = json.loads(verify(['--latest'], 0, {**env, 'RESTIC_HOST':'other-host'}).stdout)
        assert latest['snapshot']['id'] == present['snapshot']['id']
        assert latest['capture']['selection'] == 'latest_for_policy'
        rejected = root/'must-not-exist.html'
        invalid = verify(['--latest'], 2, {**env, 'RESTIC_PASSWORD':'wrong-private-password-sentinel'}, ['--format', 'html', '--output', str(rejected)])
        assert not invalid.stdout and not rejected.exists()
        assert b'wrong-private-password-sentinel' not in invalid.stderr and b'exit 12' in invalid.stderr
        no_match = {**policy, 'required_tags':['nonexistent-tag']}
        policy_file.write_text(json.dumps(no_match), encoding='utf-8')
        no_snapshot = verify(['--latest'], 2)
        assert not no_snapshot.stdout and b'output discarded' in no_snapshot.stderr
        restic("restore",present['snapshot']['id'],"--target",str(root/'restored'))
        restored = list((root/'restored').rglob('note.txt'))
        assert len(restored)==1 and restored[0].read_bytes()==(data/'documents/note.txt').read_bytes()
        print(json.dumps({"restic":version,"excluded_backup_integrity_check":0,"excluded_path_check":failed['exit_code'],"complete_path_check":passed['exit_code'],"direct_verify_exits":[captured_missing['exit_code'], captured_present['exit_code'], invalid.returncode],"latest_host_and_all_tags":"passed including RESTIC_HOST override", "missing_snapshot":"exit 2 without report", "restored_fixture_sha256":hashlib.sha256(restored[0].read_bytes()).hexdigest(),"docker_inventory":"synthetic Linux mount projection; restic backup and restore are real"},indent=2))


if __name__ == '__main__':
    main()
