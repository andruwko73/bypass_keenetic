*v1.1001 (1 Aug 2026) -* main

*Разделяет текущую полную проверку и последнюю завершённую проверку ключей. Прогресс нового запуска `0 из N` больше не подменяет сохранённый результат; состояние старых версий мигрирует без сброса сводки.*

*Использует точные подписи «Записей в пулах», «С сохранённым результатом» и «Проверено ключей». Убраны неоднозначные «уникальные ключи» и «предварительная проверка»; сообщения о паузе из-за нагрузки переведены на русский.*

*Не перечитывает все строки пулов каждые 15 секунд во время полной проверки. Прогресс остаётся живым через лёгкий API, а полные данные обновляются после завершения или явного действия пользователя.*

*Удаляет подтверждённо неиспользуемые серверные рендереры, обёртки и снимки состояния. Рабочий код и устаревшие тестовые ветки уменьшены более чем на 1200 строк; UI-фикстура использует тот же лёгкий HTML и API-путь, что роутер.*

*Не добавляет новый worker, демон, зависимость, сетевую проверку или фоновый цикл. Самодостаточный чистый установщик и узкие дочерние процессы сохранены ради низкой нагрузки на роутер.*

*Проверено 238 Python-регрессиями, Ruff `F/E9`, secret scan, Python/JavaScript/Bash syntax и Playwright UI smoke во всех трёх режимах на мобильных, desktop, Full HD, 2K и 4K 16:9/16:10. Полный Ruff по-прежнему содержит только 24 осознанных `E402` загрузочного порядка `bot.py`.*

*Исключает потерю результатов при одновременной полной проверке пула и фоновой проверке активного ключа: весь цикл чтения, изменения и записи `key_probe_cache.json` теперь защищён общей межпроцессной транзакцией в оперативной памяти роутера.*

*Сохраняет тип проверки `screening`, поэтому веб-интерфейс и Telegram-бот больше не принимают лёгкую фоновую проверку за смену ключа или полный запуск. Запись выполняется атомарно через уникальный временный файл; при занятом lock программа ждёт ограниченное время и никогда не пишет кэш без защиты.*

*Отделяет историческое число ключей с сохранённым результатом от результата последнего полного запуска. Веб-карточка показывает явную строку «Последняя полная проверка», а Telegram сообщает об успешном завершении только после сохранения результатов всех уникальных ключей.*

*Ночная проверка с окном 03:00–06:00 теперь хранит состояния `running`, `paused`, `failed` и `completed`, продолжает безопасно прерванный запуск и делает не более трёх попыток с паузой. Незавершённый запуск больше не блокирует следующие попытки на весь день.*

*Защищает общий файл сводки отдельным лёгким `RLock`, чтобы обновление счётчиков и состояния последнего запуска не могли перезаписать друг друга. Новых workers, демонов, сетевых опросов или постоянной нагрузки не добавлено.*

*Проверено 237 Python-регрессиями, реальной конкуренцией отдельных процессов, Ruff, сканером секретов, Python/JavaScript/Bash syntax и браузерной матрицей режимов «Сложный», «Простой» и «Только веб» от мобильного разрешения до 4K 16:9/16:10.*

*Мигрирует сохранённую последнюю сводку пула со старыми сокращёнными названиями на актуальные полные названия сервисов. Роутер с неизменившимся размером пула больше не возвращает `Instagram / Facebo...` из `pool_summary_last.json` после обновления программы.*

*Последние результаты и счётчики проверок не сбрасываются: миграция переносит их на текущий список сервисов, обновляет текст сводки и сохраняет исправленный снимок. Если состав сервисов изменился, несовместимый старый снимок безопасно не применяется.*

*Операция линейна только по небольшому списку отображаемых сервисов, выполняется при чтении контрольной точки и не добавляет процесс, worker, проверку сети или периодическую нагрузку на роутер.*

*Добавлена регрессия, которая воспроизводит контрольную точку 1.996 с `Instagram / Facebo...`, подтверждает полное `Instagram / Facebook`, сохранение всех счётчиков и перезапись исправленного снимка.*

*Показывает в сводке «Ключи и пул» полные названия всех дополнительных сервисов. `Instagram / Facebook` больше не превращается в `Instagram / Facebo...`; длинная строка безопасно переносится внутри карточки.*

