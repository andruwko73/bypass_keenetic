#!/bin/sh
set -eu

REPO_OWNER="${BYPASS_REPO_OWNER:-andruwko73}"
REPO_NAME="${BYPASS_REPO_NAME:-bypass_keenetic}"
REPO_BRANCH="${BYPASS_REPO_BRANCH:-main}"
RAW_BASE="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${REPO_BRANCH}"

BOT_DIR="/opt/etc/bot"
STATIC_DIR="$BOT_DIR/static"
BOT_CONFIG_PATH="$BOT_DIR/bot_config.py"
BOT_MAIN_PATH="$BOT_DIR/main.py"
INSTALLER_PATH="$BOT_DIR/installer.py"
INSTALLER_ENV_PATH="$BOT_DIR/installer.env"
LEGACY_CONFIG_PATH="/opt/etc/bot_config.py"
LEGACY_MAIN_PATH="/opt/etc/bot.py"
SERVICE_PATH="/opt/etc/init.d/S99telegram_bot"
INSTALLER_SERVICE_PATH="/opt/etc/init.d/S98telegram_bot_installer"
TMP_DIR="/tmp/bypass-bootstrap.$$"
BACKUP_ROOT="/opt/root/bypass-installer-backups"
BACKUP_ID="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$BACKUP_ID"
ABSENT_PATHS_FILE="$BACKUP_DIR/.absent-paths"
ROLLBACK_SCRIPT="$BACKUP_DIR/rollback.sh"
LAST_ROLLBACK_LINK="/opt/root/bypass-last-rollback.sh"
BOT_RUNTIME_MODULES="app_version.py app_runtime_mode.py auto_failover_runtime.py custom_checks_store.py entware_dns_runtime.py event_history.py installer_common.py key_pool_store.py key_pool_web.py pool_probe_controller.py pool_probe_runner.py probe_cache.py proxy_apply_runtime.py proxy_config_builder.py proxy_key_store.py proxy_protocols.py proxy_status.py repo_update.py route_intersections.py router_health_runtime.py service_catalog.py service_routes.py subscription_runtime.py telegram_auth_state.py telegram_call_learning.py telegram_confirm.py telegram_healthcheck.py telegram_info_runtime.py telegram_install_ui.py telegram_jobs.py telegram_key_ui.py telegram_message_flow.py telegram_pool_ui.py unblock_lists.py update_status.py web_command_state.py web_commands_runtime.py web_form_blocks.py web_form_template.py web_get_actions.py web_http_common.py web_pool_form_blocks.py web_post_actions.py web_route_tools_runtime.py web_status_builder.py web_status_runtime.py web_template_scripts.py web_template_styles.py xray_compat_runtime.py youtube_edge_prefetch.py youtube_edge_prefetch_runner.py youtube_healthcheck.py version.md README.md"

cleanup() {
    rm -rf "$TMP_DIR"
}

trap cleanup EXIT INT TERM

fail() {
    echo "ERROR: $1" >&2
    exit 1
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || fail "Команда '$1' не найдена"
}

need_var() {
    eval "value=\${$1-}"
    [ -n "$value" ] || fail "Не задана переменная $1"
}

download_file() {
    url="$1"
    target="$2"
    marker="$3"

    curl -fsSL --connect-timeout 20 --retry 2 --retry-delay 1 -o "$target" "$url" || fail "Не удалось скачать $url"
    [ -s "$target" ] || fail "Скачан пустой файл: $url"
    [ -z "$marker" ] || grep -q "$marker" "$target" || fail "Файл $url не прошёл проверку содержимого"
}

download_static_assets() {
    icons="chatgpt claude copilot deepseek discord facebook gemini grok instagram meta perplexity"
    mkdir -p "$STATIC_DIR/service-icons"
    curl -fsSL --connect-timeout 20 --retry 2 --retry-delay 1 -o "$STATIC_DIR/telegram.png" "$RAW_BASE/static/telegram.png" || true
    curl -fsSL --connect-timeout 20 --retry 2 --retry-delay 1 -o "$STATIC_DIR/youtube.png" "$RAW_BASE/static/youtube.png" || true
    for icon in $icons; do
        curl -fsSL --connect-timeout 20 --retry 2 --retry-delay 1 -o "$STATIC_DIR/service-icons/${icon}.png" "$RAW_BASE/static/service-icons/${icon}.png" || true
    done
    find "$STATIC_DIR" -type d -exec chmod 755 {} \; 2>/dev/null || true
    find "$STATIC_DIR" -type f -exec chmod 644 {} \; 2>/dev/null || true
}

ensure_symlink_or_copy() {
    source_path="$1"
    legacy_path="$2"

    rm -f "$legacy_path"
    if ! ln -s "$source_path" "$legacy_path" 2>/dev/null; then
        cp "$source_path" "$legacy_path"
    fi
}

