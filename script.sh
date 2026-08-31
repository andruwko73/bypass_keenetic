#!/bin/sh

repo="andruwko73"
REPO_REF="${REPO_REF:-main}"
REPO_APP_DIR="${BYPASS_REPO_APP_DIR:-app}"
if [ "${RAW_GITHUB_BYPASS:-0}" = "1" ] || [ -n "${UPDATE_ARCHIVE_ROOT:-}" ]; then
  unset RAW_GITHUB_USE_SOCKS RAW_GITHUB_SOCKS_NOTICE_SHOWN
else
  unset UPDATE_ARCHIVE_ROOT RAW_GITHUB_USE_SOCKS RAW_GITHUB_BYPASS RAW_GITHUB_SOCKS_NOTICE_SHOWN
fi

repo_file_url() {
  repo_path="$1"
  case "$repo_path" in
    script.sh|version.md|README.md|CHANGELOG.md|LICENSE|bootstrap/*)
      printf '%s\n' "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/${repo_path}"
      ;;
    *)
      printf '%s\n' "https://raw.githubusercontent.com/${repo}/bypass_keenetic/${REPO_REF}/${REPO_APP_DIR}/${repo_path}"
      ;;
  esac
}

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

detect_ipset_type() {
  set_type="hash:net"
  ipset create testset hash:net -exist > /dev/null 2>&1
  retVal=$?
  ipset destroy testset > /dev/null 2>&1 || true
  if [ $retVal -ne 0 ]; then
    set_type="hash:ip"
  fi
  printf '%s' "$set_type"
}

cleanup_update_artifacts() {
  keep_count="${1:-1}"
  ls -dt /opt/root/update-* 2>/dev/null | tail -n "+$((keep_count + 1))" | while IFS= read -r old_dir; do
    case "$old_dir" in /opt/root/update-*) rm -rf "$old_dir" ;; esac
  done
  ls -dt /opt/root/backup-* 2>/dev/null | tail -n "+$((keep_count + 1))" | while IFS= read -r old_dir; do
    case "$old_dir" in /opt/root/backup-*) rm -rf "$old_dir" ;; esac
  done
}

cleanup_removed_connection_artifacts() {
  [ -x /opt/etc/init.d/S35tor ] && /opt/etc/init.d/S35tor stop >/dev/null 2>&1 || true
  rm -f /opt/etc/init.d/S35tor 2>/dev/null || true
  rm -rf /opt/etc/tor /opt/tmp/tor /opt/etc/openvpn /opt/etc/wireguard 2>/dev/null || true
  rm -f /opt/etc/unblock/tor.txt /opt/etc/unblock/tor-*.txt /opt/etc/unblock/vpn.txt /opt/etc/unblock/vpn-*.txt 2>/dev/null || true
  rm -rf /opt/etc/ndm/netfilter.d/100-unblock-vpn /opt/etc/ndm/netfilter.d/100-unblock-vpn.sh 2>/dev/null || true
  rm -rf /opt/etc/ndm/ifstatechanged.d/100-unblock-vpn /opt/etc/ndm/ifstatechanged.d/100-unblock-vpn.sh 2>/dev/null || true
}

remove_path() {
  target="$1"
  [ -e "$target" ] || [ -L "$target" ] || return 0
  chmod -R u+rwx "$target" 2>/dev/null || true
  rm -rf "$target"
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
UPDATE_MAINTENANCE_PATH="/tmp/bypass_update_maintenance"
UPDATE_MAINTENANCE_READY_PATH="/tmp/bypass_update_maintenance.ready"
update_application_maintenance_active=0
update_application_was_running=0

main_application_pids() {
  lock_pid=""
  [ -f /tmp/bypass_telegram_bot_main.lock/pid ] && lock_pid=$(cat /tmp/bypass_telegram_bot_main.lock/pid 2>/dev/null || true)
  case "$lock_pid" in
    ''|*[!0-9]*) ;;
    *)
      if [ -r "/proc/$lock_pid/cmdline" ] && grep -qa "$BOT_MAIN_PATH" "/proc/$lock_pid/cmdline"; then
        printf '%s\n' "$lock_pid"
        return 0
      fi
      ;;
  esac
  pgrep -f "python3.*$BOT_MAIN_PATH" 2>/dev/null | head -n1 || true
}

clear_update_maintenance_files() {
  rm -f "$UPDATE_MAINTENANCE_PATH" "$UPDATE_MAINTENANCE_READY_PATH" 2>/dev/null || true
}

resume_application_after_cancelled_update() {
  clear_update_maintenance_files
  if grep -q 'UPDATE_MAINTENANCE_READY_PATH' "$BOT_MAIN_PATH" 2>/dev/null; then
    for bot_pid in $(main_application_pids); do
      kill -USR2 "$bot_pid" >/dev/null 2>&1 || true
    done
  fi
  update_application_maintenance_active=0
}

prepare_application_for_update() {
  echo "Переводим программу в режим обслуживания; веб-интерфейс остаётся доступным."
  write_cli_update_status update true 50 Обслуживание "Приостанавливаем Telegram и фоновые проверки; веб-интерфейс остаётся доступным"

  [ -x "$INSTALLER_SERVICE_PATH" ] && "$INSTALLER_SERVICE_PATH" stop >/dev/null 2>&1 || true
  cleanup_pool_probe_runtime

  if pgrep -f "/tmp/bypass_pool_probe_" >/dev/null 2>&1; then
    echo "Ошибка: процесс проверки пула ещё работает; обновление отменено до замены файлов"
    return 1
  fi

  bot_pids=$(main_application_pids)
  if [ -z "$bot_pids" ]; then
    echo "Основной процесс не запущен; обновление продолжится без режима обслуживания веб-интерфейса."
    update_application_was_running=0
    return 0
  fi

  update_application_was_running=1
  clear_update_maintenance_files
  : > "$UPDATE_MAINTENANCE_PATH"

  if grep -q 'UPDATE_MAINTENANCE_READY_PATH' "$BOT_MAIN_PATH" 2>/dev/null; then
    for bot_pid in $bot_pids; do
      kill -USR1 "$bot_pid" >/dev/null 2>&1 || {
        resume_application_after_cancelled_update
        echo "Ошибка: не удалось запросить режим обслуживания программы"
        return 1
      }
    done
    attempts=0
    while [ ! -f "$UPDATE_MAINTENANCE_READY_PATH" ] && [ "$attempts" -lt 35 ]; do
      sleep 1
      attempts=$((attempts + 1))
    done
    if [ ! -f "$UPDATE_MAINTENANCE_READY_PATH" ]; then
      resume_application_after_cancelled_update
      echo "Ошибка: программа не подтвердила режим обслуживания; обновление отменено до замены файлов"
      return 1
    fi
  else
    echo "Текущая версия ещё не поддерживает сигнал обслуживания; сохраняем прежнюю работу веб-интерфейса и блокируем внешние проверки скриптом."
    sleep 2
  fi

  if [ -z "$(main_application_pids)" ]; then
    clear_update_maintenance_files
    echo "Ошибка: программа остановилась при переходе в режим обслуживания"
    return 1
  fi
  update_application_maintenance_active=1
  echo "Режим обслуживания подтверждён; порт веб-интерфейса остаётся активным."
  return 0
}

stop_application_for_final_restart() {
  if [ -x "$BOT_SERVICE_PATH" ]; then
    "$BOT_SERVICE_PATH" stop || return 1
  else
    for bot_pid in $(main_application_pids); do
      kill "$bot_pid" >/dev/null 2>&1 || true
    done
    attempts=0
    while [ -n "$(main_application_pids)" ] && [ "$attempts" -lt 20 ]; do
      sleep 1
      attempts=$((attempts + 1))
    done
    [ -z "$(main_application_pids)" ] || return 1
  fi
  clear_update_maintenance_files
  update_application_maintenance_active=0
  return 0
}

recover_runtime_after_failed_update() {
  runtime_guard_path="$BOT_RUNTIME_DIR/update_runtime_guard.sh"
  if [ -f "$runtime_guard_path" ]; then
    . "$runtime_guard_path"
    bypass_capture_bot_start_failure \
      "$BOT_RUNTIME_DIR/error.log" \
      /opt/root/bypass-last-failed-update-bot.log \
      update-failed >/dev/null 2>&1 || true
  fi
  if [ "${update_runtime_quiesced:-0}" != "1" ]; then
    early_snapshot_tool="${backup_dir:-}/.rollback-tools/managed_state_snapshot.py"
    if [ -f "${backup_dir:-}/full-state/manifest.json" ] && [ -f "$early_snapshot_tool" ]; then
      PYTHONPATH="$(dirname "$early_snapshot_tool")" python3 \
        "$early_snapshot_tool" restore "$backup_dir/full-state" >/dev/null 2>&1 || true
    fi
    return 0
  fi
  echo "Обновление прервано в режиме обслуживания. Восстанавливаем рабочее состояние."
  if [ -n "${backup_dir:-}" ] && [ -x "$backup_dir/rollback.sh" ]; then
    /bin/sh "$backup_dir/rollback.sh" && return 0
    echo "Предупреждение: автоматический откат не удался; пробуем запустить установленный сервис бота."
  fi
  if [ "${update_application_was_running:-0}" = "1" ] && [ -n "$(main_application_pids)" ]; then
    resume_application_after_cancelled_update
    return 0
  fi
  clear_update_maintenance_files
  clear_runtime_update_env
  if [ -x "$BOT_SERVICE_PATH" ]; then
    "$BOT_SERVICE_PATH" start >/dev/null 2>&1 || "$BOT_SERVICE_PATH" restart >/dev/null 2>&1 || true
  fi
}

handle_cli_update_exit() {
  update_exit_code="$1"
  trap - EXIT
  trap '' TERM INT HUP
  if [ "${cli_update_status_active:-0}" = "1" ] && [ "$update_exit_code" -ne 0 ]; then
    recover_runtime_after_failed_update
    write_cli_update_status update false 100 Ошибка "Обновление не удалось; выполнена попытка восстановить рабочее состояние"
  fi
  exit "$update_exit_code"
}

clear_runtime_update_env() {
  if [ "${RAW_GITHUB_BYPASS:-0}" = "1" ] || [ -n "${UPDATE_ARCHIVE_ROOT:-}" ]; then
    unset RAW_GITHUB_USE_SOCKS RAW_GITHUB_SOCKS_NOTICE_SHOWN
  else
    unset REPO_REF UPDATE_ARCHIVE_ROOT RAW_GITHUB_USE_SOCKS RAW_GITHUB_BYPASS RAW_GITHUB_SOCKS_NOTICE_SHOWN
  fi
}

sanitize_xray26_compat() {
  for config_path in /opt/etc/xray/config.json /opt/etc/v2ray/config.json; do
    [ -f "$config_path" ] && sed -i '/allowInsecure/d' "$config_path" >/dev/null 2>&1 || true
  done
}

validate_xray_core_config() {
  xray_validate_config_path="${1:-/opt/etc/xray/config.json}"
  [ -x /opt/etc/init.d/S24xray ] || return 0
  [ -x /opt/sbin/xray ] || return 0
  [ -f "$xray_validate_config_path" ] || return 0
  log_path="/tmp/bypass-xray-test.log"
  if /opt/sbin/xray run -test -c "$xray_validate_config_path" > "$log_path" 2>&1; then
    return 0
  fi
  echo "Проверка конфигурации Xray завершилась ошибкой:"
  tail -n 12 "$log_path" 2>/dev/null || cat "$log_path" 2>/dev/null || true
  return 1
}

load_runtime_guard() {
  guard_path="$1"
  [ -f "$guard_path" ] || {
    echo "Ошибка: модуль контроля запуска не найден: $guard_path"
    return 1
  }
  . "$guard_path"
}

validate_staged_shell_runtime() {
  shell_checker=''
  shell_checker_mode='direct'
  if /bin/sh -n /dev/null >/dev/null 2>&1; then
    shell_checker=/bin/sh
  elif [ -x /opt/bin/sh ] && /opt/bin/sh -n /dev/null >/dev/null 2>&1; then
    shell_checker=/opt/bin/sh
  elif [ -x /opt/bin/bash ] && /opt/bin/bash -n /dev/null >/dev/null 2>&1; then
    shell_checker=/opt/bin/bash
  elif command -v busybox >/dev/null 2>&1 && busybox ash -n /dev/null >/dev/null 2>&1; then
    shell_checker=busybox
    shell_checker_mode=ash
  fi

  if [ -z "$shell_checker" ]; then
    echo "Предупреждение: установленный shell не поддерживает безопасный режим проверки -n; проверка shell уже выполнена при сборке релиза."
    return 0
  fi

  for shell_path in \
    "$stage_dir/script.sh" \
    "$stage_dir/100-ipset.sh" \
    "$stage_dir/100-redirect.sh" \
    "$stage_dir/unblock_ipset.sh" \
    "$stage_dir/unblock_dnsmasq.sh" \
    "$stage_dir/unblock_update.sh" \
    "$stage_dir/S99unblock" \
    "$stage_dir/S98telegram_bot_installer" \
    "$stage_dir/S99telegram_bot" \
    "$stage_dir/update_runtime_guard.sh"; do
    if [ "$shell_checker_mode" = "ash" ]; then
      busybox ash -n "$shell_path" || return 1
    else
      "$shell_checker" -n "$shell_path" || return 1
    fi
  done
}

validate_staged_update_runtime() {
  load_runtime_guard "$stage_dir/update_runtime_guard.sh" || return 1
  validate_staged_shell_runtime || return 1
  candidate_config="$stage_dir/.candidate-core-config.json"
  if ! bypass_validate_staged_python_runtime "$stage_dir" "$BOT_RUNTIME_DIR"; then
    rm -f "$candidate_config" 2>/dev/null || true
    return 1
  fi
  validate_xray_core_config "$candidate_config"
  validation_rc=$?
  rm -f "$candidate_config" 2>/dev/null || true
  return "$validation_rc"
}

bypass_runtime_status_heartbeat() {
  [ "${cli_update_status_active:-0}" -eq 1 ] || return 0
  heartbeat_elapsed="$1"
  heartbeat_timeout="$2"
  heartbeat_attempt="${runtime_start_attempt:-1}"
  write_cli_update_status update true 88 Запуск \
    "Проверяем готовность новой версии: попытка ${heartbeat_attempt}/2, ${heartbeat_elapsed}/${heartbeat_timeout} сек."
}

start_updated_bot_transactionally() {
  load_runtime_guard "$BOT_RUNTIME_DIR/update_runtime_guard.sh" || return 1
  attempt=0
  while [ "$attempt" -lt 2 ]; do
    attempt=$((attempt + 1))
    runtime_start_attempt="$attempt"
    write_cli_update_status update true 88 Запуск \
      "Проверяем готовность новой версии: попытка ${attempt}/2"
    bypass_clear_stale_main_lock "$BOT_MAIN_PATH" || true
    start_rc=0
    "$BOT_SERVICE_PATH" start || start_rc=$?
    readiness_timeout=45
    [ "$start_rc" -eq 0 ] || readiness_timeout=5
    if bypass_apply_runtime_network_rules && \
       bypass_wait_application_ready "$BOT_SERVICE_PATH" "$readiness_timeout"; then
      return 0
    fi
    bypass_capture_bot_start_failure \
      "$BOT_RUNTIME_DIR/error.log" \
      /opt/root/bypass-last-failed-update-bot.log \
      "update-start-attempt-$attempt" >/dev/null 2>&1 || true
    "$BOT_SERVICE_PATH" stop >/dev/null 2>&1 || true
    sleep 2
  done
  echo "Ошибка: новая версия не достигла готовности: ${BYPASS_RUNTIME_GUARD_REASON:-причина сохранена в закрытом диагностическом файле}"
  return 1
}

download_static_asset() {
  repo_path="$1"
  target="$2"
  url="$(repo_file_url "$repo_path")"
  temporary="${target}.update.$$"

  rm -f "$temporary"
  download_repo_file_from_archive "$url" "$temporary" >/dev/null 2>&1 || true
  if [ ! -s "$temporary" ]; then
    GITHUB_API_TIMEOUT=12 download_repo_file_via_api "$url" "$temporary" >/dev/null 2>&1 || true
  fi
  if [ ! -s "$temporary" ]; then
    curl -fsSL --connect-timeout 12 --max-time 30 --retry 2 --retry-delay 1 -o "$temporary" "$url" >/dev/null 2>&1 || true
  fi
  if [ -s "$temporary" ]; then
    mv -f "$temporary" "$target"
    return 0
  fi
  rm -f "$temporary"
  return 1
}

static_asset_paths() {
  printf '%s\n' \
    app.css app.js telegram.svg youtube.svg \
    service-icons/chatgpt.png service-icons/claude.png service-icons/copilot.png \
    service-icons/deepseek.png service-icons/discord.png \
    service-icons/gemini.png service-icons/grok.png service-icons/instagram.png \
    service-icons/perplexity.png service-icons/telegram.png service-icons/tiktok.png \
    service-icons/youtube.png service-icons/chrome_remote_desktop.png
}

activate_static_assets_dir() {
  source_dir="$1"
  static_dir="${BOT_RUNTIME_DIR}/static"
  next_dir="${BOT_RUNTIME_DIR}/.static.next.$$"
  old_dir="${BOT_RUNTIME_DIR}/.static.old.$$"

  [ -s "$source_dir/app.css" ] || return 1
  [ -s "$source_dir/app.js" ] || return 1
  rm -rf "$next_dir" "$old_dir"
  mkdir -p "$next_dir" || return 1
  cp -a "$source_dir"/. "$next_dir"/ || { rm -rf "$next_dir"; return 1; }
  find "$next_dir" -type d -exec chmod 755 {} \; 2>/dev/null || true
  find "$next_dir" -type f -exec chmod 644 {} \; 2>/dev/null || true

  if [ -d "$static_dir" ]; then
    mv "$static_dir" "$old_dir" || { rm -rf "$next_dir"; return 1; }
  fi
  if ! mv "$next_dir" "$static_dir"; then
    [ -d "$old_dir" ] && mv "$old_dir" "$static_dir" 2>/dev/null || true
    rm -rf "$next_dir"
    return 1
  fi
  rm -rf "$old_dir" "$source_dir"
}

install_static_assets() {
  download_dir="${BOT_RUNTIME_DIR}/.static.download.$$"
  rm -rf "$download_dir"
  mkdir -p "$download_dir/service-icons" || return 1
  for asset_path in $(static_asset_paths); do
    download_static_asset "static/${asset_path}" "$download_dir/${asset_path}" || {
      rm -rf "$download_dir"
      return 1
    }
  done
  activate_static_assets_dir "$download_dir"
}

stage_static_assets() {
  staged_static_dir="$stage_dir/static"
  rm -rf "$staged_static_dir"
  mkdir -p "$staged_static_dir/service-icons" || return 1
  for asset_path in $(static_asset_paths); do
    marker=""
    [ "$asset_path" = "app.css" ] && marker=".hero-popover"
    [ "$asset_path" = "app.js" ] && marker="setupBackgroundControls"
    download_update_file "$(repo_file_url "static/${asset_path}")" "$staged_static_dir/${asset_path}" "$marker" "static/${asset_path}" || return 1
  done
}

install_staged_static_assets() {
  activate_static_assets_dir "$stage_dir/static"
}

telegram_config_complete() {
  [ -f "$BOT_CONFIG_PATH" ] || return 1
  grep -q "^token[[:space:]]*=" "$BOT_CONFIG_PATH" || return 1
  grep -q "^usernames[[:space:]]*=" "$BOT_CONFIG_PATH" || return 1
}

start_telegram_installer() {
  clear_runtime_update_env
  [ -x "$BOT_SERVICE_PATH" ] && "$BOT_SERVICE_PATH" stop >/dev/null 2>&1 || true
  if [ -x "$INSTALLER_SERVICE_PATH" ]; then
    "$INSTALLER_SERVICE_PATH" restart >/dev/null 2>&1 || "$INSTALLER_SERVICE_PATH" start >/dev/null 2>&1 || true
    echo "Настройки Telegram не заполнены. Откройте веб-интерфейс на порту $(config_get 'browser_port' '8080') и заполните токен и имя пользователя."
  else
    echo "⚠️ Настройки Telegram не заполнены, а служба установщика не найдена."
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
localporthysteria2=$(config_get "localporthysteria2" "10840")
localporthysteria2_transparent=$(config_get "localporthysteria2_transparent" "10841")
dnsovertlsport=$(config_get "dnsovertlsport" "40500")
dnsoverhttpsport=$(config_get "dnsoverhttpsport" "40508")
keen_os_full=$(curl -s localhost:79/rci/show/version/title | tr -d \",)
keen_os_short=$(printf '%s' "$keen_os_full" | grep -Eo '[0-9]+' | head -n1)

dns_local_udp_listener_available() {
  dns_port="$1"
  [ -n "$dns_port" ] || return 1
  netstat -lnu 2>/dev/null | grep -Eq "127\\.0\\.0\\.1:${dns_port}[[:space:]]"
}

dns_public_ipv4_answer_available() {
  dns_answer_resolver="$1"
  awk -v resolver="$dns_answer_resolver" '
    {
      octet_count = split($0, octets, ".")
      if (octet_count != 4) next
      valid = 1
      for (octet_index = 1; octet_index <= 4; octet_index++) {
        if (octets[octet_index] !~ /^[0-9]+$/ || octets[octet_index] > 255) valid = 0
      }
      if (!valid || $0 == resolver) next
      first = octets[1] + 0
      second = octets[2] + 0
      if (first == 0 || first == 10 || first == 127 || first >= 224) next
      if (first == 100 && second >= 64 && second <= 127) next
      if (first == 169 && second == 254) next
      if (first == 172 && second >= 16 && second <= 31) next
      if (first == 192 && second == 168) next
      found = 1
    }
    END { exit found ? 0 : 1 }
  '
}

dns_udp_upstream_available() {
  dns_server="$1"
  [ -n "$dns_server" ] || return 1
  command -v dig >/dev/null 2>&1 || return 1
  printf '%s\n' "$dns_server" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || return 1

  for dns_probe_domain in example.com www.youtube.com; do
    dig +time=2 +tries=1 +short A "$dns_probe_domain" "@$dns_server" 2>/dev/null |
      dns_public_ipv4_answer_available "$dns_server" || return 1
  done
}

select_dnsmasq_fallback_upstreams() {
  dns_fallback_candidates="${BYPASS_DNS_FALLBACK_CANDIDATES:-9.9.9.9 77.88.8.8 94.140.14.14 8.8.8.8 1.1.1.1}"
  dns_fallback_selected=""
  dns_fallback_count=0

  for dns_fallback_candidate in $dns_fallback_candidates; do
    case " $dns_fallback_selected " in
      *" $dns_fallback_candidate "*) continue ;;
    esac
    dns_udp_upstream_available "$dns_fallback_candidate" || continue
    dns_fallback_selected="${dns_fallback_selected}${dns_fallback_selected:+ }${dns_fallback_candidate}"
    dns_fallback_count=$((dns_fallback_count + 1))
    [ "$dns_fallback_count" -ge 2 ] && break
  done

  # bind-dig может быть ещё не установлен во время первичной подготовки Entware.
  # В этом случае оставляем пару, которая не зависит от Google/Cloudflare UDP.
  if [ "$dns_fallback_count" -eq 0 ]; then
    dns_fallback_selected="9.9.9.9 77.88.8.8"
  fi
  printf '%s\n' "$dns_fallback_selected"
}

configure_dnsmasq_upstreams() {
  dnsmasq_path="$1"
  [ -f "$dnsmasq_path" ] || return 1

  if ! grep -q '^# BYPASS_DNS_UPSTREAMS_BEGIN$' "$dnsmasq_path" || \
     ! grep -q '^# BYPASS_DNS_UPSTREAMS_END$' "$dnsmasq_path"; then
    dnsmasq_legacy_tmp="${dnsmasq_path}.legacy.$$"
    awk \
      -v tls_line="server=127.0.0.1#${dnsovertlsport}" \
      -v https_line="server=127.0.0.1#${dnsoverhttpsport}" '
        $0 == "strict-order" { next }
        $0 == tls_line { next }
        $0 == https_line { next }
        $0 == "server=8.8.8.8" { next }
        $0 == "server=1.1.1.1" { next }
        $0 == "server=9.9.9.9" { next }
        $0 == "server=77.88.8.8" { next }
        $0 == "server=94.140.14.14" { next }
        { print }
        END {
          print ""
          print "# BYPASS_DNS_UPSTREAMS_BEGIN"
          print "strict-order"
          print "# BYPASS_DNS_UPSTREAMS_END"
        }
      ' "$dnsmasq_path" > "$dnsmasq_legacy_tmp" || {
        rm -f "$dnsmasq_legacy_tmp"
        return 1
      }
    mv "$dnsmasq_legacy_tmp" "$dnsmasq_path" || return 1
  fi

  dns_tls_ready=0
  dns_https_ready=0
  dns_local_udp_listener_available "$dnsovertlsport" && dns_tls_ready=1
  dns_local_udp_listener_available "$dnsoverhttpsport" && dns_https_ready=1
  dns_fallback_upstreams=""
  if [ "$dns_tls_ready" -ne 1 ] && [ "$dns_https_ready" -ne 1 ]; then
    dns_fallback_upstreams=$(select_dnsmasq_fallback_upstreams) || return 1
    [ -n "$dns_fallback_upstreams" ] || return 1
  fi
  dnsmasq_tmp="${dnsmasq_path}.upstreams.$$"

  awk \
    -v tls_port="$dnsovertlsport" \
    -v https_port="$dnsoverhttpsport" \
    -v tls_ready="$dns_tls_ready" \
    -v https_ready="$dns_https_ready" \
    -v fallback_upstreams="$dns_fallback_upstreams" '
      /^# BYPASS_DNS_UPSTREAMS_BEGIN$/ {
        print
        print "strict-order"
        if (tls_ready == 1) print "server=127.0.0.1#" tls_port
        if (https_ready == 1) print "server=127.0.0.1#" https_port
        if (tls_ready != 1 && https_ready != 1) {
          fallback_count = split(fallback_upstreams, fallback, /[[:space:]]+/)
          for (fallback_index = 1; fallback_index <= fallback_count; fallback_index++) {
            if (fallback[fallback_index] != "") print "server=" fallback[fallback_index]
          }
        }
        replacing = 1
        next
      }
      /^# BYPASS_DNS_UPSTREAMS_END$/ {
        replacing = 0
        print
        next
      }
      replacing != 1 { print }
    ' "$dnsmasq_path" > "$dnsmasq_tmp" || {
      rm -f "$dnsmasq_tmp"
      return 1
    }
  mv "$dnsmasq_tmp" "$dnsmasq_path" || return 1

  if [ "$dns_tls_ready" -eq 1 ] || [ "$dns_https_ready" -eq 1 ]; then
    echo "DNS: используются доступные защищённые локальные прокси Keenetic."
  else
    echo "DNS: локальные DNS-прокси Keenetic не найдены; включены совместимые внешние DNS-серверы."
  fi
}

repair_legacy_dnsmasq_backup() {
  dnsmasq_backup_path="$1"
  [ -f "$dnsmasq_backup_path" ] || return 0
  grep -q '^# BYPASS_DNS_UPSTREAMS_BEGIN$' "$dnsmasq_backup_path" && return 0
  dns_local_udp_listener_available "$dnsovertlsport" && return 0
  dns_local_udp_listener_available "$dnsoverhttpsport" && return 0
  if grep -Eq "^server=127\\.0\\.0\\.1#(${dnsovertlsport}|${dnsoverhttpsport})$" "$dnsmasq_backup_path"; then
    configure_dnsmasq_upstreams "$dnsmasq_backup_path"
  fi
}

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
    sanitize_xray26_compat
    if [ "$preferred_core" = "/opt/etc/init.d/S24xray" ]; then
      validate_xray_core_config || return 1
    fi
    "$preferred_core" restart > /dev/null 2>&1 || "$preferred_core" start > /dev/null 2>&1 || {
      echo "Не удалось запустить основной прокси-сервис: $preferred_core"
      return 1
    }
    sleep 1
    "$preferred_core" status > /tmp/bypass-core-service-status.log 2>&1 || {
      echo "Не удалось подтвердить состояние основного прокси-сервиса: $preferred_core"
      cat /tmp/bypass-core-service-status.log 2>/dev/null || true
      return 1
    }
  fi
  return 0
}

run_update_ipset_refresh() {
  label="$1"
  timeout_seconds="${UPDATE_IPSET_REFRESH_TIMEOUT_SECONDS:-75}"
  [ -x /opt/bin/unblock_update.sh ] || return 0
  /opt/bin/unblock_update.sh >/tmp/bypass-update-ipset-refresh.log 2>&1 &
  refresh_pid="$!"
  elapsed=0
  while kill -0 "$refresh_pid" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$timeout_seconds" ] 2>/dev/null; then
      echo "${label}: обновление ipset продолжается дольше ${timeout_seconds} с; основное обновление продолжится, а ipset завершится в фоне."
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  wait "$refresh_pid" >/dev/null 2>&1
  rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "${label}: обновление ipset завершилось с кодом ${rc}; продолжаем с сохранёнными рабочими наборами."
  fi
  return 0
}

run_youtube_edge_prefetch_once() {
  trigger="${1:-update}"
  python_bin="/opt/bin/python3"
  [ -x "$python_bin" ] || python_bin="$(command -v python3 2>/dev/null || true)"
  [ -n "$python_bin" ] || return 0
  runner="${BOT_RUNTIME_DIR}/youtube_edge_prefetch_runner.py"
  [ -f "$runner" ] || return 0
  PYTHONPATH="$BOT_RUNTIME_DIR" "$python_bin" "$runner" --trigger "$trigger" >/tmp/bypass-youtube-edge-prefetch.log 2>&1 || true
}

youtube_edge_prefetch_skipped_reason() {
  status_file="${BOT_RUNTIME_DIR}/youtube_edge_prefetch_status.json"
  [ -r "$status_file" ] || return 0
  sed -n 's/.*"skipped_reason"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$status_file" 2>/dev/null | head -n 1
}

run_youtube_edge_prefetch_retry_if_skipped() {
  trigger="${1:-Post-update-late}"
  delay_seconds="${2:-90}"
  (
    sleep "$delay_seconds"
    reason="$(youtube_edge_prefetch_skipped_reason)"
    case "$reason" in
      low_available_memory|lock_busy|unblock_running|pool_probe_running)
        run_youtube_edge_prefetch_once "$trigger"
        ;;
    esac
  ) >/tmp/bypass-youtube-edge-prefetch-late.log 2>&1 &
}

install_unblock_ipset_cron_job() {
  cron_tmp="/tmp/bypass-unblock-crontab.$$"
  {
    crontab -l 2>/dev/null \
      | grep -v '/opt/bin/unblock_ipset.sh' \
      | grep -v '/opt/etc/init.d/S99unblock refresh' \
      | grep -v '/opt/etc/init.d/S99unblock tick' \
      | grep -v '^# DO NOT EDIT THIS FILE' \
      | grep -v '^# (.* installed on ' \
      | grep -v '^# (Cron version ' \
      | sed '/^[[:space:]]*$/d' || true
    printf '%s\n' '*/15 * * * * /opt/etc/init.d/S99unblock tick >/dev/null 2>&1'
  } > "$cron_tmp"
  if crontab "$cron_tmp" >/dev/null 2>&1; then
    rm -f "$cron_tmp"
    chown root:root /opt/var/spool/cron /opt/var/spool/cron/crontabs /opt/var/spool/cron/crontabs/root 2>/dev/null || true
    chmod 700 /opt/var/spool/cron /opt/var/spool/cron/crontabs 2>/dev/null || true
    chmod 600 /opt/var/spool/cron/crontabs/root 2>/dev/null || true
    return 0
  fi
  rm -f "$cron_tmp"
  echo "Предупреждение: не удалось установить активный root crontab для unblock_ipset.sh."
  return 1
}

