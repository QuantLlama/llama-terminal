# Desktop distribution

## Supported entry points

The authoritative pipeline is `scripts/build_backend.py` (safe staging → Cython →
PyInstaller), then `scripts/build_js.js` (bytenode), then electron-builder.
Public npm scripts `start`, `obfuscate-backend`, `obfuscate-js`, `pack`, and `dist`
retain their names and commands. App ID, product name, NSIS, AppImage and deb
configuration are unchanged. Configuration is not proof that an installer works.

`python build_dist.py` is now a compatibility wrapper for the backend builder,
not a second Nuitka distribution. `python build_dist.py --help` safely shows the
backend help. The old `--cleanup-only` option is intentionally rejected with exit
2: deleting development files is not part of a distribution build. Previously
`--help` was not parsed and could start a destructive build; that behavior is
intentionally retired. Both Python builders accept `--project-root PATH`.

## Check before building

From a clean, isolated checkout, using its prepared Python environment:

```sh
python scripts/check_build_inputs.py --project-root .
python scripts/obfuscate.py --project-root . --stage-only
```

The first command checks the exact Electron file/resource graph and collects
allowlisted inputs without creating output. The second actually copies those
inputs to a **fresh** `build/obf_src`, without compiling or installing anything.
Do not run the full pipeline in that same staging probe checkout: existing build
outputs are rejected, not cleaned. Use another fresh isolated checkout instead.
No output override accepts arbitrary directories. Symlink output paths and copied
symlink inputs are rejected. Existing binaries, virtual environments and owner
configuration are never disposable build inputs.

## Publishable inputs

- Python source, approved web/static extensions, explicit branding images,
  `src/live/live_dashboard.html`, technical documentation, and the engine YAML schema.
- Generated empty live/broker settings and empty per-platform symbol maps, never
  the owner's configured files. Account managers initialize runtime stores later.
- Root PyInstaller metadata contains only `name` and `version` from package.json,
  supporting the frozen product-version loader.
- Electron resources come only from sanitized staging and exact backend executable
  names, not `outputs`, raw `src/live`, or arbitrary binary wildcard matches.
  `electron/health.js` is explicitly included in staged Electron application files.

`.env`, account JSON, encryption keys, databases, saved models, configured outputs,
backups and pre-existing native extensions are not release seed content. Runtime
Supabase/auth settings must be supplied via the environment; never add them to
package metadata. The allowlist is not a substitute for source secret scanning or
independent PR #28 security approval. Node production dependencies are still
resolved by electron-builder; audit the lockfile/dependency tree before release.

## Actual build (later, isolated and parent-controlled)

Use `npm run pack` for an unpacked package or `npm run dist` for installers only
in a fresh isolated checkout with no prior build children. Prerequisites include
prepared Python/Node dependencies, Cython/native compiler, PyInstaller hooks,
existing branding icons, Electron-compatible bytenode, and platform packaging
tools. The builder does not install Cython or regenerate source icons. No hidden
imports or transformer/XGBoost requirements were removed in this slice.

Cython already used `_cython_tmp` under build staging before this change (#14);
there was no demonstrated current source-output bug there. Compilation now also
uses that directory as its working directory, excludes stale source native files,
and refuses reused staging. Bytenode output moves from `electron/*.jsc` to
`build/electron/*.jsc`; source files and old bytecode remain untouched.

NSIS requires a Windows-capable build environment; Linux AppImage/deb require
their respective tools. Neither Linux runtime compatibility nor any actual
installer has been validated here. No build or deployment authorizes bypassing
the unresolved PR #28 independent security proof.

## Browser launcher

`browser_launcher.py` resolves the packaged backend name per platform: `backend.exe`
on Windows and `backend` elsewhere, matching what `scripts/build_backend.py` emits.
The hidden-console creation flag is Windows-only, and a missing or non-executable
backend fails before any browser window opens. On Windows the Chrome app-mode lookup
uses the registry; other platforms fall back to the default browser without reporting
a fake registry error. This is source-level compatibility covered by stubbed tests, not
proof that a Linux AppImage or deb runs correctly.