generate_udp_quic_policy_file() {
    python_bin="/opt/bin/python3"
    [ -x "$python_bin" ] || python_bin="$(command -v python3 2>/dev/null || true)"
    [ -n "$python_bin" ] || return 0
    policy_tmp="$BOT_DIR/udp_quic_routes.txt.$$"
    if PYTHONPATH="$BOT_DIR" "$python_bin" - <<'PY' > "$policy_tmp" 2>/dev/null; then
from service_catalog import UDP_QUIC_ROUTE_ENTRIES
for entry in UDP_QUIC_ROUTE_ENTRIES:
    print(entry)
PY
        mv "$policy_tmp" "$BOT_DIR/udp_quic_routes.txt"
        chmod 644 "$BOT_DIR/udp_quic_routes.txt" 2>/dev/null || true
    else
        rm -f "$policy_tmp"
    fi
    exclude_tmp="$BOT_DIR/udp_quic_exclude.txt.$$"
    if PYTHONPATH="$BOT_DIR" "$python_bin" - <<'PY' > "$exclude_tmp" 2>/dev/null; then
from service_catalog import UDP_QUIC_EXCLUDE_ENTRIES
for entry in UDP_QUIC_EXCLUDE_ENTRIES:
    print(entry)
PY
        mv "$exclude_tmp" "$BOT_DIR/udp_quic_exclude.txt"
        chmod 644 "$BOT_DIR/udp_quic_exclude.txt" 2>/dev/null || true
    else
        rm -f "$exclude_tmp"
    fi
    call_signal_tmp="$BOT_DIR/call_signal_routes.txt.$$"
    if PYTHONPATH="$BOT_DIR" "$python_bin" - <<'PY' > "$call_signal_tmp" 2>/dev/null; then
from service_catalog import REALTIME_CALL_SIGNAL_ROUTE_ENTRIES
for entry in REALTIME_CALL_SIGNAL_ROUTE_ENTRIES:
    print(entry)
PY
        mv "$call_signal_tmp" "$BOT_DIR/call_signal_routes.txt"
        chmod 644 "$BOT_DIR/call_signal_routes.txt" 2>/dev/null || true
    else
        rm -f "$call_signal_tmp"
    fi
    block_tmp="$BOT_DIR/udp_policy.conf.$$"
    if PYTHONPATH="$BOT_DIR" "$python_bin" - <<'PY' > "$block_tmp" 2>/dev/null; then
import os
import re
from urllib.parse import urlparse

from service_catalog import REALTIME_CALL_SIGNAL_ROUTE_ENTRIES, TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES, YOUTUBE_UNBLOCK_ENTRIES

try:
    import bot_config as config
except Exception:
    config = None

UNBLOCK_DIR = os.environ.get('UNBLOCK_DIR', '/opt/etc/unblock')
PROTOCOLS = (
    ('SHADOWSOCKS', 'shadowsocks.txt', 'udp_quic_block_shadowsocks_enabled'),
    ('VMESS', 'vmess.txt', 'udp_quic_block_vmess_enabled'),
    ('VLESS', 'vless.txt', 'udp_quic_block_vless_enabled'),
    ('VLESS2', 'vless-2.txt', 'udp_quic_block_vless2_enabled'),
    ('TROJAN', 'trojan.txt', 'udp_quic_block_trojan_enabled'),
)


def config_bool(name, default=True):
    if config is None:
        return default
    return bool(getattr(config, name, default))


def config_int(name, default, minimum, maximum):
    if config is None:
        value = default
    else:
        try:
            value = int(getattr(config, name, default))
        except Exception:
            value = default
    return max(int(minimum), min(int(maximum), value))


def youtube_quic_policy():
    if config is None:
        return 'auto'
    value = str(getattr(config, 'youtube_quic_policy', 'auto') or 'auto').strip().lower()
    return value if value in ('auto', 'allow', 'block') else 'auto'


def telegram_udp_policy():
    if config is None:
        return 'auto'
    value = str(getattr(config, 'telegram_udp_policy', 'auto') or 'auto').strip().lower()
    return value if value in ('auto', 'allow', 'block') else 'auto'


def normalize_token(value):
    value = str(value or '').split('#', 1)[0].strip().lower()
    if not value:
        return ''
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value):
        try:
            value = urlparse(value).hostname or ''
        except Exception:
            value = ''
    value = re.sub(r'^(full:|domain:)', '', value)
    value = re.sub(r'^\+\.', '', value)
    return value.lstrip('*.').strip('.')


def normalize_domain(value):
    value = normalize_token(value)
    if not value or '/' in value or ':' in value:
        return ''
    if re.match(r'^[a-z0-9_.-]+\.[a-z0-9_.-]+$', value):
        return value
    return ''


def domain_matches(domain, candidate):
    return bool(domain and candidate and (domain == candidate or domain.endswith('.' + candidate)))


def entry_matches(entry, candidate):
    entry_domain = normalize_domain(entry)
    candidate_domain = normalize_domain(candidate)
    if entry_domain and candidate_domain:
        return domain_matches(entry_domain, candidate_domain) or domain_matches(candidate_domain, entry_domain)
    entry_token = normalize_token(entry)
    candidate_token = normalize_token(candidate)
    return bool(entry_token and candidate_token and entry_token == candidate_token)


def route_contains_catalog(filename, catalog_entries):
    path = os.path.join(UNBLOCK_DIR, filename)
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as file:
            entries = file.readlines()
    except Exception:
        return False
    return any(entry_matches(entry, catalog_entry) for entry in entries for catalog_entry in catalog_entries)


def route_contains_youtube(filename):
    return route_contains_catalog(filename, YOUTUBE_UNBLOCK_ENTRIES)


def route_contains_telegram(filename):
    return route_contains_catalog(filename, TELEGRAM_CALL_SIGNAL_ROUTE_ENTRIES)


def route_contains_realtime_call(filename):
    return route_contains_catalog(filename, REALTIME_CALL_SIGNAL_ROUTE_ENTRIES)


print('# Generated by bypass_keenetic. Edit bot_config.py values instead.')
telegram_route_flags = {}
realtime_call_route_flags = {}
for env_name, filename, attr in PROTOCOLS:
    telegram_route = route_contains_telegram(filename)
    telegram_route_flags[env_name] = telegram_route
    realtime_call_route_flags[env_name] = route_contains_realtime_call(filename)
    enabled = config_bool(attr, True)
    if route_contains_youtube(filename):
        policy = youtube_quic_policy()
        if policy == 'allow':
            enabled = False
        elif policy == 'block':
            enabled = True
        else:
            enabled = True
    elif telegram_route:
        policy = telegram_udp_policy()
        if policy == 'block':
            enabled = True
        else:
            enabled = False
    print(f'BYPASS_UDP_QUIC_BLOCK_{env_name}={1 if enabled else 0}')
