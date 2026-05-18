# ВЕРСИЯ СКРИПТА v1.611

token = 'MyBotFatherToken'  # ключ api бота
usernames = ['MyTelegramLogin']  # Ваш логин в телеграмме без @, не бота.

routerip = '192.168.1.1'  # ip роутера
browser_port = '8080'  # порт для веб-интерфейса установки ключей
web_auth_user = 'admin'  # логин веб-интерфейса
web_auth_token = ''  # пароль веб-интерфейса; если пусто, вход будет без пароля
web_auth_disabled = False  # True отключает пароль веб-интерфейса, оставляя только LAN + CSRF
fork_repo_owner = 'andruwko73'  # GitHub username вашего форка bypass_keenetic
fork_repo_name = 'bypass_keenetic'  # имя репозитория форка
fork_button_label = 'Fork by andruwko73'  # подпись кнопки установки из вашего форка
app_runtime_mode = 'advanced'  # simple, advanced или web_only
pool_probe_min_available_kb = 190000  # проверка пула не запускает временный xray, если доступной памяти меньше этого порога
pool_probe_delay_seconds = 1.5  # пауза между ключами, чтобы полная проверка пула не забивала CPU роутера
pool_probe_cpu_guard_enabled = True
pool_probe_max_cpu_percent = 70.0
pool_probe_cpu_sample_seconds = 0.35
pool_probe_high_cpu_delay_seconds = 5.0
pool_probe_high_cpu_max_wait_seconds = 45.0
memory_watchdog_enabled = True  # бот сам перезапустит свой сервис, если память Python долго держится выше безопасного порога
memory_watchdog_rss_soft_kb = 87040  # при достижении порога очищаются кэши статуса и запускается gc.collect()
memory_watchdog_rss_limit_kb = 112640  # выше этого RSS бот перезапустится, если сейчас не идёт обновление или проверка пула
memory_watchdog_idle_restart_rss_kb = 61440  # если бот долго держит RSS выше этого уровня в простое, сервис будет мягко перезапущен
memory_watchdog_idle_restart_hold_seconds = 120.0
memory_watchdog_check_interval = 60.0
memory_watchdog_min_uptime_seconds = 300.0
memory_watchdog_restart_cooldown_seconds = 1800.0
memory_post_pool_restart_enabled = True  # после проверки пула бот сам снизит память и перезапустится, если Python RSS остался высоким
memory_post_pool_restart_rss_kb = 61440
memory_post_pool_restart_delay_seconds = 20.0
udp_quic_block_vless_enabled = True  # умная блокировка QUIC/UDP 443 для YouTube-доменов из списка Vless 1
udp_quic_block_vless2_enabled = True  # умная блокировка QUIC/UDP 443 для YouTube-доменов из списка Vless 2
youtube_vless2_failover_enabled = True  # YouTube остается на Vless 2: если текущий Vless2 ключ перестал отвечать, бот подберет другой из пула Vless2
youtube_vless2_failover_grace_seconds = 180
youtube_vless2_failover_poll_seconds = 120
youtube_vless2_failover_switch_cooldown_seconds = 300
youtube_vless2_failover_check_connect_timeout = 6
youtube_vless2_failover_check_read_timeout = 10
youtube_vless2_failover_confirm_retries = 3
youtube_vless2_failover_confirm_delay_seconds = 8.0

# следующие настройки могут быть оставлены по умолчанию, но можно будет что-то поменять
localportsh = '1082'  # локальный порт для shadowsocks
localportvmess = '10810'  # локальный порт для vmess
localportvless = '10811'  # локальный порт для vless
localporttrojan = '10829'  # локальный порт для trojan
default_proxy_mode = 'none'  # выбор прокси для Telegram API: none, shadowsocks, vmess, vless, vless2, trojan
dnsovertlsport = '40500'  # можно посмотреть номер порта командой "cat /tmp/ndnproxymain.stat"
dnsoverhttpsport = '40508'  # можно посмотреть номер порта командой "cat /tmp/ndnproxymain.stat"
