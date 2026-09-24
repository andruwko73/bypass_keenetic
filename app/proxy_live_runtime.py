"""Recoverable, serialized runtime/key-file executor.

The bot supplies controlled startup, protocol health and an isolated candidate
check. Only a protocol-owned service callback may run inside file commit/recovery;
the common Xray lifecycle is never touched. Cold apply remains an explicit caller
policy for changes outside the qualified outbound-only subset.
"""
from copy import deepcopy
from contextlib import nullcontext
import json
from pathlib import Path
import time

from proxy_apply_attestation import AttestationStore
from proxy_apply_coordinator import StaleApply, _atomic_json, core_process_identity
from proxy_apply_plan import ChangeKind, PlanAction, classify_config_change, config_fingerprint, plan_proxy_apply
from proxy_apply_state import ApplyFileBundle, ApplyStateError, _regular
from xray_live_apply import (
    HysteriaCacheGuard, LiveApplyError, PersistUncertain, XrayApi, balancer_tag, managed_config,
    qualify_outbound, switch_prepared_outbound,
)


class ProxyLiveRuntime:
    """Executor for an attested, fixed-balancer core.

    All public mutation methods require the coordinator's execution lock.
    allowed_protocols is the deployment allowlist, narrower than lab eligibility.
    Retained generations are bounded; qualified detachment never uses a timer
    to infer drain and never calls Close on handlers serving existing flows.
    """

    def __init__(self, *, coordinator, directory, ram_directory, config_path, key_paths,
                 binary, api_port=10899, identity=None, clock=time.monotonic,
                 allowed_protocols=(), max_retained=8, detach_qualified=False, api=None,
                 metadata_paths=(), metadata_lock=None, metadata_updates=None,
                 resource_guard=None, max_attempts_per_minute=0,
                 key_encoder=None, service_protocols=(), service_apply=None):
        self.coordinator = coordinator
        self.directory, self.ram_directory = Path(directory), Path(ram_directory)
        self.config_path = Path(config_path).absolute()
        self.key_paths = {key: Path(path).absolute() for key, path in key_paths.items()}
        self.receipt_path = (self.directory / 'applied.json').absolute()
        self.pending_path = self.directory / 'pending.json'
        self.api_port, self.clock = api_port, clock
        self.allowed_protocols, self.max_retained = frozenset(allowed_protocols), max_retained
        self.detach_qualified = bool(detach_qualified)
        self.metadata_lock, self.metadata_updates = metadata_lock, metadata_updates
        self.key_encoder = key_encoder or (lambda protocol, key: (key.strip() + '\n').encode('utf-8'))
        self.service_protocols, self.service_apply = frozenset(service_protocols), service_apply
        if (not self.service_protocols.issubset(self.allowed_protocols) or
                self.service_protocols and not callable(self.service_apply)):
            raise ValueError('Invalid dependent service policy')
        if type(max_attempts_per_minute) is not int or not 0 <= max_attempts_per_minute <= 60:
            raise ValueError('Invalid apply rate budget')
        self.resource_guard, self.max_attempts_per_minute = resource_guard, max_attempts_per_minute
        self._attempts = []
        if (not self.allowed_protocols.issubset(self.key_paths) or
                type(max_retained) is not int or not 1 <= max_retained <= 32):
            raise ValueError('Invalid runtime capability/budget policy')
        self.identity = identity or (lambda: core_process_identity(binary, self.config_path))
        self.api = api or XrayApi(binary, port=api_port, directory=self.ram_directory)
        self.attestation = AttestationStore(self.ram_directory / 'health.json')
        self.hysteria_guard = HysteriaCacheGuard(self.ram_directory / 'hysteria-cache.json')
        self.bundle = ApplyFileBundle(self.directory, [self.config_path, self.receipt_path,
                                                      *self.key_paths.values(), *metadata_paths])

    def _owned(self):
        import threading
        if self.coordinator.lock._owner != threading.get_ident():
            raise RuntimeError('Runtime mutation requires the coordinator lock')

    def _receipt(self):
        raw, _ = _regular(self.receipt_path, 2 * 1024 * 1024)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            if (value['schema'] != 1 or type(value['generation']) is not int or value['generation'] < 0 or
                    not isinstance(value['process_identity'], str) or not value['process_identity'] or
                    not isinstance(value['targets'], dict) or not isinstance(value['retained'], list) or
                    not isinstance(value['observed'], str) or
                    config_fingerprint(value['logical']) != value['fingerprint']):
                raise ValueError
            managed_config(value['logical'], api_port=self.api_port, targets=value['targets'])
            return value
        except (ValueError, TypeError, KeyError):
            raise LiveApplyError('Applied state is invalid; controlled recovery is required') from None

    def _targets(self, logical):
        tags = [item['tag'] for item in logical['outbounds'] if item['tag'].startswith('proxy-')]
        try:
            previous = (self._receipt() or {}).get('targets', {})
        except LiveApplyError:
            # This path only builds a complete config for a controlled cold
            # load. It does not attest the currently running core.
            previous = {}
        return {tag: previous.get(tag, tag + '@initial.') for tag in tags}

    def config_for_load(self, logical):
        return managed_config(logical, api_port=self.api_port, targets=self._targets(logical))

    def _observe(self, targets):
        return self.api.observation([balancer_tag(tag) for tag in targets])

    def register_controlled_load(self, logical, *, previous_identity, generation):
        self._owned()
        if self.bundle.pending():
            raise LiveApplyError('File recovery must precede a controlled load')
        identity = self.identity()
        if not identity or identity == previous_identity:
            raise LiveApplyError('A new controlled core process was not confirmed')
        targets = self._targets(logical)
        expected = managed_config(logical, api_port=self.api_port, targets=targets)
        disk, _ = _regular(self.config_path, 2 * 1024 * 1024)
        try:
            matches = disk is not None and config_fingerprint(json.loads(disk)) == config_fingerprint(expected)
        except (ValueError, TypeError):
            matches = False
        if not matches or set(self.api.outbounds()) != {item['tag'] for item in expected['outbounds']}:
            raise LiveApplyError('Controlled configuration was not confirmed')
        observed = self._observe(targets)
        if identity != self.identity():
            raise LiveApplyError('Core changed during load confirmation')
        state = {'schema': 1, 'process_identity': identity, 'generation': generation,
                 'logical': logical, 'fingerprint': config_fingerprint(logical),
                 'targets': targets, 'retained': [], 'observed': observed}
        _atomic_json(self.receipt_path, state)
        self.hysteria_guard.initialize(logical, identity)
        self.attestation.record_loaded(logical, process_identity=identity,
                                       generation=generation, observed_fingerprint=observed)
        # A planned full load supersedes any runtime-only interrupted operation;
        # file journal recovery must already have happened before the load.
        self._clear_pending()

    def _clear_pending(self):
        try:
            self.pending_path.unlink()
            ApplyFileBundle._sync_directory(self.directory)
        except FileNotFoundError:
            pass

    def recover_files_before_startup(self):
        self._owned()
        result = self.bundle.recover()
        # A crash may have happened after the dependent service read staged
        # files but before their durable commit. Reconcile it with recovered
        # disk state before the caller can reload/attest the main core.
        pending, _ = _regular(self.pending_path, 16384)
        if pending:
            protocol = json.loads(pending).get('logical_tag', '').removeprefix('proxy-')
            if protocol in self.service_protocols and self.service_apply(protocol) is not True:
                raise LiveApplyError('Dependent service recovery was not confirmed')
        state = self._receipt()
        self.coordinator.recover_abandoned_manual(minimum_generation=(state or {}).get('generation', 0))
        return result

    def _detach_previous(self, state, target, ticket):
        """Detach a qualified idle-or-active handler without calling Close.

        Xray 26.2.6 RemoveHandler removes only the manager reference. Existing
        connections own their handler until they finish. This is NOT an idle
        timeout or a claim that the handler has been destroyed. The opt-in is
        permitted only after transport-specific continuity/resource tests.
        """
        if target not in state['retained'] or target in state['targets'].values():
            raise LiveApplyError('Cannot detach the selected handler')
        snapshot = self.api.snapshot([balancer_tag(tag) for tag in state['targets']])
        if self.api.fingerprint(snapshot) != state['observed'] or target not in snapshot['outbounds']:
            raise LiveApplyError('Runtime changed before handler retirement')
        expected = deepcopy(snapshot)
        del expected['outbounds'][target]
        expected_observed = self.api.fingerprint(expected)
        _atomic_json(self.pending_path, {'phase': 'retiring', 'target': target,
                                        'process_identity': state['process_identity'],
                                        'generation': ticket.generation})
        try:
            self.api.remove(target)
        except LiveApplyError:
            # An acknowledgement can be lost after a successful detach.
            if self._observe(state['targets']) != expected_observed:
                raise
        if (self.identity() != state['process_identity'] or
                self._observe(state['targets']) != expected_observed):
            raise LiveApplyError('Handler retirement was not confirmed')
        updated = deepcopy(state)
        updated['retained'].remove(target)
        updated['observed'] = expected_observed
        # Bookkeeping for a completed commit is required even when a newer
        # manual request arrived. It cannot change the selected route or key.
        _atomic_json(self.receipt_path, updated)
        state.update(updated)
        self._clear_pending()

    def try_apply(self, protocol, key, *, current, desired, ticket, verify, precheck):
        """Return 'hot'/'noop'/'unhealthy', or None for an explicit cold change.

        The caller must not interpret an exception as a cold-restart request.
        Without qualified detachment, previous handlers stay retained and
        max_retained prevents unbounded accumulation. With it, manager refs
        are detached only after the new configuration is durably committed.
        """
        self._owned()
        change = classify_config_change(current, desired)
        if protocol not in self.allowed_protocols:
            return None
        logical_tag = 'proxy-' + protocol
        old_out = {item['tag']: item for item in current['outbounds']}
        new_out = {item['tag']: item for item in desired['outbounds']}
        if (change not in (ChangeKind.UNCHANGED, ChangeKind.OUTBOUND) or logical_tag not in new_out):
            return None
        if change == ChangeKind.OUTBOUND and (not qualify_outbound(new_out[logical_tag]) or
                                              not qualify_outbound(old_out[logical_tag])):
            return None
        if change == ChangeKind.OUTBOUND and {
            tag for tag in old_out if json.dumps(old_out[tag], sort_keys=True) != json.dumps(new_out[tag], sort_keys=True)
        } != {logical_tag}:
            return None
        if self.bundle.pending() or self.pending_path.exists() or self.pending_path.is_symlink():
            raise LiveApplyError('An earlier transaction requires recovery')
        state = self._receipt()
        identity = self.identity()
        if (not identity or state is None or state['process_identity'] != identity or
                state['fingerprint'] != config_fingerprint(current)):
            raise LiveApplyError('Runtime is not attested; a controlled check is required')
        observed = self._observe(state['targets'])
        if observed != state['observed']:
            raise LiveApplyError('Runtime changed outside the coordinator')
        self.coordinator.require_current(ticket)
        if not self.hysteria_guard.check(new_out[logical_tag], identity):
            # Official core cannot accept changed auth/TLS at a cached HY2
            # destination. Do not run a misleading "healthy" probe with old auth.
            return None
        if change == ChangeKind.UNCHANGED:
            evidence = self.attestation.evidence(protocol, observed_fingerprint=observed)
            plan = plan_proxy_apply(current, desired, evidence=evidence, process_identity=identity,
                                    generation=state['generation'], process_running=True, now=self.clock())
            if plan.action == PlanAction.NOOP:
                return 'noop'
            healthy = verify() is True
            self.coordinator.require_current(ticket)
            if identity != self.identity() or self._observe(state['targets']) != observed:
                raise LiveApplyError('Runtime changed during verification')
            self.attestation.record_loaded(current, process_identity=identity, generation=state['generation'],
                                           observed_fingerprint=observed)
            self.attestation.record_health(protocol, config=current, process_identity=identity,
                                           generation=state['generation'], observed_fingerprint=observed,
                                           checked_at=self.clock(), healthy=healthy)
            return 'noop' if healthy else 'unhealthy'
        if len(state['retained']) >= self.max_retained:
            raise LiveApplyError('Retained generation budget reached; controlled drain is required')
        if self.resource_guard is not None and self.resource_guard() is not True:
            raise LiveApplyError('Insufficient resource budget for an isolated candidate')
        if self.max_attempts_per_minute:
            now = self.clock()
            self._attempts = [stamp for stamp in self._attempts if 0 <= now - stamp < 60]
            if len(self._attempts) >= self.max_attempts_per_minute:
                raise LiveApplyError('Apply rate budget reached; retry later')
            self._attempts.append(now)
        new_target = logical_tag + '@g' + str(ticket.generation) + '.'
        targets = dict(state['targets'], **{logical_tag: new_target})
        candidate_config = managed_config(desired, api_port=self.api_port, targets=targets)
        self.api.validate(candidate_config)
        if precheck() is not True:
            raise LiveApplyError('Isolated candidate verification failed')
        self.coordinator.require_current(ticket)

        # Keep reservations on failed API/data-plane trials too: they may have
        # initialized the official core's process-wide client cache.
        if not self.hysteria_guard.check(new_out[logical_tag], identity, reserve=True):
            raise LiveApplyError('Hysteria destination became incompatible')

        def checkpoint(phase, old, new):
            _atomic_json(self.pending_path, {
                'phase': phase, 'logical_tag': logical_tag, 'old': old, 'new': new,
                'process_identity': identity, 'generation': ticket.generation,
            })

        def persist(target):
            new_state = deepcopy(state)
            new_state.update(logical=desired, fingerprint=config_fingerprint(desired),
                             targets=targets, generation=ticket.generation,
                             retained=[*state['retained'], state['targets'][logical_tag]],
                             observed=self._observe(targets))
            with (self.metadata_lock if self.metadata_lock is not None else nullcontext()):
                updates = {
                    self.key_paths[protocol]: self.key_encoder(protocol, key),
                    self.config_path: json.dumps(candidate_config, ensure_ascii=False, indent=2).encode('utf-8'),
                    self.receipt_path: json.dumps(new_state, separators=(',', ':')).encode('utf-8'),
                }
                if self.metadata_updates is not None:
                    extra = {Path(path).absolute(): data
                             for path, data in self.metadata_updates(protocol, key).items()}
                    if updates.keys() & extra.keys():
                        raise LiveApplyError('Metadata cannot replace a core transaction file')
                    updates.update(extra)
                with self.coordinator.commit_guard(ticket):
                    self.bundle.prepare(updates)
                    service_attempted = False

                    def activate_service():
                        nonlocal service_attempted
                        service_attempted = True
                        return (self.service_apply(protocol) is True and self.identity() == identity and
                                self._observe(targets) == new_state['observed'])

                    try:
                        if protocol in self.service_protocols:
                            self.bundle.commit(after_write=activate_service)
                        else:
                            self.bundle.commit()
                    except (OSError, ApplyStateError):
                        try:
                            recovered = self.bundle.recover()
                        except (OSError, ApplyStateError):
                            raise PersistUncertain('Cannot determine durable file state') from None
                        if recovered != 'committed':
                            if service_attempted:
                                try:
                                    restored = self.service_apply(protocol) is True
                                except Exception:
                                    restored = False
                                if not restored:
                                    raise PersistUncertain('Dependent service rollback is uncertain') from None
                            raise LiveApplyError('File commit was rolled back') from None
            state.update(new_state)

        try:
            switch_prepared_outbound(
                self.api, logical_tag=logical_tag, old_target=state['targets'][logical_tag],
                candidate=new_out[logical_tag], generation=ticket.generation, checkpoint=checkpoint,
                require_current=lambda: self.coordinator.require_current(ticket), verify=verify,
                persist=persist, current_identity=self.identity, expected_identity=identity,
            )
        except LiveApplyError:
            # Only a positively completed API rollback may clear the checkpoint.
            raw, _ = _regular(self.pending_path, 16384)
            if raw and json.loads(raw).get('phase') == 'rolled_back' and not self.bundle.pending():
                self._clear_pending()
            raise
        # After the durable commit, cleanup failures must never roll back the
        # newly selected key. Leave a recovery marker and report confirmed hot
        # apply with deferred cleanup; a later apply will refuse unknown state.
        cleanup_deferred = False
        if self.detach_qualified:
            try:
                self._detach_previous(state, state['retained'][-1], ticket)
            except (LiveApplyError, StaleApply, OSError):
                cleanup_deferred = True
        self.attestation.record_loaded(desired, process_identity=identity, generation=ticket.generation,
                                       observed_fingerprint=state['observed'])
        self.attestation.record_health(protocol, config=desired, process_identity=identity,
                                       generation=ticket.generation, observed_fingerprint=state['observed'],
                                       checked_at=self.clock(), healthy=True)
        if not cleanup_deferred:
            self._clear_pending()
        return 'hot_cleanup_pending' if cleanup_deferred else 'hot'
