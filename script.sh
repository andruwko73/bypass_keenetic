#!/bin/sh

# 2023. Keenetic DNS bot /  Проект: bypass_keenetic / Автор: tas_unn
# GitHub: https://github.com/tas-unn/bypass_keenetic
# Данный бот предназначен для управления обхода блокировок на роутерах Keenetic
# Демо-бот: https://t.me/keenetic_dns_bot
#
# Файл: script.sh, Версия 2.2.1, последнее изменение: 19.04.2026, 15:10
# Доработал: NetworK (https://github.com/znetworkx)

# оригинальный репозиторий (tas-unn), пользовательский форк

repo="andruwko73"
REPO_REF="${REPO_REF:-codex/independent-v1}"

config_get() {
  key="$1"
  default_value="$2"

  if [ -f "$BOT_CONFIG_PATH" ]; then
    value=$(grep "^${key}[[:space:]]*=" "$BOT_CONFIG_PATH" 2>/dev/null | grep -Eo "[0-9]{1,5}" | head -n1)
    if [ -n "$value" ]; then
      printf '%s' "$value"
      return 0
    fi
  fi

  printf '%s' "$default_value"
}

cleanup_update_artifacts() {
  keep_count="${1:-3}"
  ls -dt /opt/root/update-* 2>/dev/null | tail -n "+$((keep_count + 1))" | while IFS= read -r old_dir; do
    case "$old_dir" in /opt/root/update-*) rm -rf "$old_dir" ;; esac
  done
  ls -dt /opt/root/backup-* 2>/dev/null | tail -n "+$((keep_count + 1))" | while IFS= read -r old_dir; do
    case "$old_dir" in /opt/root/backup-*) rm -rf "$old_dir" ;; esac
  done
}

cleanup_pool_probe_runtime() {
  for pid in $(pgrep -f "/tmp/bypass_pool_probe_" 2>/dev/null); do
    kill "$pid" >/dev/null 2>&1 || true
  done
  sleep 1
  for pid in $(pgrep -f "/tmp/bypass_pool_probe_" 2>/dev/null); do
    kill -9 "$pid" >/dev/null 2>&1 || true
  done
  rm -f /tmp/bypass_pool_probe_*.json 2>/dev/null || true
}

cleanup_web_only_runtime() {
  [ -x /opt/etc/init.d/S99web_bot ] && /opt/etc/init.d/S99web_bot stop >/dev/null 2>&1 || true
  for web_pid in $(pgrep -f "python3.*web_bot.py" 2>/dev/null); do
    kill "$web_pid" >/dev/null 2>&1 || true
  done
  rm -f /opt/etc/init.d/S99web_bot /opt/etc/web_bot.py /opt/etc/web_bot.log 2>/dev/null || true
}

BOT_CONFIG_PATH="/opt/etc/bot_config.py"
BOT_MAIN_PATH="/opt/etc/bot.py"
BOT_SERVICE_PATH="/opt/etc/init.d/S99telegram_bot"
INSTALLER_MAIN_PATH="/opt/etc/bot/installer.py"
INSTALLER_SERVICE_PATH="/opt/etc/init.d/S98telegram_bot_installer"
if [ -f "/opt/etc/bot/bot_config.py" ]; then
  BOT_CONFIG_PATH="/opt/etc/bot/bot_config.py"
fi
if [ -d "/opt/etc/bot" ] || grep -q '/opt/etc/bot/main.py' /opt/etc/init.d/S99telegram_bot 2>/dev/null; then
  BOT_MAIN_PATH="/opt/etc/bot/main.py"
fi
BOT_RUNTIME_DIR=$(dirname "$BOT_MAIN_PATH")

download_static_asset() {
  repo_path="$1"
  target="$2"
  url="https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/${repo_path}"

  rm -f "$target"
  GITHUB_API_TIMEOUT=8 download_repo_file_via_api "$url" "$target" >/dev/null 2>&1 || true
  [ -s "$target" ] || rm -f "$target"
}

install_static_assets() {
  static_dir="${BOT_RUNTIME_DIR}/static"
  icons="chatgpt claude copilot deepseek discord facebook gemini grok instagram meta perplexity"
  mkdir -p "$static_dir/service-icons"
  download_static_asset "static/telegram.png" "$static_dir/telegram.png"
  download_static_asset "static/youtube.png" "$static_dir/youtube.png"
  for icon in $icons; do
    download_static_asset "static/service-icons/${icon}.png" "$static_dir/service-icons/${icon}.png"
  done
  find "$static_dir" -type d -exec chmod 755 {} \; 2>/dev/null || true
  find "$static_dir" -type f -exec chmod 644 {} \; 2>/dev/null || true
}

telegram_config_complete() {
  [ -f "$BOT_CONFIG_PATH" ] || return 1
  grep -q "^token[[:space:]]*=" "$BOT_CONFIG_PATH" || return 1
  grep -q "^usernames[[:space:]]*=" "$BOT_CONFIG_PATH" || return 1
}

start_telegram_installer() {
  [ -x "$BOT_SERVICE_PATH" ] && "$BOT_SERVICE_PATH" stop >/dev/null 2>&1 || true
  if [ -x "$INSTALLER_SERVICE_PATH" ]; then
    "$INSTALLER_SERVICE_PATH" restart >/dev/null 2>&1 || "$INSTALLER_SERVICE_PATH" start >/dev/null 2>&1 || true
    echo "Telegram-настройки не заполнены. Откройте web-интерфейс на порту $(config_get 'browser_port' '8080') и заполните token и username."
  else
    echo "⚠️ Telegram-настройки не заполнены, но installer service не найден."
  fi
}