print(f'BYPASS_IPV6_FALLBACK_ENABLED={1 if config_bool("ipv6_bypass_fallback_enabled", True) else 0}')
print(f'BYPASS_TELEGRAM_CALL_LEARNING_ENABLED={1 if config_bool("telegram_call_learning_enabled", False) else 0}')
print(f'BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT={config_int("telegram_call_learning_client_timeout_seconds", 900, 30, 86400)}')
print(f'BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT={config_int("telegram_call_learning_address_timeout_seconds", 14400, 120, 86400)}')
print(f'BYPASS_TELEGRAM_CALL_TPROXY_ENABLED={1 if config_bool("telegram_call_tproxy_enabled", False) else 0}')
print('BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED=0')
print(f'TELEGRAM_CALL_TPROXY_PORT_SHADOWSOCKS={config_int("localportsh_tproxy", 11802, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_VMESS={config_int("localportvmess_tproxy", 11815, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_VLESS={config_int("localportvless_tproxy", 11812, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_VLESS2={config_int("localportvless2_tproxy", 11814, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_TROJAN={config_int("localporttrojan_tproxy", 11829, 1, 65535)}')
for env_name, _filename, _attr in PROTOCOLS:
    print(f'BYPASS_TELEGRAM_CALL_ROUTE_{env_name}={1 if realtime_call_route_flags.get(env_name) else 0}')
for env_name, _filename, _attr in PROTOCOLS:
    print(f'BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_{env_name}={1 if telegram_route_flags.get(env_name) else 0}')
PY
        mv "$block_tmp" "$BOT_DIR/udp_policy.conf"
        chmod 644 "$BOT_DIR/udp_policy.conf" 2>/dev/null || true
    else
        rm -f "$block_tmp"
    fi
}

backup_path() {
    source_path="$1"

    if [ -e "$source_path" ] || [ -L "$source_path" ]; then
        mkdir -p "$BACKUP_DIR$(dirname "$source_path")"
        cp -a "$source_path" "$BACKUP_DIR$source_path"
    else
        printf '%s\n' "$source_path" >> "$ABSENT_PATHS_FILE"
    fi
}

write_rollback_script() {
    cat > "$ROLLBACK_SCRIPT" <<EOF
#!/bin/sh
set -eu

BACKUP_DIR='$BACKUP_DIR'
ABSENT_PATHS_FILE='$ABSENT_PATHS_FILE'
BOT_RUNTIME_MODULES='$BOT_RUNTIME_MODULES'

restore_path() {
    target_path="\$1"
    backup_path="\$BACKUP_DIR\$target_path"

    if [ -e "\$backup_path" ] || [ -L "\$backup_path" ]; then
        mkdir -p "\$(dirname "\$target_path")"
        rm -rf "\$target_path"
        cp -a "\$backup_path" "\$target_path"
    fi
}

remove_added_path() {
    target_path="\$1"
    if [ -e "\$target_path" ] || [ -L "\$target_path" ]; then
        rm -rf "\$target_path"
    fi
}

install_unblock_ipset_cron_job() {
    cron_tmp="/tmp/bypass-unblock-crontab.\$\$"
    {
        crontab -l 2>/dev/null \\
            | grep -v '/opt/bin/unblock_ipset.sh' \\
            | grep -v '/opt/etc/init.d/S99unblock refresh' \\
            | grep -v '^# DO NOT EDIT THIS FILE' \\
            | grep -v '^# (.* installed on ' \\
            | grep -v '^# (Cron version ' \\
            | sed '/^[[:space:]]*$/d' || true
        printf '%s\n' '*/15 * * * * /opt/etc/init.d/S99unblock refresh >/dev/null 2>&1'
    } > "\$cron_tmp"
    if crontab "\$cron_tmp" >/dev/null 2>&1; then
        rm -f "\$cron_tmp"
        chown root:root /opt/var/spool/cron /opt/var/spool/cron/crontabs /opt/var/spool/cron/crontabs/root 2>/dev/null || true
        chmod 700 /opt/var/spool/cron /opt/var/spool/cron/crontabs 2>/dev/null || true
        chmod 600 /opt/var/spool/cron/crontabs/root 2>/dev/null || true
        return 0
    fi
    rm -f "\$cron_tmp"
    echo "Warning: failed to install active root crontab for unblock_ipset.sh."
    return 1
}

restore_path /opt/etc/bot/main.py
restore_path /opt/etc/bot/installer.py
restore_path /opt/etc/bot/installer.env
restore_path /opt/etc/bot/app_version.py
restore_path /opt/etc/bot/app_runtime_mode.py
restore_path /opt/etc/bot/key_pool_store.py
restore_path /opt/etc/bot/key_pool_web.py
restore_path /opt/etc/bot/router_health_runtime.py
restore_path /opt/etc/bot/telegram_pool_ui.py
restore_path /opt/etc/bot/pool_probe_runner.py
restore_path /opt/etc/bot/service_catalog.py
restore_path /opt/etc/bot/probe_cache.py
restore_path /opt/etc/bot/custom_checks_store.py
restore_path /opt/etc/bot/web_form_template.py
restore_path /opt/etc/bot/web_template_styles.py
restore_path /opt/etc/bot/web_template_scripts.py
restore_path /opt/etc/bot/web_form_blocks.py
restore_path /opt/etc/bot/web_pool_form_blocks.py
restore_path /opt/etc/bot/web_http_common.py
restore_path /opt/etc/bot/web_get_actions.py
restore_path /opt/etc/bot/web_post_actions.py
restore_path /opt/etc/bot/web_command_state.py
restore_path /opt/etc/bot/web_commands_runtime.py
restore_path /opt/etc/bot/unblock_lists.py
restore_path /opt/etc/bot/proxy_key_store.py
restore_path /opt/etc/bot/proxy_protocols.py
restore_path /opt/etc/bot/proxy_config_builder.py
restore_path /opt/etc/bot/proxy_status.py
restore_path /opt/etc/bot/installer_common.py
for module in \$BOT_RUNTIME_MODULES; do
    restore_path "/opt/etc/bot/\$module"
done
restore_path /opt/etc/web_bot.py
restore_path /opt/etc/bot.py
restore_path /opt/etc/init.d/S99telegram_bot
restore_path /opt/etc/init.d/S98telegram_bot_installer
restore_path /opt/etc/init.d/S99web_bot
restore_path /opt/etc/ndm/fs.d/100-ipset.sh
restore_path /opt/etc/shadowsocks.json
restore_path /opt/etc/init.d/S22shadowsocks
restore_path /opt/etc/xray/config.json
restore_path /opt/etc/v2ray/config.json
restore_path /opt/etc/trojan/config.json
restore_path /opt/etc/init.d/S24xray
restore_path /opt/etc/init.d/S24v2ray
restore_path /opt/bin/unblock_ipset.sh
restore_path /opt/bin/unblock_dnsmasq.sh
restore_path /opt/bin/unblock_update.sh
restore_path /opt/etc/init.d/S99unblock
restore_path /opt/etc/ndm/netfilter.d/100-redirect.sh
restore_path /opt/etc/dnsmasq.conf
restore_path /opt/etc/crontab

if [ -f "\$ABSENT_PATHS_FILE" ]; then
    while IFS= read -r added_path; do
        [ -n "\$added_path" ] || continue
        remove_added_path "\$added_path"
    done < "\$ABSENT_PATHS_FILE"
fi

/opt/etc/init.d/S98telegram_bot_installer stop >/dev/null 2>&1 || true
sed -i '/allowInsecure/d' /opt/etc/xray/config.json /opt/etc/v2ray/config.json /opt/etc/bot/proxy_protocols.py 2>/dev/null || true
if [ -x /opt/sbin/xray ] && [ -f /opt/etc/xray/config.json ]; then
    if /opt/sbin/xray run -test -c /opt/etc/xray/config.json >/tmp/bypass-xray-rollback-test.log 2>&1; then
        echo "Xray config OK after rollback."
    else
        echo "Warning: Xray config failed after rollback:"
        tail -n 12 /tmp/bypass-xray-rollback-test.log 2>/dev/null || true
    fi
fi
if [ -x /opt/etc/init.d/S99web_bot ]; then
    /opt/etc/init.d/S99telegram_bot stop >/dev/null 2>&1 || true
    /opt/etc/init.d/S99web_bot restart >/dev/null 2>&1 || /opt/etc/init.d/S99web_bot start >/dev/null 2>&1 || true
else
    /opt/etc/init.d/S99telegram_bot restart >/dev/null 2>&1 || /opt/etc/init.d/S99telegram_bot start >/dev/null 2>&1 || true
fi
/opt/bin/unblock_update.sh >/dev/null 2>&1 || true
install_unblock_ipset_cron_job || true
/opt/etc/init.d/S10cron restart >/dev/null 2>&1 || /opt/etc/init.d/S10cron start >/dev/null 2>&1 || true
/opt/etc/init.d/S22shadowsocks restart >/dev/null 2>&1 || true
/opt/etc/init.d/S24xray restart >/dev/null 2>&1 || true
/opt/etc/init.d/S24v2ray restart >/dev/null 2>&1 || true
/opt/etc/init.d/S24xray status 2>/dev/null || true
/opt/etc/init.d/S22trojan restart >/dev/null 2>&1 || true
/opt/etc/init.d/S99unblock restart >/dev/null 2>&1 || true

echo "Rollback completed from \$BACKUP_DIR"
EOF

    chmod 700 "$ROLLBACK_SCRIPT"
    rm -f "$LAST_ROLLBACK_LINK"
    ln -s "$ROLLBACK_SCRIPT" "$LAST_ROLLBACK_LINK" 2>/dev/null || cp "$ROLLBACK_SCRIPT" "$LAST_ROLLBACK_LINK"
}

