"""CLI ``test-recognizer`` command (OGE-322).

Runs a user-supplied recognizer module through Presidio's analyzer and
prints what it matches. The intent is to give community contributors a
fast feedback loop while authoring a custom :class:`PatternRecognizer`
without needing to wire it into a profile first.

Usage::

    ogentic-shield test-recognizer path/to/my_recognizer.py
    ogentic-shield test-recognizer path/to/my_recognizer.py --text "Try me"
    ogentic-shield test-recognizer path/to/my_recognizer.py \\
        --text "Try me" \\
        --text-file fixtures/sample.txt \\
        --min-confidence 0.6

Discovery rules:

- Imports the file as a module via ``importlib``.
- Finds every :class:`presidio_analyzer.PatternRecognizer` subclass
  *defined in that module* (imports of upstream classes are ignored).
- Each subclass is instantiated with no arguments — the recognizer must
  expose a zero-arg ``__init__`` (the standard pattern in
  ``CLAUDE.md`` §4.1).

Input texts (all combined for the run):

- Strings passed via ``--text`` (repeatable).
- Contents of files passed via ``--text-file`` (repeatable).
- A module-level ``SAMPLE_TEXTS: list[str]`` if the recognizer file
  defines one.

Exit codes:

- ``0`` — the harness ran (regardless of whether anything matched).
- ``1`` — the file couldn't be imported or contained no recognizers.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import click
from presidio_analyzer import AnalyzerEngine, PatternRecognizer
from rich.console import Console
from rich.table import Table


def _load_module(path: Path):
    """Import a Python file at ``path`` as a one-off module.

    The module name we assign is intentionally unique-per-call so that
    repeated invocations don't collide in ``sys.modules`` cache (matters
    in tests; benign elsewhere). The parent dir is prepended to
    ``sys.path`` so any sibling-file imports the recognizer makes also
    resolve.
    """
    module_name = f"_ogentic_shield_test_recognizer_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise click.ClickException(f"Could not load module from {path}")

    parent = str(path.parent.resolve())
    if parent not in sys.path:
        sys.path.insert(0, parent)

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise click.ClickException(f"Failed to import {path}: {exc}") from exc
    return module


def _find_recognizer_classes(module) -> list[type[PatternRecognizer]]:
    """Return PatternRecognizer subclasses defined *in* this module.

    We filter by ``__module__`` so re-imports of upstream classes
    (e.g. ``PatternRecognizer`` itself) don't get instantiated.
    """
    classes: list[type[PatternRecognizer]] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, PatternRecognizer)
            and obj is not PatternRecognizer
            and obj.__module__ == module.__name__
        ):
            classes.append(obj)
    return classes


def _instantiate(recognizer_cls: type[PatternRecognizer]) -> PatternRecognizer:
    """Instantiate a recognizer class with no arguments.

    Surfaces a clear error if the class needs constructor args — most
    common author mistake is forgetting that the test harness calls
    ``cls()`` with nothing.
    """
    try:
        # User subclasses fill `supported_entity` inside their own
        # zero-arg `__init__`; mypy can't see through that.
        return recognizer_cls()  # type: ignore[call-arg]
    except TypeError as exc:
        raise click.ClickException(
            f"{recognizer_cls.__name__}() needs constructor arguments — "
            f"the test harness instantiates it with no args. "
            f"Underlying error: {exc}",
        ) from exc


def _gather_texts(
    inline_texts: tuple[str, ...],
    text_files: tuple[Path, ...],
    module,
) -> list[tuple[str, str]]:
    """Return a list of ``(label, text)`` pairs to evaluate.

    Order: ``--text`` args, then ``--text-file`` contents, then the
    module's ``SAMPLE_TEXTS`` if defined. Empty inputs are dropped so
    blank trailing newlines in a file don't produce noise.
    """
    pairs: list[tuple[str, str]] = []
    for i, t in enumerate(inline_texts, start=1):
        if t.strip():
            pairs.append((f"--text #{i}", t))
    for path in text_files:
        content = path.read_text()
        if content.strip():
            pairs.append((f"file: {path.name}", content))
    sample_texts = getattr(module, "SAMPLE_TEXTS", None)
    if sample_texts:
        for i, t in enumerate(sample_texts, start=1):
            if isinstance(t, str) and t.strip():
                pairs.append((f"SAMPLE_TEXTS[{i - 1}]", t))
    return pairs


def _run_one(
    analyzer: AnalyzerEngine,
    instances: list[PatternRecognizer],
    text: str,
    min_confidence: float,
) -> list[dict]:
    """Run all recognizer instances against ``text`` and return matches.

    Each match is a dict shaped for the result table — kept loose
    (rather than a dataclass) because the only consumer is the printer
    a few lines below.
    """
    entity_types = sorted({inst.supported_entities[0] for inst in instances})
    results = analyzer.analyze(text=text, entities=entity_types, language="en")
    out: list[dict] = []
    for r in results:
        if r.score < min_confidence:
            continue
        out.append(
            {
                "category": r.entity_type,
                "text": text[r.start : r.end],
                "start": r.start,
                "end": r.end,
                "score": r.score,
            },
        )
    return out


@click.command("test-recognizer")
@click.argument(
    "recognizer_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--text",
    "-t",
    "inline_texts",
    multiple=True,
    help="Text to analyze. Repeatable.",
)
@click.option(
    "--text-file",
    "text_files",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a UTF-8 text file to analyze. Repeatable.",
)
@click.option(
    "--min-confidence",
    type=float,
    default=0.5,
    show_default=True,
    help="Drop matches scored below this threshold.",
)
def test_recognizer(
    recognizer_path: Path,
    inline_texts: tuple[str, ...],
    text_files: tuple[Path, ...],
    min_confidence: float,
) -> None:
    """Run a custom recognizer module against sample text and print matches."""
    console = Console()

    module = _load_module(recognizer_path)
    classes = _find_recognizer_classes(module)
    if not classes:
        raise click.ClickException(
            f"No PatternRecognizer subclasses found in {recognizer_path}. "
            f"Define at least one class extending presidio_analyzer.PatternRecognizer.",
        )

    instances: list[PatternRecognizer] = [_instantiate(cls) for cls in classes]

    analyzer = AnalyzerEngine()
    for inst in instances:
        analyzer.registry.add_recognizer(inst)

    texts = _gather_texts(inline_texts, text_files, module)
    if not texts:
        raise click.ClickException(
            "No text to analyze. Pass --text, --text-file, or define "
            "SAMPLE_TEXTS in the recognizer module.",
        )

    # Header summary so the user sees what's being evaluated.
    console.print(
        f"\n[bold]Loaded {len(classes)} recognizer(s) from "
        f"{recognizer_path}:[/bold]",
    )
    for cls, inst in zip(classes, instances):
        # `patterns` is set by Presidio's `__init__` but missing from its
        # public attribute typing — use a local cast to keep mypy quiet.
        pattern_count = len(inst.patterns)  # type: ignore[has-type]
        console.print(
            f"  • [cyan]{cls.__name__}[/cyan] "
            f"→ entity=[green]{inst.supported_entities[0]}[/green] "
            f"({pattern_count} pattern{'s' if pattern_count != 1 else ''})",
        )

    # Per-text result table.
    total_matches = 0
    for label, text in texts:
        matches = _run_one(analyzer, instances, text, min_confidence)
        total_matches += len(matches)
        console.print()
        console.print(f"[bold]── {label}[/bold]")
        snippet = text if len(text) <= 200 else text[:197] + "..."
        console.print(f"   text: {snippet!r}")
        if not matches:
            console.print("   [yellow]no matches[/yellow]")
            continue
        table = Table(show_header=True, header_style="bold")
        table.add_column("category", style="green")
        table.add_column("text", style="cyan")
        table.add_column("span")
        table.add_column("score", justify="right", style="yellow")
        for m in matches:
            table.add_row(
                m["category"],
                m["text"] if len(m["text"]) <= 60 else m["text"][:57] + "...",
                f"{m['start']}-{m['end']}",
                f"{m['score']:.2f}",
            )
        console.print(table)

    console.print(
        f"\n[bold]Done.[/bold] {total_matches} match"
        f"{'es' if total_matches != 1 else ''} across {len(texts)} input"
        f"{'s' if len(texts) != 1 else ''}.",
    )
