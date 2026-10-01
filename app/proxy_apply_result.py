"""Explicit restart policy shared by the runtime and its callers."""
from enum import Enum


class ApplyRequirement(Enum):
    HOT = 'hot'
    PROTOCOL_SERVICE_RESTART = 'protocol_service_restart'
    COMMON_CORE_RESTART = 'common_core_restart'


class AutomaticApplyBlocked(RuntimeError):
    """A capability limit, not evidence that the candidate is unhealthy."""


def requires_common_restart(result):
    # None remains fail-closed for older backends during upgrades.
    return result is None or result is ApplyRequirement.COMMON_CORE_RESTART
