"""Shield profile loading and registry."""

from ogentic_shield.models import ProfileNotFoundError, ShieldProfile
from ogentic_shield.profiles.finance import create_profile as create_finance_profile
from ogentic_shield.profiles.legal import create_profile as create_legal_profile
from ogentic_shield.profiles.therapy import create_profile as create_therapy_profile

PROFILE_REGISTRY: dict[str, ShieldProfile] = {}


def _register_builtin_profiles() -> None:
    for factory in (create_legal_profile, create_therapy_profile, create_finance_profile):
        profile = factory()
        PROFILE_REGISTRY[profile.id] = profile


_register_builtin_profiles()


def get_profile(profile_id: str) -> ShieldProfile:
    if profile_id not in PROFILE_REGISTRY:
        raise ProfileNotFoundError(
            f"Profile '{profile_id}' not found. "
            f"Available: {', '.join(PROFILE_REGISTRY.keys())}"
        )
    return PROFILE_REGISTRY[profile_id]


def list_profiles() -> list[ShieldProfile]:
    return list(PROFILE_REGISTRY.values())
