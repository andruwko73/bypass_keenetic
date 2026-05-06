<a href="https://forum.keenetic.com/topic/14672-%D0%BE%D0%B1%D1%85%D0%BE%D0%B4%D0%B0-%D0%B1%D0%BB%D0%BE%D0%BA%D0%B8%D1%80%D0%BE%D0%B2%D0%BE%D0%BA-%D0%BC%D0%BD%D0%BE%D0%B3%D0%BE-%D0%BD%D0%B5-%D0%B1%D1%8B%D0%B2%D0%B0%D0%B5%D1%82">![Forum](https://img.shields.io/badge/forum-keenetic-blue?style=social&logo=discourse)</a>

> **Проверено и работает на роутере Keenetic Giga на последней версии KeeneticOS.**

## О ветке

`codex/web-only-v1` — версия `bypass_keenetic` без Telegram-бота. Управление выполняется только через локальный веб-интерфейс роутера на `http://192.168.1.1:8080/`.

Ветка использует те же локальные настройки, ключи, пулы и списки обхода, что и версии `codex/main-v1` и `codex/independent-v1`, поэтому между версиями можно переходить без очистки пользовательских данных.

Возможности:
- веб-интерфейс с разделами **Статус**, **Ключи**, **Списки**;
- Vless 1, Vless 2, Vmess, Trojan и Shadowsocks;
- пул ключей для каждого протокола;
- загрузка subscription;
- проверка Telegram API, YouTube и дополнительных сервисов через выбранный прокси;
- пресеты проверок: ChatGPT/OpenAI/Codex, Claude, Gemini, Copilot, Perplexity, Grok, DeepSeek, Discord, Meta AI, Instagram, Facebook;
- кнопка **Добавить в список обхода** переносит домены выбранных дополнительных проверок в список обхода текущего протокола; кнопка **Добавить в список** добавляет готовые наборы Telegram, YouTube, Instagram/Meta, Discord, TikTok, X/Twitter или все сервисы сразу;
- переустановка в `codex/main-v1`, `codex/independent-v1` и обратно в `codex/web-only-v1` с сохранением данных.

## Установка

Сначала установите Entware:
- [инструкция Entware для Keenetic](https://github.com/znetworkx/bypass_keenetic/wiki/Install-Entware-and-Preparation)
- `aarch64`: [aarch64-installer.tar.gz](https://bin.entware.net/aarch64-k3.10/installer/aarch64-installer.tar.gz)
- `mipsel`: [mipsel-installer.tar.gz](https://bin.entware.net/mipselsf-k3.4/installer/mipsel-installer.tar.gz)

После Entware подключитесь к роутеру по SSH и выполните:

```sh
sh -c 'export PATH=/opt/bin:/opt/sbin:$PATH; OPKG="$(command -v opkg || echo /opt/bin/opkg)"; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; if [ ! -x "$CURL_BIN" ]; then "$OPKG" update && "$OPKG" install curl ca-bundle || exit 1; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; fi; "$CURL_BIN" -fsSL https://raw.githubusercontent.com/andruwko73/bypass_keenetic/codex/web-only-v1/bootstrap/install.sh | sh'
```

После установки откройте `http://192.168.1.1:8080/`. Telegram-бот и installer первичной настройки Telegram в этой ветке не запускаются.

Bootstrap перед заменой файлов создает backup и rollback-скрипт в `/opt/root/bypass-last-rollback.sh`.

## Веб-интерфейс

Разделы:
- **Статус** — состояние связи, активный режим, быстрый старт, переустановка и сервисные команды;
- **Ключи** — активный ключ, пул ключей, subscription и проверки;
- **Списки** — редактирование списков обхода по каждому протоколу.

Интерфейс адаптирован под ПК и телефон. На телефоне нижнее меню остается доступным, а длинная прокрутка ограничена таблицей пула ключей.

Опасные действия требуют подтверждения: удаление компонентов, перезагрузка роутера, DNS Override, очистка пула и удаление пользовательских проверок.

## Пул ключей и проверки

Пул ключей хранится в `/opt/etc/bot/key_pools.json`, кеш проверок — в `/opt/etc/bot/key_probe_cache.json`, пользовательские проверки — в `/opt/etc/bot/custom_checks.json`.

Проверка пула не переключает основной активный ключ и не разрывает текущее подключение. Активный ключ текущего режима пропускается в фоновой проверке пула, его состояние берется из живого подключения. Для остальных ключей используется временный `xray` с отдельными SOCKS-портами. Результат каждого ключа сохраняется сразу, а временные процессы и конфиги удаляются после пачки проверок.

Если свободной памяти на роутере становится мало, фоновая проверка останавливается, чтобы не подвесить устройство.

## Переустановка

Из веб-интерфейса доступны переходы:
- **Переустановить из форка без сброса** — `codex/main-v1`;
- **Переустановка (ветка independent)** — `codex/independent-v1` с Telegram-ботом;
- **Переустановка (без Telegram бота)** — текущая web-only ветка.

При переходах сохраняются активные ключи, пул ключей, пользовательские проверки, списки обхода и базовые настройки веб-интерфейса.

## Безопасность данных

Реальные ключи, IP-адреса личных серверов, пароли, токены и локальные настройки должны оставаться только на роутере. В репозиторий не добавляются `bot_config.py`, `.env`, локальные дампы роутера, временные `xray`-конфиги, пулы ключей и кеши проверок.

Скриншоты ниже сделаны с демонстрационными данными: активный ключ скрыт, идентификаторы ключей в пуле не показываются, списки обхода заменены безопасными примерами.

## Списки обхода

- [vless.txt](vless.txt) — шаблон для первого маршрута VLESS: Telegram API, дата-центры Telegram, OpenAI/ChatGPT/Codex, GitHub, Copilot и связанные сервисы.
- [vless-2.txt](vless-2.txt) — шаблон для второго маршрута VLESS: YouTube.

## Скриншоты

Статус и сервис:

<a href="docs/screenshots/web-ui-status.png">
  <img src="docs/screenshots/web-ui-status.png" alt="Статус web-only" width="520">
</a>

Активный ключ:

<a href="docs/screenshots/web-ui-key.png">
  <img src="docs/screenshots/web-ui-key.png" alt="Активный ключ web-only" width="520">
</a>

Пул ключей:

<a href="docs/screenshots/web-ui-pool.png">
  <img src="docs/screenshots/web-ui-pool.png" alt="Пул ключей web-only" width="520">
</a>

Subscription:

<a href="docs/screenshots/web-ui-subscription.png">
  <img src="docs/screenshots/web-ui-subscription.png" alt="Subscription web-only" width="520">
</a>

Проверки доступности:

<a href="docs/screenshots/web-ui-check.png">
  <img src="docs/screenshots/web-ui-check.png" alt="Проверки доступности web-only" width="520">
</a>

Списки обхода:

<a href="docs/screenshots/web-ui-lists.png">
  <img src="docs/screenshots/web-ui-lists.png" alt="Списки обхода web-only" width="520">
</a>
