"""Restricted Xray 26.2.6 API adapter for coordinated hot key changes.

Config/state must be attested by the caller;
data-plane validation, durable key storage and crash recovery are required.
No API exception is interpreted as permission to restart the shared core.
"""
from copy import deepcopy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import tempfile


API_TAG = 'bypass-api'
API_INBOUND = 'bypass-api-in'
DEFAULT_GUARD = 'bypass-default-guard'


class LiveApplyError(RuntimeError):
    """Errors deliberately exclude CLI output and configuration secrets."""


class PersistUncertain(LiveApplyError):
    """Disk commit point is unknown; do not guess which runtime to restore."""


class HysteriaCacheGuard:
    """26.2.6 caches HY2 clients by destination, ignoring new auth/TLS settings.

    Remember even failed trials for the lifetime of an attested core. Only
    hashes live in RAM; missing/corrupt history cannot authorize a hot switch.
    See upstream XTLS/Xray-core#5911. This guards, rather than fixes, that bug.
    """

    def __init__(self, path, limit=32):
        self.path, self.limit = Path(path), limit

    @staticmethod
    def _entry(outbound):
        if outbound.get('protocol') != 'hysteria':
            return None
        settings = outbound.get('settings') or {}
        address = str(settings.get('address', '')).lower()
        try:
            address = str(ipaddress.ip_address(address.strip('[]')))
        except ValueError:
            pass
        endpoint = [address, settings.get('port')]
        value = {key: item for key, item in outbound.items() if key != 'tag'}
        digest = lambda item: hashlib.sha256(json.dumps(item, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return digest(endpoint), digest(value)

    def initialize(self, logical, identity):
        from proxy_apply_coordinator import _atomic_json
        entries = {}
        for outbound in logical['outbounds']:
            entry = self._entry(outbound)
            if entry:
                endpoint, spec = entry
                if endpoint in entries and entries[endpoint] != spec:
                    raise LiveApplyError('Conflicting Hysteria destinations in controlled config')
                entries[endpoint] = spec
        _atomic_json(self.path, {'schema': 1, 'identity': identity, 'entries': entries})

    def check(self, outbound, identity, *, reserve=False):
        entry = self._entry(outbound)
        if entry is None:
            return True
        from proxy_apply_state import _regular
        from proxy_apply_coordinator import _atomic_json
        try:
            raw, _ = _regular(self.path, 16384)
            value = json.loads(raw)
            entries = value['entries']
            if (value['schema'] != 1 or value['identity'] != identity or not isinstance(entries, dict) or
                    len(entries) > self.limit or any(len(k) != 64 or len(v) != 64 for k, v in entries.items())):
                raise ValueError
        except (OSError, ValueError, TypeError, KeyError):
            raise LiveApplyError('Hysteria cache history requires a controlled load') from None
        endpoint, spec = entry
        if endpoint in entries:
            return entries[endpoint] == spec
        if len(entries) >= self.limit:
            raise LiveApplyError('Hysteria destination budget reached; controlled load required')
        if reserve:
            entries[endpoint] = spec
            _atomic_json(self.path, value)
        return True


def balancer_tag(logical_tag):
    return 'bypass-choice-' + logical_tag


def managed_config(config, *, api_port, targets=None):
    """Prepare fixed balancers; hot operations never reload the ruleset.

    Generation selectors are complete tags with a final delimiter. Xray's
    selector is a prefix match, so a plain 'proxy-vless' would also select V2.
    The permanent default guard prevents missing handlers falling through to
    a different proxy or direct. The final rule implements the original default.
    """
    from proxy_apply_plan import config_fingerprint
    config_fingerprint(config)
    if type(api_port) is not int or not 1 <= api_port <= 65535:
        raise ValueError('Invalid API listener')
    result = deepcopy(config)
    if 'api' in result or result['routing'].get('balancers'):
        raise ValueError('Existing API/balancer configuration requires migration')
    if any(item.get('proxySettings') or
           ((item.get('streamSettings') or {}).get('sockopt') or {}).get('dialerProxy')
           for item in result['outbounds']):
        raise ValueError('Chained handlers require a separate migration')
    tags = {item['tag'] for item in result['outbounds'] + result['inbounds']}
    if any(tag.startswith('bypass-') or '@' in tag for tag in tags):
        raise ValueError('Reserved runtime tag')
    if any(str(item.get('port')) == str(api_port) for item in result['inbounds']):
        raise ValueError('API listener conflicts with an existing inbound')
    managed = [item['tag'] for item in result['outbounds'] if item['tag'].startswith('proxy-')]
    targets = dict(targets or {tag: tag + '@initial.' for tag in managed})
    if (set(targets) != set(managed) or len(set(targets.values())) != len(targets) or
            any(not value.startswith(tag + '@') or not value.endswith('.')
                for tag, value in targets.items())):
        raise ValueError('Invalid generation mapping')
    original_default = result['outbounds'][0]['tag']
    result['api'] = {'tag': API_TAG, 'services': ['HandlerService', 'RoutingService']}
    result['inbounds'].append({
        'tag': API_INBOUND, 'listen': '127.0.0.1', 'port': api_port,
        'protocol': 'dokodemo-door', 'settings': {'address': '127.0.0.1'},
    })
    for item in result['outbounds']:
        if item['tag'] in targets:
            item['tag'] = targets[item['tag']]
    result['outbounds'].insert(0, {'tag': DEFAULT_GUARD, 'protocol': 'blackhole'})
    routing = result['routing']
    routing['balancers'] = [
        {'tag': balancer_tag(tag), 'selector': [targets[tag]], 'strategy': {'type': 'random'}}
        for tag in managed
    ]
    for rule in routing['rules']:
        if rule.get('outboundTag') in targets:
            rule['balancerTag'] = balancer_tag(rule.pop('outboundTag'))
    default_rule = {'type': 'field', 'network': 'tcp,udp'}
    if original_default in targets:
        default_rule['balancerTag'] = balancer_tag(original_default)
    else:
        default_rule['outboundTag'] = original_default
    routing['rules'].append(default_rule)
    routing['rules'].insert(0, {'type': 'field', 'inboundTag': [API_INBOUND], 'outboundTag': API_TAG})
    return result


class XrayApi:
    def __init__(self, binary, *, port, directory, timeout=5, run=subprocess.run):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid API listener')
        self.binary, self.port = str(binary), port
        self.directory, self.timeout, self.run = Path(directory), timeout, run

    def _command(self, command, *args, config=None, validate=False):
        path = None
        try:
            if config is not None:
                fd, path = tempfile.mkstemp(prefix='candidate-', suffix='.json', dir=self.directory)
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(config, stream, allow_nan=False)
                args = (*args, path)
            argv = ([self.binary, 'run', '-test', '-c', path] if validate else
                    [self.binary, 'api', command, '--server=127.0.0.1:' + str(self.port),
                     '-timeout=' + str(self.timeout), *args])
            result = self.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=self.timeout + 2, check=False)
            if result.returncode != 0 or len(result.stdout) > 2 * 1024 * 1024:
                raise LiveApplyError('Xray operation failed; runtime must be inspected')
            return result.stdout
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            raise LiveApplyError('Xray operation did not complete') from None
        finally:
            if path is not None:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass

    def validate(self, config):
        self._command('', config=config, validate=True)

    def outbounds(self):
        try:
            value = json.loads(self._command('lso'))
            items = value['outbounds']
            if not isinstance(items, list):
                raise ValueError
            return {item['tag']: item for item in items}
        except (ValueError, KeyError, TypeError):
            raise LiveApplyError('Xray outbound state is unavailable') from None

    def target(self, balancer):
        try:
            value = json.loads(self._command('bi', '-json', balancer))
            result = value['balancer']['override'].get('target', '')
            if not isinstance(result, str):
                raise ValueError
            return result
        except (ValueError, KeyError, TypeError):
            raise LiveApplyError('Xray route state is unavailable') from None

    def snapshot(self, balancers):
        """Private observable state. It contains credentials; never log it."""
        try:
            outbounds = self.outbounds()
            inbounds = json.loads(self._command('lsi'))['inbounds']
            rules = json.loads(self._command('lsrules'))
            if not isinstance(inbounds, list) or not isinstance(rules, dict):
                raise ValueError
            state = {
                'outbounds': outbounds,
                'inbounds': sorted(inbounds, key=lambda item: item['tag']),
                'rules': rules,
                'targets': {tag: self.target(tag) for tag in sorted(balancers)},
            }
            return state
        except (ValueError, KeyError, TypeError):
            raise LiveApplyError('Xray mutable state is unavailable') from None

    @staticmethod
    def fingerprint(state):
        canonical = json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def observation(self, balancers):
        """Fingerprint observable mutable state; never expose handler settings."""
        return self.fingerprint(self.snapshot(balancers))

    def add(self, outbound):
        self._command('ado', config={'outbounds': [outbound]})

    def select(self, balancer, target):
        self._command('bo', '-b', balancer, target)
        if self.target(balancer) != target:
            raise LiveApplyError('Xray route change was not confirmed')

    def remove(self, tag):
        self._command('rmo', tag)
        if tag in self.outbounds():
            raise LiveApplyError('Xray handler removal was not confirmed')


def qualify_outbound(outbound):
    """Exact transport subset covered by the 26.2.6 laboratory matrix.

    Deployment must additionally coordinate sidecar services and guard the HY2
    destination cache. Alternative transports and chained handlers stay excluded.
    """
    stream = outbound.get('streamSettings') or {}
    protocol, security = outbound.get('protocol'), stream.get('security', 'none')
    if protocol == 'hysteria':
        mask = (stream.get('finalmask') or {}).get('udp', [])
        settings = outbound.get('settings') or {}
        hy = stream.get('hysteriaSettings') or {}
        return (stream.get('network') == 'hysteria' and security == 'tls' and
                settings.get('version') == hy.get('version') == 2 and
                isinstance(settings.get('address'), str) and bool(settings['address']) and
                type(settings.get('port')) is int and 1 <= settings['port'] <= 65535 and
                not (outbound.get('mux') or {}).get('enabled') and not outbound.get('proxySettings') and
                not stream.get('sockopt') and not (stream.get('finalmask') or {}).get('tcp') and
                all(item.get('type') == 'salamander' for item in mask) and
                set(hy).issubset({'version', 'auth'}))
    permitted = {'vless': ('none', 'tls', 'reality'), 'vmess': ('none', 'tls'),
                 'trojan': ('none', 'tls'), 'shadowsocks': ('none',)}
    if (security not in permitted.get(protocol, ()) or
            stream.get('network', 'tcp') not in ('tcp', 'raw') or
            outbound.get('proxySettings') or (stream.get('sockopt') or {}).get('dialerProxy')):
        return False
    mux = outbound.get('mux') or {}
    if mux.get('enabled') and protocol not in ('vless', 'vmess'):
        return False
    users = [user for server in (outbound.get('settings') or {}).get('vnext', [])
             for user in server.get('users', [])]
    if any(user.get('flow') not in (None, '', 'xtls-rprx-vision') for user in users):
        return False
    if any(user.get('flow') == 'xtls-rprx-vision' for user in users):
        return protocol == 'vless' and security in ('tls', 'reality') and not mux.get('enabled')
    return True


def switch_prepared_outbound(api, *, logical_tag, old_target, candidate, generation,
                             checkpoint, require_current, verify, persist,
                             current_identity, expected_identity):
    """Exercise reversible add/select/verify/persist on an attested generation.

    Executor owns the global lock. checkpoint() must be durable before network
    mutation; persist() must recover atomically on crash/disk failure and guard
    intent until it completes. Old handlers are retained for a caller-owned
    drain policy. No deletion or restart is attempted when state is uncertain.
    """
    if not qualify_outbound(candidate):
        raise LiveApplyError('Transport has not passed hot-apply qualification')
    if type(generation) is not int or generation < 1:
        raise ValueError('Invalid apply generation')
    new_target = logical_tag + '@g' + str(generation) + '.'
    balancer = balancer_tag(logical_tag)
    added = deepcopy(candidate)
    added['tag'] = new_target

    def check():
        require_current()
        if current_identity() != expected_identity:
            raise LiveApplyError('Xray process identity changed')

    check()
    existing = api.outbounds()
    if old_target not in existing or new_target in existing:
        raise LiveApplyError('Xray generation state differs from the attested snapshot')
    previous_override = api.target(balancer)
    if previous_override not in ('', old_target):
        raise LiveApplyError('Xray route differs from the attested snapshot')
    checkpoint('prepared', old_target, new_target)
    try:
        check()
        api.add(added)
        if new_target not in api.outbounds():
            raise LiveApplyError('Candidate handler was not confirmed')
        checkpoint('added', old_target, new_target)
        check()
        # The handler may have been added, but the old selector excludes its
        # complete generation tag. It cannot receive ordinary flows yet.
        api.select(balancer, new_target)
        checkpoint('selected', old_target, new_target)
        if verify() is not True:
            raise LiveApplyError('Candidate data-plane verification failed')
        check()
        checkpoint('verified', old_target, new_target)
        persist(new_target)
        return new_target
    except PersistUncertain:
        checkpoint('recovery_required', old_target, new_target)
        raise LiveApplyError('Disk state is uncertain; explicit recovery is required') from None
    except Exception:
        # An API timeout can occur after a successful mutation. Read back the
        # actual target before deciding what can safely be reversed.
        try:
            if current_identity() != expected_identity:
                raise LiveApplyError('Xray process changed during recovery')
            selected = api.target(balancer)
            if selected == new_target:
                # Restore the exact previous override, including the empty
                # value that means the fixed selector. Selecting old_target
                # instead would restore traffic but invalidate its receipt.
                api.select(balancer, previous_override)
            elif selected not in ('', old_target):
                raise LiveApplyError('A different route now owns this balancer')
            if new_target in api.outbounds():
                api.remove(new_target)
            checkpoint('rolled_back', old_target, new_target)
        except Exception:
            checkpoint('recovery_required', old_target, new_target)
            raise LiveApplyError('Apply incomplete; explicit recovery is required') from None
        raise LiveApplyError('Candidate was not applied; previous route restored') from None
