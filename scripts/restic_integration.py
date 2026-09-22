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
        env = {**os.environ, "RESTIC_PASSWORD":"disposable-local-test-password", "RESTIC_REPOSITORY":str(root/'repo')}
        def restic(*commands):
            result = subprocess.run([args.restic,"--cache-dir",str(root/'cache'),*commands],env=env,capture_output=True,timeout=120)
            if result.returncode != 0:
                raise AssertionError(f"restic {commands[0]} failed with exit {result.returncode}: {result.stderr.decode('utf-8',errors='replace')}")
            return result.stdout
        version = restic("version").decode().strip()
        restic("init")
        restic("backup",str(data),"--host","fixture-host","--tag","daily","--exclude",str(data/'documents'))
        restic("check","--read-data")
        listing = root/'listing.jsonl'; listing.write_bytes(restic("ls","--json","latest"))
        missing = read_catalog(listing)
        photo = next(p for p in missing['nodes'] if p.endswith('/photos/photo.txt'))
        snapshot_root = photo.removesuffix('/photos/photo.txt')
        at = utc_now()
        inventory = {"version":1,"host":"fixture-host","captured_at":at,"containers":[{"name":"synthetic-consumer","mounts":[
            {"type":"bind","source":"/srv/photos","destination":"/photos","read_only":False},
            {"type":"bind","source":"/srv/documents","destination":"/documents","read_only":True}]}]}
        policy = {"version":1,"host":"fixture-host","required_tags":["daily"],"mappings":[
            {"type":"bind","source":"/srv/photos","snapshot_path":snapshot_root+'/photos'},
            {"type":"bind","source":"/srv/documents","snapshot_path":snapshot_root+'/documents',"required_files":[{"path":"note.txt","min_bytes":1}]}]}
        failed = analyze(inventory,missing,policy,at)
        assert failed['exit_code']==1 and any(i['code']=='BS001' and i['resource']=='bind:/srv/documents' for i in failed['findings'])
        restic("backup",str(data),"--host","fixture-host","--tag","daily")
        listing.write_bytes(restic("ls","--json","latest"))
        present = read_catalog(listing)
        passed = analyze(inventory,present,policy,utc_now())
        assert passed['exit_code']==0, passed
        restic("restore",present['snapshot']['id'],"--target",str(root/'restored'))
        restored = list((root/'restored').rglob('note.txt'))
        assert len(restored)==1 and restored[0].read_bytes()==(data/'documents/note.txt').read_bytes()
        print(json.dumps({"restic":version,"excluded_backup_integrity_check":0,"excluded_path_check":failed['exit_code'],"complete_path_check":passed['exit_code'],"restored_fixture_sha256":hashlib.sha256(restored[0].read_bytes()).hexdigest(),"docker_inventory":"synthetic Linux mount projection; restic backup and restore are real"},indent=2))


if __name__ == '__main__':
    main()
