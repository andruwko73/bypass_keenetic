*v1.990 (31 Jul 2026) -* main

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
