# ВЕРСИЯ СКРИПТА v1.584

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
memory_watchdog_enabled = True  # бот сам перезапустит свой сервис, если память Python долго держится выше безопасного порога
memory_watchdog_rss_soft_kb = 87040  # при достижении порога очищаются кэши статуса и запускается gc.collect()
memory_watchdog_rss_limit_kb = 112640  # выше этого RSS бот перезапустится, если сейчас не идёт обновление или проверка пула
memory_watchdog_check_interval = 60.0
memory_watchdog_min_uptime_seconds = 300.0
memory_watchdog_restart_cooldown_seconds = 1800.0

# следующие настройки могут быть оставлены по умолчанию, но можно будет что-то поменять
localportsh = '1082'  # локальный порт для shadowsocks
localportvmess = '10810'  # локальный порт для vmess
localportvless = '10811'  # локальный порт для vless
localporttrojan = '10829'  # локальный порт для trojan
default_proxy_mode = 'none'  # выбор прокси для Telegram API: none, shadowsocks, vmess, vless, vless2, trojan
dnsovertlsport = '40500'  # можно посмотреть номер порта командой "cat /tmp/ndnproxymain.stat"
dnsoverhttpsport = '40508'  # можно посмотреть номер порта командой "cat /tmp/ndnproxymain.stat"
