#!/bin/sh

# Shared transactional update/rollback checks. This file is sourced by
# script.sh and by the generated rollback script; keep it POSIX-sh compatible.

BYPASS_RUNTIME_GUARD_REASON=""

bypass_guard_fail() {
    BYPASS_RUNTIME_GUARD_REASON="$1"
    return 1
}

bypass_router_ip() {
    router_ip="$(ip -4 addr show br0 2>/dev/null | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -n1 || true)"
    printf '%s\n' "${router_ip:-192.168.1.1}"
}

bypass_main_application_pids() {
    main_path="${1:-/opt/etc/bot/main.py}"
    lock_pid=""
    [ -f /tmp/bypass_telegram_bot_main.lock/pid ] && \
        lock_pid="$(cat /tmp/bypass_telegram_bot_main.lock/pid 2>/dev/null || true)"
    case "$lock_pid" in
        ''|*[!0-9]*) ;;
        *)
            if [ -r "/proc/$lock_pid/cmdline" ] && grep -qa "$main_path" "/proc/$lock_pid/cmdline"; then
                printf '%s\n' "$lock_pid"
                return 0
            fi
            ;;
    esac
    pgrep -f "python3.*$main_path" 2>/dev/null | head -n1 || true
}

bypass_clear_stale_main_lock() {
    main_path="${1:-/opt/etc/bot/main.py}"
    [ -d /tmp/bypass_telegram_bot_main.lock ] || return 0
    [ -z "$(bypass_main_application_pids "$main_path")" ] || return 0
    rm -rf /tmp/bypass_telegram_bot_main.lock 2>/dev/null || return 1
}

bypass_capture_bot_start_failure() {
    source_log="${1:-/opt/etc/bot/error.log}"
    target_log="${2:-/opt/root/bypass-last-failed-update-bot.log}"
    label="${3:-update}"
    temporary="${target_log}.tmp.$$"
    umask 077
    {
        printf '%s label=%s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date)" "$label"
        [ -f "$source_log" ] && tail -c 262144 "$source_log" 2>/dev/null || true
    } > "$temporary" || return 1
    chmod 600 "$temporary" 2>/dev/null || true
    mv -f "$temporary" "$target_log"
}

bypass_route_specs() {
    printf '%s\n' \
        'shadowsocks.txt unblocksh' \
        'vmess.txt unblockvmess' \
        'vless.txt unblockvless' \
        'vless-2.txt unblockvless2' \
        'trojan.txt unblocktroj' \
        'hysteria2.txt unblockhy2'
}

bypass_runtime_network_ready() {
    unblock_dir="${BYPASS_UNBLOCK_DIR:-/opt/etc/unblock}"
    command -v ipset >/dev/null 2>&1 || return 0
    command -v iptables-save >/dev/null 2>&1 || return 0
    nat_rules="$(iptables-save -t nat 2>/dev/null)" || {
        bypass_guard_fail 'таблица NAT недоступна'
        return 1
    }
    while read -r route_file set_name; do
        [ -n "$route_file" ] || continue
        route_path="$unblock_dir/$route_file"
        [ -f "$route_path" ] || continue
        grep -Eq '^[[:space:]]*[^#[:space:]]' "$route_path" 2>/dev/null || continue
        ipset list "$set_name" >/dev/null 2>&1 || \
            bypass_guard_fail "не создан ipset $set_name" || return 1
        printf '%s\n' "$nat_rules" | grep -F -- "--match-set $set_name dst" >/dev/null 2>&1 || \
            bypass_guard_fail "нет правила NAT для $set_name" || return 1
    done <<EOF
$(bypass_route_specs)
EOF
    return 0
}

bypass_apply_runtime_network_rules() {
    ipset_script="${BYPASS_IPSET_BOOT_SCRIPT:-/opt/etc/ndm/fs.d/100-ipset.sh}"
    redirect_script="${BYPASS_REDIRECT_SCRIPT:-/opt/etc/ndm/netfilter.d/100-redirect.sh}"
    attempt=0
    while [ "$attempt" -lt 4 ]; do
        attempt=$((attempt + 1))
        [ ! -x "$ipset_script" ] || "$ipset_script" start >/dev/null 2>&1 || true
        if [ -x "$redirect_script" ]; then
            table=nat "$redirect_script" >/dev/null 2>&1 || true
            table=mangle "$redirect_script" >/dev/null 2>&1 || true
            type=ip6tables table=filter "$redirect_script" >/dev/null 2>&1 || true
        fi
        bypass_runtime_network_ready && return 0
        sleep 2
    done
    return 1
}

bypass_config_port() {
    key="$1"
    default_port="$2"
    config_path="${BYPASS_BOT_CONFIG_PATH:-/opt/etc/bot/bot_config.py}"
    [ -f "$config_path" ] || config_path=/opt/etc/bot_config.py
    value="$(grep "^${key}[[:space:]]*=" "$config_path" 2>/dev/null | grep -Eo '[0-9]{1,5}' | head -n1)"
    printf '%s\n' "${value:-$default_port}"
}

bypass_active_socks_port() {
    mode="$(cat /opt/etc/bot_proxy_mode 2>/dev/null || true)"
    case "$mode" in
        shadowsocks) bypass_config_port localportsh_bot 10820 ;;
        vmess) bypass_config_port localportvmess 10810 ;;
        vless) bypass_config_port localportvless 10811 ;;
        vless2) bypass_config_port localportvless2 10813 ;;
        trojan) bypass_config_port localporttrojan_bot 10830 ;;
        hysteria2) bypass_config_port localporthysteria2 10840 ;;
        *) return 0 ;;
    esac
}

