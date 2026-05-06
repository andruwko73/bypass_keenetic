import ipaddress
import os
import re
import shutil
import subprocess


def detect_router_ip():
    try:
        output = subprocess.check_output(
            ['sh', '-c', "ip -4 addr show br0 | grep -Eo '([0-9]{1,3}\\.){3}[0-9]{1,3}' | head -n1"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if output:
            return output
    except Exception:
        pass
    return '192.168.1.1'


def is_local_web_client(address):
    try:
        ip_obj = ipaddress.ip_address((address or '').strip())
    except ValueError:
        return False
    return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local


def resolve_bind_host():
    candidate = detect_router_ip().strip()
    if not candidate:
        return ''
    try:
        ip_obj = ipaddress.ip_address(candidate)
    except ValueError:
        return ''
    if ip_obj.is_unspecified:
        return ''
    return candidate


def ensure_legacy_path(source_path, legacy_path):
    try:
        if os.path.islink(legacy_path) or os.path.exists(legacy_path):
            os.remove(legacy_path)
    except Exception:
        pass

    try:
        os.symlink(source_path, legacy_path)
        return
    except Exception:
        pass

    shutil.copyfile(source_path, legacy_path)


def escape_python(value):
    return (value or '').replace('\\', '\\\\').replace("'", "\\'")


def browser_port_is_valid(value):
    port = (value or '').strip()
    return not port or bool(re.fullmatch(r'\d{2,5}', port))
