import json
import os
import tempfile

from proxy_config_builder import build_proxy_core_config
from proxy_key_store import load_current_keys
from service_catalog import CONNECTIVITY_CHECK_DOMAINS
from transparent_route_policy import compile_protocol_policies, normalize_protocol_set
from unblock_lists import UNBLOCK_DIR, read_unblock_list_entries


XRAY_CONFIG_DIR = '/opt/etc/xray'
V2RAY_CONFIG_DIR = '/opt/etc/v2ray'
XRAY_SERVICE_PATH = '/opt/etc/init.d/S24xray'


def _configured_protocols(config_module, name):
    return normalize_protocol_set(getattr(config_module, name, ()))


def _transparent_route_entries(unblock_dir=UNBLOCK_DIR):
    routes = {'vmess': 'vmess', 'vless': 'vless', 'vless2': 'vless-2'}
    result = {}
    for protocol, route_name in routes.items():
        try:
            result[protocol] = read_unblock_list_entries(route_name, unblock_dir=unblock_dir)
        except Exception:
            result[protocol] = ()
    return result


def _config_port(config_module, name, default):
    return str(getattr(config_module, name, default))


def _write_json_atomic(path, payload, mode=0o644):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def rebuild_proxy_core_config(
    *,
    config_module=None,
    core_config_dir=None,
    xray_config_dir=XRAY_CONFIG_DIR,
    v2ray_config_dir=V2RAY_CONFIG_DIR,
    output_path=None,
):
    if config_module is None:
        import bot_config as config_module
    if core_config_dir is None:
        core_config_dir = xray_config_dir if os.path.exists(XRAY_SERVICE_PATH) else v2ray_config_dir
    output_path = output_path or os.path.join(core_config_dir, 'config.json')
    vless_port = int(_config_port(config_module, 'localportvless', 10811))
    keys = load_current_keys(
        os.path.join(core_config_dir, 'vmess.key'),
        os.path.join(core_config_dir, 'vless.key'),
        os.path.join(core_config_dir, 'vless2.key'),
        xray_config_dir,
        v2ray_config_dir,
    )
    strict_transparent_protocols = _configured_protocols(config_module, 'xray_strict_transparent_protocols')
    payload = build_proxy_core_config(
        vmess_key=keys.get('vmess') or '',
        vless_key=keys.get('vless') or '',
        vless2_key=keys.get('vless2') or '',
        shadowsocks_key=keys.get('shadowsocks') or '',
        trojan_key=keys.get('trojan') or '',
        ports={
            'vmess': _config_port(config_module, 'localportvmess', 10810),
            'vmess_transparent': str(vless_port + 4),
            'vless': str(vless_port),
            'vless_transparent': str(vless_port + 1),
            'vless2': str(vless_port + 2),
            'vless2_transparent': str(vless_port + 3),
            'shadowsocks_bot': _config_port(config_module, 'localportsh_bot', 10820),
            'trojan_bot': _config_port(config_module, 'localporttrojan_bot', 10830),
            'shadowsocks_tproxy': _config_port(config_module, 'localportsh_tproxy', 11802),
            'vmess_tproxy': _config_port(config_module, 'localportvmess_tproxy', 11815),
            'vless_tproxy': _config_port(config_module, 'localportvless_tproxy', 11812),
            'vless2_tproxy': _config_port(config_module, 'localportvless2_tproxy', 11814),
            'trojan_tproxy': _config_port(config_module, 'localporttrojan_tproxy', 11829),
        },
        error_log_path=os.path.join(core_config_dir, 'error.log'),
        access_log_path='/dev/null',
        loglevel='warning',
        connectivity_check_domains=CONNECTIVITY_CHECK_DOMAINS,
        include_vmess_transparent=True,
        route_only_transparent_protocols=_configured_protocols(config_module, 'xray_route_only_transparent_protocols'),
        route_only_tproxy_protocols=_configured_protocols(config_module, 'xray_route_only_tproxy_protocols'),
        strict_transparent_protocols=strict_transparent_protocols,
        transparent_route_policies=compile_protocol_policies(
            _transparent_route_entries(),
            strict_transparent_protocols,
        ),
        bittorrent_direct_enabled=bool(getattr(config_module, 'xray_bittorrent_direct_enabled', False)),
    )
    _write_json_atomic(output_path, payload)
    return output_path


def main():
    output_path = rebuild_proxy_core_config()
    print(f'Core proxy config rebuilt: {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
