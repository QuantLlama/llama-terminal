"""Public packaging checks use synthetic projects, never owner runtime data."""
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def cli(script, *args):
    with tempfile.TemporaryDirectory() as sandbox:
        isolated = Path(sandbox)
        shutil.copytree(ROOT / 'scripts', isolated / 'scripts',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT / 'build_dist.py', isolated / 'build_dist.py')
        return subprocess.run([sys.executable, str(isolated / script), *map(str, args)],
                              cwd=isolated, capture_output=True, text=True, timeout=20)


def fixture(root):
    package = json.loads((ROOT / 'package.json').read_text())
    (root / 'package.json').write_text(json.dumps(package))
    files = ['src/services/auth.py', 'src/platform/web/index.html',
             'src/platform/web/components/App.js', 'images/QuantumLLama.png',
             'src/engine/config/config.yaml', 'start_api.py', 'train.py', 'run.py',
             'browser_launcher.py', '.env', 'src/config/mt5_accounts.json',
             'src/config/live_config.json', 'src/config/symbols_mt5.json',
             'src/services/private.key', 'src/services/auth.cpython-311.so',
             'src/platform/web/.env', 'src/platform/web/accounts.json',
             'outputs/model.pkl', 'outputs/private.html']
    for name in files:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('SENTINEL' if name not in files[:9] else '# safe')
    return {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_stage_allowlist_and_source_preservation():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        before = fixture(root)
        result = cli('scripts/obfuscate.py', '--project-root', root, '--stage-only')
        assert (result.returncode, result.stderr) == (0, '')
        assert result.stdout == 'Safe staging complete: build/obf_src\n'
        stage = root / 'build/obf_src'
        assert (stage / 'src/services/auth.py').read_text() == '# safe'
        assert (stage / 'src/platform/web/index.html').exists()
        assert (stage / 'images/QuantumLLama.png').exists()
        assert json.loads((stage / 'src/config/live_config.json').read_text()) == {}
        assert json.loads((stage / 'src/config/symbols_mt5.json').read_text()) == {
            'Futures': {}, 'Stocks': {}, 'ETF': {}, 'Crypto': {}}
        assert set(json.loads((stage / 'package.json').read_text())) == {'name', 'version'}
        assert not any(b'SENTINEL' in p.read_bytes() for p in stage.rglob('*') if p.is_file())
        assert all((root / p).read_bytes() == content for p, content in before.items())
        second = cli('scripts/obfuscate.py', '--project-root', root, '--stage-only')
        assert second.returncode == 1
        assert second.stdout == ''
        assert second.stderr == 'Packaging error: output already exists: build/obf_src\n'


def test_symlink_output_rejected_without_writes():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
        root = Path(tmp)
        before = fixture(root)
        (root / 'build').symlink_to(outside, target_is_directory=True)
        result = cli('scripts/obfuscate.py', '--project-root', root, '--stage-only')
        assert (result.returncode, result.stdout, result.stderr) == (
            1, '', 'Packaging error: symlink not allowed: build\n')
        assert not list(Path(outside).iterdir())
        assert all((root / p).read_bytes() == data for p, data in before.items())


def test_source_symlink_rejected_before_staging():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixture(root)
        (root / 'src/services/linked.py').symlink_to(root / 'start_api.py')
        result = cli('scripts/obfuscate.py', '--project-root', root, '--stage-only')
        assert (result.returncode, result.stdout, result.stderr) == (
            1, '', 'Packaging error: symlink not allowed: src/services/linked.py\n')
        assert not (root / 'build').exists()
        assert (root / 'src/services/linked.py').is_symlink()


def test_manifest_rejects_unsafe_resource_graph():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixture(root)
        result = cli('scripts/check_build_inputs.py', '--project-root', root)
        assert (result.returncode, result.stdout, result.stderr) == (
            0, 'Packaging inputs OK\n', '')
        package = json.loads((root / 'package.json').read_text())
        package['build']['extraResources'].append({'from': 'outputs', 'to': 'outputs'})
        (root / 'package.json').write_text(json.dumps(package))
        before = (root / 'package.json').read_bytes()
        result = cli('scripts/check_build_inputs.py', '--project-root', root)
        assert (result.returncode, result.stdout, result.stderr) == (
            1, '', 'Packaging error: unexpected Electron resource graph\n')
        assert (root / 'package.json').read_bytes() == before
        assert not (root / 'build').exists()


def test_bytenode_stages_only_approved_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'scripts').mkdir()
        shutil.copy2(ROOT / 'scripts/build_js.js', root / 'scripts/build_js.js')
        source = root / 'electron'
        source.mkdir()
        names = ['index.js', 'main.js', 'preload.js', 'preload-loader.js',
                 'health.js', 'splash.html', 'trial-expired.html', '.env',
                 'accounts.json', 'private.key', 'main.jsc']
        for name in names:
            (source / name).write_text(name)
        before = {p.name: p.read_bytes() for p in source.iterdir()}
        module = root / 'node_modules/bytenode'
        module.mkdir(parents=True)
        (module / 'index.js').write_text(
            "exports.compileFile = async o => require('fs').writeFileSync(o.output, 'compiled');")
        result = subprocess.run(['node', str(root / 'scripts/build_js.js')],
                                capture_output=True, text=True, timeout=20)
        assert result.returncode == 0 and result.stderr == ''
        assert {p.name: p.read_bytes() for p in source.iterdir()} == before
        staged = root / 'build/electron'
        assert {p.name for p in staged.iterdir()} == set(names[:7] + ['main.jsc', 'preload.jsc'])
        assert (staged / 'main.jsc').read_text() == 'compiled'


def test_backend_refuses_existing_output_before_loading_compilers():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        before = fixture(root)
        (root / 'build/pyinstaller_dist').mkdir(parents=True)
        result = cli('scripts/build_backend.py', '--project-root', root)
        assert (result.returncode, result.stdout, result.stderr) == (
            1, '', 'Packaging error: output already exists: build/pyinstaller_dist\n')
        assert not (root / 'build/obf_src').exists()
        assert all((root / p).read_bytes() == data for p, data in before.items())


def test_help_and_legacy_wrapper():
    for script in ['scripts/build_backend.py', 'scripts/obfuscate.py', 'build_dist.py',
                   'scripts/check_build_inputs.py']:
        result = cli(script, '--help')
        assert result.returncode == 0
        assert result.stderr == ''
        assert 'usage:' in result.stdout
    assert cli('build_dist.py', '--help').stdout == cli('scripts/build_backend.py', '--help').stdout
    result = cli('build_dist.py', '--cleanup-only')
    assert result.returncode == 2
    assert 'unrecognized arguments: --cleanup-only' in result.stderr
