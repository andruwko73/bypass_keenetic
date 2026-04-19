<a href="https://t.me/bypass_keenetic">![Telegram](https://img.shields.io/badge/bypass_keenetic--black?style=social&logo=telegram&logoColor=blue)</a>

## Об этом форке
Это форк проекта `keenetic-dev/bypass_keenetic_dev`.
- поддержка на [форуме](https://forum.keenetic.com/topic/14672-%D0%BE%D0%B1%D1%85%D0%BE%D0%B4%D0%B0-%D0%B1%D0%BB%D0%BE%D0%BA%D0%B8%D1%80%D0%BE%D0%B2%D0%BE%D0%BA-%D0%BC%D0%BD%D0%BE%D0%B3%D0%BE-%D0%BD%D0%B5-%D0%B1%D1%8B%D0%B2%D0%B0%D0%B5%D1%82) и [чате телеграм](https://t.me/bypass_keenetic)
- [Полное описание читайте в оригинальной вики](https://github.com/znetworkx/bypass_keenetic/wiki)

В текущем форке добавлены:
- веб-интерфейс установки ключей и мостов
- выбор маршрутизации Telegram через локальный VPN/прокси
- поддержка VLESS вместе с Shadowsocks, Trojan и Vmess
- поддержка двух отдельных маршрутов VLESS с разными ключами и списками сайтов
- обновления управления через Telegram-бота
- управление через телеграм бот
- удобное обновление ключей и списка адресов
- трафик vpn идет только к тем сайтам, что указаны в списках, вы спокойно можете использовать госуслуги, интернет-банки
- дальнейшее обновление одним кликом

## Установка (~30-60 минут с нуля)
- [Установка Entware](https://github.com/znetworkx/bypass_keenetic/wiki/Install-Entware-and-Preparation)

## Быстрый bootstrap после Entware
Если Entware уже установлен и `/opt` готов, достаточно один раз зайти на роутер по SSH любым клиентом, например PuTTY, и запустить bootstrap-команду. Дальше интерактивная первичная настройка продолжится уже через браузер на странице роутера, без ручной загрузки файлов через PuTTY.

Интерактивный запуск:

```sh
sh -c 'export PATH=/opt/bin:/opt/sbin:$PATH; OPKG="$(command -v opkg || echo /opt/bin/opkg)"; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; if [ ! -x "$CURL_BIN" ]; then "$OPKG" update && "$OPKG" install curl ca-bundle || exit 1; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; fi; "$CURL_BIN" -fsSL https://raw.githubusercontent.com/andruwko73/bypass_keenetic/main/bootstrap/install.sh | sh'
```

После этого откроется страница первичной настройки на `http://192.168.1.1:8080/`, где пользователь введёт BotFather token, username, app api id и app api hash. Затем installer сохранит `bot_config.py` и запустит основной бот.

Перед заменой live-файлов bootstrap создаёт локальный backup на роутере и генерирует rollback-скрипт в `/opt/root/bypass-last-rollback.sh`.

Если `bot_config.py` отсутствует, сервис бота автоматически запускает installer вместо основного Telegram-бота. После сохранения настроек installer сам переключает роутер обратно на основной сервис.

Ограничение: подготовку накопителя и установку Entware этот bootstrap не отменяет, потому что на Keenetic Entware живёт в `/opt` и обычно требует внешнее хранилище.

## Шаблоны списков
- [vless-2.txt](vless-2.txt) — готовый шаблон списка доменов для второго маршрута VLESS, собранный под GitHub Copilot, GitHub и связанную инфраструктуру VS Code/Microsoft.
