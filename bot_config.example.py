# ВЕРСИЯ СКРИПТА v1.892

token = 'MyBotFatherToken'  # ключ api бота
usernames = ['MyTelegramLogin']  # Ваш логин в телеграмме без @, не бота.

routerip = '192.168.1.1'  # ip роутера
browser_port = '8080'  # порт для веб-интерфейса установки ключей
web_auth_user = 'admin'  # логин веб-интерфейса
web_auth_token = ''  # пароль веб-интерфейса; обычно пароль основного интерфейса роутера
web_auth_disabled = False  # True отключает пароль веб-интерфейса, оставляя только LAN + CSRF
fork_repo_owner = 'andruwko73'  # GitHub username вашего форка bypass_keenetic
fork_repo_name = 'bypass_keenetic'  # имя репозитория форка
fork_button_label = 'Fork by andruwko73'  # подпись кнопки установки из вашего форка
app_runtime_mode = 'advanced'  # simple, advanced или web_only
subscription_state_path = '/opt/etc/bot/subscriptions.json'  # сохраненные subscription URL и режим HWID
subscription_router_hwid = ''  # если пусто, HWID читается read-only через ndmc show system/version
subscription_hwid_query_param = 'hwid'
subscription_hwid_header_names = ('X-HWID', 'X-Router-HWID', 'X-Device-ID')
subscription_user_agent = 'v2rayN/6.45'
subscription_accept_header = 'text/plain, */*'
subscription_auto_refresh_enabled = True
subscription_auto_refresh_interval_seconds = 86400  # раз в день для подписок с включенным HWID
subscription_auto_refresh_retry_seconds = 3600
subscription_auto_refresh_max_bot_rss_kb = 71680  # lightweight subscription refresh may run above the general background RSS guard, but not at the restart threshold
subscription_auto_refresh_min_available_kb = 92160
subscription_auto_refresh_max_cpu_percent = 80.0
subscription_auto_refresh_max_load1 = 2.5
pool_probe_process_worker_enabled = True  # run full pool checks in a separate Python process so main bot RSS can return to baseline
pool_probe_process_worker_poll_seconds = 0.75
telegram_bot_num_threads = 1  # keep Telegram command worker pool small on routers with limited RAM
pool_probe_min_available_kb = 190000  # проверка пула не запускает временный xray, если доступной памяти меньше этого порога
pool_probe_pause_available_kb = 125000  # ниже этого порога проверка ставит очередь на паузу до освобождения памяти
pool_probe_slow_available_kb = 190000  # ниже этого порога проверка идёт медленнее, но не останавливается полностью
pool_probe_slow_memory_delay_seconds = 3.0
pool_probe_delay_seconds = 3.0  # пауза между ключами, чтобы полная проверка пула не забивала CPU роутера
pool_probe_cpu_guard_enabled = True
pool_probe_max_cpu_percent = 45.0
pool_probe_cpu_sample_seconds = 0.35
pool_probe_high_cpu_delay_seconds = 8.0
pool_probe_high_cpu_max_wait_seconds = 120.0
pool_probe_max_load1 = 2.0
pool_probe_high_load_delay_seconds = 10.0
pool_probe_high_load_max_wait_seconds = 120.0
pool_probe_max_process_rss_kb = 66560  # рабочий потолок RSS во время проверки пула; restart-порог остаётся 70 MB, но проверка чистит память/приостанавливается раньше
pool_probe_youtube_profile = 'quick'  # quick для пула, full остаётся для детальной диагностики активного ключа
pool_probe_quality_enabled = True  # короткий download-sample через ключ для оценки YouTube-качества перед применением
pool_probe_quality_download_url = 'https://speed.cloudflare.com/__down?bytes={bytes}'
pool_probe_quality_download_bytes = 524288
pool_probe_quality_min_available_kb = 170000
pool_probe_quality_max_samples_per_run = 6
pool_probe_quality_download_connect_timeout = 6.0
pool_probe_quality_download_read_timeout = 10.0
pool_probe_quality_stable_latency_ms = 2500
pool_probe_quality_fast_latency_ms = 1500
pool_probe_quality_1600p_min_mbps = 25.0
pool_probe_quality_4k_min_mbps = 45.0
router_health_cache_ttl = 30.0  # быстрый веб-статус памяти/CPU без лишнего опроса роутера
router_health_dns_cache_ttl = 45.0  # dnsmasq/ipset diagnostics не дергать на каждом обновлении страницы
router_health_ndmc_cache_ttl = 30.0  # ndmc show system тяжелее /proc, держим отдельный TTL
router_health_related_process_cache_ttl = 45.0  # не сканировать все /proc на каждый веб-статус в простое
router_health_cpu_smoothing_factor = 0.35  # сглаживать короткие CPU-пики в блоке Роутер
web_status_api_cache_ttl = 30.0
router_metrics_history_limit = 120
router_metrics_warn_bot_rss_kb = 66560
router_metrics_critical_bot_rss_kb = 87040
router_metrics_warn_load1 = 3.0
web_pools_api_cache_ttl = 45.0
service_route_intersections_cache_ttl = 60.0
memory_watchdog_enabled = True  # бот сам перезапустит свой сервис, если память Python долго держится выше безопасного порога
memory_cleanup_rss_kb = 61440  # тихая очистка gc/malloc_trim без перезапуска, когда RSS держится около 60 MB
web_response_cleanup_rss_kb = 61440  # веб-ответы освобождают память уже около 60 MB, не дожидаясь 70+ MB
web_response_light_cleanup_rss_kb = 66560  # легкие status/api ответы не запускают gc на рабочей полке около 62 MB
web_response_cleanup_min_interval_seconds = 60.0
memory_watchdog_rss_soft_kb = 87040  # при достижении порога очищаются кэши статуса и запускается gc.collect()
memory_watchdog_rss_limit_kb = 112640  # выше этого RSS бот перезапустится, если сейчас не идёт обновление или проверка пула
memory_watchdog_idle_restart_rss_kb = 71680  # если бот долго держит RSS выше этого уровня в простое, сервис будет мягко перезапущен
memory_watchdog_idle_restart_hold_seconds = 120.0
memory_watchdog_check_interval = 60.0
memory_watchdog_min_uptime_seconds = 300.0
memory_watchdog_restart_cooldown_seconds = 1800.0
status_refresh_min_interval_seconds = 180.0  # minimum delay between heavy web status refreshes
memory_post_pool_restart_enabled = True  # после проверки пула бот сам снизит память и перезапустится, если Python RSS остался высоким
memory_post_pool_restart_rss_kb = 71680
memory_post_pool_cleanup_target_rss_kb = 63488  # после проверки пула повторять gc/malloc_trim до целевой полки около 62 MB, но не перезапускать ниже restart-порога
memory_post_pool_restart_delay_seconds = 20.0
memory_post_pool_restart_retry_seconds = 30.0
memory_post_pool_restart_max_wait_seconds = 300.0
memory_timeline_enabled = False
memory_timeline_path = '/opt/tmp/bypass_memory_timeline.jsonl'
memory_timeline_interval_seconds = 60.0
memory_timeline_max_events = 720
memory_malloc_trim_enabled = True  # после тяжёлой очистки просит libc вернуть свободные арены памяти системе
memory_malloc_trim_min_rss_kb = 61440
memory_malloc_trim_cooldown_seconds = 20.0
background_task_cpu_cache_ttl_seconds = 20.0
background_task_max_bot_rss_kb = 66560  # skip service background checks near 65 MB RSS so the bot does not approach the restart threshold
udp_quic_block_shadowsocks_enabled = True  # smart QUIC/UDP 443 fallback for service domains from the Shadowsocks list
udp_quic_block_vmess_enabled = True  # smart QUIC/UDP 443 fallback for service domains from the Vmess list
udp_quic_block_vless_enabled = True  # smart QUIC/UDP 443 fallback for non-YouTube routes
udp_quic_block_vless2_enabled = True  # smart QUIC/UDP 443 fallback for non-YouTube routes
udp_quic_block_trojan_enabled = True  # smart QUIC/UDP 443 fallback for service domains from the Trojan list
youtube_quic_policy = 'auto'  # auto blocks QUIC for routes that contain YouTube; allow permits QUIC; block forces TCP fallback
telegram_udp_policy = 'auto'  # auto/allow keep UDP open for Telegram routes so native calls can use relay/media traffic; block disables it
youtube_edge_prefetch_enabled = True  # lightweight DNS/IP prefetch for the active YouTube route
youtube_edge_prefetch_mode = 'external'  # external runner keeps this work out of the long-running bot process
youtube_edge_prefetch_start_delay_seconds = 120
youtube_edge_prefetch_interval_seconds = 1800
youtube_edge_prefetch_cache_path = '/opt/etc/bot/youtube_edge_cache.json'
youtube_edge_prefetch_status_path = '/opt/etc/bot/youtube_edge_prefetch_status.json'
youtube_edge_prefetch_lock_dir = '/tmp/bypass-youtube-edge-prefetch.lock'
youtube_edge_prefetch_cache_ttl_seconds = 259200
youtube_edge_prefetch_max_cache_entries = 128
youtube_edge_prefetch_max_hosts_per_run = 6
youtube_edge_prefetch_max_resolved_addresses = 16
youtube_edge_prefetch_max_candidates = 32
youtube_edge_prefetch_max_addresses_per_run = 8
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
youtube_edge_prefetch_fast_max_hosts_per_run = 4
youtube_edge_prefetch_fast_max_candidates = 16
youtube_edge_prefetch_quality_probe_enabled = True
youtube_edge_prefetch_quality_target_ms = 1000
youtube_edge_prefetch_quality_timeout_seconds = 5
youtube_edge_prefetch_quality_bad_cooldown_seconds = 3600
youtube_edge_prefetch_quality_max_candidates = 12
youtube_edge_prefetch_scheduler_max_cpu_percent = 45
youtube_edge_prefetch_scheduler_max_load1 = 2.0
youtube_edge_prefetch_cpu_sample_ms = 250
youtube_edge_watch_warm_enabled = True
youtube_edge_watch_warm_urls = (
    'https://www.youtube.com/watch?v=aqz-KE-bpKQ',
    'https://www.youtube.com/watch?v=jfKfPfyJRdk',
)
youtube_edge_watch_warm_max_pages = 1
youtube_edge_watch_warm_max_hosts = 4
youtube_edge_watch_warm_max_bytes = 900000
youtube_edge_watch_warm_connect_timeout = 4
youtube_edge_watch_warm_max_time = 10
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
telegram_call_learning_enabled = True
telegram_call_learning_state_path = '/tmp/bypass_telegram_call_learning.json'
telegram_call_learning_default_duration_seconds = 90
telegram_call_learning_max_duration_seconds = 180
telegram_call_learning_poll_interval_seconds = 1.0
telegram_call_learning_auto_enabled = True
telegram_call_learning_scan_interval_seconds = 5.0
telegram_call_learning_idle_backoff_seconds = 60.0
telegram_call_learning_route_cache_ttl_seconds = 30.0
telegram_call_learning_fast_scan_limit = 3
telegram_call_learning_min_score = 5
telegram_call_learning_min_packets = 2
telegram_call_learning_min_bytes = 240
telegram_call_learning_max_candidates = 20
telegram_call_learning_max_seen_addresses = 512
telegram_call_learning_apply_by_default = True
telegram_call_learning_client_timeout_seconds = 900  # idle kernel window after Telegram signaling from a LAN client
telegram_call_learning_address_timeout_seconds = 14400  # learned call relay/P2P addresses expire automatically
telegram_call_tproxy_enabled = True  # routes Telegram call UDP through TPROXY when KeenOS exposes xt_TPROXY/xt_socket
udp_quic_drift_priority_refresh_cooldown_seconds = 120  # refresh YouTube/Googlevideo ipset drift faster than low-priority service drift
ipset_refresh_command_timeout_seconds = 420  # allow slower low-load ipset refreshes on busy routers
ipv6_bypass_fallback_enabled = True  # для ndnproxy: сбрасывать IPv6 к доменам обхода, чтобы клиенты быстро переходили на IPv4 через прокси
reality_endpoint_overrides = {}  # необязательно: {'server.example.com': '203.0.113.10'} для Reality-доменов с нестабильным DNS-бэкендом
reality_endpoint_repair_enabled = True  # перед сменой Reality-ключа бот пробует рабочие endpoint'ы текущего ключа
reality_endpoint_repair_max_candidates = 6
reality_endpoint_repair_dns_servers = ('1.1.1.1', '8.8.8.8', '9.9.9.9')
auto_failover_startup_hold_seconds = 180  # после рестарта бот не переключает Telegram-ключи, пока Xray и маршруты стабилизируются
youtube_vless2_failover_enabled = True  # YouTube остается на Vless 2: если текущий Vless2 ключ перестал отвечать, бот подберет другой из пула Vless2
auto_failover_consecutive_failures = 3  # switch Telegram key only after repeated confirmed failures
auto_failover_traffic_guard_bypass_failures = 3  # allow Telegram failover through traffic guard after repeated confirmed failures
youtube_vless2_failover_grace_seconds = 180
youtube_vless2_failover_poll_seconds = 120
youtube_vless2_failover_switch_cooldown_seconds = 300
youtube_vless2_failover_check_connect_timeout = 6
youtube_vless2_failover_check_read_timeout = 10
youtube_vless2_failover_confirm_retries = 3
youtube_vless2_failover_confirm_delay_seconds = 8.0
active_status_recent_success_ttl = 900
auto_failover_recent_success_ttl = 900
youtube_vless2_failover_recent_success_ttl = 900
youtube_vless2_restart_recheck_enabled = True
youtube_vless2_restart_recheck_cooldown_seconds = 300
youtube_vless2_failover_consecutive_failures = 3
youtube_vless2_hard_failure_recovery_cooldown_seconds = 90
youtube_stream_guard_scan_cache_seconds = 8.0  # reuse recent conntrack scan results to avoid repeated CPU spikes
youtube_stream_guard_failover_hold_seconds = 45  # Если при просмотре YouTube трафик пропал, автозамена Vless2 сможет продолжиться после этой паузы
youtube_stream_guard_event_interval_seconds = 1800  # не чаще одного stream_guard_defer в истории за 30 минут

# следующие настройки могут быть оставлены по умолчанию, но можно будет что-то поменять
localportsh = '1082'  # локальный порт для shadowsocks
localportvmess = '10810'  # локальный порт для vmess
localportvless = '10811'  # локальный порт для vless
localporttrojan = '10829'  # локальный порт для trojan
localportsh_tproxy = '11802'  # UDP TPROXY inbound for Telegram calls through Shadowsocks
localportvmess_tproxy = '11815'  # UDP TPROXY inbound for Telegram calls through VMess
localportvless_tproxy = '11812'  # UDP TPROXY inbound for Telegram calls through Vless
localportvless2_tproxy = '11814'  # UDP TPROXY inbound for Telegram calls through Vless 2
localporttrojan_tproxy = '11829'  # UDP TPROXY inbound for Telegram calls through Trojan
default_proxy_mode = 'none'  # выбор прокси для Telegram API: none, shadowsocks, vmess, vless, vless2, trojan
dnsovertlsport = '40500'  # можно посмотреть номер порта командой "cat /tmp/ndnproxymain.stat"
dnsoverhttpsport = '40508'  # можно посмотреть номер порта командой "cat /tmp/ndnproxymain.stat"