*Удаляет только устаревшее 18-символьное сокращение общего генератора сводки, который используют веб-интерфейс и Telegram-бот. Подсчёт ключей и сервисов, проверки пула, Xray, маршруты и фоновые процессы не меняются.*

*Проверено отдельной Python-регрессией полного названия и браузерной матрицей режимов «Сложный», «Простой» и «Только веб» на мобильном, Full HD, 2K и 4K с соотношениями 16:9 и 16:10.*

*Prevents a browser from retaining pre-update service artwork for up to 24 hours: every service icon URL now carries the installed application version, so an update automatically requests the matching PNG without a manual cache clear or hard reload.*

*Applies the same cache-busting rule to server-rendered pool rows, route tools, dynamically refreshed JavaScript status icons, and the Telegram topbar indicator. The existing one-day cache remains available within a version, keeping normal router and browser work unchanged.*

*Adds regressions for Python and JavaScript icon URL generation, the initial page configuration, and the absence of an unversioned CSS background URL. No Xray, route, key, probe, worker, scheduler, or polling behavior changes.*

*Replaces the mixed service badges with one professionally sourced set of twelve transparent 128×128 PNG logos used consistently by the web interface and its Telegram-managed views: Telegram, YouTube, ChatGPT, Discord, Instagram, Chrome Remote Desktop, Claude, Gemini, DeepSeek, Twitter for Grok, Perplexity, and Copilot.*

*Removes redundant Meta and Facebook image assets because the combined Instagram / Facebook preset now has one unambiguous Instagram identity; Chrome Remote Desktop uses the Chrome mark, Claude uses its product star, and Grok / X / Twitter uses the requested classic Twitter bird.*

*Keeps clean installation and in-place updates in sync with the exact PNG manifest, so new and existing routers receive the same assets without adding a process, worker, dependency, polling cycle, or runtime network request.*

*Synchronizes the Meta service route catalog with the current upstream roots `threads.com` and `circlecrewpinkcrowd.com`; existing suffix routing continues to cover the Instagram API, media, CDN, and regional subdomains without enumerating them individually.*

*Verified by 230 Python regressions, Ruff, secret scanning, Python/JavaScript/Bash syntax checks, PNG integrity checks, and Playwright UI smoke in Advanced, Simple, and Web-only modes across the maintained mobile, desktop, 2K, and 4K 16:9/16:10 viewports.*

*Prevents automatic post-update navigation to a gateway-generated 502 page: the existing interface now keeps polling the cache-busted root page, verifies the expected new version twice in succession, and reloads only after the replacement web server is stable.*

*Preserves service-scoped global-route exceptions during an individual route assignment so Meta and other permitted entries remain genuinely idempotent without changing catalog-repair behavior.*

*Makes service-route assignment idempotent: selecting the protocol that already contains the complete service list no longer rewrites route files, restarts Xray, or runs the route updater. Adding an optional service check still refreshes only the installed active keys.*

*Stops service-route and custom-check actions from launching a hidden full-pool probe; only the currently installed active keys receive a lightweight background refresh, while the explicit full-pool check remains manual.*

*Recovers the web interface when a route action is applied but its HTTP response is interrupted: the page reloads and shows the actual persisted result instead of leaving a misleading `TypeError: Failed to fetch` error.*

*Keeps the Telegram polling lifecycle indicator active while TeleBot retries an internally handled transient connection error; failover tracking and active-key recovery continue independently.*

*Verifies all 12 routable services against all five protocols, all 10 additional check presets, 230 Python tests, secret scanning, Python/JavaScript/Bash syntax, and all three web modes from mobile through 4K 16:9 and 16:10 viewports.*

*Возвращает прежний понятный верхний статус исправного Telegram-бота: «Telegram-бот работает» и «Память роутера в норме». Технический long polling остаётся внутренним подтверждением работоспособности и больше не выглядит как затянувшееся обновление.*

*Объединяет расчёт сводки пула и трактовку результата YouTube в одном лёгком модуле, чтобы веб-интерфейс и Telegram-бот не расходились по счётчикам и статусам. Удалены только недостижимые частные функции и дубли; внешние совместимые точки входа сохранены.*

*Оптимизация не добавляет процессов, workers, проверок сети или периодических задач и не меняет Xray, маршруты, ключи и кэш проверок. Расчёт сводки для типичного пула занимает доли миллисекунды на ПК и остаётся линейным по числу ключей.*