configure_core_proxy_service() {
  core_config_source="$(repo_file_url vmessconfig.json)"

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
  sanitize_xray26_compat
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
    echo "Ошибка: ${description} скачан как пустой файл"
    return 1
  fi
  if [ -n "$marker" ] && ! grep -q "$marker" "$target"; then
    rm -f "$target"
    echo "Ошибка: ${description} не прошёл проверку содержимого"
    return 1
  fi
  return 0
}

download_raw_file_via_socks() {
  url="$1"
  target="$2"

  for port in ${GITHUB_RAW_SOCKS_PORTS:-10811 10813 10812 10814 10815}; do
    if curl -fsSL --socks5-hostname "127.0.0.1:${port}" --connect-timeout 6 --max-time 35 --retry 1 --retry-delay 1 -o "$target" "$url" >/dev/null 2>&1; then
      if [ "${RAW_GITHUB_SOCKS_NOTICE_SHOWN:-0}" != "1" ]; then
        echo "Скачиваем файлы GitHub через локальный SOCKS-порт ${port}."
        RAW_GITHUB_SOCKS_NOTICE_SHOWN=1
        export RAW_GITHUB_SOCKS_NOTICE_SHOWN
      fi
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

  archive_refs="$REPO_REF"
  case "$REPO_REF" in
    refs/*) ;;
    *) archive_refs="$REPO_REF refs/heads/$REPO_REF refs/tags/$REPO_REF" ;;
  esac

  archive_ready=0
  for archive_ref in $archive_refs; do
    archive_url="https://codeload.github.com/${repo}/bypass_keenetic/tar.gz/${archive_ref}"
    rm -f "$archive_file"
    if curl -fsSL --connect-timeout 8 --max-time 90 -o "$archive_file" "$archive_url" >/dev/null 2>&1; then
      if tar -xzf "$archive_file" -C "$archive_work" >/dev/null 2>&1; then
        archive_ready=1
        break
      fi
    fi
  done
  [ "$archive_ready" = "1" ] || return 1
  UPDATE_ARCHIVE_ROOT=$(find "$archive_work" -mindepth 1 -maxdepth 1 -type d | head -n1)
  [ -n "$UPDATE_ARCHIVE_ROOT" ] && [ -d "$UPDATE_ARCHIVE_ROOT" ] || return 1
  export UPDATE_ARCHIVE_ROOT
  echo "Резервная загрузка через архив GitHub готова."
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
  if download_repo_file_from_archive "$url" "$target" || download_repo_file_via_api "$url" "$target"; then
    validate_update_file "$target" "$marker" "$description" || return 1
    return 0
  fi
  rm -f "$target"

  if [ "${RAW_GITHUB_BYPASS:-0}" != "1" ]; then
    if [ "${RAW_GITHUB_USE_SOCKS:-0}" = "1" ]; then
      if download_raw_file_via_socks "$url" "$target"; then
        validate_update_file "$target" "$marker" "$description" || return 1
        return 0
      fi
    elif curl -fsSL --connect-timeout 5 --max-time 8 -o "$target" "$url" >/dev/null 2>&1; then
      validate_update_file "$target" "$marker" "$description" || return 1
      return 0
    else
      rm -f "$target"
      RAW_GITHUB_USE_SOCKS=1
      export RAW_GITHUB_USE_SOCKS
      echo "Прямая загрузка ${description} через архив/API GitHub и raw не удалась; пробуем локальный SOCKS."
      if download_raw_file_via_socks "$url" "$target"; then
        validate_update_file "$target" "$marker" "$description" || return 1
        return 0
      fi
    fi
  fi

  echo "Ошибка: не удалось скачать ${description}"
  return 1
}

runtime_module_url() {
  printf '%s\n' "$(repo_file_url "$1")"
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
  if [ -f "$BOT_RUNTIME_DIR/$module" ]; then
    mv "$BOT_RUNTIME_DIR/$module" "$backup_dir/$module"
  else
    : > "$backup_dir/.runtime-absent-$module"
  fi
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

backup_runtime_state_file() {
  source_path="$1"
  backup_name="$2"
  [ -f "$source_path" ] || return 0
  cp -a "$source_path" "$backup_dir/$backup_name"
}

backup_runtime_state_files() {
  backup_runtime_state_file /opt/etc/bot_app_mode bot_app_mode
  backup_runtime_state_file /opt/etc/bot_proxy_mode bot_proxy_mode
  backup_runtime_state_file /opt/etc/bot_autostart bot_autostart
  backup_runtime_state_file "$BOT_CONFIG_PATH" bot_config.py
  backup_runtime_state_file /opt/etc/bot/key_pools.json key_pools.json
  backup_runtime_state_file /opt/etc/bot/key_pools.json.last-good key_pools.json.last-good
  backup_runtime_state_file /opt/etc/bot/key_probe_cache.json key_probe_cache.json
  backup_runtime_state_file /opt/etc/bot/key_probe_cache.json.last-good key_probe_cache.json.last-good
  backup_runtime_state_file /opt/etc/bot/pool_summary_last.json pool_summary_last.json
  backup_runtime_state_file /opt/etc/bot/subscriptions.json subscriptions.json
  backup_runtime_state_file /opt/etc/bot/subscription_nightly_pool_probe.json subscription_nightly_pool_probe.json
  backup_runtime_state_file /opt/etc/bot/custom_checks.json custom_checks.json
  backup_runtime_state_file /opt/etc/xray/vmess.key vmess.key
  backup_runtime_state_file /opt/etc/xray/vless.key vless.key
  backup_runtime_state_file /opt/etc/xray/vless2.key vless2.key
  backup_runtime_state_file /opt/etc/xray/hysteria2.key hysteria2.key
  backup_runtime_state_file /opt/etc/xray/config.json xray_config.json
  backup_runtime_state_file /opt/etc/v2ray/config.json v2ray_config.json
  backup_runtime_state_file /opt/etc/shadowsocks.json shadowsocks.json
  backup_runtime_state_file /opt/etc/trojan/config.json trojan_config.json
  backup_runtime_state_file /opt/etc/unblock/shadowsocks.txt unblock_shadowsocks.txt
  backup_runtime_state_file /opt/etc/unblock/trojan.txt unblock_trojan.txt
  backup_runtime_state_file /opt/etc/unblock/vmess.txt unblock_vmess.txt
  backup_runtime_state_file /opt/etc/unblock/vless.txt unblock_vless.txt
  backup_runtime_state_file /opt/etc/unblock/vless-2.txt unblock_vless2.txt
  backup_runtime_state_file /opt/etc/unblock/hysteria2.txt unblock_hysteria2.txt
  backup_runtime_state_file /opt/etc/unblock/web-ui/background.webp web_ui_background.webp
  backup_runtime_state_file /opt/etc/unblock/web-ui/background.json web_ui_background.json
}

restore_runtime_state_file_after_update() {
  backup_name="$1"
  target_path="$2"
  file_mode="${3:-0644}"
  source_path="$backup_dir/$backup_name"
  [ -f "$source_path" ] || return 0
  mkdir -p "$(dirname "$target_path")"
  cp -a "$source_path" "$target_path"
  chmod "$file_mode" "$target_path" 2>/dev/null || true
}

restore_runtime_state_files_after_update() {
  restore_runtime_state_file_after_update bot_app_mode /opt/etc/bot_app_mode 0644
  restore_runtime_state_file_after_update bot_proxy_mode /opt/etc/bot_proxy_mode 0644
  restore_runtime_state_file_after_update bot_autostart /opt/etc/bot_autostart 0644
  restore_runtime_state_file_after_update key_pools.json "$BOT_RUNTIME_DIR/key_pools.json" 0644
  restore_runtime_state_file_after_update key_pools.json.last-good "$BOT_RUNTIME_DIR/key_pools.json.last-good" 0644
  restore_runtime_state_file_after_update key_probe_cache.json "$BOT_RUNTIME_DIR/key_probe_cache.json" 0644
  restore_runtime_state_file_after_update key_probe_cache.json.last-good "$BOT_RUNTIME_DIR/key_probe_cache.json.last-good" 0644
  restore_runtime_state_file_after_update pool_summary_last.json "$BOT_RUNTIME_DIR/pool_summary_last.json" 0644
  restore_runtime_state_file_after_update subscriptions.json "$BOT_RUNTIME_DIR/subscriptions.json" 0644
  restore_runtime_state_file_after_update subscription_nightly_pool_probe.json "$BOT_RUNTIME_DIR/subscription_nightly_pool_probe.json" 0644
  restore_runtime_state_file_after_update custom_checks.json "$BOT_RUNTIME_DIR/custom_checks.json" 0644
  restore_runtime_state_file_after_update vmess.key /opt/etc/xray/vmess.key 0600
  restore_runtime_state_file_after_update vless.key /opt/etc/xray/vless.key 0600
  restore_runtime_state_file_after_update vless2.key /opt/etc/xray/vless2.key 0600
  restore_runtime_state_file_after_update hysteria2.key /opt/etc/xray/hysteria2.key 0600
  restore_runtime_state_file_after_update xray_config.json /opt/etc/xray/config.json 0644
  restore_runtime_state_file_after_update v2ray_config.json /opt/etc/v2ray/config.json 0644
  restore_runtime_state_file_after_update shadowsocks.json /opt/etc/shadowsocks.json 0600
  restore_runtime_state_file_after_update trojan_config.json /opt/etc/trojan/config.json 0600
  restore_runtime_state_file_after_update unblock_shadowsocks.txt /opt/etc/unblock/shadowsocks.txt 0644
  restore_runtime_state_file_after_update unblock_trojan.txt /opt/etc/unblock/trojan.txt 0644
  restore_runtime_state_file_after_update unblock_vmess.txt /opt/etc/unblock/vmess.txt 0644
  restore_runtime_state_file_after_update unblock_vless.txt /opt/etc/unblock/vless.txt 0644
  restore_runtime_state_file_after_update unblock_vless2.txt /opt/etc/unblock/vless-2.txt 0644
  restore_runtime_state_file_after_update unblock_hysteria2.txt /opt/etc/unblock/hysteria2.txt 0644
  restore_runtime_state_file_after_update web_ui_background.webp /opt/etc/unblock/web-ui/background.webp 0644
  restore_runtime_state_file_after_update web_ui_background.json /opt/etc/unblock/web-ui/background.json 0644
}

ensure_hysteria2_runtime_state_files() {
  mkdir -p /opt/etc/unblock
  if [ ! -e /opt/etc/unblock/hysteria2.txt ]; then
    : > /opt/etc/unblock/hysteria2.txt
  fi
  chmod 0644 /opt/etc/unblock/hysteria2.txt 2>/dev/null || true
}

backup_static_assets() {
  static_dir="${BOT_RUNTIME_DIR}/static"
  if [ -d "$static_dir" ]; then
    mkdir -p "$backup_dir/static"
    cp -a "$static_dir"/. "$backup_dir/static"/
  else
    : > "$backup_dir/.static-absent"
  fi
}

write_update_rollback_script() {
  rollback_path="$backup_dir/rollback.sh"
  rollback_hysteria2_tproxy_port="$(config_get "localporthysteria2_tproxy" "11840")"
  cat > "$rollback_path" <<EOF
#!/bin/sh
set -eu

BACKUP_DIR="$backup_dir"
RUNTIME_GUARD_PATH="$backup_dir/.rollback-tools/update_runtime_guard.sh"
BOT_MAIN_PATH="$BOT_MAIN_PATH"
BOT_RUNTIME_DIR="$BOT_RUNTIME_DIR"
BOT_SERVICE_PATH="$BOT_SERVICE_PATH"
INSTALLER_MAIN_PATH="$INSTALLER_MAIN_PATH"
INSTALLER_SERVICE_PATH="$INSTALLER_SERVICE_PATH"
BOT_CONFIG_PATH="$BOT_CONFIG_PATH"
UPDATE_MAINTENANCE_PATH="$UPDATE_MAINTENANCE_PATH"
UPDATE_MAINTENANCE_READY_PATH="$UPDATE_MAINTENANCE_READY_PATH"
HYSTERIA2_TRANSPARENT_PORT="$localporthysteria2_transparent"
HYSTERIA2_TPROXY_PORT="$rollback_hysteria2_tproxy_port"
ROLLBACK_MODULES="$BOT_RUNTIME_MODULES CHANGELOG.md"

[ -f "\$RUNTIME_GUARD_PATH" ] || {
  echo "Ошибка отката: отсутствует модуль контроля готовности."
  exit 1
}
. "\$RUNTIME_GUARD_PATH"

write_rollback_update_status() {
  running="\${1:-true}"
  progress="\${2:-5}"
  progress_label="\${3:-Откат}"
  message="\${4:-Выполняется откат обновления}"
  PYTHONPATH="\$BACKUP_DIR/.rollback-tools" python3 - "\$running" "\$progress" "\$progress_label" "\$message" <<'PY' >/dev/null 2>&1 || true
import sys
import update_status

running, progress, progress_label, message = sys.argv[1:5]
update_status.write_update_status(
    command='rollback_update',
    running=running.lower() in ('1', 'true', 'yes', 'y'),
    progress=int(progress or 0),
    progress_label=progress_label,
    message=message,
    sync_web=True,
)
PY
}

handle_rollback_exit() {
  rollback_exit_code="\$1"
  trap - EXIT
  trap '' TERM INT HUP
  if [ "\${rollback_status_active:-0}" = "1" ] && [ "\$rollback_exit_code" -ne 0 ]; then
    write_rollback_update_status false 100 Ошибка "Откат не завершён; рабочее состояние требует проверки"
  fi
  exit "\$rollback_exit_code"
}

rollback_status_active=1
write_rollback_update_status true 10 Подготовка "Проверяем и восстанавливаем резервную копию"
trap 'handle_rollback_exit "\$?"' EXIT
trap 'exit 143' TERM INT HUP

restore_file() {
  source_path="\$BACKUP_DIR/\$1"
  target_path="\$2"
  [ -e "\$source_path" ] || [ -L "\$source_path" ] || return 0
  mkdir -p "\$(dirname "\$target_path")"
  rm -f "\$target_path"
  cp -a "\$source_path" "\$target_path"
}

ensure_runtime_legacy_paths() {
  if [ "\$BOT_MAIN_PATH" = "/opt/etc/bot/main.py" ] && [ -f "\$BOT_MAIN_PATH" ]; then
    rm -f /opt/etc/bot/bot.py
    ln -s main.py /opt/etc/bot/bot.py 2>/dev/null || cp "\$BOT_MAIN_PATH" /opt/etc/bot/bot.py
  fi
  if [ "\$BOT_MAIN_PATH" != "/opt/etc/bot.py" ] && [ -f "\$BOT_MAIN_PATH" ]; then
    rm -f /opt/etc/bot.py
    ln -s "\$BOT_MAIN_PATH" /opt/etc/bot.py 2>/dev/null || cp "\$BOT_MAIN_PATH" /opt/etc/bot.py
  fi
}

delete_saved_firewall_rules_containing() {
  firewall_command="\$1"
  firewall_table="\$2"
  rule_token="\$3"
  save_command="\${firewall_command}-save"
  command -v "\$firewall_command" >/dev/null 2>&1 || return 0
  command -v "\$save_command" >/dev/null 2>&1 || return 0
  "\$save_command" -t "\$firewall_table" 2>/dev/null | while IFS= read -r saved_rule; do
    case "\$saved_rule" in
      -A\ *"\$rule_token"*)
        delete_rule="\${saved_rule#-A }"
        delete_chain="\${delete_rule%% *}"
        delete_args="\${delete_rule#* }"
        # Generated rules contain no quoted comments; word splitting preserves
        # the exact iptables arguments emitted by iptables-save.
        # shellcheck disable=SC2086
        "\$firewall_command" -t "\$firewall_table" -D "\$delete_chain" \$delete_args >/dev/null 2>&1 || true
        ;;
    esac
  done
}

cleanup_unsupported_hysteria2_runtime() {
  restored_redirect=/opt/etc/ndm/netfilter.d/100-redirect.sh
  if [ -f "\$restored_redirect" ] && grep -q 'HYSTERIA2' "\$restored_redirect" 2>/dev/null; then
    return 0
  fi

  for rule_token in \
    '--match-set unblockhy2 ' \
    '--match-set unblockhy2udp ' \
    '--match-set bypass_call_clients_hy2 ' \
    '--match-set bypass_call_signal_hy2 ' \
    '--match-set bypass_tg_call_hy2 '; do
    for firewall_table in filter nat mangle; do
      delete_saved_firewall_rules_containing iptables "\$firewall_table" "\$rule_token"
    done
  done
  delete_saved_firewall_rules_containing iptables mangle "--on-port \$HYSTERIA2_TPROXY_PORT "
  delete_saved_firewall_rules_containing ip6tables filter '--match-set unblockhy26 '

  for reject_target in REJECT DROP; do
    while iptables -C INPUT -w -p udp --dport "\$HYSTERIA2_TRANSPARENT_PORT" -j "\$reject_target" 2>/dev/null; do
      iptables -D INPUT -w -p udp --dport "\$HYSTERIA2_TRANSPARENT_PORT" -j "\$reject_target" >/dev/null 2>&1 || break
    done
  done
  for set_name in \
    unblockhy2 unblockhy2udp unblockhy26 \
    bypass_call_clients_hy2 bypass_call_signal_hy2 bypass_tg_call_hy2; do
    ipset destroy "\$set_name" >/dev/null 2>&1 || true
  done
  rm -f /opt/etc/xray/hysteria2.key /opt/etc/v2ray/hysteria2.key /opt/etc/unblock/hysteria2.txt
}

install_unblock_ipset_cron_job() {
  cron_tmp="/tmp/bypass-unblock-crontab.\$\$"
  {
    crontab -l 2>/dev/null \\
      | grep -v '/opt/bin/unblock_ipset.sh' \\
      | grep -v '/opt/etc/init.d/S99unblock refresh' \\
      | grep -v '/opt/etc/init.d/S99unblock tick' \\
      | grep -v '^# DO NOT EDIT THIS FILE' \\
      | grep -v '^# (.* installed on ' \\
      | grep -v '^# (Cron version ' \\
      | sed '/^[[:space:]]*$/d' || true
    printf '%s\n' '*/15 * * * * /opt/etc/init.d/S99unblock tick >/dev/null 2>&1'
  } > "\$cron_tmp"
  if crontab "\$cron_tmp" >/dev/null 2>&1; then
    rm -f "\$cron_tmp"
    chown root:root /opt/var/spool/cron /opt/var/spool/cron/crontabs /opt/var/spool/cron/crontabs/root 2>/dev/null || true
    chmod 700 /opt/var/spool/cron /opt/var/spool/cron/crontabs 2>/dev/null || true
    chmod 600 /opt/var/spool/cron/crontabs/root 2>/dev/null || true
    return 0
  fi
  rm -f "\$cron_tmp"
  echo "Предупреждение: не удалось установить активный root crontab для unblock_ipset.sh."
  return 1
}