detect_router_ip() {
    detected_ip=$(ip -4 addr show br0 2>/dev/null | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -n1 || true)
    if [ -n "$detected_ip" ]; then
        printf '%s' "$detected_ip"
    else
        printf '%s' '192.168.1.1'
    fi
}

if [ "$(id -u)" -ne 0 ]; then
    fail "Запустите bootstrap от root на роутере"
fi

need_cmd curl
need_cmd grep
need_cmd sed
need_cmd mkdir

if [ ! -x /opt/bin/opkg ] && ! command -v opkg >/dev/null 2>&1; then
    echo "Entware не найден в /opt." >&2
    echo "Этот bootstrap убирает ручную SSH-установку, но не отменяет подготовку хранилища для Entware на Keenetic." >&2
    echo "Сначала подготовьте накопитель и установите Entware, затем повторите запуск bootstrap." >&2
    exit 2
fi

mkdir -p "$TMP_DIR" "$BOT_DIR"
mkdir -p "$BACKUP_DIR"
: > "$ABSENT_PATHS_FILE"

ROUTER_IP="${BYPASS_ROUTER_IP:-$(detect_router_ip)}"
BROWSER_PORT="${BYPASS_BROWSER_PORT:-8080}"
DEFAULT_PROXY_MODE="${BYPASS_DEFAULT_PROXY_MODE:-none}"
FORK_BUTTON_LABEL="${BYPASS_FORK_BUTTON_LABEL:-Fork by ${REPO_OWNER}}"

