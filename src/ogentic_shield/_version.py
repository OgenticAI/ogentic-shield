"""Single source of truth for the package version.

Imported by both ``__init__.py`` (public ``__version__``) and runtime
modules (audit event emission, CLI banner) to avoid circular imports.
"""

__version__ = "0.2.0.dev0"
