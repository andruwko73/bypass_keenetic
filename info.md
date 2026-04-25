*Информационный раздел*

*Об этом форке*
- Это форк проекта [keenetic-dev/bypass_keenetic_dev](https://github.com/keenetic-dev/bypass_keenetic)
- В форке добавлены веб-интерфейс установки ключей и мостов, выбор маршрутизации Telegram через локальный VPN/прокси, поддержка VLESS, VLESS 2, Shadowsocks, Trojan и Vmess, а также обновлённое управление через Telegram-бота

*Полезные ссылки*
- *Fork by NetworK* [@znetworkx](https://github.com/znetworkx/bypass_keenetic)
- *Основной репозиторий* [@tas-unn](https://github.com/tas-unn/bypass_keenetic)
- *Группа в Telegram* [@bypass_keenetic](https://t.me/bypass_keenetic)
- *Тема на форуме* [keenetic](https://forum.keenetic.com/topic/14672-%D0%BE%D0%B1%D1%85%D0%BE%D0%B4%D0%B0-%D0%B1%D0%BB%D0%BE%D0%BA%D0%B8%D1%80%D0%BE%D0%B2%D0%BE%D0%BA-%D0%BC%D0%BD%D0%BE%D0%B3%D0%BE-%D0%BD%D0%B5-%D0%B1%D1%8B%D0%B2%D0%B0%D0%B5%D1%82/)
- *Полное описание и wiki* [znetworkx wiki](https://github.com/znetworkx/bypass_keenetic/wiki)
- *Где брать ключи* - команда /keys_free
- *Проверка обновлений* - команда /check_update

*Быстрый bootstrap после Entware*
- Если Entware уже установлен и `/opt` готов, можно запустить bootstrap одной SSH-командой и продолжить первичную настройку уже через браузер
- Команда: `sh -c 'export PATH=/opt/bin:/opt/sbin:$PATH; OPKG="$(command -v opkg || echo /opt/bin/opkg)"; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; if [ ! -x "$CURL_BIN" ]; then "$OPKG" update && "$OPKG" install curl ca-bundle || exit 1; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; fi; "$CURL_BIN" -fsSL https://raw.githubusercontent.com/andruwko73/bypass_keenetic/main/bootstrap/install.sh | sh'`
- После запуска откроется страница первичной настройки на `http://192.168.1.1:8080/`, где нужно указать BotFather token, username, app api id и app api hash. Страница доступна только из локальной сети.
- Bootstrap создаёт backup на роутере и rollback-скрипт в `/opt/root/bypass-last-rollback.sh`

*Шаблоны списков*
- В форке есть шаблон [vless-2.txt](https://github.com/andruwko73/bypass_keenetic/blob/main/vless-2.txt) для второго маршрута VLESS под GitHub, Copilot и связанную инфраструктуру VS Code/Microsoft

*Поддержать проект*
- *znetworkx aka NetworK*
- `4817760309908527` СБЕР VISA
- *tas-unn aka Masterland*
- `2204120100988217` КАРТА МИР
