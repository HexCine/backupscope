"""Install the built wheel offline into a clean venv; exercise public entrypoints."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv
import zipfile

project = Path(__file__).resolve().parents[1]
version = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
wheel = project / f'dist/backupscope-{version}-py3-none-any.whl'
assert wheel.is_file(), 'Build the wheel first: python -m build'
with zipfile.ZipFile(wheel) as archive:
    metadata = archive.read(next(n for n in archive.namelist() if n.endswith('/METADATA'))).decode()
    assert 'Requires-Dist:' not in metadata
    assert all('..' not in Path(n).parts for n in archive.namelist())
with tempfile.TemporaryDirectory(prefix='backupscope-wheel-') as folder:
    root = Path(folder)
    venv.EnvBuilder(with_pip=True).create(root/'env')
    binary = root/'env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    command = root/'env'/('Scripts/backupscope.exe' if os.name=='nt' else 'bin/backupscope')
    environment = {k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME')}
    def run(args, expected=0):
        r = subprocess.run(list(map(str,args)),cwd=root,env=environment,capture_output=True,text=True,encoding='utf-8',timeout=120)
        assert r.returncode==expected,(r.returncode,r.stdout,r.stderr)
        return r
    run([binary,'-m','pip','--isolated','install','--no-index','--no-deps','--cache-dir',root/'empty-cache',wheel])
    shutil.copytree(project/'examples',root/'examples')
    run([command,'--version'])
    assert '--latest' in run([command,'verify','--help']).stdout
    failure = run([command,'verify','--inventory','examples/inventory.json','--policy','examples/policy.json','--latest','--restic',root/'absent-restic'],2)
    assert not failure.stdout and 'Cannot start restic' in failure.stderr
    run([binary,'-c',f"import backupscope; assert backupscope.__version__ == {version!r}; assert 'env' in backupscope.__file__"])
    base=[command,'check','--inventory','examples/inventory.json','--policy','examples/policy.json','--at','2026-09-22T13:00:00Z']
    for name, code in [('missing',1),('present',0)]:
        r=run([*base,'--snapshot',f'examples/{name}.jsonl','--format','json'],code)
        assert json.loads(r.stdout)['exit_code']==code
    run([*base,'--snapshot','does-not-exist.jsonl'],2)
    target=root/'coverage.html'
    run([*base,'--snapshot','examples/present.jsonl','--format','html','--output',target])
    content=target.read_bytes()
    run([*base,'--snapshot','examples/present.jsonl','--output',target],2)
    assert content==target.read_bytes() and b'<script' not in content
    print(json.dumps({'python':sys.version.split()[0],'offline_install':True,'runtime_dependencies':0,'source_isolated':True,'public_cli_examples':[1,0,2],'exclusive_output':True}))
