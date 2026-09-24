"""Side-effect-free preparation for a future serialized proxy apply backend.

Not wired into production apply yet. A plan is NOT permission to mutate Xray.
The caller must supply an attested runtime snapshot, not just the file on disk.
Syntax/capability checks by the actual Xray binary are still required.
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math


class ChangeKind(str, Enum):
    UNCHANGED = 'unchanged'
    OUTBOUND = 'outbound'
    ROUTING = 'routing'
    OUTBOUND_AND_ROUTING = 'outbound_and_routing'
    CORE = 'core'


class PlanAction(str, Enum):
    NOOP = 'noop'
    VERIFY_RUNTIME = 'verify_runtime'
    RECOVER_RUNTIME = 'recover_runtime'
    PREPARE_OUTBOUND = 'prepare_outbound'
    PREPARE_ROUTING = 'prepare_routing'
    PREPARE_TRANSACTION = 'prepare_transaction'
    RESTART_REQUIRED = 'restart_required'


@dataclass(frozen=True)
class RuntimeEvidence:
    """Trusted collector input; identity includes boot id, PID and start ticks.

    generation changes for every accepted intent, including A -> B -> A.
    healthy is a data-plane result tied to verified_fingerprint and checked_at.
    A successful SOCKS greeting cannot populate healthy=True on its own.
    Fingerprints and identity are private and deliberately excluded from repr.
    """

    applied_fingerprint: str = field(repr=False)
    verified_fingerprint: str = field(repr=False)
    process_identity: str = field(repr=False)
    generation: int
    checked_at: float
    healthy: bool | None


@dataclass(frozen=True)
class ApplyPlan:
    change: ChangeKind
    action: PlanAction
    reason: str


def _json_value(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError('Unsupported configuration value')


def _canonical(value):
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _validate_config(config):
    # This deliberately accepts only the project's tagged, generated configs.
    # It is a structural guard, not a replacement for xray run -test.
    if type(config) is not dict:
        raise ValueError('Expected a generated proxy configuration')
    _canonical(config)
    for section in ('inbounds', 'outbounds'):
        entries = config.get(section)
        if type(entries) is not list or (section == 'outbounds' and not entries):
            raise ValueError('Invalid handler collection')
        tags = set()
        for entry in entries:
            if type(entry) is not dict:
                raise ValueError('Invalid handler entry')
            tag = entry.get('tag')
            protocol = entry.get('protocol')
            if not isinstance(tag, str) or not tag.strip() or tag in tags:
                raise ValueError('Missing or duplicate handler tag')
            if not isinstance(protocol, str) or not protocol.strip():
                raise ValueError('Missing handler protocol')
            tags.add(tag)
    routing = config.get('routing')
    if type(routing) is not dict:
        raise ValueError('Invalid routing configuration')
    for section in ('rules', 'balancers'):
        entries = routing.get(section, [])
        if type(entries) is not list or any(type(item) is not dict for item in entries):
            raise ValueError('Invalid routing collection')


def config_fingerprint(config):
    """Private identity for a complete effective config; never log the input."""
    _validate_config(config)
    return hashlib.sha256(_canonical(config).encode('utf-8')).hexdigest()


def classify_config_change(current, desired):
    """Classify a delta conservatively, preserving every JSON array's order."""
    current_digest = config_fingerprint(current)
    desired_digest = config_fingerprint(desired)
    if current_digest == desired_digest:
        return ChangeKind.UNCHANGED

    def core(config):
        return {key: value for key, value in config.items() if key not in ('outbounds', 'routing')}

    def routing_base(config):
        return {key: value for key, value in config['routing'].items() if key not in ('rules', 'balancers')}
    if (_canonical(core(current)) != _canonical(core(desired)) or
            _canonical(routing_base(current)) != _canonical(routing_base(desired)) or
            [item['tag'] for item in current['outbounds']] !=
            [item['tag'] for item in desired['outbounds']]):
        # The first outbound is the fallback; topology changes are not an
        # ordinary key update. RoutingService does not apply domainStrategy.
        return ChangeKind.CORE

    outbound_changed = _canonical(current['outbounds']) != _canonical(desired['outbounds'])
    routing_changed = _canonical(current['routing']) != _canonical(desired['routing'])
    if outbound_changed and routing_changed:
        return ChangeKind.OUTBOUND_AND_ROUTING
    return ChangeKind.OUTBOUND if outbound_changed else ChangeKind.ROUTING


def _finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def plan_proxy_apply(
    current,
    desired,
    *,
    evidence=None,
    process_identity=None,
    generation=None,
    process_running=None,
    now,
    max_health_age=30.0,
):
    """Plan only. Unknown evidence requests verification, never a restart.

    now/checked_at use the same monotonic clock; max_health_age is a caller
    policy, not an empirically tuned threshold. Caller holds the future common
    transaction lock and revalidates generation/identity before execution.
    """
    if not _finite_number(now) or not _finite_number(max_health_age) or max_health_age < 0:
        raise ValueError('Invalid health freshness policy')
    change = classify_config_change(current, desired)
    if process_running is False:
        return ApplyPlan(change, PlanAction.RECOVER_RUNTIME, 'process_not_running')
    if process_running is not True or not isinstance(evidence, RuntimeEvidence):
        return ApplyPlan(change, PlanAction.VERIFY_RUNTIME, 'runtime_unattested')
    if (not isinstance(process_identity, str) or not process_identity or
            evidence.process_identity != process_identity or
            type(generation) is not int or generation < 0 or
            type(evidence.generation) is not int or evidence.generation != generation):
        return ApplyPlan(change, PlanAction.VERIFY_RUNTIME, 'runtime_identity_changed')
    fingerprint = config_fingerprint(current)
    if evidence.applied_fingerprint != fingerprint or evidence.verified_fingerprint != fingerprint:
        return ApplyPlan(change, PlanAction.VERIFY_RUNTIME, 'snapshot_unattested')
    if (not _finite_number(evidence.checked_at) or
            not 0 <= now - evidence.checked_at <= max_health_age):
        return ApplyPlan(change, PlanAction.VERIFY_RUNTIME, 'health_not_fresh')
    if evidence.healthy is False:
        return ApplyPlan(change, PlanAction.RECOVER_RUNTIME, 'data_plane_failed')
    if evidence.healthy is not True:
        return ApplyPlan(change, PlanAction.VERIFY_RUNTIME, 'health_unknown')
    actions = {
        ChangeKind.UNCHANGED: PlanAction.NOOP,
        ChangeKind.OUTBOUND: PlanAction.PREPARE_OUTBOUND,
        ChangeKind.ROUTING: PlanAction.PREPARE_ROUTING,
        ChangeKind.OUTBOUND_AND_ROUTING: PlanAction.PREPARE_TRANSACTION,
        ChangeKind.CORE: PlanAction.RESTART_REQUIRED,
    }
    return ApplyPlan(change, actions[change], 'confirmed_snapshot')
