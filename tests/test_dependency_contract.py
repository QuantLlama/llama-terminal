"""Dependency declarations and extracted bootstrap functions; no real installs/services."""
import ast
import builtins
import io
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
REMOVED = {'transformers', 'xgboost'}
GPU_DEPS = [
    'rich', 'pandas', 'numpy<2', 'yfinance', 'matplotlib',
    'scikit-learn', 'statsmodels', 'requests', 'joblib', 'python-dotenv',
    'supabase', 'ccxt', 'MetaTrader5', 'pytz', 'python-dateutil',
    'websockets', 'ta-lib', 'seaborn', 'mplfinance', 'cryptography',
]


def extract(path, names, namespace):
    """Compile only named function definitions, never module-level dispatch/imports."""
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == set(names)
    def reject_import(*args, **kwargs):
        raise AssertionError('Extracted function attempted a real import: ' + str(args[0]))
    namespace['__builtins__'] = dict(vars(builtins), __import__=reject_import)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def test_requirements_no_longer_declare_unused_training_packages():
    lines = (ROOT / 'requirements.txt').read_text().splitlines()
    names = {line.split('==')[0].lower() for line in lines if line and not line.startswith('#')}
    assert not names & REMOVED
    assert {'torch', 'torchvision', 'scikit-learn', 'statsmodels', 'vectorbt', 'gym'} <= names


