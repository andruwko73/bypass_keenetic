<a href="https://t.me/bypass_keenetic">![Telegram](https://img.shields.io/badge/bypass_keenetic--black?style=social&logo=telegram&logoColor=blue)</a>

# bypass_keenetic

Управление обходом блокировок на роутерах Keenetic через веб-интерфейс и Telegram.

[Установка](#установка) · [Использование](docs/user-guide.md) · [Обновление и откат](#обновление-и-откат) · [История изменений](CHANGELOG.md)

## Возможности

- Два независимых профиля VLESS, а также VMess, Trojan, Hysteria2 и Shadowsocks.
- Ключи и подписки, отдельные списки обхода для каждого протокола.
- Проверки Telegram, YouTube и дополнительных сервисов, включая ChatGPT/Codex.
- Автоматический подбор ключа при подтверждённом отказе назначенных сервисов; смена без общего перезапуска.
- Звонки Telegram, WhatsApp и Discord через выбранный протокол.
- Веб-интерфейс для ПК и телефона: статус, ключи, списки, темы и собственный фон.
- Telegram-бот в простом и сложном режимах; режим **Web only** без бота.
- Обновление из GitHub и откат из сохранённой копии.

Подробности проверок, подписок, DNS и маршрутизации — в [руководстве](docs/user-guide.md).
Доступность сервиса зависит от выбранного ключа и ограничений самого сервиса.

## Установка

Проверено на **Keenetic Giga**. Для других моделей учитывайте архитектуру и доступность Entware; поддержка каждой модели отдельно не заявляется.

1. [Подготовьте Entware](https://github.com/znetworkx/bypass_keenetic/wiki/Install-Entware-and-Preparation), доступный в `/opt`. На поддерживаемых моделях его можно разместить во внутренней памяти; USB-накопитель для работы программы не обязателен.
2. Подключитесь к Entware по SSH и выполните команду ниже.
3. Откройте `http://192.168.1.1:8080/` и завершите первичную настройку. Это адрес по умолчанию: при другой LAN-сети используйте адрес своего роутера.

<details>
<summary>Команда чистой установки из GitHub main</summary>

```sh
sh -c 'set -eu; export PATH=/opt/bin:/opt/sbin:$PATH; OPKG="$(command -v opkg || echo /opt/bin/opkg)"; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; if [ ! -x "$CURL_BIN" ]; then "$OPKG" update && "$OPKG" install curl ca-bundle || exit 1; CURL_BIN="$(command -v curl || echo /opt/bin/curl)"; fi; TMP="/tmp/bypass-bootstrap-install.$$"; rm -rf "$TMP"; mkdir -p "$TMP"; trap "rm -rf \"$TMP\"" EXIT INT TERM; if ! "$CURL_BIN" -fsSL --connect-timeout 12 --max-time 45 -o "$TMP/install.sh" https://raw.githubusercontent.com/andruwko73/bypass_keenetic/main/bootstrap/install.sh; then "$CURL_BIN" -fsSL --connect-timeout 12 --max-time 90 -o "$TMP/repo.tar.gz" https://codeload.github.com/andruwko73/bypass_keenetic/tar.gz/refs/heads/main && tar -xzf "$TMP/repo.tar.gz" -C "$TMP" && cp "$TMP"/*/bootstrap/install.sh "$TMP/install.sh"; fi; [ -s "$TMP/install.sh" ] || exit 1; sh "$TMP/install.sh"'
```

Команда устанавливает необходимый curl и запускает bootstrap. Если raw.githubusercontent.com недоступен, используется GitHub archive через codeload.github.com. Если недоступны оба адреса, потребуется временный доступ к GitHub или ручная загрузка bootstrap/install.sh.

</details>

Для Telegram-бота укажите токен BotFather и Telegram username. Если бот не нужен, выберите **Запустить режим Web only**. Можно задать пароль веб-интерфейса; без него доступ ограничен локальными/private адресами. Не публикуйте токены, пароли и ключи.

## Использование

В панели доступны **Статус**, **Ключи** и **Списки**. В простом режиме расширенный пул скрыт; в сложном и Web only доступны пулы, подписки и дополнительные проверки.

Проверка пула использует временный Xray и не подменяет основной ключ. Сервисы и пользовательские адреса назначаются нужному протоколу через списки обхода.

- [Панель, списки и маршрутизация](docs/user-guide.md#веб-интерфейс)
- [Telegram-бот](docs/user-guide.md#telegram-бот)
- [Пулы и подписки](docs/user-guide.md#пул-ключей)
- [Скриншоты интерфейса](docs/user-guide.md#скриншоты)

<a href="docs/screenshots/web-ui-status.png"><img src="docs/screenshots/web-ui-status.png" alt="Статус программы и роутера" width="720"></a>

## Обновление и откат

Обновляйте программу из веб-панели или Telegram-бота. Обновление из `main` сохраняет настройки, активные ключи, пулы, подписки, проверки, списки обхода и выбранный режим.

Откат доступен из панели или бота и восстанавливает снимок перед последним обновлением, включая прежние настройки и подписки. Изменения, сделанные после создания снимка, в него не входят. Для аварийного отката после обновления предусмотрен `/opt/root/bypass-last-update-rollback.sh`; первоначальная bootstrap-копия использует `/opt/root/bypass-last-rollback.sh`.

Работающая установка обновляется штатным действием, без повторной чистой установки. [Переход со старых веток](docs/user-guide.md#обновление-со-старых-веток).

## Если возникла проблема

Проверьте статус программы и сервисов в панели, затем историю событий. При обращении укажите модель Keenetic, версии KeeneticOS и программы, действие и время ошибки. Не прикладывайте токены, полные ключи и конфигурации с паролями.

[Руководство](docs/user-guide.md) · [Сообщить об ошибке](https://github.com/andruwko73/bypass_keenetic/issues) · [Telegram проекта](https://t.me/bypass_keenetic)
