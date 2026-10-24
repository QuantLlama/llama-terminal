"""Exercise setup only in disposable projects, with no real Python/pip installs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "setup_env.sh"
HELP = (
    "Usage: ./setup_env.sh [--recreate | --help]\n"
    "Create or reuse venv_linux; fall back to XDG_DATA_HOME/quantumllama.\n"
    "--recreate  Replace only a validated, owned virtual environment.\n"
    "--help      Show this help without changing files.\n"
)
SHIM = r'''#!/bin/bash
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
    printf 'create:%s\n' "$3" >> "$CALLS"
    [ "$CREATE_FAIL" != all ] || exit 9
    [ "$CREATE_FAIL" != local ] || { [ "$3" != ./venv_linux ] && [ "$3" != venv_linux ]; } || exit 9
    mkdir -p "$3/bin"
    printf 'home = fake\n' > "$3/pyvenv.cfg"
    printf '# fake activation\n' > "$3/bin/activate"
    cp "$SHIM" "$3/bin/python"
    chmod +x "$3/bin/python"
elif [ "$1" = "-m" ] && [ "$2" = pip ]; then
    printf 'pip:%s\n' "${*:3}" >> "$CALLS"
    [ "$PIP_FAIL" != "$3" ] || exit 7
elif [ "$1" = "-c" ]; then
    exit "${INVALID_PYTHON:-0}"
else
    exit 99
fi
'''


@pytest.fixture
def project():
    # TemporaryDirectory also removes scratch on failures; never use the owner's HOME.
    with tempfile.TemporaryDirectory(prefix="setup-env-") as temp:
        root = Path(temp)
        work = root / "project with spaces"
        work.mkdir()
        shutil.copy2(SCRIPT, work / "setup_env.sh")
        (work / "requirements.txt").write_text("fake-package\n")
        tools = root / "tools"
        tools.mkdir()
        shim = tools / "python3"
        shim.write_text(SHIM)
        shim.chmod(0o755)
        pip = tools / "pip"
        pip.write_text('#!/bin/bash\nexec "$SHIM" -m pip "$@"\n')
        pip.chmod(0o755)
        home = root / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(root / "data with spaces"),
                   PATH=f"{tools}:/usr/bin:/bin", CALLS=str(root / "calls"),
                   SHIM=str(shim), CREATE_FAIL="", PIP_FAIL="", INVALID_PYTHON="0",
                   TMPDIR=str(root))
        yield work, env


def run(project, *args):
    work, env = project
    return subprocess.run(["/bin/bash", "setup_env.sh", *args], cwd=work,
                          env=env, text=True, capture_output=True, timeout=5)


def calls(project):
    path = Path(project[1]["CALLS"])
    return path.read_text().splitlines() if path.exists() else []


def snapshot(root):
    return {str(p.relative_to(root)): ("link", os.readlink(p)) if p.is_symlink()
            else ("file", p.read_bytes()) if p.is_file() else ("dir",)
            for p in root.rglob("*")}


def assert_error(result, message, code=1):
    assert (result.returncode, result.stdout, result.stderr) == (code, "", message + "\n")


def success(path="./venv_linux", requirements=True, reuse=True):
    message = (f"Reusing virtual environment: {path}\n" if reuse else
               "Virtual environment creado localmente con éxito.\n" if path == "./venv_linux" else
               f"Created virtual environment: {path}\n")
    return ("Setting up environment...\n" + message
            + ("Requirements installed.\n" if requirements else "requirements.txt not found.\n")
            + "Setup complete.\n")


def test_clean_local_setup_preserves_baseline_output(project):
    result = run(project)
    assert (result.returncode, result.stdout, result.stderr) == (
        0, "Setting up environment...\n"
        "Virtual environment creado localmente con éxito.\n"
        "Requirements installed.\nSetup complete.\n", "")


@pytest.mark.parametrize("reuse", [False, True])
def test_local_setup_ignores_unused_symlinked_fallback(project, reuse):
    work, env = project
    if reuse:
        assert run(project).returncode == 0
    Path(env["XDG_DATA_HOME"]).symlink_to(Path(env["HOME"]))
    before = snapshot(Path(env["HOME"]))
    result = run(project)
    message = ("Reusing virtual environment: ./venv_linux\n" if reuse else
               "Virtual environment creado localmente con éxito.\n")
    assert (result.returncode, result.stdout, result.stderr) == (
        0, "Setting up environment...\n" + message
        + "Requirements installed.\nSetup complete.\n", "")
    assert snapshot(Path(env["HOME"])) == before


def test_create_and_repeat_preserve_user_files(project):
    work, _ = project
    assert (run(project).returncode, calls(project)) == (
        0, ["create:./venv_linux", "pip:install --upgrade pip", "pip:install -r requirements.txt"])
    sentinel = work / "venv_linux" / "user file"
    sentinel.write_text("keep me")
    before = snapshot(work)
    result = run(project)
    assert (result.returncode, result.stdout, result.stderr) == (0, success(), "")
    assert snapshot(work) == before
    assert calls(project).count("create:./venv_linux") == 1
    assert (work / ".venv_linux_path").read_text() == "./venv_linux\n"


@pytest.mark.parametrize("args,message,code", [
    (("--help",), HELP, 0),
    (("--unknown",), "Error: unknown argument: --unknown\n", 2),
    (("--recreate", "--unknown"), "Error: unknown argument: --unknown\n", 2),
    (("--help", "--unknown"), "Error: unknown argument: --unknown\n", 2),
])
def test_options_have_no_side_effects(project, args, message, code):
    work, _ = project
    (work / "venv_linux").mkdir()
    (work / "venv_linux" / "precious").write_text("preserve")
    before = snapshot(work.parent)
    result = run(project, *args)
    assert (result.returncode, result.stdout, result.stderr) == (
        code, message if code == 0 else "", message if code else "")
    assert snapshot(work.parent) == before


@pytest.mark.parametrize("recreate", [False, True])
@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "broken-link", "incomplete", "invalid-python"])
def test_reject_unsafe_targets_without_mutation(project, recreate, kind):
    work, env = project
    target = work / "venv_linux"
    if kind in ("incomplete", "invalid-python"):
        assert run(project).returncode == 0
        if kind == "incomplete":
            (target / "pyvenv.cfg").rename(target / "not-a-venv")
        else:
            env["INVALID_PYTHON"] = "1"
    elif kind == "file":
        target.write_text("preserve")
    elif kind in ("symlink", "broken-link"):
        outside = work.parent / "outside"
        if kind == "symlink":
            outside.mkdir()
            (outside / "precious").write_text("preserve")
        target.symlink_to(outside)
    else:
        target.mkdir()
        (target / "precious").write_text("preserve")
    before = snapshot(work.parent)
    result = run(project, *(("--recreate",) if recreate else ()))
    assert_error(result, "Error: refusing unsafe virtual environment: ./venv_linux")
    assert snapshot(work.parent) == before


def test_recreate_requires_opt_in_and_replaces_valid_environment(project):
    work, _ = project
    assert run(project).returncode == 0
    sentinel = work / "venv_linux" / "user file"
    sentinel.write_text("explicitly disposable")
    result = run(project, "--recreate")
    assert (result.returncode, result.stdout, result.stderr) == (0, success(reuse=False), "")
    assert not sentinel.exists()
    assert calls(project).count("create:./venv_linux") == 2


def test_recreate_does_not_remove_second_environment_after_local_failure(project):
    work, env = project
    env["CREATE_FAIL"] = "local"
    assert run(project).returncode == 0
    fallback = Path(env["XDG_DATA_HOME"]) / "quantumllama/venv_linux"
    sentinel = fallback / "user file"
    sentinel.write_text("keep unselected environment")
    (work / ".venv_linux_path").write_text("./venv_linux\n")
    env["CREATE_FAIL"] = ""
    assert run(project).returncode == 0
    env["CREATE_FAIL"] = "local"
    before = snapshot(fallback)
    result = run(project, "--recreate")
    assert (result.returncode, result.stdout, result.stderr) == (0, success(str(fallback)), "")
    assert snapshot(fallback) == before


@pytest.mark.parametrize("xdg", [True, False])
def test_fallback_is_portable_and_reused(project, xdg):
    work, env = project
    env["CREATE_FAIL"] = "local"
    if not xdg:
        env.pop("XDG_DATA_HOME")
    target = Path(env.get("XDG_DATA_HOME", env["HOME"] + "/.local/share")) / "quantumllama/venv_linux"
    result = run(project)
    assert (result.returncode, result.stdout, result.stderr) == (0, success(str(target), reuse=False), "")
    (target / "user file").write_text("keep")
    before = snapshot(work), snapshot(target)
    previous_calls = calls(project)
    result = run(project)
    assert (result.returncode, result.stdout, result.stderr) == (0, success(str(target)), "")
    assert (snapshot(work), snapshot(target)) == before
    assert calls(project) == previous_calls + ["pip:install --upgrade pip", "pip:install -r requirements.txt"]
    assert calls(project).count("create:./venv_linux") == 1
    assert (work / ".venv_linux_path").read_text() == str(target) + "\n"


@pytest.mark.parametrize("kind", ["pointer", "pointer-symlink", "fallback-symlink"])
def test_reject_unsafe_routing(project, kind):
    work, env = project
    if kind == "pointer":
        (work / ".venv_linux_path").write_text(str(work.parent) + "\n")
        message = "Error: invalid .venv_linux_path."
    elif kind == "pointer-symlink":
        (work / ".venv_linux_path").symlink_to(work / "requirements.txt")
        message = "Error: invalid .venv_linux_path."
    else:
        Path(env["XDG_DATA_HOME"]).symlink_to(Path(env["HOME"]))
        (work / ".venv_linux_path").write_text(
            env["XDG_DATA_HOME"] + "/quantumllama/venv_linux\n")
        message = f"Error: refusing unsafe virtual environment: {env['XDG_DATA_HOME']}/quantumllama/venv_linux"
    before = snapshot(work.parent)
    result = run(project, "--recreate")
    assert_error(result, message)
    assert snapshot(work.parent) == before


def test_failed_local_creation_rejects_symlinked_fallback(project):
    work, env = project
    Path(env["XDG_DATA_HOME"]).symlink_to(Path(env["HOME"]))
    env["CREATE_FAIL"] = "local"
    before = snapshot(work), snapshot(Path(env["HOME"]))
    result = run(project)
    assert_error(result, "Error: refusing unsafe virtual environment: "
                 + env["XDG_DATA_HOME"] + "/quantumllama/venv_linux")
    assert (snapshot(work), snapshot(Path(env["HOME"]))) == before
    assert calls(project) == ["create:./venv_linux"]


@pytest.mark.parametrize("failure,message,code", [
    ("create", "Error: virtual environment creation failed.", 1),
    ("install", "Error: pip upgrade failed.", 7),
    ("requirements", "Error: requirements installation failed.", 7),
])
def test_failure_propagation(project, failure, message, code):
    work, env = project
    if failure == "create":
        env["CREATE_FAIL"] = "all"
    else:
        env["PIP_FAIL"] = "install"
        if failure == "requirements":
            # Distinguish the two install invocations in the shim.
            shim = Path(env["SHIM"])
            shim.write_text(SHIM.replace('[ "$PIP_FAIL" != "$3" ]', '[ "$4" != "-r" ]'))
    result = run(project)
    assert_error(result, message, code)
    assert (work / "requirements.txt").read_text() == "fake-package\n"
    if failure == "create":
        assert not (work / ".venv_linux_path").exists()
    elif failure == "install":
        assert "pip:install -r requirements.txt" not in calls(project)


@pytest.mark.parametrize("component", ["pyvenv.cfg", "bin", "bin/activate"])
def test_recreate_rejects_symlinked_metadata(project, component):
    work, _ = project
    assert run(project).returncode == 0
    path = work / "venv_linux" / component
    saved = path.with_name(path.name + ".saved")
    path.rename(saved)
    path.symlink_to(saved)
    before = snapshot(work.parent)
    assert_error(run(project, "--recreate"),
                 "Error: refusing unsafe virtual environment: ./venv_linux")
    assert snapshot(work.parent) == before


def test_recreation_does_not_follow_contained_symlinks(project):
    work, _ = project
    assert run(project).returncode == 0
    outside = work.parent / "outside"
    outside.mkdir()
    (outside / "precious").write_text("keep")
    (work / "venv_linux" / "external").symlink_to(outside)
    before = snapshot(outside)
    result = run(project, "--recreate")
    assert (result.returncode, result.stdout, result.stderr) == (0, success(reuse=False), "")
    assert snapshot(outside) == before


def test_missing_requirements_preserves_existing_behavior(project):
    work, _ = project
    (work / "requirements.txt").rename(work / "requirements.saved")
    result = run(project)
    assert (result.returncode, result.stdout, result.stderr) == (0, success(requirements=False, reuse=False), "")
    assert calls(project) == ["create:./venv_linux"]