# ip роутера
lanip=$(ip -4 addr show br0 | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -n1)
ssredir="ss-redir"
localportsh=$(config_get "localportsh" "1082")
localportvmess=$(config_get "localportvmess" "10810")
localportvless=$(config_get "localportvless" "10811")
localportvless_transparent=$((localportvless + 1))
localportvless2=$((localportvless + 2))
localportvless2_transparent=$((localportvless + 3))
localporttrojan=$(config_get "localporttrojan" "10829")
dnsovertlsport=$(config_get "dnsovertlsport" "40500")
dnsoverhttpsport=$(config_get "dnsoverhttpsport" "40508")
keen_os_full=$(curl -s localhost:79/rci/show/version/title | tr -d \",)
keen_os_short=$(printf '%s' "$keen_os_full" | grep -Eo '[0-9]+' | head -n1)

detect_core_proxy_package() {
  for candidate in xray-core xray v2ray; do
    if opkg list 2>/dev/null | awk '{print $1}' | grep -qx "$candidate"; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  printf '%s' 'v2ray'
}

preferred_core_service() {
  if [ -x /opt/etc/init.d/S24xray ]; then
    printf '%s' '/opt/etc/init.d/S24xray'
    return 0
  fi
  if [ -x /opt/etc/init.d/S24v2ray ]; then
    printf '%s' '/opt/etc/init.d/S24v2ray'
    return 0
  fi
  return 1
}

start_preferred_core_service() {
  preferred_core=$(preferred_core_service 2>/dev/null || true)

  if [ -x /opt/etc/init.d/S24xray ] && [ "$preferred_core" != "/opt/etc/init.d/S24xray" ]; then
    /opt/etc/init.d/S24xray stop > /dev/null 2>&1 || true
  fi
  if [ -x /opt/etc/init.d/S24v2ray ] && [ "$preferred_core" != "/opt/etc/init.d/S24v2ray" ]; then
    /opt/etc/init.d/S24v2ray stop > /dev/null 2>&1 || true
  fi
  if [ -n "$preferred_core" ]; then
    "$preferred_core" start > /dev/null 2>&1 || true
  fi
}

configure_core_proxy_service() {
  core_config_source="https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/vmessconfig.json"

  if [ ! -x /opt/etc/init.d/S24xray ] && [ -x /opt/sbin/xray ]; then
    cat > /opt/etc/init.d/S24xray <<'EOF'
#!/bin/sh

ENABLED=yes
PROCS=xray
ARGS="run -c /opt/etc/$PROCS/config.json"
PREARGS=""
DESC=$PROCS
PATH=/opt/sbin:/opt/bin:/opt/usr/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

. /opt/etc/init.d/rc.func
EOF
  fi

  if [ -x /opt/etc/init.d/S24xray ]; then
    mkdir -p /opt/etc/xray
    if [ ! -s /opt/etc/xray/config.json ]; then
      curl -fsSL --connect-timeout 5 --max-time 8 -o /opt/etc/xray/config.json "$core_config_source" >/dev/null 2>&1 || true
    fi
    chmod 755 /opt/etc/init.d/S24xray || chmod +x /opt/etc/init.d/S24xray
    sed -i 's|ARGS="-confdir /opt/etc/xray"|ARGS="run -c /opt/etc/xray/config.json"|g' /opt/etc/init.d/S24xray > /dev/null 2>&1 || true
    sed -i 's|ARGS="-config /opt/etc/xray/config.json"|ARGS="run -c /opt/etc/xray/config.json"|g' /opt/etc/init.d/S24xray > /dev/null 2>&1 || true
  fi

  if [ -x /opt/etc/init.d/S24v2ray ]; then
    mkdir -p /opt/etc/v2ray
    if [ ! -s /opt/etc/v2ray/config.json ]; then
      curl -fsSL --connect-timeout 5 --max-time 8 -o /opt/etc/v2ray/config.json "$core_config_source" >/dev/null 2>&1 || true
    fi
    chmod 755 /opt/etc/init.d/S24v2ray || chmod +x /opt/etc/init.d/S24v2ray
    sed -i 's|ARGS="-confdir /opt/etc/v2ray"|ARGS="run -c /opt/etc/v2ray/config.json"|g' /opt/etc/init.d/S24v2ray > /dev/null 2>&1 || true
  fi
}

ensure_entware_dns() {
  if nslookup bin.entware.net 192.168.1.1 >/dev/null 2>&1; then
    return 0
  fi

  echo "Локальный DNS не резолвит bin.entware.net, перестраиваем /etc/resolv.conf для Entware"
  tmp_resolv="/tmp/resolv.entware.$$"
  {
    printf 'nameserver 8.8.8.8\n'
    printf 'nameserver 1.1.1.1\n'
    grep -v '^[[:space:]]*nameserver[[:space:]]' /etc/resolv.conf 2>/dev/null || true
  } > "$tmp_resolv"
  cat "$tmp_resolv" > /etc/resolv.conf
  rm -f "$tmp_resolv"

  entware_ip=$(nslookup bin.entware.net 8.8.8.8 2>/dev/null | awk '/^Address [0-9]+: / {print $3}' | tail -n1)
  if [ -n "$entware_ip" ]; then
    tmp_hosts="/tmp/hosts.entware.$$"
    {
      grep -v '[[:space:]]bin\.entware\.net$' /etc/hosts 2>/dev/null || true
      printf '%s bin.entware.net\n' "$entware_ip"
    } > "$tmp_hosts"
    cat "$tmp_hosts" > /etc/hosts
    rm -f "$tmp_hosts"
    echo "bin.entware.net закреплён в /etc/hosts как $entware_ip"
  fi
}

download_repo_file_via_api() {
  url="$1"
  target="$2"
  raw_prefix="https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/"

  case "$url" in
    "$raw_prefix"*) repo_path=${url#"$raw_prefix"} ;;
    *) return 1 ;;
  esac

  command -v python3 >/dev/null 2>&1 || return 1
  REPO_OWNER="$repo" REPO_REF="$REPO_REF" REPO_PATH="$repo_path" TARGET_PATH="$target" python3 - <<'PY'
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

owner = os.environ['REPO_OWNER']
repo_ref = os.environ['REPO_REF']
repo_path = os.environ['REPO_PATH']
target_path = os.environ['TARGET_PATH']
api_url = (
    'https://api.github.com/repos/'
    + urllib.parse.quote(owner, safe='')
    + '/bypass_keenetic/contents/'
    + urllib.parse.quote(repo_path, safe='/')
    + '?ref='
    + urllib.parse.quote(repo_ref, safe='')
)
request = urllib.request.Request(
    api_url,
    headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'bypass-keenetic-updater'},
)
try:
    timeout = int(os.environ.get('GITHUB_API_TIMEOUT', '35'))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if payload.get('encoding') != 'base64' or 'content' not in payload:
        raise ValueError('unexpected GitHub contents API payload')
    content = ''.join(str(payload.get('content', '')).split())
    with open(target_path, 'wb') as output:
        output.write(base64.b64decode(content))
