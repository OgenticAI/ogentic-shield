"""Output formatters for CLI: JSON, table, and summary."""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

from ogentic_shield.models import AnalysisResult


def format_json(result: AnalysisResult) -> str:
    """Format analysis result as JSON."""
    return json.dumps(
        {
            "text_hash": result.text_hash,
            "score": result.score,
            "sensitivity_level": result.sensitivity_level.value,
            "routing_suggestion": result.routing_suggestion,
            "entity_count": result.entity_count,
            "processing_time_ms": result.processing_time_ms,
            "layers_invoked": [layer.value for layer in result.layers_invoked],
            "profiles_active": result.profile_ids,
            "entities": [
                {
                    "text": e.text,
                    "category": e.category,
                    "category_group": e.category_group.value,
                    "confidence": round(e.confidence, 2),
                    "detection_layer": e.detection_layer.value,
                    "start": e.start,
                    "end": e.end,
                }
                for e in result.entities
            ],
        },
        indent=2,
    )


def format_table(result: AnalysisResult) -> None:
    """Format analysis result as a Rich table."""
    console = Console()

    profiles_str = ", ".join(result.profile_ids)
    layers_str = ", ".join(layer.value for layer in result.layers_invoked)

    table = Table(
        title=f"ogentic-shield v0.1.0 — {profiles_str}",
        caption=(
            f"Score: {result.score}/100  Level: {result.sensitivity_level.value}  "
            f"Route: {result.routing_suggestion}\n"
            f"Entities: {result.entity_count}    Time: {result.processing_time_ms}ms    "
            f"Layers: {layers_str}"
        ),
    )

    table.add_column("Entity", style="cyan", max_width=20)
    table.add_column("Category", style="green")
    table.add_column("Conf.", justify="right", style="yellow")
    table.add_column("Layer", style="magenta")

    for entity in result.entities:
        text = entity.text[:18] + "…" if len(entity.text) > 18 else entity.text
        table.add_row(
            text,
            entity.category,
            f"{entity.confidence:.2f}",
            entity.detection_layer.value,
        )

    console.print(table)


def format_summary(result: AnalysisResult) -> str:
    """Format analysis result as a one-line summary."""
    top = ""
    if result.top_category:
        top = f" | {result.top_category} ({result.top_confidence:.2f})"
    return (
        f"{result.sensitivity_level.value} ({result.score}) | "
        f"{result.routing_suggestion} | "
        f"{result.entity_count} entities{top} | "
        f"{result.processing_time_ms}ms"
    )


def output_result(result: AnalysisResult, output_format: str) -> None:
    """Output result in the requested format."""
    if output_format == "json":
        click.echo(format_json(result))
    elif output_format == "table":
        format_table(result)
    elif output_format == "summary":
        click.echo(format_summary(result))
    else:
        click.echo(format_json(result))
