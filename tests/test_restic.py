"""Real child-process failures plus command and public CLI contracts."""
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from backupscope import cli, restic
from backupscope.core import analyze
from backupscope.report import html_report, text_report
from backupscope.validation import InputError, utc_now

EX = Path(__file__).resolve().parents[1] / 'examples'
ID = 'a' * 64


def child(code):
    return [sys.executable, '-c', code]


def test_capture_waits_for_success_and_preserves_bytes():
    with restic.capture(child("import sys; sys.stdout.buffer.write(b'first\\nlast\\n')"), 5) as stream:
        assert stream.read() == b'first\nlast\n'


@pytest.mark.parametrize('code', [1, 2, 3, 10, 11, 12, 130, 77])
def test_valid_prefix_is_discarded_on_any_failure(code):
    source = "import sys; sys.stdout.buffer.write(" + repr((EX/'present.jsonl').read_bytes()) + "); sys.stderr.write('private-secret-sentinel'); sys.exit(" + str(code) + ")"
    with pytest.raises(InputError, match=f'exit {code}') as error:
        with restic.capture(child(source), 5):
            pytest.fail('Nonzero exit must not yield evidence')
    assert 'private-secret-sentinel' not in str(error.value)


@pytest.mark.parametrize('source', [
    "import time; time.sleep(30)",
    "import os,time; os.close(1); time.sleep(30)",
    "import os; b=b'x'*65536\nwhile True: os.write(2,b)",
])
def test_timeout_kills_and_reaps_process(monkeypatch, source):
    created = []
    original = subprocess.Popen
    def start(*args, **kwargs):
        process = original(*args, **kwargs)
        created.append(process)
        return process
    monkeypatch.setattr(restic.subprocess, 'Popen', start)
    begin = time.monotonic()
    with pytest.raises(InputError, match='timed out'):
        with restic.capture(child(source), 0.2):
            pytest.fail('Timed out process must not yield evidence')
    assert time.monotonic() - begin < 5
    assert created[0].poll() is not None


def test_output_is_bounded_and_process_stopped():
    with pytest.raises(InputError, match='size limit'):
        with restic.capture(child("import os; b=b'x'*65536\nwhile True: os.write(1,b)"), 5, limit=1024):
            pytest.fail('Oversized output must not yield evidence')


def test_exact_size_limit_is_accepted():
    with restic.capture(child("import os; os.write(1,b'x'*1024)"), 5, limit=1024) as stream:
        assert len(stream.read()) == 1024


@pytest.mark.parametrize('timeout', [0, -1, float('inf'), float('nan'), 3601])
def test_invalid_timeout_never_starts_process(monkeypatch, timeout):
    monkeypatch.setattr(restic.subprocess, 'Popen', lambda *a, **k: pytest.fail('Invalid timeout contacted restic'))
    with pytest.raises(InputError):
        with restic.capture(['restic'], timeout):
            pass


@pytest.fixture
def recorded_capture(monkeypatch):
    calls = []
    @contextmanager
    def fake(command, timeout):
        calls.append(command)
        yield BytesIO((EX/'present.jsonl').read_bytes())
    monkeypatch.setattr(restic, 'capture', fake)
    return calls


def test_latest_scopes_host_and_ands_tags_without_shell(recorded_capture):
    catalog = restic.collect_catalog({'host':'demo-server', 'required_tags':['daily','docker']})
    assert recorded_capture == [['restic', '--no-lock', '--no-cache', 'ls', '--json', '--host=demo-server', '--tag=daily,docker', '--', 'latest']]
    assert catalog['capture']['completion_confirmed'] is True
    assert catalog['capture']['restic_exit_code'] == 0


def test_exact_id_is_unfiltered_and_matches_header(recorded_capture):
    restic.collect_catalog({'host':'demo-server'}, ID)
    assert recorded_capture[0][-2:] == ['--', ID]
    assert not any(arg.startswith('--host') for arg in recorded_capture[0])
    with pytest.raises(InputError, match='different snapshot ID'):
        restic.collect_catalog({'host':'demo-server'}, 'b'*64)


@pytest.mark.parametrize('identifier', ['latest', 'a'*8, 'A'*64, '../x', '--help', 'a'*64+':/backup'])
def test_ambiguous_id_never_contacts_restic(recorded_capture, identifier):
    with pytest.raises(InputError):
        restic.collect_catalog({'host':'demo-server'}, identifier)
    assert recorded_capture == []


