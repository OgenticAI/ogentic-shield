"""CLI profiles command group."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from ogentic_shield.profiles import get_profile, list_profiles


@click.group()
def profiles():
    """Manage shield profiles."""


@profiles.command("list")
def list_cmd():
    """List all available shield profiles."""
    console = Console()
    table = Table(title="Available Shield Profiles")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Version", style="yellow")
    table.add_column("Entities", justify="right")
    table.add_column("Description")

    for profile in list_profiles():
        table.add_row(
            profile.id,
            profile.name,
            profile.version,
            str(len(profile.supported_entities)),
            profile.description,
        )

    console.print(table)


@profiles.command("show")
@click.argument("profile_id")
def show_cmd(profile_id):
    """Show details for a specific profile."""
    console = Console()
    profile = get_profile(profile_id)

    console.print(f"\n[bold cyan]{profile.name}[/bold cyan]")
    console.print(f"  ID:      {profile.id}")
    console.print(f"  Version: {profile.version}")
    console.print(f"  {profile.description}\n")

    table = Table(title="Supported Entity Types")
    table.add_column("Entity Type", style="green")
    for entity in profile.supported_entities:
        table.add_row(entity)
    console.print(table)

    weights_table = Table(title="Scoring Weights")
    weights_table.add_column("Category Group", style="cyan")
    weights_table.add_column("Weight", justify="right", style="yellow")
    for group, weight in profile.scoring_weights.items():
        weights_table.add_row(group.value, str(weight))
    console.print(weights_table)