backup_path "$BOT_MAIN_PATH"
backup_path "$INSTALLER_PATH"
backup_path "$INSTALLER_ENV_PATH"
backup_path "$BOT_DIR/app_version.py"
backup_path "$BOT_DIR/app_runtime_mode.py"
backup_path "$BOT_DIR/key_pool_store.py"
backup_path "$BOT_DIR/key_pool_web.py"
backup_path "$BOT_DIR/router_health_runtime.py"
backup_path "$BOT_DIR/telegram_call_learning.py"
backup_path "$BOT_DIR/telegram_pool_ui.py"
backup_path "$BOT_DIR/pool_probe_runner.py"
backup_path "$BOT_DIR/service_catalog.py"
backup_path "$BOT_DIR/probe_cache.py"
backup_path "$BOT_DIR/custom_checks_store.py"
backup_path "$BOT_DIR/web_form_template.py"
backup_path "$BOT_DIR/web_template_styles.py"
backup_path "$BOT_DIR/web_template_scripts.py"
backup_path "$BOT_DIR/web_form_blocks.py"
backup_path "$BOT_DIR/web_pool_form_blocks.py"
backup_path "$BOT_DIR/web_http_common.py"
backup_path "$BOT_DIR/web_get_actions.py"
backup_path "$BOT_DIR/web_post_actions.py"
backup_path "$BOT_DIR/web_command_state.py"
backup_path "$BOT_DIR/web_commands_runtime.py"
backup_path "$BOT_DIR/unblock_lists.py"
backup_path "$BOT_DIR/proxy_key_store.py"
backup_path "$BOT_DIR/proxy_protocols.py"
backup_path "$BOT_DIR/proxy_config_builder.py"
backup_path "$BOT_DIR/proxy_status.py"
backup_path "$BOT_DIR/installer_common.py"
for module in $BOT_RUNTIME_MODULES; do
    backup_path "$BOT_DIR/$module"
done
backup_path "/opt/etc/web_bot.py"
backup_path "$LEGACY_MAIN_PATH"
backup_path "$SERVICE_PATH"
backup_path "$INSTALLER_SERVICE_PATH"
backup_path "/opt/etc/init.d/S99web_bot"
backup_path "/opt/etc/ndm/fs.d/100-ipset.sh"
backup_path "/opt/etc/shadowsocks.json"
backup_path "/opt/etc/init.d/S22shadowsocks"
backup_path "/opt/etc/xray/config.json"
backup_path "/opt/etc/v2ray/config.json"
backup_path "/opt/etc/trojan/config.json"
backup_path "/opt/etc/init.d/S24xray"
backup_path "/opt/etc/init.d/S24v2ray"
backup_path "/opt/bin/unblock_ipset.sh"
backup_path "/opt/bin/unblock_dnsmasq.sh"
backup_path "/opt/bin/unblock_update.sh"
backup_path "/opt/etc/init.d/S99unblock"
backup_path "/opt/etc/ndm/netfilter.d/100-redirect.sh"
backup_path "/opt/etc/dnsmasq.conf"
backup_path "/opt/etc/crontab"
write_rollback_script

download_file "$RAW_BASE/script.sh" "$TMP_DIR/script.sh" 'if \[ "$1" = "-install" \]; then'
download_file "$RAW_BASE/bot.py" "$TMP_DIR/main.py" 'KeyInstallHTTPRequestHandler'
download_file "$RAW_BASE/installer.py" "$TMP_DIR/installer.py" 'ThreadingHTTPServer'
download_file "$RAW_BASE/app_version.py" "$TMP_DIR/app_version.py" 'APP_VERSION_COUNTER'
download_file "$RAW_BASE/app_runtime_mode.py" "$TMP_DIR/app_runtime_mode.py" 'set_app_runtime_mode'
download_file "$RAW_BASE/key_pool_store.py" "$TMP_DIR/key_pool_store.py" 'def normalize_key_pools'
download_file "$RAW_BASE/key_pool_web.py" "$TMP_DIR/key_pool_web.py" 'pool_status_summary'
download_file "$RAW_BASE/router_health_runtime.py" "$TMP_DIR/router_health_runtime.py" 'RouterHealthRuntime'
download_file "$RAW_BASE/telegram_call_learning.py" "$TMP_DIR/telegram_call_learning.py" 'def read_lan_conntrack_flows'
download_file "$RAW_BASE/telegram_pool_ui.py" "$TMP_DIR/telegram_pool_ui.py" 'pool_action_markup'
download_file "$RAW_BASE/pool_probe_runner.py" "$TMP_DIR/pool_probe_runner.py" 'run_pool_probe_worker'
download_file "$RAW_BASE/service_catalog.py" "$TMP_DIR/service_catalog.py" 'CUSTOM_CHECK_PRESETS'
download_file "$RAW_BASE/probe_cache.py" "$TMP_DIR/probe_cache.py" 'record_key_probe'
download_file "$RAW_BASE/custom_checks_store.py" "$TMP_DIR/custom_checks_store.py" 'add_custom_check'
download_file "$RAW_BASE/web_form_template.py" "$TMP_DIR/web_form_template.py" 'render_web_form'
download_file "$RAW_BASE/web_template_styles.py" "$TMP_DIR/web_template_styles.py" 'render_web_styles'
download_file "$RAW_BASE/web_template_scripts.py" "$TMP_DIR/web_template_scripts.py" 'render_web_scripts'
download_file "$RAW_BASE/web_form_blocks.py" "$TMP_DIR/web_form_blocks.py" 'render_message_block'
download_file "$RAW_BASE/web_pool_form_blocks.py" "$TMP_DIR/web_pool_form_blocks.py" 'render_protocol_panel'
download_file "$RAW_BASE/web_http_common.py" "$TMP_DIR/web_http_common.py" 'WebRequestMixin'
download_file "$RAW_BASE/web_get_actions.py" "$TMP_DIR/web_get_actions.py" 'dispatch'
download_file "$RAW_BASE/web_post_actions.py" "$TMP_DIR/web_post_actions.py" 'dispatch'
download_file "$RAW_BASE/web_command_state.py" "$TMP_DIR/web_command_state.py" 'start_command'
download_file "$RAW_BASE/web_commands_runtime.py" "$TMP_DIR/web_commands_runtime.py" 'run_web_command'
download_file "$RAW_BASE/unblock_lists.py" "$TMP_DIR/unblock_lists.py" 'save_unblock_list_file'
download_file "$RAW_BASE/proxy_key_store.py" "$TMP_DIR/proxy_key_store.py" 'load_current_keys'
download_file "$RAW_BASE/proxy_protocols.py" "$TMP_DIR/proxy_protocols.py" 'proxy_outbound_from_key'
download_file "$RAW_BASE/proxy_config_builder.py" "$TMP_DIR/proxy_config_builder.py" 'build_proxy_core_config'
download_file "$RAW_BASE/proxy_status.py" "$TMP_DIR/proxy_status.py" 'status_snapshot_signature'
download_file "$RAW_BASE/installer_common.py" "$TMP_DIR/installer_common.py" 'browser_port_is_valid'
for module in $BOT_RUNTIME_MODULES; do
    if [ ! -f "$TMP_DIR/$module" ]; then
        download_file "$RAW_BASE/$module" "$TMP_DIR/$module" ''
    fi
