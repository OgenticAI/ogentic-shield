"""CLI analyze command."""

from __future__ import annotations

import sys

import click

from ogentic_shield.cli.formatters import output_result
from ogentic_shield.shield import Shield


@click.command()
@click.argument("text", required=False)
@click.option("--file", "-f", "file_path", type=click.Path(exists=True), help="Read text from file")
@click.option("--profiles", "-p", multiple=True, help="Shield profiles to use")
@click.option("--output", "-o", "output_format", type=click.Choice(["json", "table", "summary"]), default="json")
@click.option("--min-confidence", type=float, default=None, help="Minimum confidence threshold")
def analyze(text, file_path, profiles, output_format, min_confidence):
    """Analyze text for regulatory sensitivity."""
    if text is None and file_path is None:
        if not sys.stdin.isatty():
            text = sys.stdin.read()
        else:
            raise click.UsageError("Provide text as argument, --file, or pipe via stdin.")

    if file_path:
        with open(file_path) as f:
            text = f.read()

    profile_list = list(profiles) if profiles else None
    shield = Shield(profiles=profile_list)
    result = shield.analyze(text, min_confidence=min_confidence)
    output_result(result, output_format)