*Проверено 227 Python-регрессиями, полным линтером и сканером секретов, Python/JavaScript/Bash syntax и браузерной матрицей режимов Сложный, Простой и Web only на mobile, compact desktop, Full HD, 2K и 4K с соотношениями 16:9 и 16:10.*

*Исправляет расхождение статуса активного ключа во время проверки пула: если Telegram-бот реально получает обновления через Vless 1, веб-карточка больше не заменяет этот факт устаревшим `tg_ok=false` и не показывает ложное «Частично работает».*

*Подтверждение polling применяется к первоначальному HTML и `/api/status`, включая уже закэшированный ответ. Значок Telegram, подпись карточки и подробности остаются согласованными после обновления статуса, обновления пула и применения ключа.*

*Исправление использует лёгкий снимок назначений сервисов, не запускает проверки ключей, не меняет Xray, маршруты и кэш пула и не загружает тяжёлые модули маршрутизации в быстром цикле веб-интерфейса.*

*Проверено 227 Python-регрессиями, сканером секретов, синтаксическими проверками и браузерной матрицей режимов Сложный, Простой и Web only на mobile, compact desktop, Full HD, 2K и 4K с соотношениями 16:9 и 16:10.*

*Restores Chrome Remote Desktop session setup by routing Google's documented `74.125.247.128:3478/udp` STUN endpoint through the existing protocol-specific Xray TPROXY inbound instead of the unreliable UDP REDIRECT path.*

*Selects the TPROXY inbound from the service's actual route assignment, removes stale exact rules before every refresh, and rolls back the narrow exception if policy-rule installation fails.*

*Keeps the fix router-light: only one destination and UDP port receive exact iptables rules; TCP signaling, QUIC, YouTube, Telegram, and other service traffic retain their existing routes.*

*Separates allowed shared service-catalog addresses from real route conflicts and shows the exact address, source files, original file lines, routes, and affected services without offering automatic deletion.*

*Shows complete and partial service-route coverage as explicit matched/total counts, bounds shared-entry details to 120 rows, and keeps the existing cached worker model with no new process or dependency.*

*Verifies the new route diagnostics in all three web modes across mobile, desktop, 2K, and 4K viewports while preserving the existing update, pool, bot, and clean-install behavior.*

*Restores the latest pool-check counters immediately after keys are removed by keeping the light cache reader on schema 9 with compatibility for schemas 6–9.*

*Protects the last complete pool summary from transient partial or empty snapshots while still showing recomputed results for the current pool size.*

*Uses a bounded, non-sensitive route-assignment snapshot from the existing web workers so Telegram, YouTube, and custom-service statuses follow their actual protocols even when the global proxy mode is disabled.*

*Preserves automatic rollback when the update watchdog sends TERM on POSIX shells by routing soft signals through the existing EXIT recovery trap.*

*Makes updates lighter and safer without a new worker: live output is byte-bounded and debounced, quiet redirected stages count status-file activity, and stalled process groups receive a recovery grace period before forced termination.*

*Keeps the six-hour dnsmasq/ipset full refresh deadline anchored to the last real refresh: unchanged hourly checks no longer postpone it, and legacy skipped state is repaired on the next due run.*

*Убирает повтор «API отвечает» из нормального статуса работающего Telegram-бота: под заголовком остаётся только информация о памяти роутера.*

*Сразу после полной проверки пула сохраняет итоговую сводку всех строк, поэтому главная страница больше не показывает устаревшее число проверенных ключей.*

*Делает прозрачность блоков и кнопок одинаковой на всех вкладках при использовании пользовательского фона и сохраняет читаемость меню оформления.*

*Документирует темы и пользовательский фон, добавляет актуальные обезличенные скриншоты веб-интерфейса с текущего роутера.*

*В карточке обновления время «В среднем» теперь отображается отдельной строкой под «Прошло».*

*Keeps pool rows compact: they show the latest result and its time, while the source of the result remains available internally and in technical logs.*

*Keeps every YouTube address exclusively on its configured route, adds a guarded small CDN-quality preference, and makes key failover history clearer.*

*Uses only two or three freshly approved `i.ytimg.com` addresses for an optional DNS preference; normal DNS remains active whenever the quality threshold is not met.*
