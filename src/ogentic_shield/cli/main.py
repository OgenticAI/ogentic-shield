"""Click CLI entry point for ogentic-shield."""

from __future__ import annotations

import click

from ogentic_shield import __version__
from ogentic_shield.cli.analyze import analyze
from ogentic_shield.cli.profiles_cmd import profiles


@click.group()
@click.version_option(version=__version__, prog_name="ogentic-shield")
def cli():
    """ogentic-shield: Regulatory sensitivity detection for AI applications."""


cli.add_command(analyze)
cli.add_command(profiles)

if __name__ == "__main__":
    cli()