except Exception as exc:
    print('GitHub API fallback failed: %s' % exc, file=sys.stderr)
    sys.exit(1)
PY
}

repo_path_from_raw_url() {
  url="$1"
  raw_prefix="https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/"

  case "$url" in
    "$raw_prefix"*) printf '%s' "${url#"$raw_prefix"}" ;;
    *) return 1 ;;
  esac
}

validate_update_file() {
  target="$1"
  marker="$2"
  description="$3"

  if [ ! -s "$target" ]; then
    rm -f "$target"
    echo "Error: ${description} downloaded as empty file"
    return 1
  fi
  if [ -n "$marker" ] && ! grep -q "$marker" "$target"; then
    rm -f "$target"
    echo "Error: ${description} failed content validation"
    return 1
  fi
  return 0
}

download_raw_file_via_socks() {
  url="$1"
  target="$2"

  for port in ${GITHUB_RAW_SOCKS_PORTS:-10811 10813 10812 10814 10815}; do
    if curl -fsSL --socks5-hostname "127.0.0.1:${port}" --connect-timeout 6 --max-time 35 --retry 1 --retry-delay 1 -o "$target" "$url" >/dev/null 2>&1; then
      echo "Downloaded via local SOCKS port ${port}."
      return 0
    fi
  done
  return 1
}

prepare_update_archive() {
  [ -n "${UPDATE_ARCHIVE_ROOT:-}" ] && [ -d "$UPDATE_ARCHIVE_ROOT" ] && return 0
  [ -n "${stage_dir:-}" ] || return 1

  archive_work="$stage_dir/repo-archive"
  archive_file="$archive_work/repo.tar.gz"
  mkdir -p "$archive_work" || return 1

  archive_ref="$REPO_REF"
  case "$archive_ref" in
    refs/*) ;;
    */*) archive_ref="refs/heads/$archive_ref" ;;
  esac
  archive_url="https://codeload.github.com/${repo}/bypass_keenetic/tar.gz/${archive_ref}"

  curl -fsSL --connect-timeout 8 --max-time 90 -o "$archive_file" "$archive_url" >/dev/null 2>&1 || return 1
  tar -xzf "$archive_file" -C "$archive_work" >/dev/null 2>&1 || return 1
  UPDATE_ARCHIVE_ROOT=$(find "$archive_work" -mindepth 1 -maxdepth 1 -type d | head -n1)
  [ -n "$UPDATE_ARCHIVE_ROOT" ] && [ -d "$UPDATE_ARCHIVE_ROOT" ] || return 1
  export UPDATE_ARCHIVE_ROOT
  echo "GitHub archive fallback is ready."
  return 0
}

download_repo_file_from_archive() {
  url="$1"
  target="$2"
  repo_path=$(repo_path_from_raw_url "$url") || return 1

  prepare_update_archive || return 1
  src="$UPDATE_ARCHIVE_ROOT/$repo_path"
  [ -f "$src" ] || return 1
  cp "$src" "$target"
}

download_update_file() {
  url="$1"
  target="$2"
  marker="$3"
  description="$4"

  rm -f "$target" "$target".tmp.*
  if [ "${RAW_GITHUB_USE_SOCKS:-0}" = "1" ]; then
    if download_raw_file_via_socks "$url" "$target"; then
      validate_update_file "$target" "$marker" "$description" || return 1
      return 0
    fi
    rm -f "$target"
    RAW_GITHUB_BYPASS=1
    export RAW_GITHUB_BYPASS
  fi

  if [ "${RAW_GITHUB_BYPASS:-0}" = "1" ]; then
    echo "Using GitHub archive/API fallback for ${description}."
    if download_repo_file_from_archive "$url" "$target" || download_repo_file_via_api "$url" "$target"; then
      validate_update_file "$target" "$marker" "$description" || return 1
      return 0
    fi
    echo "Error: failed to download ${description}"
    return 1
  fi

  if curl -fsSL --connect-timeout 5 --max-time 8 -o "$target" "$url" >/dev/null 2>&1; then
    validate_update_file "$target" "$marker" "$description" || return 1
    return 0
  fi

  rm -f "$target"
  RAW_GITHUB_USE_SOCKS=1
  export RAW_GITHUB_USE_SOCKS
  echo "raw.githubusercontent.com direct download failed for ${description}; trying local SOCKS."
  if download_raw_file_via_socks "$url" "$target"; then
    validate_update_file "$target" "$marker" "$description" || return 1
    return 0
  fi

  rm -f "$target"
  RAW_GITHUB_BYPASS=1
  export RAW_GITHUB_BYPASS
  echo "raw.githubusercontent.com unavailable; using GitHub archive fallback."
  if download_repo_file_from_archive "$url" "$target" || download_repo_file_via_api "$url" "$target"; then
    validate_update_file "$target" "$marker" "$description" || return 1
    return 0
  fi

  echo "Error: failed to download ${description}"
  return 1
}

