"""Stdlib-only packaging policy and input check; never reads runtime stores."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINTS = ('start_api.py', 'train.py', 'run.py', 'browser_launcher.py')
ASSET_SUFFIXES = {'.js', '.html', '.css', '.svg', '.png', '.jpg', '.jpeg', '.ico',
                  '.woff', '.woff2', '.ttf', '.mp3', '.wav', '.txt', '.md'}
IMAGE_NAMES = {'AlgoLab.png', 'MiAvatar.png', 'QuantumLLama.ico', 'QuantumLLama.png',
               'QuantumLLama_Browser.ico', 'QuantumLLama_Browser.png',
               'QuantumLLama_Trainer.ico', 'QuantumLLama_Trainer.png',
               'agentellama.png', 'logo2.ico', 'logobacktest.png', 'logonbm.png', 'puntoicoma.png'}
RESOURCES = [
    {'from': 'build/pyinstaller_dist', 'filter':
     ['backend', 'Trainer', 'BrowserMode', 'backend.exe', 'Trainer.exe', 'BrowserMode.exe'], 'to': '.'},
    *({'from': 'build/obf_src/' + name, 'to': name} for name in
      ('src/indicators', 'src/algorithms', 'src/features/indicators.py',
       'src/live', 'src/doctecnicaalgos')),
]
ELECTRON_FILES = [
    {'from': 'build/electron', 'to': 'electron', 'filter':
     ['index.js', 'main.js', 'main.jsc', 'preload.js', 'preload.jsc',
      'preload-loader.js', 'health.js', 'splash.html', 'trial-expired.html']},
    {'from': 'images', 'to': 'images', 'filter': ['QuantumLLama.ico', 'QuantumLLama.png']},
    'package.json', 'node_modules/**/*', '!**/.env{,.*}',
    '!**/*.{key,pem,p12,pfx}', '!**/*accounts*.json', '!**/outputs/**',
]


def parser(description):
    result = argparse.ArgumentParser(description=description)
    result.add_argument('--project-root', type=Path, default=ROOT,
                        help='Project input root (default: repository root)')
    return result


def no_symlinks(root, relative):
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f'symlink not allowed: {path.relative_to(root)}')
    return path


def new_output(root, relative):
    """Only fresh, fixed build children are writable; never remove an old build."""
    if relative not in ('build/obf_src', 'build/pyinstaller_dist',
                        'build/pyinstaller_work', 'build/electron', 'build/specs'):
        raise ValueError('output must be an isolated build directory')
    path = no_symlinks(root, relative)
    if path.exists():
        raise ValueError(f'output already exists: {relative}')
    return path


def check(root):
    package = json.loads(no_symlinks(root, 'package.json').read_text())
    if package['build']['extraResources'] != RESOURCES:
        raise ValueError('unexpected Electron resource graph')
    if package['build']['files'] != ELECTRON_FILES:
        raise ValueError('unexpected Electron file graph')
    no_symlinks(root, 'build')
    return package


def collect_inputs(root):
    """Code, static UI and one engine schema only; no configured runtime data."""
    selected = []
    for base in ('src', 'images'):
        folder = no_symlinks(root, base)
        if not folder.is_dir():
            raise ValueError(f'missing input directory: {base}')
        for path in folder.rglob('*'):
            rel = path.relative_to(root)
            parts = rel.parts
            if any(p.startswith('.') or p in {'__pycache__', '__tests__', 'node_modules',
                       'outputs', 'accounts', 'keys', 'config'} for p in parts):
                # Engine config is the only source config, not a runtime store.
                if rel.as_posix() != 'src/engine/config/config.yaml':
                    continue
            if base == 'images' and path.name not in IMAGE_NAMES:
                continue
            if path.suffix != '.py' and any(word in path.stem.lower() for word in
                    ('account', 'secret', 'credential', 'private', 'token', 'key')):
                continue
            allowed = (base == 'src' and path.suffix == '.py') or (
                ('src/platform/web' in rel.as_posix() or base == 'images'
                 or 'src/doctecnicaalgos' in rel.as_posix())
                and path.suffix.lower() in ASSET_SUFFIXES)
            if allowed or rel.as_posix() in ('src/engine/config/config.yaml',
                                              'src/live/live_dashboard.html'):
                no_symlinks(root, rel)
                if path.is_file():
                    selected.append(rel)
    for name in ENTRY_POINTS:
        if not no_symlinks(root, name).is_file():
            raise ValueError(f'missing entry point: {name}')
        selected.append(Path(name))
    return selected


def stage(root):
    package = check(root)
    output = new_output(root, 'build/obf_src')
    inputs = collect_inputs(root)  # Validate everything before writing anything.
    output.mkdir(parents=True)
    for rel in inputs:
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    config = output / 'src/config'
    config.mkdir(parents=True, exist_ok=True)
    defaults = {'live_config.json': {}, 'brokers.json': {}}
    defaults.update({f'symbols{suffix}.json': dict.fromkeys(
        ('Futures', 'Stocks', 'ETF', 'Crypto'), {})
        for suffix in ('', '_mt5', '_crypto', '_nt8', '_tradovate')})
    for name, value in defaults.items():
        (config / name).write_text(json.dumps(value) + '\n')
    (output / 'package.json').write_text(json.dumps(
        {key: package[key] for key in ('name', 'version')}) + '\n')
    return output


def main():
    args = parser(__doc__).parse_args()
    try:
        check(args.project_root.resolve())
        collect_inputs(args.project_root.resolve())
    except (ValueError, KeyError, OSError) as exc:
        print(f'Packaging error: {exc}', file=sys.stderr)
        return 1
    print('Packaging inputs OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
