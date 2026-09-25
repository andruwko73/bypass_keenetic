"""Manual intent must not be vetoed by reachability; automation stays strict."""
import ast
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from proxy_config_builder import build_proxy_core_config
from proxy_apply_coordinator import ApplyCoordinator
from proxy_live_runtime import ProxyLiveRuntime
from proxy_live_services import encode_key, restart_service
from proxy_protocols import proxy_outbound_from_key
from xray_live_apply import LiveApplyError
from test_proxy_live_runtime import Api

PROTOCOLS = ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks', 'hysteria2')
PORTS = dict(vmess=10810, vmess_transparent=10817, vless=10811, vless_transparent=10812,
             vless2=10813, vless2_transparent=10814, shadowsocks_bot=10815, trojan_bot=10816,
             shadowsocks=1080, trojan=1081, hysteria2=10840, hysteria2_transparent=10841)


def key(proto, name):
    host = name + '.invalid'
    if proto in ('vless', 'vless2'):
        return 'vless://00000000-0000-4000-8000-000000000001@' + host + ':443?security=tls'  # Synthetic fixture.
    if proto == 'vmess':
        return 'vmess://' + base64.b64encode(json.dumps(dict(v='2', add=host, port='443',
            id='00000000-0000-4000-8000-000000000001', aid='0', net='tcp', tls='tls')).encode()).decode()
    if proto == 'trojan':
        return 'trojan://synthetic@' + host + ':443?security=tls'  # Synthetic fixture.
    if proto == 'shadowsocks':
        return 'ss://YWVzLTEyOC1nY206c3ludGhldGlj@' + host + ':443'  # Synthetic fixture.
    return 'hy2://synthetic@' + host + ':443?sni=' + host  # Synthetic fixture.


def config(keys):
    args = {('vless_key' if proto == 'vless' else proto + '_key'): value for proto, value in keys.items()}
    return build_proxy_core_config(**args, ports=PORTS, error_log_path='/dev/null',
                                  include_vmess_transparent=True, reserve_protocol_slots=True)


@pytest.mark.parametrize('proto', PROTOCOLS)
def test_offline_manual_first_replace_last_delete_and_automatic_guard(tmp_path, proto):
    control, api = ApplyCoordinator(tmp_path / 'ram'), Api()
    path, keypath = tmp_path / 'config', tmp_path / 'key'
    (tmp_path / 'private').mkdir()
    (tmp_path / 'ram').mkdir()
    alias = tmp_path / 'legacy-key'; alias.write_text('old-legacy-key')
    runtime = ProxyLiveRuntime(coordinator=control, directory=tmp_path / 'private',
        ram_directory=tmp_path / 'ram', config_path=path,
        key_paths={p: keypath if p == proto else tmp_path / ('key-' + p) for p in PROTOCOLS},
        key_aliases={proto: [alias]}, binary='unused', api=api, identity=lambda: 'boot:1:10',
        allowed_protocols=PROTOCOLS, detach_qualified=True,
        key_encoder=lambda p, k: encode_key(p, k, ports=PORTS))
    current = config({})
    path.write_text(json.dumps(runtime.config_for_load(current)))
    api.load(runtime.config_for_load(current))
    with control.lock:
        runtime.register_controlled_load(current, previous_identity=None, generation=0)
    probes = []
    def offline():
        probes.append('called')
        return False
    for value in (key(proto, 'one'), key(proto, 'two'), ''):
        desired = config({proto: value})
        assert current['inbounds'] == desired['inbounds']
        assert current['routing'] == desired['routing']
        ticket = control.request_manual()
        with control.transaction(ticket, manual=True):
            assert runtime.try_apply(proto, value, current=current, desired=desired, ticket=ticket,
                verify=offline, precheck=offline, require_health=False) == 'hot'
        assert keypath.read_bytes() == encode_key(proto, value, ports=PORTS)
        assert runtime.attestation.evidence(proto, observed_fingerprint=runtime._receipt()['observed']).healthy is None
        assert len(api.handlers) == 8  # six selected handlers, one guard, direct
        current = desired
    assert probes == [] and alias.read_bytes() == b''
    assert all(o['protocol'] == 'blackhole' for o in current['outbounds'] if o['tag'].startswith('proxy-'))
    original = path.read_bytes()
    ticket = control.request_manual()
    with control.transaction(ticket, manual=True), pytest.raises(LiveApplyError, match='verification failed'):
        runtime.try_apply(proto, key(proto, 'three'), current=current, desired=config({proto: key(proto, 'three')}),
                          ticket=ticket, verify=offline, precheck=offline)
    assert probes == ['called'] and path.read_bytes() == original


