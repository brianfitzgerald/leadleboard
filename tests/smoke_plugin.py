"""Save pytest smoke results and exact report previews."""

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4
from warnings import WarningMessage

import pytest
from pydantic import ConfigDict, Field

from leadleboard.config import Config
from leadleboard.models import DataModel


class TestResult(DataModel):
    """The result and captured output of one pytest phase."""

    __test__ = False
    nodeid: str
    phase: str
    outcome: str
    duration: float
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    log: str = ""


class SmokeResults(DataModel):
    """The status, results, warnings, and files of a smoke run."""

    model_config = ConfigDict(frozen=False)
    schema_version: Literal[1] = 1
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["incomplete", "passed", "failed", "interrupted"] = "incomplete"
    posting_tested: bool = False
    tests: list[TestResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    access_details: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class SmokeRun:
    """Write results throughout one pytest session."""

    def __init__(self, config: pytest.Config) -> None:
        started_at = datetime.now(UTC)
        root = config.getoption("--smoke-output-dir")
        directory = Path(str(root)) if root else config.rootpath / ".data" / "smoke-tests"
        name = f"{started_at:%Y%m%dT%H%M%S.%fZ}-{uuid4().hex[:8]}"
        self.directory = directory / name
        self.directory.mkdir(parents=True)
        self.results = SmokeResults(started_at=started_at)
        self.secrets: set[str] = set()

    def redact(self, text: str) -> str:
        """Remove configured secrets from captured test output."""
        for secret in self.secrets:
            text = text.replace(secret, "[redacted]")
        return text

    def save(self) -> None:
        """Write Markdown and JSON results after each update."""
        results = self.results
        lines = [
            "# Smoke test results",
            "",
            f"Status: {results.status}",
            f"Started: {results.started_at.isoformat()}",
            f"Finished: {results.finished_at.isoformat() if results.finished_at else 'pending'}",
            "Posting was not tested. No Discord messages were sent.",
            "",
            "## Tests",
            "",
            "| Test | Phase | Result | Seconds |",
            "| --- | --- | --- | --- |",
        ]
        for result in results.tests:
            nodeid = result.nodeid.replace("|", r"\|")
            lines.append(
                f"| {nodeid} | {result.phase} | {result.outcome} | {result.duration:.3f} |"
            )
        lines.extend(("", "## Files", ""))
        for artifact in results.artifacts:
            lines.append(f"- [{artifact}]({artifact})")
        lines.extend(("", "## Access checks", "", *results.access_details))
        lines.extend(("", "## Warnings", "", *results.warnings))
        for result in results.tests:
            output = "\n".join(
                part for part in (result.error, result.stdout, result.stderr, result.log) if part
            )
            if output:
                longest = max((len(s) for s in output.split() if set(s) == {"`"}), default=0)
                fence = "`" * max(4, longest + 1)
                lines.extend(("", f"## {result.nodeid} ({result.phase})", "", fence, output, fence))
        (self.directory / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (self.directory / "results.json").write_text(
            results.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        """Save collection failures."""
        if report.failed:
            self.results.tests.append(
                TestResult(
                    nodeid=report.nodeid,
                    phase="collect",
                    outcome="failed",
                    duration=0,
                    error=self.redact(report.longreprtext),
                )
            )
            self.save()

    def pytest_warning_recorded(self, warning_message: WarningMessage) -> None:
        """Save Python warnings from collection and test execution."""
        warning = f"{warning_message.category.__name__}: {warning_message.message}"
        self.results.warnings.append(self.redact(warning))
        self.save()


SMOKE_RUN = pytest.StashKey[SmokeRun]()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register explicit live-test and output-directory options."""
    parser.addoption("--run-smoke", action="store_true", help="Run live Discord smoke tests")
    parser.addoption("--smoke-output-dir", help="Parent directory for smoke-test results")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Create a result directory before collection starts."""
    if session.config.getoption("--run-smoke"):
        run = SmokeRun(session.config)
        session.config.stash[SMOKE_RUN] = run
        session.config.pluginmanager.register(run, "smoke-results")
        run.save()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests unless they were explicitly enabled."""
    if not config.getoption("--run-smoke"):
        for item in items:
            if item.get_closest_marker("smoke") is not None:
                item.add_marker(
                    pytest.mark.skip(reason="Use --run-smoke to run live Discord tests")
                )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Save setup, call, and teardown outcomes."""
    report = yield
    if SMOKE_RUN in item.config.stash:
        run = item.config.stash[SMOKE_RUN]
        run.results.tests.append(
            TestResult(
                nodeid=report.nodeid,
                phase=report.when or "unknown",
                outcome=report.outcome,
                duration=report.duration,
                error=run.redact(report.longreprtext) if report.failed else "",
                stdout=run.redact(report.capstdout),
                stderr=run.redact(report.capstderr),
                log=run.redact(report.caplog),
            )
        )
        run.save()
    return report


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Finalize results after completion or interruption."""
    if SMOKE_RUN in session.config.stash:
        run = session.config.stash[SMOKE_RUN]
        run.results.finished_at = datetime.now(UTC)
        if exitstatus == pytest.ExitCode.INTERRUPTED and not any(
            result.phase == "collect" and result.outcome == "failed" for result in run.results.tests
        ):
            run.results.status = "interrupted"
        else:
            run.results.status = "passed" if exitstatus == 0 else "failed"
        run.save()


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Print the saved result path."""
    if SMOKE_RUN in terminalreporter.config.stash:
        run = terminalreporter.config.stash[SMOKE_RUN]
        terminalreporter.write_line(f"Smoke results: {run.directory / 'results.md'}")


@pytest.fixture
def smoke_run(request: pytest.FixtureRequest) -> SmokeRun:
    """Return the result writer for an explicit smoke run."""
    return request.config.stash[SMOKE_RUN]


@pytest.fixture(scope="session")
def smoke_config(request: pytest.FixtureRequest) -> Config:
    """Load live configuration and register the token for redaction."""
    config = Config.load()
    request.config.stash[SMOKE_RUN].secrets.add(config.token.get_secret_value())
    return config