wait_for_rollback_readiness() {
  bypass_wait_application_ready "\$BOT_SERVICE_PATH" 60
}

bypass_runtime_status_heartbeat() {
  heartbeat_elapsed="\$1"
  heartbeat_timeout="\$2"
  write_rollback_update_status true 90 Запуск \
    "Проверяем восстановленную версию: \${heartbeat_elapsed}/\${heartbeat_timeout} сек."
}

full_state_restored=0
if [ -f "\$BACKUP_DIR/full-state/manifest.json" ] && [ -f "\$BACKUP_DIR/.rollback-tools/managed_state_snapshot.py" ]; then
  PYTHONPATH="\$BACKUP_DIR/.rollback-tools" python3 \
    "\$BACKUP_DIR/.rollback-tools/managed_state_snapshot.py" restore "\$BACKUP_DIR/full-state"
  full_state_restored=1
fi
write_rollback_update_status true 35 Состояние "Настройки, ключи и DNS восстановлены из полного снимка"

restore_file unblock_ipset.sh /opt/bin/unblock_ipset.sh
restore_file unblock_dnsmasq.sh /opt/bin/unblock_dnsmasq.sh
restore_file unblock_update.sh /opt/bin/unblock_update.sh
restore_file dnsmasq.conf /opt/etc/dnsmasq.conf
restore_file crontab /opt/etc/crontab
restore_file S99unblock /opt/etc/init.d/S99unblock
restore_file 100-ipset.sh /opt/etc/ndm/fs.d/100-ipset.sh
restore_file 100-redirect.sh /opt/etc/ndm/netfilter.d/100-redirect.sh
restore_file bot.py "\$BOT_MAIN_PATH"
restore_file installer.py "\$INSTALLER_MAIN_PATH"
restore_file S98telegram_bot_installer "\$INSTALLER_SERVICE_PATH"
restore_file S99telegram_bot "\$BOT_SERVICE_PATH"
restore_file bot_app_mode /opt/etc/bot_app_mode
restore_file bot_proxy_mode /opt/etc/bot_proxy_mode
restore_file bot_autostart /opt/etc/bot_autostart
restore_file bot_config.py "\$BOT_CONFIG_PATH"
restore_file bot_config.py /opt/etc/bot_config.py
restore_file key_pools.json "\$BOT_RUNTIME_DIR/key_pools.json"
restore_file key_pools.json.last-good "\$BOT_RUNTIME_DIR/key_pools.json.last-good"
restore_file key_probe_cache.json "\$BOT_RUNTIME_DIR/key_probe_cache.json"
restore_file key_probe_cache.json.last-good "\$BOT_RUNTIME_DIR/key_probe_cache.json.last-good"
restore_file pool_summary_last.json "\$BOT_RUNTIME_DIR/pool_summary_last.json"
restore_file subscriptions.json "\$BOT_RUNTIME_DIR/subscriptions.json"
restore_file subscription_nightly_pool_probe.json "\$BOT_RUNTIME_DIR/subscription_nightly_pool_probe.json"
restore_file custom_checks.json "\$BOT_RUNTIME_DIR/custom_checks.json"
restore_file vmess.key /opt/etc/xray/vmess.key
restore_file vless.key /opt/etc/xray/vless.key
restore_file vless2.key /opt/etc/xray/vless2.key
restore_file hysteria2.key /opt/etc/xray/hysteria2.key
restore_file xray_config.json /opt/etc/xray/config.json
restore_file v2ray_config.json /opt/etc/v2ray/config.json
restore_file shadowsocks.json /opt/etc/shadowsocks.json
restore_file trojan_config.json /opt/etc/trojan/config.json
restore_file unblock_shadowsocks.txt /opt/etc/unblock/shadowsocks.txt
restore_file unblock_trojan.txt /opt/etc/unblock/trojan.txt
restore_file unblock_vmess.txt /opt/etc/unblock/vmess.txt
restore_file unblock_vless.txt /opt/etc/unblock/vless.txt
restore_file unblock_vless2.txt /opt/etc/unblock/vless-2.txt
restore_file unblock_hysteria2.txt /opt/etc/unblock/hysteria2.txt

