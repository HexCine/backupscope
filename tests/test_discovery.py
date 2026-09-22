import json
import subprocess
from types import SimpleNamespace
import pytest
from backupscope.inventory import collect, command
from backupscope.validation import InputError


def test_discovery_uses_only_read_commands_and_redacted_projection(monkeypatch):
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        if args[2]=='ls':return SimpleNamespace(returncode=0,stdout=('a'*64+'\n').encode())
        return SimpleNamespace(returncode=0,stdout=json.dumps({'Name':'/demo','Mounts':[{'Type':'volume','Source':'/var/lib/docker/volumes/demo/_data','Destination':'/data','Name':'demo','RW':True}]}).encode())
    monkeypatch.setattr(subprocess,'run',run)
    data=collect('fixture','my-project')
    assert data['containers'][0]['name']=='demo'
    assert calls[0][-1]=='label=com.docker.compose.project=my-project'
    assert [c[2] for c in calls]==['ls','inspect']
    assert '.Mounts' in calls[1][4] and '.Config' not in calls[1][4]


def test_failed_discovery_withholds_raw_stderr(monkeypatch):
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout=b'',stderr=b'secret-sentinel'))
    with pytest.raises(InputError,match='Docker command failed') as exc:collect('fixture')
    assert 'secret-sentinel' not in str(exc.value)


def test_discovery_timeout_fails(monkeypatch):
    def fail(*a,**k):raise subprocess.TimeoutExpired('docker',30)
    monkeypatch.setattr(subprocess,'run',fail)
    with pytest.raises(InputError,match='timed out'):command(['docker','container','ls'])


def test_discovery_empty_is_explicit_inventory(monkeypatch):
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=b''))
    assert collect('fixture')['containers']==[]
