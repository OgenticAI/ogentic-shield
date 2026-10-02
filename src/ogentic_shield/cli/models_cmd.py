"""CLI ``models`` command: explicit, one-time setup of the spaCy NER model.

Analysis never downloads models (see ``layers.regex_ner.ensure_model_installed``);
this is the only code path that does.
"""

from __future__ import annotations

import subprocess
import sys

import click
import spacy.util

from ogentic_shield.config import DEFAULT_NER_MODEL


@click.group()
def models() -> None:
    """Manage the spaCy NER model Shield needs (one-time setup)."""


@models.command()
@click.option("--model", default=DEFAULT_NER_MODEL, show_default=True, help="spaCy model package to install.")
def download(model: str) -> None:
    """Download and install the spaCy model (en_core_web_lg is ~400 MB)."""
    if spacy.util.is_package(model):
        click.echo(f"{model} is already installed.", err=True)
        return
    click.echo(f"Downloading {model} ...", err=True)
    # spaCy shells out to pip; point the child's stdout at fd 2 (stderr) so
    # our stdout carries nothing but requested output.
    rc = subprocess.call([sys.executable, "-m", "spacy", "download", model], stdout=2)
    if rc != 0:
        raise click.ClickException(f"Download of {model} failed (exit {rc}).")
    click.echo(f"{model} installed.", err=True)
