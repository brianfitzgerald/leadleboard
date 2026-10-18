from pathlib import Path

import pytest

from tests.smoke_plugin import SmokeResults


@pytest.mark.parametrize(
    ("source", "status", "phase", "outcome"),
    [
        ("def test_example():\n    print('saved output')", "passed", "call", "passed"),
        ("def test_example():\n    assert False, 'test failure'", "failed", "call", "failed"),
        (
            "import pytest\n@pytest.fixture\ndef broken():\n    raise ValueError('setup failure')\n"
            "def test_example(broken):\n    pass",
            "failed",
            "setup",
            "failed",
        ),
        (
            "import pytest\n@pytest.fixture\ndef broken():\n    yield\n"
            "    raise ValueError('teardown failure')\ndef test_example(broken):\n    pass",
            "failed",
            "teardown",
            "failed",
        ),
        ("invalid python syntax", "failed", "collect", "failed"),
        ("def test_example():\n    raise KeyboardInterrupt()", "interrupted", None, None),
    ],
)
def test_smoke_results_survive_failures(
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    status: str,
    phase: str | None,
    outcome: str | None,
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parent.parent))
    pytester.makepyfile(test_example=source)
    root = pytester.path / "results"
    result = pytester.runpytest_subprocess(
        "-p", "tests.smoke_plugin", "--run-smoke", f"--smoke-output-dir={root}", "-q"
    )
    directories = list(root.iterdir())
    assert len(directories) == 1
    directory = directories[0]
    saved = SmokeResults.model_validate_json((directory / "results.json").read_text())
    assert saved.status == status
    assert saved.finished_at is not None
    assert not saved.posting_tested
    assert (directory / "results.md").read_text().startswith("# Smoke test results")
    assert "Smoke results:" in result.stdout.str()
    if phase is not None:
        assert any(test.phase == phase and test.outcome == outcome for test in saved.tests)
    if status == "passed":
        assert "saved output" in (directory / "results.md").read_text()


def test_regular_pytest_skips_live_tests_and_does_not_save_results(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parent.parent))
    pytester.makeini("[pytest]\nmarkers = smoke: live tests")
    pytester.makepyfile(
        "import pytest\n@pytest.mark.smoke\ndef test_live():\n    raise AssertionError('must skip')"
    )
    result = pytester.runpytest_subprocess("-p", "tests.smoke_plugin", "-q")
    result.assert_outcomes(skipped=1)
    assert not (pytester.path / ".data").exists()


def test_smoke_runs_keep_separate_directories_and_save_warnings(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parent.parent))
    pytester.makepyfile(
        "import warnings\ndef test_example():\n    warnings.warn('saved warning', UserWarning)"
    )
    root = pytester.path / "results"
    for _ in range(2):
        result = pytester.runpytest_subprocess(
            "-p", "tests.smoke_plugin", "--run-smoke", f"--smoke-output-dir={root}", "-q"
        )
        result.assert_outcomes(passed=1)
    assert len(list(root.iterdir())) == 2
    for directory in root.iterdir():
        saved = SmokeResults.model_validate_json((directory / "results.json").read_text())
        assert saved.warnings == ["UserWarning: saved warning"]
        assert "saved warning" in (directory / "results.md").read_text()


def test_missing_live_configuration_fails_and_saves_results(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parent.parent))
    monkeypatch.setenv("DISCORD_TOKEN", "")
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    pytester.makepyfile("def test_example(smoke_config):\n    pass")
    root = pytester.path / "results"
    result = pytester.runpytest_subprocess(
        "-p", "tests.smoke_plugin", "--run-smoke", f"--smoke-output-dir={root}", "-q"
    )
    result.assert_outcomes(errors=1)
    directory = next(root.iterdir())
    assert "Missing environment variables" in (directory / "results.md").read_text()
    assert (
        SmokeResults.model_validate_json((directory / "results.json").read_text()).status
        == "failed"
    )


def test_smoke_results_redact_secrets(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parent.parent))
    pytester.makepyfile(
        "import warnings\ndef test_example(smoke_run):\n"
        "    smoke_run.secrets.add('test-secret')\n"
        "    print('test-secret')\n"
        "    warnings.warn('test-secret', UserWarning)\n"
        "    raise ValueError('test-secret')"
    )
    root = pytester.path / "results"
    result = pytester.runpytest_subprocess(
        "-p", "tests.smoke_plugin", "--run-smoke", f"--smoke-output-dir={root}", "-q"
    )
    result.assert_outcomes(failed=1)
    directory = next(root.iterdir())
    for filename in ("results.md", "results.json"):
        content = (directory / filename).read_text()
        assert "test-secret" not in content
        assert "[redacted]" in content