bypass_socks_ready() {
    socks_port="$(bypass_active_socks_port)"
    [ -n "$socks_port" ] || return 0
    python_bin="$(command -v python3 2>/dev/null || true)"
    [ -n "$python_bin" ] || return 0
    "$python_bin" - "$socks_port" <<'PY' >/dev/null 2>&1
import socket
import sys

with socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=3) as sock:
    sock.settimeout(3)
    sock.sendall(b'\x05\x01\x00')
    if sock.recv(2) != b'\x05\x00':
        raise SystemExit(1)
PY
}

bypass_wait_application_ready() {
    bot_service="${1:-/opt/etc/init.d/S99telegram_bot}"
    timeout_seconds="${2:-45}"
    heartbeat_seconds="${BYPASS_RUNTIME_HEARTBEAT_SECONDS:-10}"
    case "$heartbeat_seconds" in
        ''|*[!0-9]*|0) heartbeat_seconds=10 ;;
    esac
    router_ip="$(bypass_router_ip)"
    started_at="$(date +%s)"
    deadline=$(( started_at + timeout_seconds ))
    next_heartbeat="$started_at"
    stable_samples=0
    while :; do
        now="$(date +%s)"
        [ "$now" -lt "$deadline" ] || break
        if [ "$now" -ge "$next_heartbeat" ]; then
            elapsed=$(( now - started_at ))
            echo "Ожидаем готовность программы и сети: ${elapsed}/${timeout_seconds} сек."
            if command -v bypass_runtime_status_heartbeat >/dev/null 2>&1; then
                bypass_runtime_status_heartbeat "$elapsed" "$timeout_seconds" || true
            fi
            next_heartbeat=$(( now + heartbeat_seconds ))
        fi
        ready=1
        [ -x "$bot_service" ] && "$bot_service" status >/dev/null 2>&1 || ready=0
        HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy= \
            curl -sS --max-time 3 -o /dev/null "http://$router_ip:8080/" || ready=0
        if [ -x /opt/etc/init.d/S24xray ]; then
            /opt/etc/init.d/S24xray status >/dev/null 2>&1 || ready=0
        elif [ -x /opt/etc/init.d/S24v2ray ]; then
            /opt/etc/init.d/S24v2ray status >/dev/null 2>&1 || ready=0
        fi
        bypass_runtime_network_ready || ready=0
        bypass_socks_ready || ready=0
        if [ "$ready" -eq 1 ]; then
            stable_samples=$((stable_samples + 1))
            [ "$stable_samples" -ge 2 ] && return 0
        else
            stable_samples=0
        fi
        sleep 2
    done
    bypass_guard_fail 'программа, веб-интерфейс, локальный SOCKS или прозрачные правила не достигли готовности'
}

bypass_validate_python_sources() {
    runtime_dir="$1"
    python_bin="$(command -v python3 2>/dev/null || true)"
    [ -n "$python_bin" ] || bypass_guard_fail 'Python 3 не найден'
    [ -d "$runtime_dir" ] || bypass_guard_fail "каталог Python runtime не найден: $runtime_dir"
    PYTHONDONTWRITEBYTECODE=1 "$python_bin" - "$runtime_dir" <<'PY'
import os
import sys

runtime_dir = os.path.abspath(sys.argv[1])
paths = sorted(
    os.path.join(runtime_dir, filename)
    for filename in os.listdir(runtime_dir)
    if filename.endswith('.py')
)
if not paths:
    raise SystemExit(f'Python sources not found in {runtime_dir}')
for path in paths:
    with open(path, 'rb') as source_file:
        source = source_file.read()
    compile(source, path, 'exec')
PY
}

bypass_validate_staged_python_runtime() {
    stage_dir="$1"
    live_runtime_dir="${2:-/opt/etc/bot}"
    python_bin="$(command -v python3 2>/dev/null || true)"
    [ -n "$python_bin" ] || bypass_guard_fail 'Python 3 не найден'
    bypass_validate_python_sources "$stage_dir" || return 1
    candidate_config="$stage_dir/.candidate-core-config.json"
    BYPASS_KEENETIC_COMMAND_WORKER=1 \
    BYPASS_KEENETIC_POOL_PROBE_WORKER=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$stage_dir:$live_runtime_dir:/opt/etc" \
        "$python_bin" - "$stage_dir" "$candidate_config" <<'PY'
import importlib.util
import json
import os
import sys

stage_dir, candidate_config = sys.argv[1:3]
stage_dir = os.path.abspath(stage_dir)
sys.path.insert(0, stage_dir)

spec = importlib.util.spec_from_file_location('bypass_update_candidate', os.path.join(stage_dir, 'bot.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
current = module._load_current_keys()
payload = module._build_v2ray_config(
    vmess_key=current.get('vmess'),
    vless_key=current.get('vless'),
    vless2_key=current.get('vless2'),
    shadowsocks_key=current.get('shadowsocks'),
    trojan_key=current.get('trojan'),
    hysteria2_key=current.get('hysteria2'),
)
with open(candidate_config, 'w', encoding='utf-8') as file:
    json.dump(payload, file, ensure_ascii=False, separators=(',', ':'))
os.chmod(candidate_config, 0o600)
PY
}