done
download_file "$RAW_BASE/S99telegram_bot" "$TMP_DIR/S99telegram_bot" 'Bot started successfully'
download_file "$RAW_BASE/S98telegram_bot_installer" "$TMP_DIR/S98telegram_bot_installer" 'Installer started successfully'

cp "$TMP_DIR/main.py" "$BOT_MAIN_PATH"
cp "$TMP_DIR/installer.py" "$INSTALLER_PATH"
cp "$TMP_DIR/app_version.py" "$BOT_DIR/app_version.py"
cp "$TMP_DIR/app_runtime_mode.py" "$BOT_DIR/app_runtime_mode.py"
cp "$TMP_DIR/key_pool_store.py" "$BOT_DIR/key_pool_store.py"
cp "$TMP_DIR/key_pool_web.py" "$BOT_DIR/key_pool_web.py"
cp "$TMP_DIR/router_health_runtime.py" "$BOT_DIR/router_health_runtime.py"
cp "$TMP_DIR/telegram_call_learning.py" "$BOT_DIR/telegram_call_learning.py"
cp "$TMP_DIR/telegram_pool_ui.py" "$BOT_DIR/telegram_pool_ui.py"
cp "$TMP_DIR/pool_probe_runner.py" "$BOT_DIR/pool_probe_runner.py"
cp "$TMP_DIR/service_catalog.py" "$BOT_DIR/service_catalog.py"
cp "$TMP_DIR/probe_cache.py" "$BOT_DIR/probe_cache.py"
cp "$TMP_DIR/custom_checks_store.py" "$BOT_DIR/custom_checks_store.py"
cp "$TMP_DIR/web_form_template.py" "$BOT_DIR/web_form_template.py"
cp "$TMP_DIR/web_template_styles.py" "$BOT_DIR/web_template_styles.py"
cp "$TMP_DIR/web_template_scripts.py" "$BOT_DIR/web_template_scripts.py"
cp "$TMP_DIR/web_form_blocks.py" "$BOT_DIR/web_form_blocks.py"
cp "$TMP_DIR/web_pool_form_blocks.py" "$BOT_DIR/web_pool_form_blocks.py"
cp "$TMP_DIR/web_http_common.py" "$BOT_DIR/web_http_common.py"
cp "$TMP_DIR/web_get_actions.py" "$BOT_DIR/web_get_actions.py"
cp "$TMP_DIR/web_post_actions.py" "$BOT_DIR/web_post_actions.py"
cp "$TMP_DIR/web_command_state.py" "$BOT_DIR/web_command_state.py"
cp "$TMP_DIR/web_commands_runtime.py" "$BOT_DIR/web_commands_runtime.py"
cp "$TMP_DIR/unblock_lists.py" "$BOT_DIR/unblock_lists.py"
cp "$TMP_DIR/proxy_key_store.py" "$BOT_DIR/proxy_key_store.py"
cp "$TMP_DIR/proxy_protocols.py" "$BOT_DIR/proxy_protocols.py"
cp "$TMP_DIR/proxy_config_builder.py" "$BOT_DIR/proxy_config_builder.py"
cp "$TMP_DIR/proxy_status.py" "$BOT_DIR/proxy_status.py"
cp "$TMP_DIR/installer_common.py" "$BOT_DIR/installer_common.py"
for module in $BOT_RUNTIME_MODULES; do
    cp "$TMP_DIR/$module" "$BOT_DIR/$module"
done
cp "$TMP_DIR/S99telegram_bot" "$SERVICE_PATH"
cp "$TMP_DIR/S98telegram_bot_installer" "$INSTALLER_SERVICE_PATH"
download_static_assets

chmod 755 "$TMP_DIR/script.sh" "$BOT_MAIN_PATH" "$INSTALLER_PATH" "$SERVICE_PATH" "$INSTALLER_SERVICE_PATH"
chmod 644 "$BOT_DIR/app_version.py" "$BOT_DIR/app_runtime_mode.py" "$BOT_DIR/key_pool_store.py" "$BOT_DIR/key_pool_web.py" "$BOT_DIR/router_health_runtime.py" "$BOT_DIR/telegram_call_learning.py" "$BOT_DIR/telegram_pool_ui.py" "$BOT_DIR/pool_probe_runner.py" "$BOT_DIR/service_catalog.py" "$BOT_DIR/probe_cache.py" "$BOT_DIR/custom_checks_store.py" "$BOT_DIR/web_form_template.py" "$BOT_DIR/web_template_styles.py" "$BOT_DIR/web_template_scripts.py" "$BOT_DIR/web_form_blocks.py" "$BOT_DIR/web_pool_form_blocks.py" "$BOT_DIR/web_http_common.py" "$BOT_DIR/web_get_actions.py" "$BOT_DIR/web_post_actions.py" "$BOT_DIR/web_command_state.py" "$BOT_DIR/web_commands_runtime.py" "$BOT_DIR/unblock_lists.py" "$BOT_DIR/proxy_key_store.py" "$BOT_DIR/proxy_protocols.py" "$BOT_DIR/proxy_config_builder.py" "$BOT_DIR/proxy_status.py" "$BOT_DIR/installer_common.py"
for module in $BOT_RUNTIME_MODULES; do
    chmod 644 "$BOT_DIR/$module"
done
ensure_symlink_or_copy "$BOT_MAIN_PATH" "$LEGACY_MAIN_PATH"
ensure_symlink_or_copy "$BOT_MAIN_PATH" "$BOT_DIR/bot.py"
generate_udp_quic_policy_file