runtime_module_url() {
  printf '%s\n' "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/$1"
}

install_runtime_module() {
  module="$1"
  curl -fsSL -o "$BOT_RUNTIME_DIR/$module" "$(runtime_module_url "$module")" || exit 1
  chmod 644 "$BOT_RUNTIME_DIR/$module"
}

stage_runtime_module() {
  module="$1"
  marker="$2"
  download_update_file "$(runtime_module_url "$module")" "$stage_dir/$module" "$marker" "$module"
}

backup_runtime_module() {
  module="$1"
  [ -f "$BOT_RUNTIME_DIR/$module" ] && mv "$BOT_RUNTIME_DIR/$module" "$backup_dir/$module"
}

activate_runtime_module() {
  module="$1"
  mv "$stage_dir/$module" "$BOT_RUNTIME_DIR/$module"
  chmod 644 "$BOT_RUNTIME_DIR/$module"
}

install_runtime_modules() {
  for module in "$@"; do
    install_runtime_module "$module"
  done
}

backup_runtime_modules() {
  for module in "$@"; do
    backup_runtime_module "$module"
  done
}

activate_runtime_modules() {
  for module in "$@"; do
    activate_runtime_module "$module"
  done
}

BOT_RUNTIME_MODULES="pool_probe_runner.py key_pool_store.py key_pool_web.py telegram_pool_ui.py probe_cache.py custom_checks_store.py service_catalog.py web_form_template.py web_http_common.py web_command_state.py unblock_lists.py proxy_key_store.py proxy_protocols.py proxy_config_builder.py proxy_status.py installer_common.py"

if [ "$1" = "-remove" ]; then
    echo "Начинаем удаление"
    opkg remove bind-dig cron dnsmasq-full ipset iptables shadowsocks-libev-ss-redir shadowsocks-libev-config xray-core xray v2ray trojan
    echo "Пакеты удалены, удаляем папки, файлы и настройки"
    ipset flush testset
    ipset flush unblocksh
    ipset flush unblockvmess
    ipset flush unblockvless
    ipset flush unblockvless2
    ipset flush unblocktroj
    chmod 777 /opt/root/get-pip.py || rm -Rfv /opt/root/get-pip.py
    chmod 777 /opt/etc/crontab || rm -Rfv /opt/etc/crontab
    chmod 777 /opt/etc/init.d/S22shadowsocks || rm -Rfv /opt/etc/init.d/S22shadowsocks
    chmod 777 /opt/etc/init.d/S22trojan || rm -Rfv /opt/etc/init.d/S22trojan
    chmod 777 /opt/etc/init.d/S24xray || rm -Rfv /opt/etc/init.d/S24xray
    chmod 777 /opt/etc/init.d/S24v2ray || rm -Rfv /opt/etc/init.d/S24v2ray
    chmod 777 /opt/etc/init.d/S35tor || rm -Rfv /opt/etc/init.d/S35tor
    chmod 777 /opt/etc/init.d/S56dnsmasq || rm -Rfv /opt/etc/init.d/S56dnsmasq
    chmod 777 /opt/etc/init.d/S99unblock || rm -Rfv /opt/etc/init.d/S99unblock
    chmod 777 /opt/etc/ndm/netfilter.d/100-redirect.sh || rm -rfv /opt/etc/ndm/netfilter.d/100-redirect.sh
    chmod 777 /opt/etc/ndm/ifstatechanged.d/100-unblock-vpn.sh || rm -rfv /opt/etc/ndm/ifstatechanged.d/100-unblock-vpn.sh
    chmod 777 /opt/etc/ndm/fs.d/100-ipset.sh || rm -rfv /opt/etc/ndm/fs.d/100-ipset.sh
    chmod 777 /opt/bin/unblock_dnsmasq.sh || rm -rfv /opt/bin/unblock_dnsmasq.sh
    chmod 777 /opt/bin/unblock_update.sh || rm -rfv /opt/bin/unblock_update.sh
    chmod 777 /opt/bin/unblock_ipset.sh || rm -rfv /opt/bin/unblock_ipset.sh
    chmod 777 /opt/etc/unblock.dnsmasq || rm -rfv /opt/etc/unblock.dnsmasq
    chmod 777 /opt/etc/dnsmasq.conf || rm -rfv /opt/etc/dnsmasq.conf
    chmod 777 /opt/tmp/tor || rm -Rfv /opt/tmp/tor
    # chmod 777 /opt/etc/unblock || rm -Rfv /opt/etc/unblock
    chmod 777 /opt/etc/tor || rm -Rfv /opt/etc/tor
    chmod 777 /opt/etc/xray || rm -Rfv /opt/etc/xray
    chmod 777 /opt/etc/v2ray || rm -Rfv /opt/etc/v2ray
    chmod 777 /opt/etc/trojan || rm -Rfv /opt/etc/trojan
    echo "Созданные папки, файлы и настройки удалены"
    echo "Если вы хотите полностью отключить DNS Override, перейдите в меню Сервис -> DNS Override -> DNS Override ВЫКЛ. После чего включится встроенный (штатный) DNS и роутер перезагрузится."
    #echo "Отключаем opkg dns-override"
    #ndmc -c 'no opkg dns-override'
    #sleep 3
    #echo "Сохраняем конфигурацию на роутере"
    #ndmc -c 'system configuration save'
    #sleep 3
    #echo "Перезагрузка роутера"
    #sleep 3
    #ndmc -c 'system reboot'
    exit 0
