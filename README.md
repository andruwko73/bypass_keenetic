<a href="https://t.me/bypass_keenetic">![Telegram](https://img.shields.io/badge/bypass_keenetic--black?style=social&logo=telegram&logoColor=blue)</a>

# bypass_keenetic

Локальная панель управления обходом блокировок на роутерах Keenetic.

> Проверено на Keenetic Giga с актуальной KeeneticOS.

## Что изменилось

Раньше у программы было несколько веток с разным поведением: простая версия, independent-версия с пулом ключей и web-only версия. Теперь они объединены в одну ветку `main`.

Выбор варианта работы больше не требует установки другой ветки. В веб-интерфейсе есть **режим работы программы**:
- **Простой** — интерфейс и Telegram-бот;
- **Сложный** — интерфейс с пулом ключей и Telegram-бот;
- **Web only** — интерфейс с пулом ключей без Telegram-бота.

Переход между режимами выполняется с подтверждением. Ключи, пул ключей, пользовательские проверки, списки обхода и настройки Telegram сохраняются.

## Возможности

- Веб-интерфейс на `http://192.168.1.1:8080/` для ПК и телефона.
- Разделы **Статус**, **Ключи**, **Списки**.
- Telegram-бот для режимов **Простой** и **Сложный**.
- Поддержка `Vless 1`, `Vless 2`, `Vmess`, `Trojan`, `Shadowsocks`.
- Пул ключей для каждого протокола: ручное добавление, удаление, применение, импорт subscription.
- Проверка ключей через Telegram API, YouTube и дополнительные сервисы.
- Готовые проверки: ChatGPT/OpenAI/Codex, Claude, Gemini, Copilot, Perplexity, Grok, DeepSeek, Discord, Meta AI, Instagram, Facebook.
- Добавление доменов выбранных проверок в список обхода текущего протокола.
- Подтверждение опасных действий: смена режима, обновление, удаление компонентов, DNS Override, перезагрузка роутера, очистка пула.

## Установка

Сначала установите Entware на накопитель роутера:
- [инструкция Entware для Keenetic](https://github.com/znetworkx/bypass_keenetic/wiki/Install-Entware-and-Preparation)
- `aarch64`: [aarch64-installer.tar.gz](https://bin.entware.net/aarch64-k3.10/installer/aarch64-installer.tar.gz)
- `mipsel`: [mipsel-installer.tar.gz](https://bin.entware.net/mipselsf-k3.4/installer/mipsel-installer.tar.gz)

После Entware подключитесь к роутеру по SSH и выполните:

```sh
sh -c 'export PATH=/opt/bin:/opt/sbin:$PATH; OPKG="$(command -v opkg || echo /opt/bin/opkg)"; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; if [ ! -x "$CURL_BIN" ]; then "$OPKG" update && "$OPKG" install curl ca-bundle || exit 1; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; fi; "$CURL_BIN" -fsSL https://raw.githubusercontent.com/andruwko73/bypass_keenetic/main/bootstrap/install.sh | sh'
```

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

Устаревшие артефакты старых вариантов очищаются: отдельный `web_bot.py`, старый web-only init-скрипт, tor/vpn пути и лишние runtime-файлы. Остаются только поддерживаемые протоколы: `Vless 1`, `Vless 2`, `Vmess`, `Trojan`, `Shadowsocks`.

## Веб-интерфейс

**Статус**

Показывает доступность Telegram API, активный режим прокси, количество ключей, быстрый старт и сервисные команды.

**Ключи**

Позволяет редактировать активный ключ, переключать протоколы, работать с пулом ключей и запускать проверки. В простом режиме пул ключей и расширенные проверки скрыты.

**Списки**

Редактирование списков обхода для каждого протокола. Готовые наборы можно добавлять кнопками: Telegram, YouTube, Instagram/Meta, Discord, TikTok, X/Twitter или все сервисы сразу.

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

Проверка пула не переключает основной активный ключ и не разрывает текущее подключение. Для проверки остальных ключей запускается временный `xray` с отдельными SOCKS-портами. Результаты сохраняются сразу после проверки каждого ключа.

При нехватке памяти проверка останавливается и может быть продолжена позже.

## Безопасность данных

Реальные ключи, токены Telegram, пароли, локальные пулы и кеши проверок должны оставаться только на роутере.

В репозиторий не добавляются:
- `bot_config.py`;
- `.env`;
- дампы роутера;
- временные `xray`-конфиги;
- файлы с живыми прокси-ключами.

## Скриншоты

Страница первичной настройки:

<a href="docs/screenshots/installer-setup.png">
  <img src="docs/screenshots/installer-setup.png" alt="Первичная настройка" width="420">
</a>

Статус и сервис:

<a href="docs/screenshots/web-ui-status.png">
  <img src="docs/screenshots/web-ui-status.png" alt="Статус и сервис" width="520">
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
