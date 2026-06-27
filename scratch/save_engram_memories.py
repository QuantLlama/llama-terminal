import subprocess
import os

project = "plataforma_lamaterminal_v0.1.7b"
project_root = "/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama"

# Memory 1: sdd-init
sdd_init_title = f"sdd-init/{project}"
sdd_init_content = """**What**: Initialized SDD context for the project and detected the current stack/persistence mode.
**Why**: The user requested initialization.
**Where**: Project root `/run/media/pabloezm/Respaldos/Pltaforma_Terminal_Llama`; `.atl/skill-registry.md` created; no `openspec/` directory was present.
**Learned**: The repo is configured for Engram-backed persistence by default. Stack consists of Electron frontend and Python backend, with pytest available in virtual environment `/home/pabloezm/venv_quantllama`."""

# Memory 2: testing-capabilities
tc_title = f"sdd/{project}/testing-capabilities"
tc_content = """## Testing Capabilities

**Strict TDD Mode**: enabled
**Detected**: 2026-06-24

### Test Runner

- Command: `/home/pabloezm/venv_quantllama/bin/pytest`
- Framework: pytest

### Test Layers

| Layer       | Available | Tool |
| ----------- | --------- | ---- |
| Unit        | ✅        | pytest |
| Integration | ❌        | — |
| E2E         | ❌        | — |

### Coverage

- Available: ❌
- Command: —

### Quality Tools

| Tool         | Available | Command |
| ------------ | --------- | ------- |
| Linter       | ❌        | — |
| Type checker | ❌        | — |
| Formatter    | ❌        | — |"""

# Memory 3: skill-registry
sr_title = "skill-registry"
sr_file_path = os.path.join(project_root, ".atl/skill-registry.md")
with open(sr_file_path, "r", encoding="utf-8") as f:
    sr_content = f.read()

def save_memory(title, content, type_val):
    cmd = [
        "engram", "save",
        title, "-",
        "--project", project,
        "--type", type_val
    ]
    res = subprocess.run(cmd, input=content, text=True, capture_output=True)
    if res.returncode == 0:
        print(f"Saved: {title}")
    else:
        print(f"Failed {title}: {res.stderr}")

save_memory(sdd_init_title, sdd_init_content, "architecture")
save_memory(tc_title, tc_content, "config")
save_memory(sr_title, sr_content, "config")