for module in \$ROLLBACK_MODULES; do
  if [ -f "\$BACKUP_DIR/.runtime-absent-\$module" ]; then
    rm -f "\$BOT_RUNTIME_DIR/\$module"
  else
    restore_file "\$module" "\$BOT_RUNTIME_DIR/\$module"
  fi
done
if ! bypass_validate_python_sources "\$BOT_RUNTIME_DIR"; then
  echo "Ошибка отката: восстановленные Python-файлы не прошли проверку синтаксиса."
  exit 1
fi
if [ -d "\$BACKUP_DIR/static" ]; then
  mkdir -p "\$BOT_RUNTIME_DIR/static"
  rm -rf "\$BOT_RUNTIME_DIR/static"
  mkdir -p "\$BOT_RUNTIME_DIR/static"
  cp -a "\$BACKUP_DIR/static"/. "\$BOT_RUNTIME_DIR/static"/
fi
write_rollback_update_status true 60 Файлы "Файлы предыдущего релиза восстановлены"

chmod 755 /opt/bin/unblock_*.sh /opt/etc/ndm/fs.d/100-ipset.sh /opt/etc/ndm/netfilter.d/100-redirect.sh 2>/dev/null || true
[ -f "\$BOT_MAIN_PATH" ] && chmod 755 "\$BOT_MAIN_PATH" || true
[ -f "\$INSTALLER_MAIN_PATH" ] && chmod 755 "\$INSTALLER_MAIN_PATH" || true
[ -f "\$BOT_SERVICE_PATH" ] && chmod 755 "\$BOT_SERVICE_PATH" || true
[ -f "\$INSTALLER_SERVICE_PATH" ] && chmod 755 "\$INSTALLER_SERVICE_PATH" || true
restore_file script.sh /opt/root/script.sh
[ -f /opt/root/script.sh ] && chmod 755 /opt/root/script.sh || true
ensure_runtime_legacy_paths
cleanup_unsupported_hysteria2_runtime
write_rollback_update_status true 75 Сервисы "Запускаем DNS и прокси-сервисы предыдущего релиза"

if [ "\$full_state_restored" -ne 1 ]; then
  /opt/bin/unblock_update.sh >/dev/null 2>&1 || true
  install_unblock_ipset_cron_job || true
fi
[ -x /opt/etc/init.d/S56dnsmasq ] && /opt/etc/init.d/S56dnsmasq restart >/dev/null 2>&1 || true
[ -x /opt/etc/init.d/S10cron ] && /opt/etc/init.d/S10cron restart >/dev/null 2>&1 || /opt/etc/init.d/S10cron start >/dev/null 2>&1 || true
[ -x /opt/etc/init.d/S22shadowsocks ] && /opt/etc/init.d/S22shadowsocks restart >/dev/null 2>&1 || /opt/etc/init.d/S22shadowsocks start >/dev/null 2>&1 || true
[ -x /opt/etc/init.d/S24xray ] && /opt/etc/init.d/S24xray restart >/dev/null 2>&1 || /opt/etc/init.d/S24xray start >/dev/null 2>&1 || true
[ -x /opt/etc/init.d/S24v2ray ] && /opt/etc/init.d/S24v2ray restart >/dev/null 2>&1 || /opt/etc/init.d/S24v2ray start >/dev/null 2>&1 || true
[ -x /opt/etc/init.d/S22trojan ] && /opt/etc/init.d/S22trojan restart >/dev/null 2>&1 || /opt/etc/init.d/S22trojan start >/dev/null 2>&1 || true
[ -x /opt/etc/init.d/S99unblock ] && /opt/etc/init.d/S99unblock restart >/dev/null 2>&1 || true
if [ "\$full_state_restored" -eq 1 ] && [ -x /opt/etc/init.d/S99unblock ]; then
  # The full snapshot already restored the route sources. Recheck their
  # signature instead of forcing a costly DNS/ipset rebuild when unchanged.
  /opt/etc/init.d/S99unblock tick >/dev/null 2>&1 || true
fi
if ! bypass_apply_runtime_network_rules; then
  echo "Ошибка отката: не удалось восстановить прозрачные ipset/NAT/mangle правила."
  exit 1
fi
rm -f "\$UPDATE_MAINTENANCE_PATH" "\$UPDATE_MAINTENANCE_READY_PATH" 2>/dev/null || true
write_rollback_update_status true 90 Запуск "Перезапускаем программу предыдущего релиза"
bypass_clear_stale_main_lock "\$BOT_MAIN_PATH" || true
[ -x "\$BOT_SERVICE_PATH" ] && "\$BOT_SERVICE_PATH" restart >/dev/null 2>&1 || "\$BOT_SERVICE_PATH" start >/dev/null 2>&1 || true

if ! wait_for_rollback_readiness; then
  bypass_capture_bot_start_failure \
    "\$BOT_RUNTIME_DIR/error.log" \
    /opt/root/bypass-last-failed-rollback-bot.log \
    rollback-start >/dev/null 2>&1 || true
  echo "Ошибка отката: программа, веб-интерфейс, SOCKS или прозрачные правила не достигли готовности."
  exit 1
fi

write_rollback_update_status false 100 Готово "Откат завершён; предыдущий релиз и сохранённое состояние восстановлены"
rollback_status_active=0
trap - EXIT TERM INT HUP
echo "Откат восстановил файлы из \$BACKUP_DIR."
EOF
  chmod 700 "$rollback_path"
  ln -sf "$rollback_path" /opt/root/bypass-last-update-rollback.sh 2>/dev/null || true
}

activate_runtime_modules() {
  for module in "$@"; do
    activate_runtime_module "$module"
  done
}

BOT_RUNTIME_MODULES="app_version.py app_runtime_mode.py auto_failover_runtime.py custom_check_policy.py custom_checks_store.py entware_dns_runtime.py event_history.py failover_candidate_runner.py health_check_runner.py installer_common.py key_pool_store.py key_pool_web.py managed_state_snapshot.py pool_probe_controller.py pool_probe_process_runner.py pool_probe_resume.py pool_probe_runner.py probe_cache.py protocol_catalog.py proxy_apply_runtime.py proxy_config_builder.py proxy_config_recovery.py proxy_key_store.py proxy_protocols.py proxy_status.py repo_update.py route_intersections.py router_health_runtime.py router_metrics.py service_catalog.py service_routes.py subscription_pool_fetch.py subscription_runtime.py subscription_refresh_runtime.py system_command_runtime.py telegram_auth_state.py telegram_call_learning.py telegram_confirm.py telegram_healthcheck.py telegram_info_runtime.py telegram_install_ui.py telegram_jobs.py telegram_key_ui.py telegram_message_flow.py telegram_pool_ui.py transparent_route_policy.py unblock_lists.py update_maintenance_runtime.py update_runtime_guard.sh update_status.py web_background.py web_command_state.py web_commands_runtime.py web_form_blocks.py web_form_template.py web_get_actions.py web_http_common.py web_pool_form_blocks.py web_pool_snapshot_worker.py web_post_actions.py web_route_tools_runtime.py web_service_routes_worker.py web_status_builder.py web_status_runtime.py xray_compat_runtime.py youtube_edge_prefetch.py youtube_edge_prefetch_runner.py youtube_failover_policy.py youtube_failover_runtime.py youtube_failover_transaction.py youtube_healthcheck.py youtube_route_owner.py pool_probe_curl.py version.md README.md"

ensure_runtime_legacy_paths() {
  if [ "$BOT_MAIN_PATH" = "/opt/etc/bot/main.py" ] && [ -f "$BOT_MAIN_PATH" ]; then
    rm -f /opt/etc/bot/bot.py
    ln -s main.py /opt/etc/bot/bot.py 2>/dev/null || cp "$BOT_MAIN_PATH" /opt/etc/bot/bot.py
  fi
  if [ "$BOT_MAIN_PATH" != "/opt/etc/bot.py" ] && [ -f "$BOT_MAIN_PATH" ]; then
    rm -f /opt/etc/bot.py
    ln -s "$BOT_MAIN_PATH" /opt/etc/bot.py 2>/dev/null || cp "$BOT_MAIN_PATH" /opt/etc/bot.py
  fi
}

write_cli_update_status() {
  command="${1:-update}"
  running="${2:-true}"
  progress="${3:-0}"
  progress_label="${4:-}"
  message="${5:-}"
  target_version="${6:-}"
  python3 - "$command" "$running" "$progress" "$progress_label" "$message" "$target_version" <<'PY' >/dev/null 2>&1 || true
import json
import os
import sys
import time

status_path = os.environ.get('BYPASS_UPDATE_STATUS_PATH', '/opt/etc/bot/update_status.json')
web_state_path = os.environ.get('BYPASS_WEB_COMMAND_STATE_PATH', '/opt/etc/bot/web_command_state.json')
job_path = os.environ.get('BYPASS_COMMAND_JOB_PATH', '/opt/etc/bot/telegram_command_job.json')
command, running, progress, progress_label, message, target_version = sys.argv[1:7]

def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def write_json(path, value):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, separators=(',', ':'))
        os.replace(tmp_path, path)
        return True
    except Exception:
        return False

def float_value(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def int_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

try:
    progress = max(0, min(100, int(progress or 0)))
except Exception:
    progress = 0
now = time.time()
current = read_json(status_path)
web_state = read_json(web_state_path)
job_state = read_json(job_path)
job_started_at = float_value(job_state.get('started_at'))
web_started_at = float_value(web_state.get('started_at'))
matching_web_job = bool(
    job_state.get('source') == 'web'
    and job_state.get('command') == command
    and web_state.get('running')
    and web_state.get('command') == command
    and job_started_at > 0
    and web_started_at > 0
    and abs(job_started_at - web_started_at) <= 10
)
operation_started_at = job_started_at if matching_web_job else 0
current_started_at = float_value(current.get('started_at'))
same_status_run = bool(
    current.get('running')
    and current.get('command') == command
    and (
        not operation_started_at
        or not current_started_at
        or abs(current_started_at - operation_started_at) <= 10
    )
)
started_at = operation_started_at or (current_started_at if same_status_run else now)
if same_status_run and int_value(current.get('progress')) > progress:
    progress = int_value(current.get('progress'))
    progress_label = current.get('progress_label') or progress_label
    message = current.get('message') or message
elif matching_web_job and progress < 5:
    progress = 5
if same_status_run and not target_version:
    target_version = current.get('target_version') or ''
is_running = str(running).lower() in ('1', 'true', 'yes', 'y')
status = {
    'running': is_running,
    'command': command,
    'progress': progress,
    'progress_label': progress_label,
    'message': message,
    'target_version': target_version,
    'started_at': started_at,
    'updated_at': now,
    'finished_at': 0 if is_running else now,
}
write_json(status_path, status)
if matching_web_job:
    web_progress = max(0, min(100, int_value(web_state.get('progress'))))
    if progress >= web_progress:
        web_state['progress'] = progress
        web_state['progress_label'] = progress_label
    if target_version:
        web_state['target_version'] = target_version
    if not is_running:
        web_state['running'] = False
        web_state['progress'] = 100
        web_state['progress_label'] = progress_label
        web_state['result'] = message
        web_state['finished_at'] = now
        web_state['shown_after_finish'] = False
        job_state['running'] = False
        job_state['finished_at'] = now
        write_json(job_path, job_state)
    write_json(web_state_path, web_state)
PY
}

