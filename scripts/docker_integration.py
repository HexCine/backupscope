"""Optional Linux daemon test, using only a newly created, never-started container."""
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from backupscope.inventory import collect

name = 'backupscope-test-' + uuid.uuid4().hex[:12]
identifier = None
with tempfile.TemporaryDirectory(prefix='backupscope-docker-') as folder:
    def docker(*args):
        return subprocess.run(['docker',*args],check=True,capture_output=True,text=True,timeout=120).stdout.strip()
    try:
        # Alpine is an official Docker image. No command in the image is executed.
        identifier = docker('create','--name',name,'--label','com.docker.compose.project='+name,'--mount','type=bind,source='+str(Path(folder).resolve())+',target=/fixture,readonly','alpine:3.22')
        data=collect('fixture-host',name)
        assert len(data['containers'])==1 and data['containers'][0]['name']==name
        mount=next(m for m in data['containers'][0]['mounts'] if m['destination']=='/fixture')
        assert mount['type']=='bind' and mount['read_only'] is True
        assert 'Config' not in json.dumps(data)
        print(json.dumps({'docker_discovery':'passed','container_started':False,'read_only_mount':True}))
    finally:
        if identifier:
            assert len(identifier)==64 and all(c in '0123456789abcdef' for c in identifier)
            assert docker('inspect','--format','{{.Name}}',identifier)=='/'+name
            docker('rm',identifier)
