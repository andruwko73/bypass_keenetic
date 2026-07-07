<a href="https://t.me/bypass_keenetic">![Telegram](https://img.shields.io/badge/bypass_keenetic--black?style=social&logo=telegram&logoColor=blue)</a>

# bypass_keenetic

Локальная панель управления обходом блокировок на роутерах Keenetic.

> Проверено на Keenetic Giga с актуальной KeeneticOS.

## Возможности

- Веб-интерфейс на `http://192.168.1.1:8080/` для ПК и телефона.
- Разделы **Статус**, **Ключи**, **Списки**.
- Telegram-бот для режимов **Простой** и **Сложный**.
- Поддержка двух протоколов `Vless`, протоколов `Vmess`, `Trojan`, `Shadowsocks`.
- Пул ключей для каждого протокола: ручное добавление, удаление, применение, импорт подписки.
- Проверка ключей через Telegram API, YouTube и дополнительные сервисы: ChatGPT/OpenAI/Codex, Claude, Gemini, Copilot, Perplexity, Grok, DeepSeek, Discord, Meta AI/Instagram/Facebook.
- Прогрев YouTube для ускорения загрузки видео.
- Автоматический обход realtime-звонков Telegram, WhatsApp и Discord: программа определяет активных клиентов, временно запоминает UDP-адреса звонка и отправляет их через TPROXY-порт выбранного протокола.
- Диагностика роутера в блоке **Статус**: память, нагрузка, состояние DNS, время последнего обновления `ipset` и количество записей в наборах обхода.

## Установка

Сначала установите Entware на накопитель роутера:
- [инструкция Entware для Keenetic](https://github.com/znetworkx/bypass_keenetic/wiki/Install-Entware-and-Preparation)
- `aarch64`: [aarch64-installer.tar.gz](https://bin.entware.net/aarch64-k3.10/installer/aarch64-installer.tar.gz)
- `mipsel`: [mipsel-installer.tar.gz](https://bin.entware.net/mipselsf-k3.4/installer/mipsel-installer.tar.gz)

Важно: бот и bootstrap не заменяют подготовку накопителя и установку Entware. На Keenetic Entware живёт в `/opt` и обычно требует внешнее хранилище.

После Entware подключитесь к роутеру по SSH и выполните:

```sh
sh -c 'set -eu; export PATH=/opt/bin:/opt/sbin:$PATH; OPKG="$(command -v opkg || echo /opt/bin/opkg)"; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; if [ ! -x "$CURL_BIN" ]; then "$OPKG" update && "$OPKG" install curl ca-bundle || exit 1; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; fi; TMP="/tmp/bypass-bootstrap-install.$$"; rm -rf "$TMP"; mkdir -p "$TMP"; trap "rm -rf \"$TMP\"" EXIT INT TERM; if ! "$CURL_BIN" -fsSL --connect-timeout 12 --max-time 45 -o "$TMP/install.sh" https://raw.githubusercontent.com/andruwko73/bypass_keenetic/main/bootstrap/install.sh; then "$CURL_BIN" -fsSL --connect-timeout 12 --max-time 90 -o "$TMP/repo.tar.gz" https://codeload.github.com/andruwko73/bypass_keenetic/tar.gz/refs/heads/main && tar -xzf "$TMP/repo.tar.gz" -C "$TMP" && cp "$TMP"/*/bootstrap/install.sh "$TMP/install.sh"; fi; [ -s "$TMP/install.sh" ] || exit 1; sh "$TMP/install.sh"'
```

Команда выше является актуальной командой чистой установки из GitHub `main`. Она ставит минимальный `curl`, скачивает `bootstrap/install.sh`, затем bootstrap скачивает основной `script.sh`, веб-установщик, Telegram-бота и все runtime-модули.

Команда сначала пробует `raw.githubusercontent.com`, затем GitHub archive через `codeload.github.com`. Это важно для чистой установки: fallback не требует уже установленного ключа или локального SOCKS. Если с чистого роутера недоступны и raw, и codeload, нужен временный прямой доступ к GitHub или ручная загрузка `bootstrap/install.sh`.

## Структура репозитория

В корне оставлены только файлы, которые нужны пользователю и совместимости установки: `README.md`, `CHANGELOG.md`, `LICENSE`, `version.md`, `script.sh` и `bootstrap/install.sh`. Основные файлы программы, роутерные скрипты, конфиги и статические ассеты лежат в папке `app/`. Установщик и обновлятор сами используют этот путь, поэтому команда чистой установки остаётся прежней.

Прогрев YouTube выполняется отдельным коротким процессом для ускорения загрузки видео.

При первой чистой установке откроется первичная настройка на `http://192.168.1.1:8080/`.

Нужно указать:
- BotFather token;
- Telegram username;
- при желании пароль для веб-интерфейса.

Если Telegram-бот не нужен, нажмите **Запустить режим Web only**. Пароль веб-интерфейса не обязателен: если его не задать, доступ останется только с локальных/private адресов.

Bootstrap перед заменой файлов создает backup и rollback-скрипт в `/opt/root/bypass-last-rollback.sh`.

## Обновление со старых веток

Переход на новую ветку `main` должен быть плавным с любой старой установленной версии:
- `main`;
- `codex/main`;
- `codex/main-v1`;
- `codex/independent-v1`;
- `codex/web-only-v1`;
- `feature/independent-rework`;
- `feature/web-only`;
- `feature/without-telegram-bot`.

В старом Telegram-боте или веб-интерфейсе можно нажать обновление/переустановку из текущей ветки. Старое имя ветки будет вести на новый код `main`, после чего установленная программа уже будет обновляться из `main`.

При обновлении сохраняются:
- `/opt/etc/bot_config.py` или `/opt/etc/bot/bot_config.py`;
- активные ключи;
- пул ключей;
- пользовательские проверки;
- списки обхода;
- выбранный режим работы программы.

Устаревшие артефакты старых вариантов очищаются: отдельный `web_bot.py`, старый web-only init-скрипт, tor/vpn пути и лишние runtime-файлы. Остаются только поддерживаемые протоколы: два `Vless`, `Vmess`, `Trojan`, `Shadowsocks`.

## Веб-интерфейс

**Статус**

Показывает состояние роутера, ключей, быстрый старт и сервисные команды. В режимах с ботом дополнительно отображаются Telegram API и активный режим Telegram-бота; в **Web only** эти элементы скрыты.

В блоке роутера DNS-часть показывает текущий режим и состояние `ipset`. Кнопки **DNS Override ВКЛ** и **DNS Override ВЫКЛ** явно переключают между штатным DNS Keenetic через `ndnproxy` и основным DNS через `dnsmasq`: в режиме `dnsmasq` наборы `ipset` наполняются динамически по route-файлам, а в режиме `ndnproxy` домены заранее резолвятся скриптом `/opt/bin/unblock_ipset.sh`. Обновление программы и перезагрузка сервисов не меняют DNS Override скрыто; плановый refresh поддерживает актуальность наборов, IPv6/UDP fallback и удаление пересечений между route-файлами.

UDP/443 обрабатывается по содержимому списков обхода: YouTube/QUIC-наборы создаются для того протокола, где сейчас находится YouTube, а Telegram остаётся на своём маршруте даже при совместном списке. Базовую политику можно поменять в `bot_config.py` через `udp_quic_block_*_enabled`, `youtube_quic_policy` и `telegram_udp_policy`.

Realtime-звонки Telegram, WhatsApp и Discord работают без отдельной кнопки: программа определяет активных клиентов, временно запоминает связанные UDP-медиа-адреса и отправляет их через TPROXY-порт текущего протокола сервиса. Таймауты можно поменять параметрами `telegram_call_learning_client_timeout_seconds` и `telegram_call_learning_address_timeout_seconds` в `bot_config.py`.

**Ключи**

Позволяет редактировать активный ключ, переключать протоколы, работать с пулом ключей и запускать проверки. В простом режиме пул ключей и расширенные проверки скрыты.

**Списки**

Редактирование списков обхода для каждого протокола. Готовые наборы можно добавлять кнопками: Telegram, YouTube, ChatGPT/Codex, Claude, Gemini, Copilot, Perplexity, Grok, DeepSeek, Discord, Chrome Remote Desktop, Meta AI/Instagram/Facebook или все сервисы сразу.

## Telegram-бот

Telegram-бот использует нижнюю клавиатуру и работает в режимах **Простой** и **Сложный**.

Основные разделы:
- управление активным протоколом и ключами;
- списки обхода;
- пул ключей в сложном режиме;
- сервисные команды;
- обновление до последнего релиза с подтверждением.

Путь к пулу: **Ключи** -> **Пул ключей**. Кнопки ключей содержат короткий код протокола, поэтому старая кнопка из другого пула не применит ключ к неверному протоколу.

## Пул ключей

Пул хранится локально на роутере:
- `/opt/etc/bot/key_pools.json`;
- `/opt/etc/bot/key_probe_cache.json`;
- `/opt/etc/bot/custom_checks.json`.

Проверка пула не переключает основной активный ключ и не разрывает текущее подключение. Для проверки остальных ключей запускается временный `xray` с отдельными SOCKS-портами. Результаты сохраняются сразу после проверки каждого ключа. Полная проверка проходит все ключи из всех пулов; при высокой нагрузке CPU или нехватке памяти она замедляется либо ставится на паузу, чтобы не забивать роутер.

Активный ключ автоматически добавляется в свой пул, если его там нет. Это защищает от ситуации, когда текущий рабочий ключ пропадает из интерфейса после импорта или ручной чистки пула. Если один и тот же набор Vless-ключей используется и для `Vless 1`, и для `Vless 2`, их можно хранить одинаковыми списками; программа не печатает ключи в диагностике, не возвращает их в JSON-ответах действий и сравнивает их по внутренним идентификаторам.

При нехватке памяти проверка останавливается и может быть продолжена позже.

## Безопасность данных

Реальные ключи, токены Telegram, пароли, локальные пулы и кеши проверок должны оставаться только на роутере. Проверки Telegram и YouTube считают HTTP 4xx ответом отказа сервиса, а не подтверждением доступа. JSON API пула не отдаёт полные ключи даже при ручном `include_keys=1`; полные значения остаются только в серверной веб-форме, где их можно выделять и копировать.

В репозиторий не добавляются:
- `bot_config.py`;
- `.env`;
- дампы роутера;
- временные `xray`-конфиги;
- файлы с живыми прокси-ключами.

## Скриншоты

Скриншоты веб-интерфейса сняты в режиме **Сложный**. Поля и строки с ключами замаскированы.

Страница первичной настройки:

<a href="docs/screenshots/installer-setup.png">
  <img src="docs/screenshots/installer-setup.png" alt="Первичная настройка" width="420">
</a>

Статус и сервис, версия для ПК:

<a href="docs/screenshots/web-ui-status.png">
  <img src="docs/screenshots/web-ui-status.png" alt="Статус и сервис для ПК" width="720">
</a>

Статус и сервис, версия для телефона:

<a href="docs/screenshots/web-ui-status-mobile.png">
  <img src="docs/screenshots/web-ui-status-mobile.png" alt="Статус и сервис для телефона" width="320">
</a>

Активный ключ:

<a href="docs/screenshots/web-ui-key.png">
  <img src="docs/screenshots/web-ui-key.png" alt="Активный ключ" width="520">
</a>

Пул ключей:

<a href="docs/screenshots/web-ui-pool.png">
  <img src="docs/screenshots/web-ui-pool.png" alt="Пул ключей" width="520">
</a>

Subscription:

<a href="docs/screenshots/web-ui-subscription.png">
  <img src="docs/screenshots/web-ui-subscription.png" alt="Subscription" width="520">
</a>

Проверки доступности:

<a href="docs/screenshots/web-ui-check.png">
  <img src="docs/screenshots/web-ui-check.png" alt="Проверки доступности" width="520">
</a>

Списки обхода:

<a href="docs/screenshots/web-ui-lists.png">
  <img src="docs/screenshots/web-ui-lists.png" alt="Списки обхода" width="520">
</a>