migrate_runtime_config_defaults() {
  [ -f "$BOT_CONFIG_PATH" ] || return 0
  if grep -Eq '^memory_timeline_enabled[[:space:]]*=[[:space:]]*True([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^memory_timeline_enabled[[:space:]]*=.*/memory_timeline_enabled = False/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^memory_timeline_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf '\nmemory_timeline_enabled = False\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^memory_timeline_path[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^memory_timeline_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'memory_timeline_interval_seconds = 60.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^memory_timeline_max_events[[:space:]]*=[[:space:]]*240([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^memory_timeline_max_events[[:space:]]*=.*/memory_timeline_max_events = 720/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^memory_timeline_max_events[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'memory_timeline_max_events = 720\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^memory_timeline_trim_min_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'memory_timeline_trim_min_interval_seconds = 300.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^memory_malloc_trim_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'memory_malloc_trim_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^memory_malloc_trim_min_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'memory_malloc_trim_min_rss_kb = 61440\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^memory_malloc_trim_cooldown_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'memory_malloc_trim_cooldown_seconds = 20.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^background_task_cpu_cache_ttl_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'background_task_cpu_cache_ttl_seconds = 20.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^background_task_max_cpu_percent[[:space:]]*=[[:space:]]*(65\.0|65)([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^background_task_max_cpu_percent[[:space:]]*=.*/background_task_max_cpu_percent = 45.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^background_task_max_cpu_percent[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'background_task_max_cpu_percent = 45.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^background_task_max_bot_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'background_task_max_bot_rss_kb = 66560\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^background_task_critical_max_bot_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'background_task_critical_max_bot_rss_kb = 71680\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^background_task_max_program_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'background_task_max_program_rss_kb = 102400\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^background_task_critical_max_program_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'background_task_critical_max_program_rss_kb = 102400\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^auto_failover_idle_log_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'auto_failover_idle_log_interval_seconds = 900\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^subscription_auto_refresh_interval_seconds[[:space:]]*=[[:space:]]*86400([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^subscription_auto_refresh_interval_seconds[[:space:]]*=.*/subscription_auto_refresh_interval_seconds = 21600/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^subscription_auto_refresh_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_auto_refresh_interval_seconds = 21600\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^subscription_auto_refresh_check_seconds[[:space:]]*=[[:space:]]*3600([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^subscription_auto_refresh_check_seconds[[:space:]]*=.*/subscription_auto_refresh_check_seconds = 300/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^subscription_auto_refresh_check_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_auto_refresh_check_seconds = 300\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^subscription_auto_refresh_max_bot_rss_kb[[:space:]]*=[[:space:]]*71680([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^subscription_auto_refresh_max_bot_rss_kb[[:space:]]*=.*/subscription_auto_refresh_max_bot_rss_kb = 81920/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^subscription_auto_refresh_max_bot_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_auto_refresh_max_bot_rss_kb = 81920\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_auto_refresh_max_program_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_auto_refresh_max_program_rss_kb = 112640\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_auto_refresh_min_available_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_auto_refresh_min_available_kb = 92160\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_auto_refresh_max_cpu_percent[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_auto_refresh_max_cpu_percent = 80.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_auto_refresh_max_load1[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_auto_refresh_max_load1 = 2.5\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_nightly_pool_probe_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_nightly_pool_probe_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_nightly_pool_probe_start_hour[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_nightly_pool_probe_start_hour = 3\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_nightly_pool_probe_end_hour[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_nightly_pool_probe_end_hour = 6\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^subscription_nightly_pool_probe_max_refresh_age_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'subscription_nightly_pool_probe_max_refresh_age_seconds = 28800\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_bot_num_threads[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_bot_num_threads = 1\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^status_refresh_min_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'status_refresh_min_interval_seconds = 180.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^status_refresh_pending_min_interval_seconds[[:space:]]*=[[:space:]]*(15\.0|15|30\.0|30)([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^status_refresh_pending_min_interval_seconds[[:space:]]*=.*/status_refresh_pending_min_interval_seconds = 60.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^status_refresh_pending_min_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'status_refresh_pending_min_interval_seconds = 60.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^router_health_cache_ttl[[:space:]]*=[[:space:]]*15\.0([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^router_health_cache_ttl[[:space:]]*=.*/router_health_cache_ttl = 30.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^router_health_cache_ttl[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'router_health_cache_ttl = 30.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^router_health_related_process_cache_ttl[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'router_health_related_process_cache_ttl = 45.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^router_health_cpu_smoothing_factor[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'router_health_cpu_smoothing_factor = 0.35\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^web_status_api_cache_ttl[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'web_status_api_cache_ttl = 30.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^web_http_max_request_threads[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'web_http_max_request_threads = 16\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^router_metrics_history_limit[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'router_metrics_history_limit = 120\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^router_metrics_warn_bot_rss_kb[[:space:]]*=[[:space:]]*(65536|71680)([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^router_metrics_warn_bot_rss_kb[[:space:]]*=.*/router_metrics_warn_bot_rss_kb = 66560/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^router_metrics_warn_bot_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'router_metrics_warn_bot_rss_kb = 66560\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^router_metrics_critical_bot_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'router_metrics_critical_bot_rss_kb = 87040\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^router_metrics_warn_load1[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'router_metrics_warn_load1 = 3.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^web_pools_api_cache_ttl[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'web_pools_api_cache_ttl = 45.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^service_route_intersections_cache_ttl[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'service_route_intersections_cache_ttl = 60.0\n' >> "$BOT_CONFIG_PATH"
  if [ "$BOT_CONFIG_PATH" != "/opt/etc/bot_config.py" ] && [ -f "/opt/etc/bot_config.py" ]; then
    if grep -Eq '^router_metrics_warn_bot_rss_kb[[:space:]]*=[[:space:]]*(65536|71680)([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^router_metrics_warn_bot_rss_kb[[:space:]]*=.*/router_metrics_warn_bot_rss_kb = 66560/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^router_metrics_warn_bot_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'router_metrics_warn_bot_rss_kb = 66560\n' >> /opt/etc/bot_config.py
    grep -Eq '^background_task_cpu_cache_ttl_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'background_task_cpu_cache_ttl_seconds = 20.0\n' >> /opt/etc/bot_config.py
    if grep -Eq '^background_task_max_cpu_percent[[:space:]]*=[[:space:]]*(65\.0|65)([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^background_task_max_cpu_percent[[:space:]]*=.*/background_task_max_cpu_percent = 45.0/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^background_task_max_cpu_percent[[:space:]]*=' /opt/etc/bot_config.py || printf 'background_task_max_cpu_percent = 45.0\n' >> /opt/etc/bot_config.py
    grep -Eq '^background_task_max_bot_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'background_task_max_bot_rss_kb = 66560\n' >> /opt/etc/bot_config.py
    grep -Eq '^background_task_critical_max_bot_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'background_task_critical_max_bot_rss_kb = 71680\n' >> /opt/etc/bot_config.py
    grep -Eq '^background_task_max_program_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'background_task_max_program_rss_kb = 102400\n' >> /opt/etc/bot_config.py
    grep -Eq '^background_task_critical_max_program_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'background_task_critical_max_program_rss_kb = 102400\n' >> /opt/etc/bot_config.py
    if grep -Eq '^status_refresh_pending_min_interval_seconds[[:space:]]*=[[:space:]]*(15\.0|15|30\.0|30)([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^status_refresh_pending_min_interval_seconds[[:space:]]*=.*/status_refresh_pending_min_interval_seconds = 60.0/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^status_refresh_pending_min_interval_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'status_refresh_pending_min_interval_seconds = 60.0\n' >> /opt/etc/bot_config.py
    grep -Eq '^auto_failover_idle_log_interval_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'auto_failover_idle_log_interval_seconds = 900\n' >> /opt/etc/bot_config.py
    if grep -Eq '^subscription_auto_refresh_interval_seconds[[:space:]]*=[[:space:]]*86400([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^subscription_auto_refresh_interval_seconds[[:space:]]*=.*/subscription_auto_refresh_interval_seconds = 21600/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^subscription_auto_refresh_interval_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_auto_refresh_interval_seconds = 21600\n' >> /opt/etc/bot_config.py
    if grep -Eq '^subscription_auto_refresh_check_seconds[[:space:]]*=[[:space:]]*3600([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^subscription_auto_refresh_check_seconds[[:space:]]*=.*/subscription_auto_refresh_check_seconds = 300/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^subscription_auto_refresh_check_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_auto_refresh_check_seconds = 300\n' >> /opt/etc/bot_config.py
    if grep -Eq '^subscription_auto_refresh_max_bot_rss_kb[[:space:]]*=[[:space:]]*71680([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^subscription_auto_refresh_max_bot_rss_kb[[:space:]]*=.*/subscription_auto_refresh_max_bot_rss_kb = 81920/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^subscription_auto_refresh_max_bot_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_auto_refresh_max_bot_rss_kb = 81920\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_auto_refresh_max_program_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_auto_refresh_max_program_rss_kb = 112640\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_auto_refresh_min_available_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_auto_refresh_min_available_kb = 92160\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_auto_refresh_max_cpu_percent[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_auto_refresh_max_cpu_percent = 80.0\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_auto_refresh_max_load1[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_auto_refresh_max_load1 = 2.5\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_nightly_pool_probe_enabled[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_nightly_pool_probe_enabled = True\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_nightly_pool_probe_start_hour[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_nightly_pool_probe_start_hour = 3\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_nightly_pool_probe_end_hour[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_nightly_pool_probe_end_hour = 6\n' >> /opt/etc/bot_config.py
    grep -Eq '^subscription_nightly_pool_probe_max_refresh_age_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'subscription_nightly_pool_probe_max_refresh_age_seconds = 28800\n' >> /opt/etc/bot_config.py
    grep -Eq '^telegram_bot_num_threads[[:space:]]*=' /opt/etc/bot_config.py || printf 'telegram_bot_num_threads = 1\n' >> /opt/etc/bot_config.py
    if grep -Eq '^router_health_cache_ttl[[:space:]]*=[[:space:]]*15\.0([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^router_health_cache_ttl[[:space:]]*=.*/router_health_cache_ttl = 30.0/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^router_health_cache_ttl[[:space:]]*=' /opt/etc/bot_config.py || printf 'router_health_cache_ttl = 30.0\n' >> /opt/etc/bot_config.py
    grep -Eq '^router_health_related_process_cache_ttl[[:space:]]*=' /opt/etc/bot_config.py || printf 'router_health_related_process_cache_ttl = 45.0\n' >> /opt/etc/bot_config.py
    grep -Eq '^router_health_cpu_smoothing_factor[[:space:]]*=' /opt/etc/bot_config.py || printf 'router_health_cpu_smoothing_factor = 0.35\n' >> /opt/etc/bot_config.py
    if grep -Eq '^pool_probe_max_process_rss_kb[[:space:]]*=[[:space:]]*(65536|71680|87040)([[:space:]#]|$)' /opt/etc/bot_config.py; then
      sed -i 's/^pool_probe_max_process_rss_kb[[:space:]]*=.*/pool_probe_max_process_rss_kb = 66560/' /opt/etc/bot_config.py || true
    fi
    grep -Eq '^pool_probe_max_process_rss_kb[[:space:]]*=' /opt/etc/bot_config.py || printf 'pool_probe_max_process_rss_kb = 66560\n' >> /opt/etc/bot_config.py
    grep -Eq '^pool_probe_process_worker_enabled[[:space:]]*=' /opt/etc/bot_config.py || printf 'pool_probe_process_worker_enabled = True\n' >> /opt/etc/bot_config.py
    grep -Eq '^pool_probe_inprocess_fallback_enabled[[:space:]]*=' /opt/etc/bot_config.py || printf 'pool_probe_inprocess_fallback_enabled = False\n' >> /opt/etc/bot_config.py
    grep -Eq '^pool_probe_process_worker_poll_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'pool_probe_process_worker_poll_seconds = 0.75\n' >> /opt/etc/bot_config.py
    grep -Eq '^pool_failover_process_worker_enabled[[:space:]]*=' /opt/etc/bot_config.py || printf 'pool_failover_process_worker_enabled = True\n' >> /opt/etc/bot_config.py
    grep -Eq '^pool_failover_process_worker_timeout_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'pool_failover_process_worker_timeout_seconds = 180.0\n' >> /opt/etc/bot_config.py
    grep -Eq '^memory_timeline_trim_min_interval_seconds[[:space:]]*=' /opt/etc/bot_config.py || printf 'memory_timeline_trim_min_interval_seconds = 300.0\n' >> /opt/etc/bot_config.py
  fi
  if grep -Eq '^pool_probe_delay_seconds[[:space:]]*=[[:space:]]*1\.5([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^pool_probe_delay_seconds[[:space:]]*=.*/pool_probe_delay_seconds = 3.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^pool_probe_delay_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_delay_seconds = 3.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^pool_probe_max_cpu_percent[[:space:]]*=[[:space:]]*70\.0?([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^pool_probe_max_cpu_percent[[:space:]]*=.*/pool_probe_max_cpu_percent = 45.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^pool_probe_max_cpu_percent[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_max_cpu_percent = 45.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_probe_process_worker_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_process_worker_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_probe_inprocess_fallback_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_inprocess_fallback_enabled = False\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_probe_process_worker_poll_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_process_worker_poll_seconds = 0.75\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_failover_process_worker_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_failover_process_worker_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_failover_process_worker_timeout_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_failover_process_worker_timeout_seconds = 180.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^pool_probe_high_cpu_delay_seconds[[:space:]]*=[[:space:]]*5\.0?([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^pool_probe_high_cpu_delay_seconds[[:space:]]*=.*/pool_probe_high_cpu_delay_seconds = 8.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^pool_probe_high_cpu_delay_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_high_cpu_delay_seconds = 8.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^pool_probe_high_cpu_max_wait_seconds[[:space:]]*=[[:space:]]*45\.0?([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^pool_probe_high_cpu_max_wait_seconds[[:space:]]*=.*/pool_probe_high_cpu_max_wait_seconds = 120.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^pool_probe_high_cpu_max_wait_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_high_cpu_max_wait_seconds = 120.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_probe_max_load1[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_max_load1 = 2.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_probe_high_load_delay_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_high_load_delay_seconds = 10.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^pool_probe_high_load_max_wait_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_high_load_max_wait_seconds = 120.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^pool_probe_max_process_rss_kb[[:space:]]*=[[:space:]]*(65536|71680|87040)([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^pool_probe_max_process_rss_kb[[:space:]]*=.*/pool_probe_max_process_rss_kb = 66560/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^pool_probe_max_process_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_max_process_rss_kb = 66560\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^pool_probe_quality_download_bytes[[:space:]]*=[[:space:]]*1048576([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^pool_probe_quality_download_bytes[[:space:]]*=.*/pool_probe_quality_download_bytes = 524288/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^pool_probe_quality_download_bytes[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_quality_download_bytes = 524288\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^pool_probe_quality_max_samples_per_run[[:space:]]*=[[:space:]]*12([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^pool_probe_quality_max_samples_per_run[[:space:]]*=.*/pool_probe_quality_max_samples_per_run = 6/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^pool_probe_quality_max_samples_per_run[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'pool_probe_quality_max_samples_per_run = 6\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_udp_policy[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "telegram_udp_policy = 'auto'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_mode[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_prefetch_mode = 'external'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_start_delay_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_start_delay_seconds = 120\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_interval_seconds[[:space:]]*=[[:space:]]*0([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_interval_seconds[[:space:]]*=.*/youtube_edge_prefetch_interval_seconds = 7200/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_interval_seconds = 7200\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cache_path[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_prefetch_cache_path = '/opt/etc/bot/youtube_edge_cache.json'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_status_path[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_prefetch_status_path = '/opt/etc/bot/youtube_edge_prefetch_status.json'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_lock_dir[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_prefetch_lock_dir = '/tmp/bypass-youtube-edge-prefetch.lock'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cache_ttl_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_cache_ttl_seconds = 259200\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_max_cache_entries[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_max_cache_entries = 128\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_max_hosts_per_run[[:space:]]*=[[:space:]]*(4|12)([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_max_hosts_per_run[[:space:]]*=.*/youtube_edge_prefetch_max_hosts_per_run = 6/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_max_hosts_per_run[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_max_hosts_per_run = 6\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_max_resolved_addresses[[:space:]]*=[[:space:]]*(12|32)([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_max_resolved_addresses[[:space:]]*=.*/youtube_edge_prefetch_max_resolved_addresses = 16/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_max_resolved_addresses[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_max_resolved_addresses = 16\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_max_candidates[[:space:]]*=[[:space:]]*64([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_max_candidates[[:space:]]*=.*/youtube_edge_prefetch_max_candidates = 32/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_max_candidates[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_max_candidates = 32\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_max_addresses_per_run[[:space:]]*=[[:space:]]*16([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_max_addresses_per_run[[:space:]]*=.*/youtube_edge_prefetch_max_addresses_per_run = 8/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_max_addresses_per_run[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_max_addresses_per_run = 8\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_min_available_kb[[:space:]]*=[[:space:]]*160000([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_min_available_kb[[:space:]]*=.*/youtube_edge_prefetch_min_available_kb = 125000/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_min_available_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_min_available_kb = 125000\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_max_rss_kb[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_max_rss_kb = 66560\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_exclusive_ipsets[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_exclusive_ipsets = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_protect_shared_google[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_protect_shared_google = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cache_restore_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_cache_restore_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cache_restore_max_addresses[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_cache_restore_max_addresses = 16\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cache_restore_require_quality_ok[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_cache_restore_require_quality_ok = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cache_restore_min_candidates[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_cache_restore_min_candidates = 8\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cache_restore_max_age_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_cache_restore_max_age_seconds = 21600\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_fast_warm_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_fast_warm_enabled = True\n' >> "$BOT_CONFIG_PATH"
  if ! grep -Eq '^youtube_edge_prefetch_fast_hosts[[:space:]]*=' "$BOT_CONFIG_PATH"; then
    cat >> "$BOT_CONFIG_PATH" <<'PYCFG'
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
PYCFG
  fi
  if grep -Eq '^youtube_edge_prefetch_fast_max_hosts_per_run[[:space:]]*=[[:space:]]*8([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_fast_max_hosts_per_run[[:space:]]*=.*/youtube_edge_prefetch_fast_max_hosts_per_run = 4/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_fast_max_hosts_per_run[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_fast_max_hosts_per_run = 4\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_fast_max_candidates[[:space:]]*=[[:space:]]*32([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_fast_max_candidates[[:space:]]*=.*/youtube_edge_prefetch_fast_max_candidates = 16/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_fast_max_candidates[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_fast_max_candidates = 16\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_quality_probe_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_quality_probe_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_quality_target_ms[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_quality_target_ms = 1000\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_quality_timeout_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_quality_timeout_seconds = 5\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_quality_bad_cooldown_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_quality_bad_cooldown_seconds = 3600\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_quality_max_candidates[[:space:]]*=[[:space:]]*24([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_quality_max_candidates[[:space:]]*=.*/youtube_edge_prefetch_quality_max_candidates = 12/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_quality_max_candidates[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_quality_max_candidates = 12\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_dns_quality_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_dns_quality_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_dns_quality_hosts[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_dns_quality_hosts = ('i.ytimg.com',)\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_dns_quality_hosts_path[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_dns_quality_hosts_path = '/opt/etc/bot/youtube_edge_quality.hosts'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_dnsmasq_config_path[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_dnsmasq_config_path = '/opt/etc/dnsmasq.conf'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_dns_quality_min_addresses[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_dns_quality_min_addresses = 2\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_dns_quality_max_addresses[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_dns_quality_max_addresses = 3\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_dns_quality_max_age_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_dns_quality_max_age_seconds = 2700\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_cdn_quality_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_cdn_quality_interval_seconds = 1800\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_cdn_quality_max_candidates[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_cdn_quality_max_candidates = 6\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_cdn_quality_timeout_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_cdn_quality_timeout_seconds = 3\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_prefetch_scheduler_max_cpu_percent[[:space:]]*=[[:space:]]*60([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_prefetch_scheduler_max_cpu_percent[[:space:]]*=.*/youtube_edge_prefetch_scheduler_max_cpu_percent = 45/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_prefetch_scheduler_max_cpu_percent[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_scheduler_max_cpu_percent = 45\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_scheduler_max_load1[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_scheduler_max_load1 = 2.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_cpu_sample_ms[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_cpu_sample_ms = 250\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_skip_when_unblock_running[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_skip_when_unblock_running = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_skip_when_pool_probe_running[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_skip_when_pool_probe_running = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_unblock_lock_dir[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_prefetch_unblock_lock_dir = '/tmp/bypass-unblock-ipset.lock'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_unblock_lock_stale_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_prefetch_unblock_lock_stale_seconds = 600\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^active_status_recent_success_ttl[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'active_status_recent_success_ttl = 900\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^auto_failover_recent_success_ttl[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'auto_failover_recent_success_ttl = 900\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_route_failover_grace_seconds[[:space:]]*=[[:space:]]*180([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_route_failover_grace_seconds[[:space:]]*=.*/youtube_route_failover_grace_seconds = 5/' "$BOT_CONFIG_PATH" || true
  fi
  if grep -Eq '^youtube_route_failover_poll_seconds[[:space:]]*=[[:space:]]*120([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_route_failover_poll_seconds[[:space:]]*=.*/youtube_route_failover_poll_seconds = 60/' "$BOT_CONFIG_PATH" || true
  fi
  if grep -Eq '^youtube_route_failover_confirm_retries[[:space:]]*=[[:space:]]*3([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_route_failover_confirm_retries[[:space:]]*=.*/youtube_route_failover_confirm_retries = 2/' "$BOT_CONFIG_PATH" || true
  fi
  if grep -Eq '^youtube_route_failover_confirm_delay_seconds[[:space:]]*=[[:space:]]*8(\.0)?([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_route_failover_confirm_delay_seconds[[:space:]]*=.*/youtube_route_failover_confirm_delay_seconds = 3.0/' "$BOT_CONFIG_PATH" || true
  fi
  if grep -Eq '^youtube_route_failover_check_connect_timeout[[:space:]]*=[[:space:]]*6(\.0)?([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_route_failover_check_connect_timeout[[:space:]]*=.*/youtube_route_failover_check_connect_timeout = 3/' "$BOT_CONFIG_PATH" || true
  fi
  if grep -Eq '^youtube_route_failover_check_read_timeout[[:space:]]*=[[:space:]]*10(\.0)?([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_route_failover_check_read_timeout[[:space:]]*=.*/youtube_route_failover_check_read_timeout = 5/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_route_failover_grace_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_grace_seconds = 5\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_failover_poll_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_poll_seconds = 60\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_failover_confirm_retries[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_confirm_retries = 2\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_failover_check_connect_timeout[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_check_connect_timeout = 3\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_failover_check_read_timeout[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_check_read_timeout = 5\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_failover_confirm_delay_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_confirm_delay_seconds = 3.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_failover_max_candidates[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_max_candidates = 2\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_failover_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_failover_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_min_duration_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_min_duration_seconds = 300\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_consecutive_checks[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_consecutive_checks = 3\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_score_threshold[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_score_threshold = 55\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_candidate_min_score[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_candidate_min_score = 70\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_min_improvement[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_min_improvement = 15\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_error_rate[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_error_rate = 0.2\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_latency_ms[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_latency_ms = 2500\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_route_quality_switch_cooldown_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_quality_switch_cooldown_seconds = 900\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^(youtube_route_failover_recent_success_ttl|youtube_vless2_failover_recent_success_ttl)[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_route_failover_recent_success_ttl = 900\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^event_history_duplicate_window_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'event_history_duplicate_window_seconds = 300\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_watch_warm_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_watch_warm_urls[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_watch_warm_urls = ('https://www.youtube.com/watch?v=aqz-KE-bpKQ', 'https://www.youtube.com/watch?v=jfKfPfyJRdk')\n" >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_watch_warm_max_pages[[:space:]]*=[[:space:]]*2([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_watch_warm_max_pages[[:space:]]*=.*/youtube_edge_watch_warm_max_pages = 1/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_watch_warm_max_pages[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_max_pages = 1\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_watch_warm_max_hosts[[:space:]]*=[[:space:]]*8([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_watch_warm_max_hosts[[:space:]]*=.*/youtube_edge_watch_warm_max_hosts = 6/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_watch_warm_max_hosts[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_max_hosts = 6\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_watch_warm_max_bytes[[:space:]]*=[[:space:]]*(900000|1800000)([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_watch_warm_max_bytes[[:space:]]*=.*/youtube_edge_watch_warm_max_bytes = 450000/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_watch_warm_max_bytes[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_max_bytes = 450000\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_watch_warm_connect_timeout[[:space:]]*=[[:space:]]*6([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_watch_warm_connect_timeout[[:space:]]*=.*/youtube_edge_watch_warm_connect_timeout = 4/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_watch_warm_connect_timeout[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_connect_timeout = 4\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^youtube_edge_watch_warm_max_time[[:space:]]*=[[:space:]]*20([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^youtube_edge_watch_warm_max_time[[:space:]]*=.*/youtube_edge_watch_warm_max_time = 10/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^youtube_edge_watch_warm_max_time[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_max_time = 10\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_watch_warm_retry_count[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_retry_count = 2\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_watch_warm_retry_delay_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'youtube_edge_watch_warm_retry_delay_seconds = 2.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^youtube_edge_prefetch_dns_servers[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "youtube_edge_prefetch_dns_servers = ('local', '1.1.1.1', '8.8.8.8')\n" >> "$BOT_CONFIG_PATH"
  if ! grep -Eq '^youtube_edge_prefetch_hosts[[:space:]]*=' "$BOT_CONFIG_PATH"; then
    cat >> "$BOT_CONFIG_PATH" <<'PYCFG'
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
PYCFG
  fi
  if grep -Eq '^telegram_call_learning_enabled[[:space:]]*=[[:space:]]*False([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^telegram_call_learning_enabled[[:space:]]*=.*/telegram_call_learning_enabled = True/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^telegram_call_learning_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_enabled = True\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq "^telegram_call_learning_state_path[[:space:]]*=[[:space:]]*['\"]?/opt/tmp/bypass_telegram_call_learning\\.json['\"]?([[:space:]#]|$)" "$BOT_CONFIG_PATH"; then
    sed -i "s#^telegram_call_learning_state_path[[:space:]]*=.*#telegram_call_learning_state_path = '/tmp/bypass_telegram_call_learning.json'#" "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^telegram_call_learning_state_path[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "telegram_call_learning_state_path = '/tmp/bypass_telegram_call_learning.json'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_default_duration_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_default_duration_seconds = 90\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_max_duration_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_max_duration_seconds = 180\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_poll_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_poll_interval_seconds = 1.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^telegram_call_learning_auto_enabled[[:space:]]*=[[:space:]]*False([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^telegram_call_learning_auto_enabled[[:space:]]*=.*/telegram_call_learning_auto_enabled = True/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^telegram_call_learning_auto_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_auto_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_scan_interval_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_scan_interval_seconds = 5.0\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^telegram_call_learning_scan_interval_seconds[[:space:]]*=[[:space:]]*1\.0([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^telegram_call_learning_scan_interval_seconds[[:space:]]*=.*/telegram_call_learning_scan_interval_seconds = 5.0/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^telegram_call_learning_idle_backoff_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_idle_backoff_seconds = 60.0\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_fast_scan_limit[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_fast_scan_limit = 3\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_min_score[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_min_score = 5\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_min_packets[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_min_packets = 2\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_min_bytes[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_min_bytes = 240\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_max_candidates[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_max_candidates = 20\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_max_seen_addresses[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_max_seen_addresses = 512\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^telegram_call_learning_apply_by_default[[:space:]]*=[[:space:]]*False([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^telegram_call_learning_apply_by_default[[:space:]]*=.*/telegram_call_learning_apply_by_default = True/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^telegram_call_learning_apply_by_default[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_apply_by_default = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^telegram_call_learning_client_timeout_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_client_timeout_seconds = 900\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^telegram_call_learning_client_timeout_seconds[[:space:]]*=[[:space:]]*14400([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^telegram_call_learning_client_timeout_seconds[[:space:]]*=.*/telegram_call_learning_client_timeout_seconds = 900/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^telegram_call_learning_address_timeout_seconds[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_learning_address_timeout_seconds = 14400\n' >> "$BOT_CONFIG_PATH"
  if grep -Eq '^telegram_call_tproxy_enabled[[:space:]]*=[[:space:]]*False([[:space:]#]|$)' "$BOT_CONFIG_PATH"; then
    sed -i 's/^telegram_call_tproxy_enabled[[:space:]]*=.*/telegram_call_tproxy_enabled = True/' "$BOT_CONFIG_PATH" || true
  fi
  grep -Eq '^telegram_call_tproxy_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'telegram_call_tproxy_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^localportsh_tproxy[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localportsh_tproxy = '11802'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^localportvmess_tproxy[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localportvmess_tproxy = '11815'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^localportvless_tproxy[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localportvless_tproxy = '11812'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^localportvless2_tproxy[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localportvless2_tproxy = '11814'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^localporttrojan_tproxy[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localporttrojan_tproxy = '11829'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^localporthysteria2[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localporthysteria2 = '10840'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^localporthysteria2_transparent[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localporthysteria2_transparent = '10841'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^localporthysteria2_tproxy[[:space:]]*=' "$BOT_CONFIG_PATH" || printf "localporthysteria2_tproxy = '11840'\n" >> "$BOT_CONFIG_PATH"
  grep -Eq '^udp_quic_block_hysteria2_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'udp_quic_block_hysteria2_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^xray_bittorrent_direct_enabled[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'xray_bittorrent_direct_enabled = True\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^xray_strict_transparent_protocols[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'xray_strict_transparent_protocols = ()\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^xray_route_only_transparent_protocols[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'xray_route_only_transparent_protocols = ()\n' >> "$BOT_CONFIG_PATH"
  grep -Eq '^xray_route_only_tproxy_protocols[[:space:]]*=' "$BOT_CONFIG_PATH" || printf 'xray_route_only_tproxy_protocols = ()\n' >> "$BOT_CONFIG_PATH"
}

repair_service_route_catalog_drift() {
  python_bin="/opt/bin/python3"
  [ -x "$python_bin" ] || python_bin="$(command -v python3 2>/dev/null || true)"
  [ -n "$python_bin" ] || return 0
  PYTHONPATH="$BOT_RUNTIME_DIR" "$python_bin" - <<'PY' || true
from service_routes import repair_service_route_catalog_drift as repair_drift

result = repair_drift(update_script='')
services = int(result.get('services') or 0)
if services:
    print(
        'Service route catalog repaired: '
        f'{services} service(s), '
        f'{result.get("entries_added", 0)} added, '
        f'{result.get("entries_removed", 0)} removed.'
    )
PY
}

generate_udp_quic_policy_file() {
  python_bin="/opt/bin/python3"
  [ -x "$python_bin" ] || python_bin="$(command -v python3 2>/dev/null || true)"
  [ -n "$python_bin" ] || return 0
  mkdir -p "$BOT_RUNTIME_DIR"
  policy_tmp="$BOT_RUNTIME_DIR/udp_quic_routes.txt.$$"
  if PYTHONPATH="$BOT_RUNTIME_DIR" "$python_bin" - <<'PY' > "$policy_tmp" 2>/dev/null; then
from service_catalog import UDP_QUIC_ROUTE_ENTRIES
for entry in UDP_QUIC_ROUTE_ENTRIES:
    print(entry)
PY
    mv "$policy_tmp" "$BOT_RUNTIME_DIR/udp_quic_routes.txt"
    chmod 644 "$BOT_RUNTIME_DIR/udp_quic_routes.txt" 2>/dev/null || true
  else
    rm -f "$policy_tmp"
  fi
  exclude_tmp="$BOT_RUNTIME_DIR/udp_quic_exclude.txt.$$"
  if PYTHONPATH="$BOT_RUNTIME_DIR" "$python_bin" - <<'PY' > "$exclude_tmp" 2>/dev/null; then
from service_catalog import UDP_QUIC_EXCLUDE_ENTRIES
for entry in UDP_QUIC_EXCLUDE_ENTRIES:
    print(entry)
PY
    mv "$exclude_tmp" "$BOT_RUNTIME_DIR/udp_quic_exclude.txt"
    chmod 644 "$BOT_RUNTIME_DIR/udp_quic_exclude.txt" 2>/dev/null || true
  else
    rm -f "$exclude_tmp"
  fi
  call_signal_tmp="$BOT_RUNTIME_DIR/call_signal_routes.txt.$$"
  if PYTHONPATH="$BOT_RUNTIME_DIR" "$python_bin" - <<'PY' > "$call_signal_tmp" 2>/dev/null; then
from service_catalog import REALTIME_CALL_SIGNAL_ROUTE_ENTRIES
for entry in REALTIME_CALL_SIGNAL_ROUTE_ENTRIES:
    print(entry)
PY
    mv "$call_signal_tmp" "$BOT_RUNTIME_DIR/call_signal_routes.txt"
    chmod 644 "$BOT_RUNTIME_DIR/call_signal_routes.txt" 2>/dev/null || true
  else
    rm -f "$call_signal_tmp"
  fi
  block_tmp="$BOT_RUNTIME_DIR/udp_policy.conf.$$"
  if PYTHONPATH="$BOT_RUNTIME_DIR" "$python_bin" - <<'PY' > "$block_tmp" 2>/dev/null; then
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
    ('HYSTERIA2', 'hysteria2.txt', 'udp_quic_block_hysteria2_enabled'),
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
print(f'BYPASS_TELEGRAM_CALL_LEARNING_ENABLED={1 if config_bool("telegram_call_learning_enabled", True) else 0}')
print(f'BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT={config_int("telegram_call_learning_client_timeout_seconds", 900, 30, 86400)}')
print(f'BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT={config_int("telegram_call_learning_address_timeout_seconds", 14400, 120, 86400)}')
print(f'BYPASS_TELEGRAM_CALL_TPROXY_ENABLED={1 if config_bool("telegram_call_tproxy_enabled", True) else 0}')
print('BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED=0')
print(f'TELEGRAM_CALL_TPROXY_PORT_SHADOWSOCKS={config_int("localportsh_tproxy", 11802, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_VMESS={config_int("localportvmess_tproxy", 11815, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_VLESS={config_int("localportvless_tproxy", 11812, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_VLESS2={config_int("localportvless2_tproxy", 11814, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_TROJAN={config_int("localporttrojan_tproxy", 11829, 1, 65535)}')
print(f'TELEGRAM_CALL_TPROXY_PORT_HYSTERIA2={config_int("localporthysteria2_tproxy", 11840, 1, 65535)}')
for env_name, _filename, _attr in PROTOCOLS:
    print(f'BYPASS_TELEGRAM_CALL_ROUTE_{env_name}={1 if realtime_call_route_flags.get(env_name) else 0}')
for env_name, _filename, _attr in PROTOCOLS:
    print(f'BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_{env_name}={1 if telegram_route_flags.get(env_name) else 0}')
PY
    mv "$block_tmp" "$BOT_RUNTIME_DIR/udp_policy.conf"
    chmod 644 "$BOT_RUNTIME_DIR/udp_policy.conf" 2>/dev/null || true
  else
    rm -f "$block_tmp"
  fi
}

if [ "$1" = "-remove" ]; then
    echo "Начинаем удаление"
    opkg remove tor tor-geoip obfs4 bind-dig cron dnsmasq-full ipset iptables shadowsocks-libev-ss-redir shadowsocks-libev-config xray-core xray v2ray trojan
    cleanup_removed_connection_artifacts
    echo "Пакеты удалены, удаляем папки, файлы и настройки"
    ipset flush testset
    ipset flush unblocksh
    ipset flush unblockshudp
    ipset flush unblockvmess
    ipset flush unblockvmessudp
    ipset flush unblockvless
    ipset flush unblockvlessudp
    ipset flush unblockvless2
    ipset flush unblockvless2udp
    ipset flush unblocktroj
    ipset flush unblocktrojudp
    ipset flush unblockhy2
    ipset flush unblockhy2udp
    remove_path /opt/root/get-pip.py
    remove_path /opt/etc/crontab
    remove_path /opt/etc/init.d/S22shadowsocks
    remove_path /opt/etc/init.d/S22trojan
    remove_path /opt/etc/init.d/S24xray
    remove_path /opt/etc/init.d/S24v2ray
    remove_path /opt/etc/init.d/S35tor
    remove_path /opt/etc/init.d/S56dnsmasq
    remove_path /opt/etc/init.d/S99unblock
    remove_path /opt/etc/ndm/netfilter.d/100-redirect.sh
    remove_path /opt/etc/ndm/ifstatechanged.d/100-unblock-vpn.sh
    remove_path /opt/etc/ndm/fs.d/100-ipset.sh
    remove_path /opt/bin/unblock_dnsmasq.sh
    remove_path /opt/bin/unblock_update.sh
    remove_path /opt/bin/unblock_ipset.sh
    remove_path /opt/etc/unblock.dnsmasq
    remove_path /opt/etc/dnsmasq.conf
    remove_path /opt/tmp/tor
    # chmod 777 /opt/etc/unblock || rm -Rfv /opt/etc/unblock
    remove_path /opt/etc/tor
    remove_path /opt/etc/xray
    remove_path /opt/etc/v2ray
    remove_path /opt/etc/trojan
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
    pip_cmd="python3 -m pip"
    if ! python3 -m pip --version >/dev/null 2>&1; then
      if python -m pip --version >/dev/null 2>&1; then
        pip_cmd="python -m pip"
      else
      curl -O https://bootstrap.pypa.io/get-pip.py
      sleep 3
        python3 get-pip.py
      fi
    fi
    if ! python3 - <<'PY' >/dev/null 2>&1
import socks
import telebot
PY
    then
      $pip_cmd install pyTelegramBotAPI pysocks
    fi
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
    set_type="$(detect_ipset_type)"

    echo "Переменные роутера найдены"
    # создания множеств IP-адресов unblock
    # rm -rf /opt/etc/ndm/fs.d/100-ipset.sh
    # chmod 777 /opt/etc/ndm/fs.d/100-ipset.sh || rm -rfv /opt/etc/ndm/fs.d/100-ipset.sh
    curl -o /opt/etc/ndm/fs.d/100-ipset.sh "$(repo_file_url 100-ipset.sh)"
    chmod 755 /opt/etc/ndm/fs.d/100-ipset.sh || chmod +x /opt/etc/ndm/fs.d/100-ipset.sh
    sed -i "s/hash:net/${set_type}/g" /opt/etc/ndm/fs.d/100-ipset.sh
    echo "Созданы файлы под множества"

    # chmod 777 /opt/etc/shadowsocks.json || rm -Rfv /opt/etc/shadowsocks.json
    # chmod 777 /opt/etc/init.d/S22shadowsocks
    if [ -s /opt/etc/shadowsocks.json ]; then
      echo "Существующие настройки Shadowsocks сохранены."
    else
      curl -o /opt/etc/shadowsocks.json "$(repo_file_url shadowsocks.json)"
      echo "Установлены настройки Shadowsocks"
    fi
    sed -i "s/ss-local/${ssredir}/g" /opt/etc/init.d/S22shadowsocks
    chmod 0644 /opt/etc/shadowsocks.json
    chmod 755 /opt/etc/init.d/S22shadowsocks || chmod +x /opt/etc/init.d/S22shadowsocks
    echo "Установлен параметр ss-redir для Shadowsocks"

    # chmod 777 /opt/etc/trojan/config.json || rm -Rfv /opt/etc/trojan/config.json
    mkdir -p /opt/etc/trojan
    if [ -s /opt/etc/trojan/config.json ]; then
      echo "Существующие настройки Trojan сохранены."
    else
      curl -o /opt/etc/trojan/config.json "$(repo_file_url trojanconfig.json)"
    fi
    configure_core_proxy_service

    # unblock folder and files
    mkdir -p /opt/etc/unblock
    touch /opt/etc/hosts && chmod 0644 /opt/etc/hosts
    touch /opt/etc/unblock/shadowsocks.txt && chmod 0644 /opt/etc/unblock/shadowsocks.txt
    touch /opt/etc/unblock/trojan.txt && chmod 0644 /opt/etc/unblock/trojan.txt
    touch /opt/etc/unblock/vmess.txt && chmod 0644 /opt/etc/unblock/vmess.txt
    touch /opt/etc/unblock/vless.txt && chmod 0644 /opt/etc/unblock/vless.txt
    touch /opt/etc/unblock/vless-2.txt && chmod 0644 /opt/etc/unblock/vless-2.txt
    touch /opt/etc/unblock/hysteria2.txt && chmod 0644 /opt/etc/unblock/hysteria2.txt
    echo "Созданы файлы под сайты и ip-адреса для обхода блокировок для SS, Trojan, Vmess, Vless и Hysteria2"

    # unblock_ipset.sh
    # chmod 777 /opt/bin/unblock_ipset.sh || rm -rfv /opt/bin/unblock_ipset.sh
    curl -o /opt/bin/unblock_ipset.sh "$(repo_file_url unblock_ipset.sh)"
    chmod 755 /opt/bin/unblock_ipset.sh || chmod +x /opt/bin/unblock_ipset.sh
    sed -i "s/40500/${dnsovertlsport}/g" /opt/bin/unblock_ipset.sh
    echo "Установлен скрипт для заполнения множеств unblock IP-адресами заданного списка доменов"

    # unblock_dnsmasq.sh
    # chmod 777 /opt/bin/unblock_dnsmasq.sh || rm -rfv /opt/bin/unblock_dnsmasq.sh
    curl -o /opt/bin/unblock_dnsmasq.sh "$(repo_file_url unblock.dnsmasq)"
    chmod 755 /opt/bin/unblock_dnsmasq.sh || chmod +x /opt/bin/unblock_dnsmasq.sh
    sed -i "s/40500/${dnsovertlsport}/g" /opt/bin/unblock_dnsmasq.sh
    /opt/bin/unblock_dnsmasq.sh
    echo "Установлен скрипт для формирования дополнительного конфигурационного файла dnsmasq из заданного списка доменов и его запуск"

    # unblock_update.sh
    # chmod 777 /opt/bin/unblock_update.sh || rm -rfv /opt/bin/unblock_update.sh
    curl -o /opt/bin/unblock_update.sh "$(repo_file_url unblock_update.sh)"
    chmod 755 /opt/bin/unblock_update.sh || chmod +x /opt/bin/unblock_update.sh
    echo "Установлен скрипт ручного принудительного обновления системы после редактирования списка доменов"

    # s99unblock
    # chmod 777 /opt/etc/init.d/S99unblock || rm -Rfv /opt/etc/init.d/S99unblock
    curl -o /opt/etc/init.d/S99unblock "$(repo_file_url S99unblock)"
    chmod 755 /opt/etc/init.d/S99unblock || chmod +x /opt/etc/init.d/S99unblock
    echo "Установлен cкрипт автоматического заполнения множества unblock при загрузке маршрутизатора"

    # 100-redirect.sh
    # chmod 777 /opt/etc/ndm/netfilter.d/100-redirect.sh || rm -rfv /opt/etc/ndm/netfilter.d/100-redirect.sh
    curl -o /opt/etc/ndm/netfilter.d/100-redirect.sh "$(repo_file_url 100-redirect.sh)"
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
    sed -i "s/10840/${localporthysteria2}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    sed -i "s/10841/${localporthysteria2_transparent}/g" /opt/etc/ndm/netfilter.d/100-redirect.sh
    echo "Установлено перенаправление пакетов с адресатами из unblock в: Shadowsocks, Trojan, xray/v2ray. Правила работают на всех интерфейсах роутера."

    # dnsmasq.conf
    #rm -rf /opt/etc/dnsmasq.conf
    rm -f /opt/etc/dnsmasq.conf
    curl -o /opt/etc/dnsmasq.conf "$(repo_file_url dnsmasq.conf)"
    chmod 755 /opt/etc/dnsmasq.conf
    mkdir -p "$BOT_RUNTIME_DIR"
    [ -f "$BOT_RUNTIME_DIR/youtube_edge_quality.hosts" ] || printf '# Managed by bypass_keenetic YouTube CDN quality worker.\n' > "$BOT_RUNTIME_DIR/youtube_edge_quality.hosts"
    sed -i "s/192.168.1.1/${lanip}/g" /opt/etc/dnsmasq.conf
    sed -i "s/40500/${dnsovertlsport}/g" /opt/etc/dnsmasq.conf
    sed -i "s/40508/${dnsoverhttpsport}/g" /opt/etc/dnsmasq.conf
    configure_dnsmasq_upstreams /opt/etc/dnsmasq.conf || {
      echo "Не удалось выбрать рабочие DNS-серверы."
      exit 1
    }
    echo "Установлена настройка dnsmasq и подключение дополнительного конфигурационного файла к dnsmasq"

    # cron file
    #rm -rf /opt/etc/crontab
    rm -f /opt/etc/crontab
    curl -o /opt/etc/crontab "$(repo_file_url crontab)"
    chmod 755 /opt/etc/crontab
    install_unblock_ipset_cron_job || true
    [ -x /opt/etc/init.d/S10cron ] && /opt/etc/init.d/S10cron restart >/dev/null 2>&1 || /opt/etc/init.d/S10cron start >/dev/null 2>&1 || true
    echo "Установлено добавление задачи в cron для периодического обновления содержимого множества"
    mkdir -p "$BOT_RUNTIME_DIR"
    install_runtime_modules $BOT_RUNTIME_MODULES
    rm -f "$BOT_RUNTIME_DIR/CHANGELOG.md" 2>/dev/null || true
    install_static_assets || exit 1
    rm -f "$BOT_RUNTIME_DIR/web_asset_builder.py" "$BOT_RUNTIME_DIR/web_template_styles.py" "$BOT_RUNTIME_DIR/web_template_scripts.py"
    ensure_runtime_legacy_paths
    generate_udp_quic_policy_file
    /opt/bin/unblock_update.sh
    load_runtime_guard "$BOT_RUNTIME_DIR/update_runtime_guard.sh" || exit 1
    bypass_validate_python_sources "$BOT_RUNTIME_DIR" || {
      echo "Ошибка: установленные Python-файлы не прошли проверку синтаксиса."
      exit 1
    }
    bypass_apply_runtime_network_rules || {
      echo "Ошибка: прозрачные сетевые правила не достигли готовности после установки."
      exit 1
    }
    /opt/etc/init.d/S99unblock restart >/dev/null 2>&1 || /opt/etc/init.d/S99unblock start >/dev/null 2>&1 || true
    run_youtube_edge_prefetch_once "Post-install"
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
    curl -s -o /opt/root/script.sh "$(repo_file_url script.sh)"
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
    cli_update_status_active=1
    write_cli_update_status update true 3 Подготовка "Обновление запущено"
    update_runtime_quiesced=0
    trap 'handle_cli_update_exit "$?"' EXIT
    trap 'exit 143' TERM INT HUP
    now=$(date +"%Y.%m.%d.%H-%M-%S")
    stage_dir="/opt/root/update-${now}"
    backup_dir="/opt/root/backup-${now}"
    mkdir -m 700 "$stage_dir"
    download_update_file "$(repo_file_url managed_state_snapshot.py)" \
      "$stage_dir/managed_state_snapshot.py" "SNAPSHOT_FORMAT" "managed_state_snapshot.py" || exit 1
    mkdir -m 700 "$backup_dir"
    PYTHONPATH="$stage_dir" python3 "$stage_dir/managed_state_snapshot.py" backup "$backup_dir/full-state" || exit 1
    mkdir -m 700 "$backup_dir/.rollback-tools"
    cp -p "$stage_dir/managed_state_snapshot.py" "$backup_dir/.rollback-tools/managed_state_snapshot.py"
    chmod 600 "$backup_dir/.rollback-tools/managed_state_snapshot.py"

    ensure_entware_dns
    opkg update > /dev/null 2>&1
    core_proxy_pkg=$(detect_core_proxy_package)
    opkg install "$core_proxy_pkg" > /dev/null 2>&1 || true
    for legacy_pkg in obfs4 tor-geoip tor; do
      opkg remove "$legacy_pkg" > /dev/null 2>&1 || true
    done
    # opkg update
    echo "Ваша версия KeenOS" "${keen_os_full}."
    echo "Пакеты обновлены."

    echo "Скачиваем обновления во временную папку и проверяем файлы."
    write_cli_update_status update true 10 Загрузка "Скачиваем файлы обновления"
    download_update_file "$(repo_file_url script.sh)" "$stage_dir/script.sh" "#!/bin/sh" "script.sh" || exit 1
    download_update_file "$(repo_file_url 100-ipset.sh)" "$stage_dir/100-ipset.sh" "#!/bin/sh" "100-ipset.sh" || exit 1
    download_update_file "$(repo_file_url 100-redirect.sh)" "$stage_dir/100-redirect.sh" "iptables -I PREROUTING" "100-redirect.sh" || exit 1
    download_update_file "$(repo_file_url unblock_ipset.sh)" "$stage_dir/unblock_ipset.sh" "#!/bin/sh" "unblock_ipset.sh" || exit 1
    download_update_file "$(repo_file_url unblock.dnsmasq)" "$stage_dir/unblock_dnsmasq.sh" "#!/bin/sh" "unblock.dnsmasq" || exit 1
    download_update_file "$(repo_file_url unblock_update.sh)" "$stage_dir/unblock_update.sh" "#!/bin/sh" "unblock_update.sh" || exit 1
    download_update_file "$(repo_file_url dnsmasq.conf)" "$stage_dir/dnsmasq.conf" "listen-address=" "dnsmasq.conf" || exit 1
    download_update_file "$(repo_file_url crontab)" "$stage_dir/crontab" "S99unblock tick" "crontab" || exit 1
    download_update_file "$(repo_file_url S99unblock)" "$stage_dir/S99unblock" "bypass unblock scheduler" "S99unblock" || exit 1
    download_update_file "$(repo_file_url bot.py)" "$stage_dir/bot.py" "KeyInstallHTTPRequestHandler" "bot.py" || exit 1
    staged_runtime_modules=$(sed -n 's/^BOT_RUNTIME_MODULES="\([^\"]*\)"$/\1/p' "$stage_dir/script.sh" | head -n1)
    [ -n "$staged_runtime_modules" ] || { echo "Ошибка: во временном скрипте нет списка модулей программы"; exit 1; }
    BOT_RUNTIME_MODULES="$staged_runtime_modules"
    for module in $staged_runtime_modules; do
      stage_runtime_module "$module" "" || exit 1
    done
    stage_runtime_module pool_probe_runner.py run_pool_probe_worker || exit 1
    stage_runtime_module key_pool_store.py "def normalize_key_pools" || exit 1
    stage_runtime_module key_pool_web.py pool_status_summary || exit 1
    stage_runtime_module telegram_pool_ui.py pool_action_markup || exit 1
    stage_runtime_module probe_cache.py record_key_probe || exit 1
    stage_runtime_module custom_checks_store.py add_custom_check || exit 1
    stage_runtime_module service_catalog.py CUSTOM_CHECK_PRESETS || exit 1
    stage_runtime_module web_background.py WebBackgroundStore || exit 1
    stage_runtime_module web_form_template.py render_web_form || exit 1
    stage_runtime_module web_form_blocks.py render_message_block || exit 1
    stage_runtime_module web_pool_form_blocks.py render_protocol_check_content || exit 1
    stage_runtime_module web_http_common.py WebRequestMixin || exit 1
    stage_runtime_module web_get_actions.py dispatch || exit 1
    stage_runtime_module web_post_actions.py dispatch || exit 1
    stage_runtime_module web_command_state.py command_state_snapshot || exit 1
    stage_runtime_module unblock_lists.py save_unblock_list_file || exit 1
    stage_runtime_module proxy_key_store.py load_current_keys || exit 1
    stage_runtime_module proxy_protocols.py proxy_outbound_from_key || exit 1
    stage_runtime_module proxy_config_builder.py build_proxy_core_config || exit 1
    stage_runtime_module transparent_route_policy.py compile_protocol_policies || exit 1
    stage_runtime_module proxy_status.py status_snapshot_signature || exit 1
    download_update_file "$(repo_file_url installer.py)" "$stage_dir/installer.py" "ThreadingHTTPServer" "installer.py" || exit 1
    stage_runtime_module installer_common.py browser_port_is_valid || exit 1
    download_update_file "$(repo_file_url S98telegram_bot_installer)" "$stage_dir/S98telegram_bot_installer" "Installer started" "S98telegram_bot_installer" || exit 1
    download_update_file "$(repo_file_url S99telegram_bot)" "$stage_dir/S99telegram_bot" "Bot started" "S99telegram_bot" || exit 1
    stage_static_assets || exit 1

    set_type="$(detect_ipset_type)"
    sed -i "s/hash:net/${set_type}/g" "$stage_dir/100-ipset.sh"
    sed -i "s/hash:net/${set_type}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/192.168.1.1/${lanip}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/1082/${localportsh}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10810/${localportvmess}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10811/${localportvless}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10812/${localportvless_transparent}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10813/${localportvless2}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10814/${localportvless2_transparent}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10829/${localporttrojan}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10840/${localporthysteria2}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/10841/${localporthysteria2_transparent}/g" "$stage_dir/100-redirect.sh"
    sed -i "s/40500/${dnsovertlsport}/g" "$stage_dir/unblock_ipset.sh"
    sed -i "s/40500/${dnsovertlsport}/g" "$stage_dir/unblock_dnsmasq.sh"
    sed -i "s/192.168.1.1/${lanip}/g" "$stage_dir/dnsmasq.conf"
    sed -i "s/40500/${dnsovertlsport}/g" "$stage_dir/dnsmasq.conf"
    sed -i "s/40508/${dnsoverhttpsport}/g" "$stage_dir/dnsmasq.conf"
    configure_dnsmasq_upstreams "$stage_dir/dnsmasq.conf" || exit 1
    validate_staged_update_runtime || {
      echo "Ошибка: подготовленный релиз не прошёл проверку запуска; текущая версия продолжает работать."
      exit 1
    }
    echo "Файлы успешно скачаны и подготовлены."
    target_release=$(sed -n 's/^\*v\([0-9][0-9A-Za-z._-]*\).*/v\1/p' "$stage_dir/version.md" | head -n1)
    write_cli_update_status update true 40 Подготовлено "Файлы обновления скачаны и проверены" "$target_release"
    echo "Дальнейший журнал обновления сохраняется в $stage_dir/update.log."
    exec >> "$stage_dir/update.log" 2>&1

    update_runtime_quiesced=1
    prepare_application_for_update || exit 1
    echo "Пересобираем конфигурацию core proxy из сохранённых ключей."
    PYTHONPATH="$stage_dir:$BOT_RUNTIME_DIR" python3 "$stage_dir/proxy_config_recovery.py" || exit 1

    /opt/etc/init.d/S22shadowsocks stop > /dev/null 2>&1
    /opt/etc/init.d/S24xray stop > /dev/null 2>&1
    /opt/etc/init.d/S24v2ray stop > /dev/null 2>&1
    /opt/etc/init.d/S22trojan stop > /dev/null 2>&1
    /opt/etc/init.d/S99unblock stop > /dev/null 2>&1 || true
    echo "Сервисы остановлены."
    write_cli_update_status update true 55 "Резервная копия" "Сервисы остановлены; создаём резервную копию"

    PYTHONPATH="$backup_dir/.rollback-tools" python3 \
      "$backup_dir/.rollback-tools/managed_state_snapshot.py" verify "$backup_dir/full-state" || exit 1
    [ -f /opt/bin/unblock_ipset.sh ] && mv /opt/bin/unblock_ipset.sh "$backup_dir"/unblock_ipset.sh
    [ -f /opt/bin/unblock_dnsmasq.sh ] && mv /opt/bin/unblock_dnsmasq.sh "$backup_dir"/unblock_dnsmasq.sh
    [ -f /opt/bin/unblock_update.sh ] && mv /opt/bin/unblock_update.sh "$backup_dir"/unblock_update.sh
    [ -f /opt/etc/dnsmasq.conf ] && mv /opt/etc/dnsmasq.conf "$backup_dir"/dnsmasq.conf
    repair_legacy_dnsmasq_backup "$backup_dir/dnsmasq.conf" || exit 1
    [ -f /opt/etc/crontab ] && mv /opt/etc/crontab "$backup_dir"/crontab
    [ -f /opt/etc/init.d/S99unblock ] && mv /opt/etc/init.d/S99unblock "$backup_dir"/S99unblock
    [ -f /opt/etc/ndm/fs.d/100-ipset.sh ] && mv /opt/etc/ndm/fs.d/100-ipset.sh "$backup_dir"/100-ipset.sh
    [ -f /opt/etc/ndm/netfilter.d/100-redirect.sh ] && mv /opt/etc/ndm/netfilter.d/100-redirect.sh "$backup_dir"/100-redirect.sh
    if [ -f "$BOT_MAIN_PATH" ]; then
      mv "$BOT_MAIN_PATH" "$backup_dir"/bot.py
    fi
    if [ -f /opt/root/script.sh ]; then
      mv /opt/root/script.sh "$backup_dir"/script.sh
    fi
    if [ -f "$INSTALLER_MAIN_PATH" ]; then
      mv "$INSTALLER_MAIN_PATH" "$backup_dir"/installer.py
    fi
    if [ -f "$INSTALLER_SERVICE_PATH" ]; then
      mv "$INSTALLER_SERVICE_PATH" "$backup_dir"/S98telegram_bot_installer
    fi
    if [ -f "$BOT_SERVICE_PATH" ]; then
      mv "$BOT_SERVICE_PATH" "$backup_dir"/S99telegram_bot
    fi
    backup_runtime_state_files
    backup_runtime_modules $BOT_RUNTIME_MODULES
    backup_static_assets
    cp -p "$stage_dir/update_status.py" "$backup_dir/.rollback-tools/update_status.py"
    cp -p "$stage_dir/web_command_state.py" "$backup_dir/.rollback-tools/web_command_state.py"
    cp -p "$stage_dir/update_runtime_guard.sh" "$backup_dir/.rollback-tools/update_runtime_guard.sh"
    chmod 600 \
      "$backup_dir/.rollback-tools/update_status.py" \
      "$backup_dir/.rollback-tools/web_command_state.py" \
      "$backup_dir/.rollback-tools/update_runtime_guard.sh"
    write_update_rollback_script
    cleanup_removed_connection_artifacts
    chmod 700 "$backup_dir" "$backup_dir/rollback.sh" 2>/dev/null || true
    echo "Бэкап создан."
    write_cli_update_status update true 65 Установка "Устанавливаем подготовленные файлы"

    touch /opt/etc/hosts && chmod 0644 /opt/etc/hosts
    mv "$stage_dir/script.sh" /opt/root/script.sh
    chmod 755 /opt/root/script.sh || chmod +x /opt/root/script.sh
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
    mkdir -p "$BOT_RUNTIME_DIR"
    [ -f "$BOT_RUNTIME_DIR/youtube_edge_quality.hosts" ] || printf '# Managed by bypass_keenetic YouTube CDN quality worker.\n' > "$BOT_RUNTIME_DIR/youtube_edge_quality.hosts"
    if [ -x /opt/etc/init.d/S56dnsmasq ]; then
      /opt/etc/init.d/S56dnsmasq restart > /dev/null 2>&1 || /opt/etc/init.d/S56dnsmasq start > /dev/null 2>&1 || true
    fi
    mv "$stage_dir/crontab" /opt/etc/crontab
    chmod 755 /opt/etc/crontab
    install_unblock_ipset_cron_job || true
    mv "$stage_dir/S99unblock" /opt/etc/init.d/S99unblock
    chmod 755 /opt/etc/init.d/S99unblock

    configure_core_proxy_service

    mkdir -p "$BOT_RUNTIME_DIR"
    mv "$stage_dir/bot.py" "$BOT_MAIN_PATH"
    chmod 755 "$BOT_MAIN_PATH"
    activate_runtime_modules $BOT_RUNTIME_MODULES
    rm -f "$BOT_RUNTIME_DIR/CHANGELOG.md" 2>/dev/null || true
    restore_runtime_state_files_after_update
    ensure_hysteria2_runtime_state_files
    ensure_runtime_legacy_paths
    migrate_runtime_config_defaults
    generate_udp_quic_policy_file
    repair_service_route_catalog_drift
    mkdir -p "$(dirname "$INSTALLER_MAIN_PATH")"
    mv "$stage_dir/installer.py" "$INSTALLER_MAIN_PATH"
    chmod 755 "$INSTALLER_MAIN_PATH"
    install_staged_static_assets || exit 1
    rm -f "$BOT_RUNTIME_DIR/web_asset_builder.py" "$BOT_RUNTIME_DIR/web_template_styles.py" "$BOT_RUNTIME_DIR/web_template_scripts.py"
    mv "$stage_dir/S98telegram_bot_installer" "$INSTALLER_SERVICE_PATH"
    mv "$stage_dir/S99telegram_bot" "$BOT_SERVICE_PATH"
    chmod 755 "$INSTALLER_SERVICE_PATH" "$BOT_SERVICE_PATH"
    rmdir "$stage_dir" 2>/dev/null || true
    cleanup_update_artifacts 1
    echo "Обновления скачены, права настроены."
    write_cli_update_status update true 85 Перезапуск "Перезапускаем сервисы"
    load_runtime_guard "$BOT_RUNTIME_DIR/update_runtime_guard.sh" || exit 1
    bypass_validate_python_sources "$BOT_RUNTIME_DIR" || {
      echo "Ошибка: установленная версия не прошла итоговую проверку Python; запускаем автоматический откат."
      exit 1
    }

    /opt/etc/init.d/S10cron restart > /dev/null 2>&1 || /opt/etc/init.d/S10cron start > /dev/null 2>&1 || true
    /opt/etc/init.d/S22shadowsocks start > /dev/null 2>&1
    start_preferred_core_service || exit 1
    /opt/etc/init.d/S22trojan start > /dev/null 2>&1
    /opt/etc/init.d/S99unblock restart > /dev/null 2>&1 || /opt/etc/init.d/S99unblock start > /dev/null 2>&1 || true

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
    clear_runtime_update_env
    update_completion_message="Обновление завершено"
    write_cli_update_status update true 88 Запуск "Запускаем программу и веб-интерфейс"
    stop_application_for_final_restart || {
      echo "Ошибка: не удалось остановить процесс обслуживания перед итоговым перезапуском"
      exit 1
    }
    if ! telegram_config_complete; then
      start_telegram_installer
      update_completion_message="Обновление завершено; запущен установщик первичной настройки"
    elif [ -x "$BOT_SERVICE_PATH" ]; then
      start_updated_bot_transactionally || exit 1
      echo "Бот, веб-интерфейс, локальный прокси и прозрачные правила подтверждены. Нажмите сюда: /start"
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
        echo "Ошибка: не удалось подтвердить перезапуск бота"
        exit 1
      fi
    fi

    update_runtime_quiesced=0
    write_cli_update_status update true 90 Завершение "Веб-интерфейс доступен; завершаем обновление сетевых списков"
    echo "Веб-интерфейс запущен. Завершаем обновление сетевых списков."
    echo "Обновляем ipset после запуска основного прокси-сервиса."
    run_update_ipset_refresh "После обновления"
    run_youtube_edge_prefetch_once "Post-update"
    run_youtube_edge_prefetch_retry_if_skipped "Post-update-late" 90
    write_cli_update_status update false 100 Готово "$update_completion_message"
    cli_update_status_active=0
    trap - EXIT TERM INT HUP
    exit 0
fi

if [ "$1" = "-reboot" ]; then
    echo "Перезагрузка роутера"
    ndmc -c 'system reboot'
fi

if [ "$1" = "-version" ]; then
    echo "Ваша версия KeenOS" "${keen_os_full}"
fi

if [ "$1" = "-help" ]; then
    echo "-install — установить программу и необходимые компоненты"
    echo "-remove — удалить файлы программы"
    echo "-update — скачать и установить обновление"
    echo "-reinstall — переустановить программу"
fi

if [ -z "$1" ]; then
    #echo not found "$1".
    echo "-install — установить программу и необходимые компоненты"
    echo "-remove — удалить файлы программы"
    echo "-update — скачать и установить обновление"
    echo "-reinstall — переустановить программу"
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
