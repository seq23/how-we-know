"""Preview job paths; prepare a runner twice against a local Git remote only."""
import os
import plistlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
installer = ROOT / 'bin/loop-install-launchd.sh'
with tempfile.TemporaryDirectory() as td:
    temp = Path(td)
    runner = temp / 'runner'
    runtime = temp / 'runtime'; runtime.mkdir()
    for name in ['.venv', '.venv-tts', '.secrets']: (runtime / name).mkdir()
    env = {**os.environ, 'HWK_RUNNER_ROOT': str(runner), 'HWK_RUNTIME_SOURCE': str(runtime)}
    for name in ['batch', 'nightquit', 'batch-resume', 'food', 'food-resume', 'backfill']:
        raw = subprocess.check_output(['bash', str(installer), '--plist', name], env=env)
        doc = plistlib.loads(raw)
        assert str(runner) in doc['ProgramArguments'][-1], doc
        assert str(ROOT) not in doc['ProgramArguments'][-1], doc
    # Copy the installer into a tiny local source checkout. No launchd commands.
    source = temp / 'source'; source.mkdir()
    (source / 'bin').mkdir()
    script = source / 'bin' / installer.name
    script.write_bytes(installer.read_bytes())
    def git(*args, cwd=source):
        return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.STDOUT)
    git('init', '-b', 'main')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'initial')
    remote = temp / 'remote.git'
    git('clone', '--bare', str(source), str(remote))
    git('remote', 'add', 'origin', str(remote))
    subprocess.run(['bash', str(script), '--prepare-runner'], env=env, check=True, capture_output=True)
    (source / 'new.txt').write_text('updated')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'update')
    git('push', 'origin', 'main')
    subprocess.run(['bash', str(script), '--prepare-runner'], env=env, check=True, capture_output=True)
    assert (runner / 'new.txt').read_text() == 'updated'
    for name in ['.venv', '.venv-tts', '.secrets']:
        assert (runner / name).resolve() == (runtime / name).resolve()
    assert not git('status', '--porcelain', cwd=runner).strip()
print('PASS: six job paths; isolated clone creation and fast-forward update')