/bin/sh "$TMP_DIR/script.sh" -install

if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_USERNAME:-}" ]; then
    TG_WEB_AUTH_TOKEN_VALUE="${TG_WEB_AUTH_TOKEN:-}"
    BOT_CONFIG_PATH_ENV="$BOT_CONFIG_PATH" BOT_DIR_ENV="$BOT_DIR" \
    TG_BOT_TOKEN_ENV="$TG_BOT_TOKEN" TG_USERNAME_ENV="$TG_USERNAME" \
    TG_WEB_AUTH_TOKEN_ENV="$TG_WEB_AUTH_TOKEN_VALUE" ROUTER_IP_ENV="$ROUTER_IP" \
    BROWSER_PORT_ENV="$BROWSER_PORT" REPO_OWNER_ENV="$REPO_OWNER" REPO_NAME_ENV="$REPO_NAME" \
    FORK_BUTTON_LABEL_ENV="$FORK_BUTTON_LABEL" DEFAULT_PROXY_MODE_ENV="$DEFAULT_PROXY_MODE" \
    python3 - <<'PY'
import os
import sys

sys.path.insert(0, os.environ['BOT_DIR_ENV'])
from app_version import APP_VERSION_COUNTER


def py_string(name, default=''):
    return repr(str(os.environ.get(name, default)))


config_text = f"""# ВЕРСИЯ СКРИПТА v{APP_VERSION_COUNTER}

token = {py_string('TG_BOT_TOKEN_ENV')}
usernames = [{py_string('TG_USERNAME_ENV')}]

routerip = {py_string('ROUTER_IP_ENV')}
browser_port = {py_string('BROWSER_PORT_ENV')}
web_auth_user = 'admin'
web_auth_token = {py_string('TG_WEB_AUTH_TOKEN_ENV')}
web_auth_disabled = False
fork_repo_owner = {py_string('REPO_OWNER_ENV')}
fork_repo_name = {py_string('REPO_NAME_ENV')}
fork_button_label = {py_string('FORK_BUTTON_LABEL_ENV')}
app_runtime_mode = 'advanced'
pool_probe_min_available_kb = 190000
pool_probe_pause_available_kb = 125000
pool_probe_slow_available_kb = 190000
pool_probe_slow_memory_delay_seconds = 3.0
pool_probe_delay_seconds = 1.5
pool_probe_cpu_guard_enabled = True
pool_probe_max_cpu_percent = 70.0
pool_probe_cpu_sample_seconds = 0.35
pool_probe_high_cpu_delay_seconds = 5.0
pool_probe_high_cpu_max_wait_seconds = 45.0
pool_probe_max_process_rss_kb = 87040
pool_probe_youtube_profile = 'quick'
pool_probe_quality_enabled = True
pool_probe_quality_download_url = 'https://speed.cloudflare.com/__down?bytes={{bytes}}'
pool_probe_quality_download_bytes = 1048576
pool_probe_quality_min_available_kb = 170000
pool_probe_quality_max_samples_per_run = 12
pool_probe_quality_download_connect_timeout = 6.0
pool_probe_quality_download_read_timeout = 10.0
pool_probe_quality_stable_latency_ms = 2500
pool_probe_quality_fast_latency_ms = 1500
pool_probe_quality_1600p_min_mbps = 25.0
pool_probe_quality_4k_min_mbps = 45.0
memory_watchdog_enabled = True
memory_watchdog_rss_soft_kb = 87040
memory_watchdog_rss_limit_kb = 112640
memory_watchdog_idle_restart_rss_kb = 71680
memory_watchdog_idle_restart_hold_seconds = 120.0
memory_watchdog_check_interval = 60.0
memory_watchdog_min_uptime_seconds = 300.0
memory_watchdog_restart_cooldown_seconds = 1800.0
status_refresh_min_interval_seconds = 180.0
memory_post_pool_restart_enabled = True
memory_post_pool_restart_rss_kb = 71680
memory_post_pool_restart_delay_seconds = 20.0
memory_post_pool_restart_retry_seconds = 30.0
memory_post_pool_restart_max_wait_seconds = 300.0
memory_timeline_enabled = False
memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'
memory_timeline_interval_seconds = 60.0
memory_timeline_max_events = 720
udp_quic_block_shadowsocks_enabled = True
udp_quic_block_vmess_enabled = True
udp_quic_block_vless_enabled = True
udp_quic_block_vless2_enabled = True
udp_quic_block_trojan_enabled = True
youtube_quic_policy = 'auto'
telegram_udp_policy = 'auto'
youtube_edge_prefetch_enabled = True
youtube_edge_prefetch_mode = 'external'
youtube_edge_prefetch_start_delay_seconds = 120
youtube_edge_prefetch_interval_seconds = 900
youtube_edge_prefetch_cache_path = '/opt/etc/bot/youtube_edge_cache.json'
youtube_edge_prefetch_status_path = '/opt/etc/bot/youtube_edge_prefetch_status.json'
youtube_edge_prefetch_lock_dir = '/tmp/bypass-youtube-edge-prefetch.lock'
youtube_edge_prefetch_cache_ttl_seconds = 259200
youtube_edge_prefetch_max_cache_entries = 128
youtube_edge_prefetch_max_hosts_per_run = 12
youtube_edge_prefetch_max_resolved_addresses = 32
youtube_edge_prefetch_max_candidates = 64
youtube_edge_prefetch_max_addresses_per_run = 16
youtube_edge_prefetch_min_available_kb = 125000
youtube_edge_prefetch_max_rss_kb = 66560
youtube_edge_prefetch_exclusive_ipsets = True
youtube_edge_prefetch_protect_shared_google = True
youtube_edge_prefetch_cache_restore_enabled = True
youtube_edge_prefetch_cache_restore_max_addresses = 16
youtube_edge_prefetch_cache_restore_require_quality_ok = True
youtube_edge_prefetch_fast_warm_enabled = True
youtube_edge_prefetch_fast_hosts = (
    'www.youtube.com',
    'youtube.com',
    'youtubei.googleapis.com',
    'manifest.googlevideo.com',
    'redirector.googlevideo.com',
    'i.ytimg.com',
    's.ytimg.com',
    'yt3.ggpht.com',
)
youtube_edge_prefetch_fast_max_hosts_per_run = 8
youtube_edge_prefetch_fast_max_candidates = 32
youtube_edge_prefetch_quality_probe_enabled = True
youtube_edge_prefetch_quality_target_ms = 1000
youtube_edge_prefetch_quality_timeout_seconds = 5
youtube_edge_prefetch_quality_bad_cooldown_seconds = 3600
youtube_edge_prefetch_quality_max_candidates = 24
youtube_edge_watch_warm_enabled = True
youtube_edge_watch_warm_urls = (
    'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
    'https://www.youtube.com/watch?v=jfKfPfyJRdk',
)
youtube_edge_watch_warm_max_pages = 2
youtube_edge_watch_warm_max_hosts = 8
youtube_edge_watch_warm_max_bytes = 1800000
youtube_edge_watch_warm_connect_timeout = 6
youtube_edge_watch_warm_max_time = 20
youtube_edge_prefetch_dns_servers = ('local', '1.1.1.1', '8.8.8.8')
youtube_edge_prefetch_hosts = (
    'www.youtube.com',
    'youtube.com',
    'm.youtube.com',
    'youtubei.googleapis.com',
    'youtubei-att.googleapis.com',
    'jnn-pa.googleapis.com',
    'play-fe.googleapis.com',
    'i.ytimg.com',
    's.ytimg.com',
    'yt3.ggpht.com',
    'www.gstatic.com',
    'manifest.googlevideo.com',
    'redirector.googlevideo.com',
)
telegram_call_learning_enabled = False
telegram_call_learning_state_path = '/tmp/bypass_telegram_call_learning.json'
telegram_call_learning_default_duration_seconds = 90
telegram_call_learning_max_duration_seconds = 180
telegram_call_learning_poll_interval_seconds = 1.0
telegram_call_learning_auto_enabled = True
telegram_call_learning_scan_interval_seconds = 5.0
telegram_call_learning_min_score = 5
telegram_call_learning_min_packets = 2
telegram_call_learning_min_bytes = 240
telegram_call_learning_max_candidates = 20
telegram_call_learning_max_seen_addresses = 512
telegram_call_learning_apply_by_default = True
telegram_call_learning_client_timeout_seconds = 900
telegram_call_learning_address_timeout_seconds = 14400
telegram_call_tproxy_enabled = False
ipset_refresh_command_timeout_seconds = 420
ipv6_bypass_fallback_enabled = True
reality_endpoint_overrides = {}
reality_endpoint_repair_enabled = True
reality_endpoint_repair_max_candidates = 6
reality_endpoint_repair_dns_servers = ('1.1.1.1', '8.8.8.8', '9.9.9.9')
auto_failover_startup_hold_seconds = 180
auto_failover_consecutive_failures = 3
youtube_vless2_failover_enabled = True
youtube_vless2_failover_grace_seconds = 180
youtube_vless2_failover_poll_seconds = 120
youtube_vless2_failover_switch_cooldown_seconds = 300
youtube_vless2_failover_check_connect_timeout = 6
youtube_vless2_failover_check_read_timeout = 10
youtube_vless2_failover_confirm_retries = 3
youtube_vless2_failover_confirm_delay_seconds = 8.0
youtube_vless2_restart_recheck_enabled = True
youtube_vless2_restart_recheck_cooldown_seconds = 300
youtube_vless2_failover_consecutive_failures = 3
youtube_vless2_hard_failure_recovery_cooldown_seconds = 90

localportsh = '1082'
localportvmess = '10810'
localportvless = '10811'
localporttrojan = '10829'
localportsh_tproxy = '11802'
localportvmess_tproxy = '11815'
localportvless_tproxy = '11812'
localportvless2_tproxy = '11814'
localporttrojan_tproxy = '11829'
default_proxy_mode = {py_string('DEFAULT_PROXY_MODE_ENV')}
dnsovertlsport = '40500'
dnsoverhttpsport = '40508'
"""

