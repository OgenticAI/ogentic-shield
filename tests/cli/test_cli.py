"""Tests for CLI commands."""

import json

from click.testing import CliRunner

from ogentic_shield.cli.main import cli


class TestAnalyzeCommand:
    """Tests for the analyze CLI command."""

    def test_analyze_json_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "analyze",
            "Outside counsel reviewed the privileged document.",
            "--profiles", "shield-legal",
            "--output", "json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "score" in data
        assert "entities" in data
        assert "routing_suggestion" in data

    def test_analyze_summary_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "analyze",
            "The weather is nice today.",
            "--profiles", "shield-legal",
            "--output", "summary",
        ])
        assert result.exit_code == 0
        assert "CLOUD_OK" in result.output or "NONE" in result.output or "LOW" in result.output

    def test_analyze_from_stdin(self):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["analyze", "--profiles", "shield-legal", "--output", "json"],
            input="Outside counsel at Davis Polk reviewed the case.",
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["entity_count"] >= 1

    def test_analyze_with_min_confidence(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "analyze",
            "Outside counsel at Davis Polk reviewed the case.",
            "--profiles", "shield-legal",
            "--output", "json",
            "--min-confidence", "0.99",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for entity in data["entities"]:
            assert entity["confidence"] >= 0.99

    def test_analyze_multiple_profiles(self):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "analyze",
            "Outside counsel reviewed the case. Patient: Jane D. DOB: 03/15/1988.",
            "--profiles", "shield-legal",
            "--profiles", "shield-therapy",
            "--output", "json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["profiles_active"]) == 2


class TestProfilesCommand:
    """Tests for the profiles CLI command."""

    def test_profiles_list(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["profiles", "list"])
        assert result.exit_code == 0
        assert "shield-legal" in result.output
        assert "shield-therapy" in result.output
        assert "shield-finance" in result.output

    def test_profiles_show(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["profiles", "show", "shield-legal"])
        assert result.exit_code == 0
        assert "Legal Privilege Protection" in result.output


class TestVersionFlag:
    """Tests for --version flag."""

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