fi

if [ "$1" = "-install" ]; then
    echo "Начинаем установку"
    echo "Ваша версия KeenOS" "${keen_os_full}"
  ensure_entware_dns
    opkg update
    core_proxy_pkg=$(detect_core_proxy_package)
    opkg install curl mc bind-dig cron dnsmasq-full ipset iptables shadowsocks-libev-ss-redir shadowsocks-libev-config python3 python3-pip "$core_proxy_pkg" trojan
    curl -O https://bootstrap.pypa.io/get-pip.py
    sleep 3
    python get-pip.py
    pip install pyTelegramBotAPI pysocks
    #pip install pathlib
    #pip install --upgrade pip
    #pip install pytelegrambotapi
    #pip install paramiko
    echo "Установка пакетов завершена. Продолжаем установку"

    #ipset flush unblocksh
    #ipset flush unblockvmess
    #ipset flush unblocktroj
    #ipset flush testset

    # есть поддержка множества hash:net или нет, если нет, то при этом вы потеряете возможность разблокировки по диапазону и CIDR
    set_type="hash:net"
    ipset create testset hash:net -exist > /dev/null 2>&1
    retVal=$?
    if [ $retVal -ne 0 ]; then
        set_type="hash:ip"
    fi

    echo "Переменные роутера найдены"
    # создания множеств IP-адресов unblock
    # rm -rf /opt/etc/ndm/fs.d/100-ipset.sh
    # chmod 777 /opt/etc/ndm/fs.d/100-ipset.sh || rm -rfv /opt/etc/ndm/fs.d/100-ipset.sh
    curl -o /opt/etc/ndm/fs.d/100-ipset.sh https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/100-ipset.sh
    chmod 755 /opt/etc/ndm/fs.d/100-ipset.sh || chmod +x /opt/etc/ndm/fs.d/100-ipset.sh
    sed -i "s/hash:net/${set_type}/g" /opt/etc/ndm/fs.d/100-ipset.sh
    echo "Созданы файлы под множества"

    # chmod 777 /opt/etc/shadowsocks.json || rm -Rfv /opt/etc/shadowsocks.json
    # chmod 777 /opt/etc/init.d/S22shadowsocks
    curl -o /opt/etc/shadowsocks.json https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/shadowsocks.json
    echo "Установлены настройки Shadowsocks"
    sed -i "s/ss-local/${ssredir}/g" /opt/etc/init.d/S22shadowsocks
    chmod 0755 /opt/etc/shadowsocks.json || chmod 755 /opt/etc/init.d/S22shadowsocks || chmod +x /opt/etc/init.d/S22shadowsocks
    echo "Установлен параметр ss-redir для Shadowsocks"

    # chmod 777 /opt/etc/trojan/config.json || rm -Rfv /opt/etc/trojan/config.json
    curl -o /opt/etc/trojan/config.json https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/trojanconfig.json
    configure_core_proxy_service

    # unblock folder and files
    mkdir -p /opt/etc/unblock
    touch /opt/etc/hosts || chmod 0755 /opt/etc/hosts
    touch /opt/etc/unblock/shadowsocks.txt || chmod 0755 /opt/etc/unblock/shadowsocks.txt
    touch /opt/etc/unblock/trojan.txt || chmod 0755 /opt/etc/unblock/trojan.txt
    touch /opt/etc/unblock/vmess.txt || chmod 0755 /opt/etc/unblock/vmess.txt
    touch /opt/etc/unblock/vless.txt || chmod 0755 /opt/etc/unblock/vless.txt
    touch /opt/etc/unblock/vless-2.txt || chmod 0755 /opt/etc/unblock/vless-2.txt
    echo "Созданы файлы под сайты и ip-адреса для обхода блокировок для SS, Trojan, Vmess и Vless"

    # unblock_ipset.sh
    # chmod 777 /opt/bin/unblock_ipset.sh || rm -rfv /opt/bin/unblock_ipset.sh
    curl -o /opt/bin/unblock_ipset.sh https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/unblock_ipset.sh
    chmod 755 /opt/bin/unblock_ipset.sh || chmod +x /opt/bin/unblock_ipset.sh
    sed -i "s/40500/${dnsovertlsport}/g" /opt/bin/unblock_ipset.sh
    echo "Установлен скрипт для заполнения множеств unblock IP-адресами заданного списка доменов"

    # unblock_dnsmasq.sh
    # chmod 777 /opt/bin/unblock_dnsmasq.sh || rm -rfv /opt/bin/unblock_dnsmasq.sh
    curl -o /opt/bin/unblock_dnsmasq.sh https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/unblock.dnsmasq
    chmod 755 /opt/bin/unblock_dnsmasq.sh || chmod +x /opt/bin/unblock_dnsmasq.sh
    sed -i "s/40500/${dnsovertlsport}/g" /opt/bin/unblock_dnsmasq.sh
    /opt/bin/unblock_dnsmasq.sh
    echo "Установлен скрипт для формирования дополнительного конфигурационного файла dnsmasq из заданного списка доменов и его запуск"

    # unblock_update.sh
    # chmod 777 /opt/bin/unblock_update.sh || rm -rfv /opt/bin/unblock_update.sh
    curl -o /opt/bin/unblock_update.sh https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/unblock_update.sh
    chmod 755 /opt/bin/unblock_update.sh || chmod +x /opt/bin/unblock_update.sh
    echo "Установлен скрипт ручного принудительного обновления системы после редактирования списка доменов"

    # s99unblock
    # chmod 777 /opt/etc/init.d/S99unblock || rm -Rfv /opt/etc/init.d/S99unblock
    curl -o /opt/etc/init.d/S99unblock https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/S99unblock
    chmod 755 /opt/etc/init.d/S99unblock || chmod +x /opt/etc/init.d/S99unblock
    echo "Установлен cкрипт автоматического заполнения множества unblock при загрузке маршрутизатора"

    # 100-redirect.sh
    # chmod 777 /opt/etc/ndm/netfilter.d/100-redirect.sh || rm -rfv /opt/etc/ndm/netfilter.d/100-redirect.sh
    curl -o /opt/etc/ndm/netfilter.d/100-redirect.sh https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/100-redirect.sh
    chmod 755 /opt/etc/ndm/netfilter.d/100-redirect.sh || chmod +x /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/hash:net/${set_type}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/192.168.1.1/${lanip}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/1082/${localportsh}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/10810/${localportvmess}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/10811/${localportvless}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/10812/${localportvless_transparent}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/10813/${localportvless2}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/10814/${localportvless2_transparent}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/10829/${localporttrojan}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    echo "Установлено перенаправление пакетов с адресатами из unblock в: Shadowsocks, Trojan, xray/v2ray. Правила работают на всех интерфейсах, включая клиентов, подключённых к роутеру по VPN."

    # dnsmasq.conf
    #rm -rf /opt/etc/dnsmasq.conf
    chmod 777 /opt/etc/dnsmasq.conf || rm -rfv /opt/etc/dnsmasq.conf
    curl -o /opt/etc/dnsmasq.conf https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/dnsmasq.conf
    chmod 755 /opt/etc/dnsmasq.conf
    sed -i "s/192.168.1.1/${lanip}/g" /opt/etc/dnsmasq.conf
    sed -i "s/40500/${dnsovertlsport}/g" /opt/etc/dnsmasq.conf
    sed -i "s/40508/${dnsoverhttpsport}/g" /opt/etc/dnsmasq.conf
    echo "Установлена настройка dnsmasq и подключение дополнительного конфигурационного файла к dnsmasq"

    # cron file
    #rm -rf /opt/etc/crontab
    chmod 777 /opt/etc/crontab || rm -Rfv /opt/etc/crontab
    curl -o /opt/etc/crontab https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/crontab
    chmod 755 /opt/etc/crontab
    echo "Установлено добавление задачи в cron для периодического обновления содержимого множества"
    mkdir -p "$BOT_RUNTIME_DIR"
    install_runtime_modules $BOT_RUNTIME_MODULES
    install_static_assets
    /opt/bin/unblock_update.sh
    echo "Установлены все изначальные скрипты и скрипты разблокировок, выполнена основная настройка бота"

    #ndmc -c 'opkg dns-override'
    #sleep 3
    #ndmc -c 'system configuration save'
    #sleep 3
    #echo "Перезагрузка роутера"
    #ndmc -c 'system reboot'
    #sleep 5

    exit 0
