<a href="https://forum.keenetic.com/topic/14672-%D0%BE%D0%B1%D1%85%D0%BE%D0%B4%D0%B0-%D0%B1%D0%BB%D0%BE%D0%BA%D0%B8%D1%80%D0%BE%D0%B2%D0%BE%D0%BA-%D0%BC%D0%BD%D0%BE%D0%B3%D0%BE-%D0%BD%D0%B5-%D0%B1%D1%8B%D0%B2%D0%B0%D0%B5%D1%82">![Forum](https://img.shields.io/badge/forum-keenetic-blue?style=social&logo=discourse)</a>

## Об этой ветке

**Web-only версия** — управление обходом блокировок на роутерах Keenetic **через веб-интерфейс**, без Telegram-бота.

Основана на форке [andruwko73/bypass_keenetic](https://github.com/andruwko73/bypass_keenetic), который является форком проекта `keenetic-dev/bypass_keenetic_dev`.
- Обсуждение на [форуме Keenetic](https://forum.keenetic.com/topic/14672-%D0%BE%D0%B1%D1%85%D0%BE%D0%B4%D0%B0-%D0%B1%D0%BB%D0%BE%D0%BA%D0%B8%D1%80%D0%BE%D0%B2%D0%BE%D0%BA-%D0%BC%D0%BD%D0%BE%D0%B3%D0%BE-%D0%BD%D0%B5-%D0%B1%D1%8B%D0%B2%D0%B0%D0%B5%D1%82)
- [Оригинальная вики](https://github.com/znetworkx/bypass_keenetic/wiki)

Возможности:
- веб-интерфейс для управления прокси и ключами (`http://192.168.1.1:8080/`)
- поддержка VLESS (2 маршрута), Vmess, Shadowsocks, Trojan
- пул ключей с автоматической проверкой и авто-фейловером (по доступности YouTube)
- subscription-ссылки для массового импорта ключей
- JSON API `/api/status` для мониторинга
- редактирование списков обхода по протоколам
- обновление одной кнопкой из трёх веток GitHub

## Установка (~30-60 минут с нуля)
- [Установка Entware](https://github.com/znetworkx/bypass_keenetic/wiki/Install-Entware-and-Preparation)
- Актуальный архив Entware для Keenetic на `aarch64`: [aarch64-installer.tar.gz](https://bin.entware.net/aarch64-k3.10/installer/aarch64-installer.tar.gz)
- Актуальный архив Entware для Keenetic на `mipsel`: [mipsel-installer.tar.gz](https://bin.entware.net/mipselsf-k3.4/installer/mipsel-installer.tar.gz)

## Быстрый bootstrap после Entware

Если Entware уже установлен и `/opt` готов, запустите на роутере по SSH:

```sh
sh -c 'export PATH=/opt/bin:/opt/sbin:$PATH; OPKG="$(command -v opkg || echo /opt/bin/opkg)"; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; if [ ! -x "$CURL_BIN" ]; then "$OPKG" update && "$OPKG" install curl ca-bundle || exit 1; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; fi; "$CURL_BIN" -fsSL https://raw.githubusercontent.com/andruwko73/bypass_keenetic/feature/without-telegram-bot/script.sh | sh -s -- -install'
```

После завершения установки откройте в браузере `http://192.168.1.1:8080/` — веб-интерфейс будет готов к работе. Для первоначальной настройки потребуется отредактировать `bot_config.py` через SSH или веб-интерфейс.

Перед заменой live-файлов `script.sh` создаёт локальный backup на роутере в `/opt/root/backup-*`.

Ограничение: подготовку накопителя и установку Entware этот скрипт не отменяет.

## Шаблоны списков
- [vless.txt](vless.txt) — готовый шаблон списка доменов для первого маршрута VLESS: GitHub Copilot, GitHub, инфраструктура VS Code/Microsoft, расширенный набор адресов Telegram и связанная инфраструктура.
- [vless-2.txt](vless-2.txt) — готовый шаблон списка доменов для второго маршрута VLESS: YouTube.

## Как работает веб-интерфейс на 192.168.1.1:8080

После установки `web_bot.py` поднимает HTTP-сервер на роутере. Вся настройка и управление — через браузер.

Что доступно на странице:
- **Статус** — индикаторы доступности YouTube через каждый протокол, состояние процессов (Shadowsocks, Xray/V2Ray, Trojan, DNS-сервисы)
- **Ключи** — сохранение ключей Vless 1, Vless 2, Vmess, Trojan и Shadowsocks с автоматической проверкой
- **Пул ключей** — subscription-ссылки для массового импорта, авто-фейловер при недоступности YouTube
- **Списки обхода** — редактирование списков доменов по протоколам
- **DNS Override** — включение/выключение принудительного DNS через Keenetic
- **Обновление** — три кнопки:
  - *Переустановить из форка без сброса* — обновление из ветки `main`
  - *Переустановка (ветка independent)* — обновление из `feature/independent-rework`
  - *Переустановка (без Telegram бота)* — обновление из этой же ветки `feature/without-telegram-bot`
- **Перезапуск сервисов**, **удаление компонентов**, **перезагрузка роутера**

Типовой сценарий работы:
1. Откройте `http://192.168.1.1:8080/` в браузере из локальной сети.
2. Добавьте ключи через subscription-ссылку или вручную в карточки протоколов.
3. Выберите активный режим кнопкой **Режим**.
4. При необходимости отредактируйте списки обхода.
5. Убедитесь, что в блоке статуса горят зелёные индикаторы YouTube.

> **Примечание:** При обновлении из веток `main` или `feature/independent-rework` их `script.sh` может скачать Telegram-версию (`bot.py`). `web_bot.py` автоматически удаляет `bot.py` и Telegram-сервисы после завершения обновления, сохраняя web-only режим.