def test_bootstrap_and_build_have_no_removed_package_declarations():
    for relative in ('run.py', 'scripts/build_backend.py'):
        tree = ast.parse((ROOT / relative).read_text())
        declarations = {node.value.split('.')[0] for node in ast.walk(tree)
                        if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        assert not declarations & REMOVED, relative


@pytest.mark.parametrize('platform', ['linux', 'win32'])
@pytest.mark.parametrize('mode', ['success', 'fallback', 'venv-failure', 'torch-failure', 'no-python'])
def test_gpu_bootstrap_preserves_install_policy(platform, mode):
    calls, messages, markers = [], [], []
    marker = io.StringIO()
    marker.close = lambda: None
    def run(command, **kwargs):
        calls.append((command, kwargs))
        if mode == 'fallback' and kwargs.get('check'):
            raise subprocess.CalledProcessError(1, command)
        failed = (mode == 'venv-failure' and len(calls) == 1 or
                  mode == 'torch-failure' and len(calls) == 2)
        return SimpleNamespace(returncode=int(failed), stderr='stub error')
    def open_marker(path, mode):
        markers.append((path, mode))
        return marker
    root = '/synthetic/gpu'
    namespace = extract(ROOT / 'run.py', ['_install_gpu_env'], {
        'sys': SimpleNamespace(platform=platform, executable='/synthetic/python',
                               frozen=mode == 'no-python'),
        'os': SimpleNamespace(path=os.path, makedirs=Mock()),
        'shutil': SimpleNamespace(which=lambda name: None),
        'subprocess': SimpleNamespace(run=run, CalledProcessError=subprocess.CalledProcessError),
        'console': SimpleNamespace(print=lambda *args: messages.append(args)),
        'GPU_ENV_DIR': root, 'GPU_MARKER': root + '/.gpu_ready',
        '_sync_sources': Mock(), 'open': open_marker,
    })
    result = namespace['_install_gpu_env']()
    if mode == 'no-python':
        assert result is False and calls == [] and markers == []
        namespace['os'].makedirs.assert_not_called()
    else:
        namespace['os'].makedirs.assert_called_once_with(root, exist_ok=True)
        assert calls[0] == (['/synthetic/python', '-m', 'venv', root],
                            {'capture_output': True, 'text': True})
        pip = root + ('/Scripts/pip.exe' if platform == 'win32' else '/bin/pip')
        if mode != 'venv-failure':
            assert calls[1] == ([pip, 'install', 'torch==2.2.2', '--index-url',
                                 'https://download.pytorch.org/whl/cu121'],
                                {'capture_output': False})
        if mode in {'success', 'fallback'}:
            assert result is True
            assert calls[2] == ([pip, 'install'] + GPU_DEPS,
                                {'capture_output': True, 'check': True})
            expected = [([pip, 'install', dep], {'capture_output': True}) for dep in GPU_DEPS]
            assert calls[3:] == (expected if mode == 'fallback' else [])
            assert markers == [(root + '/.gpu_ready', 'w')] and marker.getvalue() == 'ok'
            namespace['_sync_sources'].assert_called_once_with()
            assert messages[-1] == ('\n[bold green]✅ ¡Entorno GPU instalado exitosamente![/bold green]',)
        else:
            assert result is False and markers == []
            assert len(calls) == (1 if mode == 'venv-failure' else 2)
    if not result:
        namespace['_sync_sources'].assert_not_called()
        assert not any('exitosamente' in str(message) for message in messages)


@pytest.mark.parametrize('platform', ['linux', 'win32'])
@pytest.mark.parametrize('frozen', [False, True])
@pytest.mark.parametrize('base', ['venv', 'custom'])
def test_existing_venv_path_options(platform, frozen, base):
    namespace = extract(ROOT / 'run.py', ['get_venv_python'], {
        'sys': SimpleNamespace(platform=platform, frozen=frozen,
                               executable='/synthetic/app', _MEIPASS='/synthetic/frozen'),
        'os': os, '__file__': '/synthetic/run.py',
    })
    expected_base = 'venv_linux' if base == 'venv' and platform != 'win32' else base
    assert namespace['get_venv_python'](base) == os.path.join(
        '/synthetic/frozen' if frozen else '/synthetic', expected_base,
        'Scripts' if platform == 'win32' else 'bin',
        'python.exe' if platform == 'win32' else 'python')


def test_packaging_build_graph_without_dependency_collection(capsys):
    """Extracted orchestration uses fake validation, staging and target builders only."""
    targets, checks, outputs = [], [], []
    process = Mock()
    namespace = extract(ROOT / 'scripts/build_backend.py', ['build'], {
        'Path': Path, 'ROOT': '/synthetic',
        'check': checks.append, 'new_output': lambda root, path: outputs.append((root, path)),
        'subprocess': SimpleNamespace(run=process),
        'sys': SimpleNamespace(executable='/synthetic/python'),
        'os': os, 'build_target': lambda *args, **kwargs: targets.append((args, kwargs)),
        'FULL_DATA_ITEMS': [], 'FULL_BINARY_ITEMS': [], 'FULL_HIDDEN_IMPORTS': [],
        'BROWSER_HIDDEN_IMPORTS': ['requests'],
    })
    namespace['build']()
    assert checks == [Path('/synthetic')]
    assert outputs == [(Path('/synthetic'), path) for path in
                       ('build/obf_src', 'build/pyinstaller_dist', 'build/pyinstaller_work', 'build/specs')]
    process.assert_called_once_with(
        ['/synthetic/python', '/synthetic/scripts/obfuscate.py'], check=True)
    assert namespace['FULL_DATA_ITEMS'] == [('/synthetic/build/obf_src/' + name, dest)
        for name, dest in [('src', 'src'), ('images', 'images'), ('train.py', '.'),
                           ('run.py', '.'), ('package.json', '.')]]
    assert namespace['FULL_BINARY_ITEMS'] == []
    assert targets == [
        (('start_api.py', 'backend'), {'hide_console': True, 'icon_path': '/synthetic/images/QuantumLLama.ico'}),
        (('run.py', 'Trainer'), {'hide_console': False, 'icon_path': '/synthetic/images/QuantumLLama_Trainer.ico'}),
        (('browser_launcher.py', 'BrowserMode'), {'hide_console': True,
            'hidden_imports': ['requests'], 'data_items': [], 'binary_items': [],
            'icon_path': '/synthetic/images/QuantumLLama_Browser.ico'}),
    ]
    assert capsys.readouterr() == ('\n[SUCCESS] All production targets built.\n', '')