fi

if [ "$1" = "-reinstall" ]; then
    curl -s -o /opt/root/script.sh https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/script.sh
    chmod 755 /opt/root/script.sh || chmod +x /opt/root/script.sh
    echo "Начинаем переустановку"
    #opkg update
    echo "Удаляем установленные пакеты и созданные файлы"
    /bin/sh /opt/root/script.sh -remove
    echo "Удаление завершено"
    echo "Выполняем установку"
    /bin/sh /opt/root/script.sh -install
    echo "Установка выполнена."
    exit 0
fi


if [ "$1" = "-update" ]; then
    echo "Начинаем обновление."
  ensure_entware_dns
    opkg update > /dev/null 2>&1
    core_proxy_pkg=$(detect_core_proxy_package)
    opkg install "$core_proxy_pkg" > /dev/null 2>&1 || true
    # opkg update
    echo "Ваша версия KeenOS" "${keen_os_full}."
    echo "Пакеты обновлены."

    now=$(date +"%Y.%m.%d.%H-%M-%S")
    stage_dir="/opt/root/update-${now}"
    backup_dir="/opt/root/backup-${now}"
    mkdir -p "$stage_dir"

    echo "Скачиваем обновления во временную папку и проверяем файлы."
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/100-ipset.sh" "$stage_dir/100-ipset.sh" "#!/bin/sh" "100-ipset.sh" || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/100-redirect.sh" "$stage_dir/100-redirect.sh" "iptables -I PREROUTING" "100-redirect.sh" || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/unblock_ipset.sh" "$stage_dir/unblock_ipset.sh" "#!/bin/sh" "unblock_ipset.sh" || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/unblock.dnsmasq" "$stage_dir/unblock_dnsmasq.sh" "#!/bin/sh" "unblock.dnsmasq" || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/unblock_update.sh" "$stage_dir/unblock_update.sh" "#!/bin/sh" "unblock_update.sh" || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/dnsmasq.conf" "$stage_dir/dnsmasq.conf" "listen-address=" "dnsmasq.conf" || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/bot.py" "$stage_dir/bot.py" "KeyInstallHTTPRequestHandler" "bot.py" || exit 1
    stage_runtime_module pool_probe_runner.py run_pool_probe_worker || exit 1
    stage_runtime_module key_pool_store.py "def normalize_key_pools" || exit 1
    stage_runtime_module key_pool_web.py pool_status_summary || exit 1
    stage_runtime_module telegram_pool_ui.py pool_action_markup || exit 1
    stage_runtime_module probe_cache.py record_key_probe || exit 1
    stage_runtime_module custom_checks_store.py add_custom_check || exit 1
    stage_runtime_module service_catalog.py CUSTOM_CHECK_PRESETS || exit 1
    stage_runtime_module web_form_template.py render_web_form || exit 1
    stage_runtime_module web_http_common.py WebRequestMixin || exit 1
    stage_runtime_module web_command_state.py start_command || exit 1
    stage_runtime_module unblock_lists.py save_unblock_list_file || exit 1
    stage_runtime_module proxy_key_store.py load_current_keys || exit 1
    stage_runtime_module proxy_protocols.py proxy_outbound_from_key || exit 1
    stage_runtime_module proxy_config_builder.py build_proxy_core_config || exit 1
    stage_runtime_module proxy_status.py status_snapshot_signature || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/installer.py" "$stage_dir/installer.py" "ThreadingHTTPServer" "installer.py" || exit 1
    stage_runtime_module installer_common.py browser_port_is_valid || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/S98telegram_bot_installer" "$stage_dir/S98telegram_bot_installer" "Installer started" "S98telegram_bot_installer" || exit 1
    download_update_file "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/S99telegram_bot" "$stage_dir/S99telegram_bot" "Bot started" "S99telegram_bot" || exit 1

    sed -i "s/hash:net/${set_type}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/192.168.1.1/${lanip}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/1082/${localportsh}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10810/${localportvmess}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10811/${localportvless}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10812/${localportvless_transparent}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10813/${localportvless2}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10814/${localportvless2_transparent}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10829/${localporttrojan}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/40500/${dnsovertlsport}/g" "$stage_dir/unblock_ipset.sh"
    sed -i "s/40500/${dnsovertlsport}/g" "$stage_dir/unblock_dnsmasq.sh"
    sed -i "s/192.168.1.1/${lanip}/g" "$stage_dir/dnsmasq.conf"
    sed -i "s/40500/${dnsovertlsport}/g" "$stage_dir/dnsmasq.conf"
    sed -i "s/40508/${dnsoverhttpsport}/g" "$stage_dir/dnsmasq.conf"
    echo "Файлы успешно скачаны и подготовлены."
    echo "Further update output is saved to $stage_dir/update.log."
    exec >> "$stage_dir/update.log" 2>&1

    /opt/etc/init.d/S22shadowsocks stop > /dev/null 2>&1
    /opt/etc/init.d/S24xray stop > /dev/null 2>&1
    /opt/etc/init.d/S24v2ray stop > /dev/null 2>&1
    /opt/etc/init.d/S22trojan stop > /dev/null 2>&1
    echo "Сервисы остановлены."

    mkdir -p "$backup_dir"
    [ -f /opt/bin/unblock_ipset.sh ] && mv /opt/bin/unblock_ipset.sh "$backup_dir"/unblock_ipset.sh
    [ -f /opt/bin/unblock_dnsmasq.sh ] && mv /opt/bin/unblock_dnsmasq.sh "$backup_dir"/unblock_dnsmasq.sh
    [ -f /opt/bin/unblock_update.sh ] && mv /opt/bin/unblock_update.sh "$backup_dir"/unblock_update.sh
    [ -f /opt/etc/dnsmasq.conf ] && mv /opt/etc/dnsmasq.conf "$backup_dir"/dnsmasq.conf
    [ -f /opt/etc/ndm/fs.d/100-ipset.sh ] && mv /opt/etc/ndm/fs.d/100-ipset.sh "$backup_dir"/100-ipset.sh
    [ -f /opt/etc/ndm/netfilter.d/100-redirect.sh ] && mv /opt/etc/ndm/netfilter.d/100-redirect.sh "$backup_dir"/100-redirect.sh
    if [ -f "$BOT_MAIN_PATH" ]; then
      mv "$BOT_MAIN_PATH" "$backup_dir"/bot.py
    fi
    backup_runtime_modules $BOT_RUNTIME_MODULES
    rm -f /opt/etc/ndm/ifstatechanged.d/100-unblock-vpn.sh > /dev/null 2>&1
    rm -f /opt/etc/init.d/S35tor > /dev/null 2>&1
    chmod 755 "$backup_dir"/* 2>/dev/null
    echo "Бэкап создан."

    touch /opt/etc/hosts || chmod 0755 /opt/etc/hosts
    mv "$stage_dir/100-ipset.sh" /opt/etc/ndm/fs.d/100-ipset.sh
    chmod 755 /opt/etc/ndm/fs.d/100-ipset.sh || chmod +x /opt/etc/ndm/fs.d/100-ipset.sh
    mv "$stage_dir/100-redirect.sh" /opt/etc/ndm/netfilter.d/100-redirect.sh
    chmod 755 /opt/etc/ndm/netfilter.d/100-redirect.sh || chmod +x /opt/etc/ndm/netfilter.d/100-redirect.sh
    if [ -x /opt/etc/init.d/S24xray ]; then
      sed -i 's|ARGS="-confdir /opt/etc/xray"|ARGS="run -c /opt/etc/xray/config.json"|g' /opt/etc/init.d/S24xray > /dev/null 2>&1 || true
      sed -i 's|ARGS="-config /opt/etc/xray/config.json"|ARGS="run -c /opt/etc/xray/config.json"|g' /opt/etc/init.d/S24xray > /dev/null 2>&1 || true
    fi
    sed -i 's|ARGS="-confdir /opt/etc/v2ray"|ARGS="run -c /opt/etc/v2ray/config.json"|g' /opt/etc/init.d/S24v2ray > /dev/null 2>&1 || true

    mv "$stage_dir/unblock_ipset.sh" /opt/bin/unblock_ipset.sh
    mv "$stage_dir/unblock_dnsmasq.sh" /opt/bin/unblock_dnsmasq.sh
    mv "$stage_dir/unblock_update.sh" /opt/bin/unblock_update.sh
    chmod 755 /opt/bin/unblock_*.sh || chmod +x /opt/bin/unblock_*.sh

    mv "$stage_dir/dnsmasq.conf" /opt/etc/dnsmasq.conf
    chmod 755 /opt/etc/dnsmasq.conf

    configure_core_proxy_service

    mkdir -p "$BOT_RUNTIME_DIR"
    mv "$stage_dir/bot.py" "$BOT_MAIN_PATH"
    chmod 755 "$BOT_MAIN_PATH"
    activate_runtime_modules $BOT_RUNTIME_MODULES
    mkdir -p "$(dirname "$INSTALLER_MAIN_PATH")"
    mv "$stage_dir/installer.py" "$INSTALLER_MAIN_PATH"
    chmod 755 "$INSTALLER_MAIN_PATH"
    install_static_assets
    mv "$stage_dir/S98telegram_bot_installer" "$INSTALLER_SERVICE_PATH"
    mv "$stage_dir/S99telegram_bot" "$BOT_SERVICE_PATH"
    chmod 755 "$INSTALLER_SERVICE_PATH" "$BOT_SERVICE_PATH"
    rmdir "$stage_dir" 2>/dev/null || true
    cleanup_update_artifacts 3
    echo "Обновления скачены, права настроены."

    /opt/etc/init.d/S56dnsmasq restart > /dev/null 2>&1
    /opt/etc/init.d/S22shadowsocks start > /dev/null 2>&1
    start_preferred_core_service
    /opt/etc/init.d/S22trojan start > /dev/null 2>&1

    bot_old_version=$(grep -m1 "ВЕРСИЯ" "$BOT_CONFIG_PATH" 2>/dev/null | grep -Eo "[0-9][0-9A-Za-z._ -]*" | head -n1)
    bot_new_version=$(grep -m1 "ВЕРСИЯ" "$BOT_MAIN_PATH" 2>/dev/null | grep -Eo "[0-9][0-9A-Za-z._ -]*" | head -n1)

    if [ -n "$bot_old_version" ] && [ -n "$bot_new_version" ]; then
      echo "Версия бота ${bot_old_version} обновлена до ${bot_new_version}."
      escaped_old_version=$(printf '%s\n' "$bot_old_version" | sed 's/[\\/&]/\\\\&/g')
      escaped_new_version=$(printf '%s\n' "$bot_new_version" | sed 's/[\\/&]/\\\\&/g')
      sed -i "s/${escaped_old_version}/${escaped_new_version}/g" "$BOT_CONFIG_PATH" || true
    elif [ -n "$bot_new_version" ]; then
      echo "Версия бота обновлена до ${bot_new_version}."
    else
      echo "Версия бота обновлена."
    fi
    sleep 2
    echo "Обновление выполнено. Сервисы перезапущены. Сейчас будет перезапущен бот (~15-30 сек)."
    sleep 7
    cleanup_pool_probe_runtime
    cleanup_web_only_runtime
    cleanup_pool_probe_runtime
    if ! telegram_config_complete; then
      start_telegram_installer
      exit 0
    fi
    if [ -x "$BOT_SERVICE_PATH" ]; then
      "$BOT_SERVICE_PATH" restart
      sleep 3
      if "$BOT_SERVICE_PATH" status | grep -q "Bot is running"; then
        echo "Бот запущен. Нажмите сюда: /start"
      else
        echo "⚠️ Не удалось подтвердить перезапуск бота через сервис $BOT_SERVICE_PATH"
      fi
    else
      bot_pid=$(pgrep -f "python3 $BOT_MAIN_PATH")
      for bot in ${bot_pid}; do kill "${bot}" >/dev/null 2>&1 || true; done
      sleep 5
      python3 "$BOT_MAIN_PATH" &
      sleep 3
      check_running=$(pgrep -f "python3 $BOT_MAIN_PATH")
      if [ -n "${check_running}" ]; then
        echo "Бот запущен. Нажмите сюда: /start"
      else
        echo "⚠️ Не удалось подтвердить перезапуск бота"
      fi
    fi

    exit 0
fi

if [ "$1" = "-reboot" ]; then
    ndmc -c 'opkg dns-override'
    sleep 3
    ndmc -c 'system configuration save'
    sleep 3
    echo "Перезагрузка роутера"
    ndmc -c 'system reboot'
fi

if [ "$1" = "-version" ]; then
    echo "Ваша версия KeenOS" "${keen_os_full}"
fi

if [ "$1" = "-help" ]; then
    echo "-install - use for install all needs for work"
    echo "-remove - use for remove all files script"
    echo "-update - use for get update files"
    echo "-reinstall - use for reinstall all files script"
fi

if [ -z "$1" ]; then
    #echo not found "$1".
    echo "-install - use for install all needs for work"
    echo "-remove - use for remove all files script"
    echo "-update - use for get update files"
    echo "-reinstall - use for reinstall all files script"
fi

#if [ -n "$1" ]; then
#    echo not found "$1".
#    echo "-install - use for install all needs for work"
#    echo "-remove - use for remove all files script"
#    echo "-update - use for get update files"
#    echo "-reinstall - use for reinstall all files script"
#else
#    echo "-install - use for install all needs for work"
#    echo "-remove - use for remove all files script"
#    echo "-update - use for get update files"
#    echo "-reinstall - use for reinstall all files script"
#fi
