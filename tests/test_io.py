import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from backupscope.catalog import read_catalog
from backupscope.validation import InputError

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


def cli(*args):
    return subprocess.run([sys.executable, "-m", "backupscope", *map(str,args)], capture_output=True, text=True, encoding="utf-8", env={**os.environ,"PYTHONPATH":str(ROOT/'src')})


def options(snapshot="present.jsonl"):
    return ["check","--inventory",EX/'inventory.json',"--snapshot",EX/snapshot,"--policy",EX/'policy.json',"--at","2026-09-22T13:00:00Z"]


@pytest.mark.parametrize("snapshot,code", [("present.jsonl",0),("missing.jsonl",1)])
def test_cli_exit_and_json(snapshot,code):
    result = cli(*options(snapshot),"--format","json")
    assert result.returncode == code and json.loads(result.stdout)["exit_code"] == code
    assert not result.stderr


def test_output_wont_overwrite(tmp_path):
    target = tmp_path/'important.json'
    target.write_text('do not replace')
    result = cli(*options(),"--output",target)
    assert result.returncode == 2 and target.read_text() == 'do not replace'


def test_actual_html_file(tmp_path):
    target = tmp_path/'report.html'
    result = cli(*options(),"--format","html","--output",target)
    assert result.returncode == 0 and 'Content-Security-Policy' in target.read_text()
    assert not result.stdout


def test_malformed_input_no_partial_report(tmp_path):
    bad = tmp_path/'bad.json'
    bad.write_text('{"secret":"private-sentinel", broken}')
    args = options();args[2] = bad
    result = cli(*args,"--format","json")
    assert result.returncode == 2 and not result.stdout and 'private-sentinel' not in result.stderr


def test_saved_inspect_needs_original_capture_time(tmp_path):
    f = tmp_path/'inspect.json'; f.write_text('[]')
    result = cli('inventory','--host','test','--inspect',f)
    assert result.returncode == 2


def test_draft_cli_valid_json():
    result = cli('init','--inventory',EX/'inventory.json')
    assert result.returncode == 0 and json.loads(result.stdout)['mappings']


@pytest.mark.parametrize('mutation', ['duplicate_header','duplicate_node','node_before_header','no_header','non_object','invalid_type','contradictory_types','bad_id','bad_utf8','blank','truncated'])
def test_catalog_rejects_ambiguous_or_incomplete_records(tmp_path,mutation):
    lines=(EX/'present.jsonl').read_text().splitlines()
    if mutation=='duplicate_header':lines.insert(1,lines[0])
    elif mutation=='duplicate_node':lines.append(lines[-1])
    elif mutation=='node_before_header':lines[0],lines[1]=lines[1],lines[0]
    elif mutation=='no_header':lines=[]
    elif mutation=='non_object':lines.append('[]')
    elif mutation=='invalid_type':lines.append('{"message_type":"error"}')
    elif mutation=='contradictory_types':lines[0]=lines[0][:-1]+',"message_type":"node"}'
    elif mutation=='bad_id':lines[0]=lines[0].replace('a'*64,'latest')
    elif mutation=='blank':lines.append('')
    elif mutation=='truncated':lines[-1]=lines[-1][:-4]
    data=('\n'.join(lines)+'\n').encode()
    if mutation=='bad_utf8':data+=b'\xff'
    target=tmp_path/'listing.jsonl';target.write_bytes(data)
    with pytest.raises(InputError):read_catalog(target)


def test_new_restic_message_type_supported(tmp_path):
    target=tmp_path/'new.jsonl'
    target.write_text((EX/'present.jsonl').read_text().replace('struct_type','message_type'))
    assert read_catalog(target)['snapshot']['hostname']=='demo-server'


def test_oversized_line_rejected(tmp_path):
    target=tmp_path/'large.jsonl';target.write_bytes(b'x'*(1024*1024+1))
    with pytest.raises(InputError):read_catalog(target)


def test_catalog_rejects_files_below_symlink(tmp_path):
    lines=[json.loads(line) for line in (EX/'present.jsonl').read_text().splitlines()]
    next(line for line in lines if line.get('path')=='/backup/photos')['type']='symlink'
    target=tmp_path/'contradiction.jsonl';target.write_text(''.join(json.dumps(x)+'\n' for x in lines))
    with pytest.raises(InputError,match='non-directory ancestor'):read_catalog(target)