with open(os.environ['BOT_CONFIG_PATH_ENV'], 'w', encoding='utf-8') as file:
    file.write(config_text)
PY
    chmod 600 "$BOT_CONFIG_PATH"
    rm -f "$INSTALLER_ENV_PATH"
    ensure_symlink_or_copy "$BOT_CONFIG_PATH" "$LEGACY_CONFIG_PATH"
    "$INSTALLER_SERVICE_PATH" stop >/dev/null 2>&1 || true
    "$SERVICE_PATH" restart || "$SERVICE_PATH" start || fail "Не удалось запустить сервис бота"
    echo "Bootstrap-установка завершена."
    echo "Веб-интерфейс: http://${ROUTER_IP}:${BROWSER_PORT}/"
    echo "Проверка сервиса: $SERVICE_PATH status"
    echo "Откат: $ROLLBACK_SCRIPT"
    exit 0
fi

cat > "$INSTALLER_ENV_PATH" <<EOF
BYPASS_INSTALLER_PORT=${BROWSER_PORT}
EOF
chmod 644 "$INSTALLER_ENV_PATH"

# Force true first-run installer mode: existing bot_config would prevent
# S98telegram_bot_installer from starting and leave the previous bot token active.
rm -f "$BOT_CONFIG_PATH" "$LEGACY_CONFIG_PATH"

"$SERVICE_PATH" stop >/dev/null 2>&1 || true
"$INSTALLER_SERVICE_PATH" restart || "$INSTALLER_SERVICE_PATH" start || fail "Не удалось запустить web installer"

echo "Bootstrap-установка завершена в режиме первичной настройки."
echo "Откройте страницу: http://${ROUTER_IP}:${BROWSER_PORT}/"
echo "После сохранения формы installer сам запустит основной бот."
echo "Откат: $ROLLBACK_SCRIPT"