@pytest.mark.parametrize('proto', ('trojan', 'shadowsocks'))
def test_last_key_stops_only_owned_service(proto):
    calls = []
    assert restart_service(proto, 12345, enabled=False,
        run=lambda args, **kw: calls.append(args) or SimpleNamespace(returncode=0),
        listening=lambda p, port: False)
    assert len(calls) == 1 and calls[0][1] == 'stop'
    assert 'xray' not in calls[0][0]


def bot_functions(names):
    tree = ast.parse((ROOT / 'app' / 'bot.py').read_text(encoding='utf-8'))
    return compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names],
                              type_ignores=[]), '<bot subset>', 'exec')


@pytest.mark.parametrize('proto', PROTOCOLS)
@pytest.mark.parametrize('operation', ('inactive', 'active', 'last', 'invalid_remaining', 'local_failure'))
def test_delete_does_not_healthcheck_and_failed_local_apply_keeps_pool(proto, operation):
    import key_pool_store as store
    old, replacement, inactive = key(proto, 'old'), key(proto, 'replacement'), key(proto, 'inactive')
    values = [old] if operation == 'last' else [old, replacement, inactive]
    if operation == 'invalid_remaining':
        values = [old, 'invalid']
    saved = {proto: list(values)}
    events = []
    def save(path, pools):
        saved.clear(); saved.update(deepcopy(pools))
    def install(p, k, *, verify, require_health):
        assert verify is False and require_health is False
        if operation == 'local_failure':
            raise OSError('synthetic disk failure')
        events.append(('install', p, k))
    ns = dict(key_pool_lock=threading.RLock(), KEY_POOLS_PATH='unused',
        _pool_delete_context=threading.local(),
        _key_pool_store=lambda: SimpleNamespace(load_key_pools=lambda _: deepcopy(saved), save_key_pools=save,
            delete_pool_key=store.delete_pool_key, set_active_key=store.set_active_key),
        _load_current_keys=lambda: {proto: old}, _dedupe_key_list=lambda v: list(dict.fromkeys(v)),
        _proxy_outbound_from_key=proxy_outbound_from_key, _install_key_for_protocol=install,
        _clear_installed_key_for_protocol=lambda p: events.append(('disable', p)),
        _audit_key_switch=lambda *a: None, _forget_unreferenced_key_probes=lambda *a: None,
        _invalidate_web_status_cache=lambda: None, _invalidate_key_status_cache=lambda: None,
        _invalidate_pool_data_cache=lambda: None, _schedule_applied_pool_key_probe=lambda *a: events.append(('probe', *a)))
    exec(bot_functions({'_delete_pool_key'}), ns)
    removed = inactive if operation == 'inactive' else old
    if operation == 'local_failure':
        with pytest.raises(OSError):
            ns['_delete_pool_key'](proto, removed)
        assert saved[proto] == values
    else:
        ns['_delete_pool_key'](proto, removed)
        assert removed not in saved[proto]
        if operation == 'active':
            assert events == [('install', proto, replacement), ('probe', proto, replacement)]
        elif operation in ('last', 'invalid_remaining'):
            assert events == [('disable', proto)]
        else:
            assert events == []
    assert ns['_pool_delete_context'].removed_keys == ()
