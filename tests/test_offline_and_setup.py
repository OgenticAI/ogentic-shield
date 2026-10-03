"""0.6.2: analysis is fully offline and never downloads models.

- Email detection must not fetch the public suffix list (Presidio's
  EmailRecognizer -> tldextract would, on a machine with a cold cache).
- A missing spaCy model must fail fast with an actionable stderr message and
  an empty stdout, never a runtime ``pip install`` whose progress corrupts
  ``--output json``. Setup is the explicit ``ogentic-shield models download``.
"""

from __future__ import annotations

import socket
import sys

import pytest
import spacy.cli
import spacy.util
import tldextract.tldextract as tldx
from click.testing import CliRunner

from ogentic_shield import ModelNotInstalledError, Shield
from ogentic_shield.cli.main import cli
from ogentic_shield.layers import regex_ner


@pytest.fixture
def no_network(monkeypatch, tmp_path):
    """Record and refuse every outbound connection, on a cold tldextract cache."""
    attempts: list[object] = []

    def refuse(*args, **kwargs):
        attempts.append(args or kwargs)
        raise OSError("network disabled by test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    # Simulate a fresh machine: Presidio's default extractor has no cached suffix list.
    monkeypatch.setattr(tldx.TLD_EXTRACTOR, "_cache", tldx.DiskCache(str(tmp_path)))
    monkeypatch.setattr(tldx.TLD_EXTRACTOR, "_extractor", None)
    return attempts


def test_email_analysis_makes_no_network_call(no_network):
    result = Shield(profiles=["shield-legal"]).analyze("Send the brief to jane.doe@lawfirm.co.uk today.")
    emails = [e for e in result.entities if e.category == "EMAIL_ADDRESS"]
    assert [e.text for e in emails] == ["jane.doe@lawfirm.co.uk"]
    assert no_network == [], f"analysis attempted network connections: {no_network}"


def test_email_with_unknown_tld_still_rejected(no_network):
    """Offline validation keeps Presidio's semantics: no public suffix, no email."""
    result = Shield(profiles=["shield-legal"]).analyze("Ping admin@intranet.notatld please.")
    assert not [e for e in result.entities if e.category == "EMAIL_ADDRESS"]
    assert no_network == []


@pytest.fixture
def model_missing(monkeypatch):
    """spaCy reports no model installed; a download would print pip noise to stdout."""
    downloads: list[str] = []

    def fake_download(name, *args, **kwargs):
        downloads.append(name)
        print(f"Collecting {name}==3.8.0\nDownloading {name}-3.8.0.whl (400.7 MB)")

    monkeypatch.setattr(spacy.util, "is_package", lambda name: False)
    monkeypatch.setattr(spacy.cli, "download", fake_download)
    regex_ner._get_analyzer.cache_clear()
    yield downloads
    regex_ner._get_analyzer.cache_clear()


def test_missing_model_raises_without_downloading(model_missing):
    with pytest.raises(ModelNotInstalledError, match="ogentic-shield models download --model en_core_web_lg"):
        Shield(profiles=["shield-legal"]).analyze("Client SSN 412-71-3359 on file.")
    assert model_missing == []


def test_cli_missing_model_keeps_stdout_clean(model_missing):
    result = CliRunner().invoke(
        cli, ["analyze", "--profiles", "shield-legal", "--output", "json"], input="Client SSN 412-71-3359 on file."
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    assert "en_core_web_lg" in result.stderr
    assert "ogentic-shield models download" in result.stderr
    assert model_missing == []


def test_models_download_invokes_spacy_with_stdout_on_stderr(monkeypatch):
    calls = []
    monkeypatch.setattr(spacy.util, "is_package", lambda name: False)
    monkeypatch.setattr(
        "ogentic_shield.cli.models_cmd.subprocess.call", lambda cmd, **kw: calls.append((cmd, kw)) or 0
    )
    result = CliRunner().invoke(cli, ["models", "download"])
    assert result.exit_code == 0, result.output
    assert calls == [([sys.executable, "-m", "spacy", "download", "en_core_web_lg"], {"stdout": 2})]
    assert result.stdout == ""


def test_models_download_failure_is_nonzero(monkeypatch):
    monkeypatch.setattr(spacy.util, "is_package", lambda name: False)
    monkeypatch.setattr("ogentic_shield.cli.models_cmd.subprocess.call", lambda cmd, **kw: 1)
    result = CliRunner().invoke(cli, ["models", "download", "--model", "en_core_web_sm"])
    assert result.exit_code != 0
    assert "en_core_web_sm" in result.stderr


def test_models_download_skips_when_installed(monkeypatch):
    monkeypatch.setattr(spacy.util, "is_package", lambda name: True)
    monkeypatch.setattr("ogentic_shield.cli.models_cmd.subprocess.call", pytest.fail)
    result = CliRunner().invoke(cli, ["models", "download"])
    assert result.exit_code == 0
    assert "already installed" in result.stderr