def test_comma_tag_requires_explicit_id(recorded_capture):
    policy = {'host':'demo-server', 'required_tags':['literal,comma']}
    with pytest.raises(InputError, match='literal comma'):
        restic.collect_catalog(policy)
    assert recorded_capture == []
    restic.collect_catalog(policy, ID)


def test_tag_whitespace_is_not_silently_trimmed(recorded_capture):
    with pytest.raises(InputError, match='surrounding whitespace'):
        restic.collect_catalog({'host':'demo-server', 'required_tags':[' daily ']})
    assert recorded_capture == []


@pytest.mark.parametrize('binary', ['restic.cmd', 'RESTIC.BAT'])
def test_batch_executable_rejected(recorded_capture, binary):
    with pytest.raises(InputError, match='native restic'):
        restic.collect_catalog({'host':'demo-server'}, ID, executable=binary)
    assert recorded_capture == []


@pytest.mark.parametrize('payload', [b'', b'{bad json}', b'[]\n'])
def test_exit_zero_still_requires_valid_catalog(monkeypatch, payload):
    @contextmanager
    def fake(*args):
        yield BytesIO(payload)
    monkeypatch.setattr(restic, 'capture', fake)
    with pytest.raises(InputError):
        restic.collect_catalog({'host':'demo-server'})


def local_inputs(tmp_path):
    inventory = json.loads((EX/'inventory.json').read_text())
    inventory['captured_at'] = utc_now()
    inv = tmp_path/'inventory.json'
    inv.write_text(json.dumps(inventory), encoding='utf-8')
    return ['verify', '--inventory', str(inv), '--policy', str(EX/'policy.json'), '--latest']


def test_cli_capture_failure_creates_no_report(monkeypatch, tmp_path, capsys):
    def fail(*args):
        raise InputError('Restic ls failed (exit 12); output discarded')
    monkeypatch.setattr(cli, 'collect_catalog', fail)
    target = tmp_path/'report.html'
    assert cli.main([*local_inputs(tmp_path), '--format', 'html', '--output', str(target)]) == 2
    assert not target.exists() and not capsys.readouterr().out


def test_cli_existing_output_prevents_repository_access(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, 'collect_catalog', lambda *a: pytest.fail('Existing output contacted restic'))
    target = tmp_path/'report.html'
    target.write_text('existing report')
    assert cli.main([*local_inputs(tmp_path), '--output', str(target)]) == 2
    assert target.read_text() == 'existing report'


def test_cli_invalid_policy_prevents_repository_access(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, 'collect_catalog', lambda *a: pytest.fail('Invalid policy contacted restic'))
    args = local_inputs(tmp_path)
    policy = tmp_path/'bad-policy.json'
    policy.write_text('{"version": 1, "host": "wrong-host"}')
    args[4] = str(policy)
    assert cli.main(args) == 2


def test_reports_distinguish_capture_completion(recorded_capture):
    inventory = json.loads((EX/'inventory.json').read_text())
    policy = json.loads((EX/'policy.json').read_text())
    catalog = restic.collect_catalog(policy, ID)
    report = analyze(inventory, catalog, policy, '2026-09-22T13:00:00Z')
    assert report['exit_code'] == 0
    assert 'completed successfully' in html_report(report)
    assert 'completed successfully' in text_report(report)
    del catalog['capture']
    offline = analyze(inventory, catalog, policy, '2026-09-22T13:00:00Z')
    assert offline['exit_code'] == 0
    assert offline['capture']['completion_confirmed'] is False
    assert 'was not observed' in html_report(offline)


def test_cli_successful_capture_preserves_unknown_identity(recorded_capture, tmp_path, capsys):
    args = local_inputs(tmp_path)
    inventory = json.loads(Path(args[2]).read_text())
    inventory['host'] = 'another-host'
    Path(args[2]).write_text(json.dumps(inventory))
    policy = json.loads((EX/'policy.json').read_text())
    policy['host'] = 'another-host'
    path = tmp_path/'policy.json'
    path.write_text(json.dumps(policy))
    args[4] = str(path)
    assert cli.main([*args, '--format', 'json']) == 2
    report = json.loads(capsys.readouterr().out)
    assert report['capture']['completion_confirmed'] is True
    assert any(item['code'] == 'BSU02' for item in report['unknowns'])
