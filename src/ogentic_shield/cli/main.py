"""Click CLI entry point for ogentic-shield."""

from __future__ import annotations

import click

from ogentic_shield import __version__
from ogentic_shield.cli.analyze import analyze
from ogentic_shield.cli.models_cmd import models
from ogentic_shield.cli.profiles_cmd import profiles
from ogentic_shield.cli.serve import serve
from ogentic_shield.cli.test_recognizer import test_recognizer
from ogentic_shield.models import ModelNotInstalledError


class _ModelMissing(click.ClickException):
    # Distinct exit code so callers can tell "run setup" apart from other failures.
    exit_code = 3


class _ShieldGroup(click.Group):
    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except ModelNotInstalledError as exc:
            raise _ModelMissing(str(exc)) from exc


@click.group(cls=_ShieldGroup)
@click.version_option(version=__version__, prog_name="ogentic-shield")
def cli():
    """ogentic-shield: Regulatory sensitivity detection for AI applications."""


cli.add_command(analyze)
cli.add_command(models)
cli.add_command(profiles)
cli.add_command(serve)
cli.add_command(test_recognizer)

if __name__ == "__main__":
    cli()
