"""Offline structural CI contracts; no hosted runner or dependency installation."""
from configparser import ConfigParser
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def workflow():
    return (ROOT / '.github/workflows/ci.yml').read_text()


def jobs():
    return dict(re.findall(r'^  ([\w-]+):\n(.*?)(?=^  [\w-]+:|\Z)',
                           workflow().split('jobs:\n', 1)[1], re.M | re.S))


def test_existing_events_checks_and_source_guard_are_preserved():
    text = workflow()
    assert 'push:\n    branches: [main]' in text
    assert '  pull_request:\n' in text
    assert 'workflow_dispatch:' in text
    assert 'permissions:\n  contents: read' in text
    existing = jobs()
    assert 'name: pytest (Python ${{ matrix.python }})' in existing['tests']
    assert 'python: ["3.11", "3.12"]' in existing['tests']
    assert 'name: Syntax, conflict markers and documentation links' in existing['static']
    assert 'run: python scripts/check_secrets.py' in existing['static']
    assert 'run: python scripts/check_docs_links.py' in existing['static']
    assert 'name: Conventional Commits' in existing['commit-hygiene']
    assert "if: github.event_name == 'pull_request'" in existing['commit-hygiene']


def test_pull_requests_to_chain_bases_are_not_filtered():
    # An unrestricted PR event admits feature/release-readiness and every
    # predecessor fix/refactor/build branch, without maintaining a prefix list.
    event = re.search(r'^  pull_request:\n(.*?)(?=^  \w|^\S|\Z)',
                      workflow(), re.M | re.S)
    assert event is not None
    assert not event.group(1).strip(), (
        'All PR bases must receive CI, including feature/release-readiness '
        'and predecessor fix/refactor/build branches'
    )


def test_minimal_lane_measures_source_without_collecting_model_tests():
    lane = jobs()['tests']
    assert 'python -m coverage run -m pytest -q' in lane
    for module in ('test_model_artifact_contract.py', 'test_simulation_compatibility.py'):
        assert f'--ignore=tests/{module}' in lane
    assert 'requirements.ci.txt' in lane
    assert 'pip install torch' not in lane
    requirements = (ROOT / 'requirements.ci.txt').read_text()
    assert re.search(r'^coverage[<>=]', requirements, re.M)
    assert re.search(r'^requests[<>=]', requirements, re.M)


def test_cpu_model_lane_runs_actual_artifact_and_simulation_contracts():
    lane = jobs()['model-simulation']
    assert 'python-version: "3.11"' in lane
    assert '--index-url https://download.pytorch.org/whl/cpu' in lane
    assert 'torch==2.2.2' in lane
    assert 'scikit-learn==1.4.2' in lane
    assert 'yfinance==0.2.40' in lane
    assert 'python -m coverage run -m pytest -q' in lane
    for module in ('test_model_artifact_contract.py', 'test_simulation_compatibility.py'):
        assert f'tests/{module}' in lane
        assert f'--ignore=tests/{module}' not in lane
    assert 'import numpy, pandas, sklearn, torch' in lane
    assert 'assert not torch.cuda.is_available()' in lane
    assert 'timeout-minutes:' in lane
    assert 'continue-on-error' not in lane


def test_each_python_lane_uploads_private_local_coverage_reports_even_on_failure():
    for name in ('tests', 'model-simulation'):
        lane = jobs()[name]
        assert 'python -m coverage xml -o "$RUNNER_TEMP/coverage.xml"' in lane
        assert 'python -m coverage report -m > "$RUNNER_TEMP/coverage.txt"' in lane
        assert 'uses: actions/upload-artifact@v4' in lane
        assert lane.count('if: always()') >= 2
        assert 'if-no-files-found: error' in lane
        assert 'retention-days: 14' in lane
        assert '${{ runner.temp }}/coverage.xml' in lane
        assert '${{ runner.temp }}/coverage.txt' in lane
        assert 'COVERAGE_FILE: ${{ runner.temp }}/.coverage' in lane
    assert 'name: coverage-python-${{ matrix.python }}' in jobs()['tests']
    assert 'name: coverage-model-simulation-python-3.11' in jobs()['model-simulation']
    assert 'codecov' not in workflow().lower()
    assert not re.search(r'\$\{\{\s*secrets\.', workflow())
    config = ConfigParser()
    config.read(ROOT / '.coveragerc')
    assert config.get('run', 'source').strip() == 'src'
    assert not config.has_option('report', 'fail_under')
    assert not config.has_option('run', 'omit')


def test_existing_static_lane_checks_both_electron_entry_points():
    lane = jobs()['static']
    assert 'node --check electron/main.js' in lane
    assert 'node --check electron/health.js' in lane
