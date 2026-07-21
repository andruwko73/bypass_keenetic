<a name="1.973"></a>
# [1.973] - 21 Jul 2026

- Added the Xray `bittorrent-direct` rule for transparent and TPROXY traffic, enabled by default.
- Added an optional strict transparent-route policy: known service domains and IP ranges use the selected proxy, and other transparent traffic remains direct.
- Preserved the existing proxy behaviour by default; `routeOnly` options remain disabled until explicitly selected.
- Included the transparent-route policy module in installation, update and recovery paths.

<a name="1.972"></a>
# [1.972] - 20 Jul 2026

- Moved the YouTube prefetch configuration migration into the newly installed bot service startup path.
- Existing routers now receive the two-hour guarded interval and cache freshness thresholds during the same update, before the bot imports its configuration.

<a name="1.971"></a>
# [1.971] - 20 Jul 2026

- Restored guarded external YouTube edge prefetch every two hours after release 1.932 disabled periodic runs.
- Scheduled refreshes now execute the full prefetch path and retry quickly when CPU, load, memory, or another maintenance task is busy.
- Post-update refresh no longer accepts a cache with fewer than eight usable candidates or data older than six hours.

<a name="1.970"></a>
# [1.970] - 19 Jul 2026

- Меню маршрута сервиса на компактном экране позиционируется до отрисовки и больше не успевает появиться за нижней границей окна.
- Сохранена добавленная в 1.969 подтверждаемая команда отката обновления в Telegram-боте.

<a name="1.969"></a>
# [1.969] - 19 Jul 2026

- В меню Telegram-бота «Установка и удаление» добавлена подтверждаемая команда «Откатить обновление».
- Telegram и веб-интерфейс используют один механизм восстановления последней резервной копии; параллельный запуск другой служебной команды блокируется.
- Откат выполняется отдельным процессом только по запросу, отображается в статусе обновления и доставляет результат в Telegram после перезапуска бота.

<a name="1.968"></a>
# [1.968] - 19 Jul 2026

- CSS и JavaScript больше не кэшируются браузером как неизменяемые на год: короткий кэш позволяет восстановительному обновлению сразу отдать актуальный интерфейс.
- Новый номер релиза меняет URL статических файлов и очищает уже закэшированную промежуточную копию 1.967.

<a name="1.967"></a>
# [1.967] - 19 Jul 2026

- Меню настройки фона остаётся плотным и читаемым при максимальной прозрачности остальных блоков и кнопок.
- Короткий результат проверки ключей на широком экране больше не растягивается до нижней границы страницы и не оставляет пустую область.
- Обновление заранее загружает полный комплект статических файлов и переключает его атомарно, чтобы код, CSS и JavaScript всегда относились к одному релизу.
- Начальная установка и обновление снова используют одинаковый полный набор runtime-модулей.

<a name="1.966"></a>
# [1.966] - 19 Jul 2026

- Проверка режима обновления больше не выполняет файловую операцию на каждом веб-запросе и проходе фонового планировщика; состояние процесса переключается сигналами обновителя.
- Страница обслуживания загружается в память только во время обновления, а не при обычном запуске программы.
- Удалён неиспользуемый повторный сканер `/proc`; основной сбор метрик по-прежнему сначала классифицирует процесс и только затем читает его `status`.
- Выбор резервных ключей больше не ищет индекс протокола внутри цикла ключей, сохраняя прежнюю сортировку и приоритеты.

<a name="1.965"></a>
# [1.965] - 19 Jul 2026

- Основной веб-сервер остаётся доступным во время обновления: процесс переходит в режим обслуживания, останавливает Telegram polling, проверки пула и фоновые операции, но продолжает показывать ход установки.
- Замена файлов начинается только после подтверждения безопасного состояния; при невозможности остановить текущие операции обновление отменяется до изменения файлов.
- Перед финальным запуском выполняется единственный короткий перезапуск процесса, после которого порт возвращается полноценному интерфейсу.
- Окно оформления сохраняет плотный размытый фон при прозрачности блоков и кнопок 100% и остаётся читаемым во всех темах.

<a name="1.964"></a>
# [1.964] - 19 Jul 2026

- Бот и веб-интерфейс теперь запускаются сразу после безопасной замены файлов и запуска основных сервисов, до длительного обновления ipset и завершающих сетевых проверок.
- В постоянный статус обновления добавлены отдельные этапы запуска веб-интерфейса и завершения сетевых списков; окно недоступности сокращено до операции замены файлов.
- Неудачный перезапуск бота теперь считается ошибкой обновления и запускает автоматическое восстановление.

<a name="1.963"></a>
# [1.963] - 19 Jul 2026

- Запись основного Xray-конфига и его миграций стала атомарной: остановка процесса больше не может оставить нулевой `config.json`.
- Перед резервным копированием и проверкой Xray обновитель пересобирает конфигурацию из сохранённых ключей.
- При ошибке после остановки программы обновитель автоматически запускает восстановление или откат, чтобы бот и веб-интерфейс не оставались выключенными.

<a name="1.962"></a>
# [1.962] - 19 Jul 2026

- Обновление теперь до замены файлов обязательно останавливает бот, проверку пула ключей и временные процессы Xray. Если любой из них не остановился, обновление отменяется до изменения runtime-файлов.
- Исправлен риск несовместимой пары `main.py` и runtime-модулей при перезапуске бота во время активной фоновой операции.

<a name="1.961"></a>
# [1.961] - 19 Jul 2026

### Фон интерфейса

- Бегунок «Затемнение фона» теперь визуально заполняет трек до самого значения 100%, без ложного серого хвоста справа.
- Добавлена сохраняемая настройка «Прозрачность блоков и кнопок»: она делает карточки, поля и кнопки прозрачнее, не ухудшая читаемость текста.
- Предпросмотр обеих настроек работает сразу, до сохранения фона на роутере.

<a name="1.960"></a>
# [1.960] - 19 Jul 2026

### Подписки и проверка пула

- Добавлена автоматическая полная проверка всех ключей один раз в сутки в локальное ночное окно 03:00–06:00, но только после свежего успешного обновления подписки.
- Проверка использует существующий отдельный worker-процесс и не запускается параллельно с обновлением, другой чувствительной к памяти операцией, активной проверкой пула или её ожидающим ручным продолжением.
- Запуск записывается в сохраняемое при обновлении состояние, поэтому перезапуск бота не создаёт повторную ночную проверку в тот же день.

<a name="1.959"></a>
# [1.959] - 19 Jul 2026

### Фон интерфейса

- Затемнение фона теперь настраивается во всём диапазоне от 0% до 100%; значение 100% сохраняется на роутере без ограничения до 80%.

<a name="1.958"></a>
# [1.958] - 19 Jul 2026

### Фон интерфейса

- Исправлено граничное округление: крупное изображение автоматически уменьшается до размера, который сервер принимает без ошибки «Разрешение фона слишком велико».
- Браузерный smoke-тест проверяет изображение 2560×1601 с мобильным MIME-типом на всём пути от выбора до удаления.

<a name="1.957"></a>
# [1.957] - 19 Jul 2026

### Совместимость

- Выбор фона работает с JPEG, PNG и WebP на ПК, Android и iPhone: если мобильный браузер не передаёт MIME-тип файла, принимается только безопасное расширение, а итоговый WebP всё равно проверяется на роутере.

<a name="1.956"></a>
# [1.956] - 19 Jul 2026

### Интерфейс и обновление

- Фон интерфейса: убрана лишняя галка; предпросмотр сохраняется при настройке затемнения, а выбор, сохранение и удаление проверяются браузерным smoke-тестом.
- Окно обновления после загрузки файлов показывает целевую версию релиза.
- Обновлятор берёт список runtime-модулей из скачанного сценария, поэтому следующий релиз не может пропустить новый модуль из-за старого сценария обновления.

<a name="1.955"></a>
# [1.955] - 19 Jul 2026

<a name="1.954"></a>
# [1.954] - 18 Jul 2026

<a name="1.953"></a>
# [1.953] - 18 Jul 2026

<a name="1.952"></a>
# [1.952] - 18 Jul 2026

<a name="1.951"></a>
# [1.951] - 18 Jul 2026

### Интерфейс и производительность

- Локальная веб-панель сохраняет компактный вид до Full HD, а на 2K и 4K экранах использует более широкую рабочую область, увеличенные элементы управления и высокий редактор списков.
- UI smoke проверяет Full HD, 2K и 4K в форматах 16:9 и 16:10 во всех режимах, включая отсутствие горизонтальной прокрутки и корректные размеры редактора списков.
- Снимок процессов для блока роутера сначала определяет процессы программы по `cmdline` и читает `/proc/<pid>/status` только для них, уменьшая лишние обращения к `/proc` без изменения показателей RSS.

<a name="1.950"></a>
# [1.950] - 18 Jul 2026

### Надёжность и ресурсы

- Метрики роутера учитывают процесс проверки пула даже при потере его временного статуса, поэтому возможный «осиротевший» worker не скрывается.
- Если рабочий поток проверки пула не удалось запустить, бот снимает блокировку, очищает временное состояние и корректно сообщает об ошибке вместо зависшего статуса.
- В строке доступной памяти убрана завершающая точка, чтобы значение читалось компактнее.

<a name="1.949"></a>
# [1.949] - 18 Jul 2026

### Telegram

- Удалён дубль «X / Twitter» из выбора сервисов: внешний список Twitter подключён к единой кнопке «Grok / X / Twitter».
- Команда `/getlist grok` использует тот же объединённый загрузчик, что и кнопка в боте.

<a name="1.948"></a>
# [1.948] - 18 Jul 2026

### Интерфейс

- Единый порядок протоколов: Vless 1, Vless 2, Vmess, Trojan, Shadowsocks.
- Этот порядок применён к переключателю веб-интерфейса, меню Telegram «Ключи», пулу и отчёту статуса ключей.

<a name="1.947"></a>
# [1.947] - 18 Jul 2026

### Изменено

- Grok, X и Twitter объединены в один сервис `Grok / X / Twitter`: одна проверка и одна кнопка добавления адресов без дублирования списков.
- Объединённая кнопка сохраняет встроенные домены Grok/X/Twitter и дополняет их актуальным списком X/Twitter.

<a name="1.946"></a>
# [1.946] - 18 Jul 2026

### Исправлено

- Снимок памяти и CPU Keenetic для карточки роутера обновляется не реже одного раза в пять секунд, чтобы не смешивать его со свежим Linux `MemAvailable`.

<a name="1.945"></a>
# [1.945] - 18 Jul 2026

### Исправлено

- В карточке роутера восстановлен компактный порядок: Linux `MemAvailable` и `MemTotal` в основной строке, затем занятая память и CPU из актуального снимка Keenetic.
- В API разделены Linux-видимый объём памяти и физический объём из Keenetic, поэтому 485 МБ больше не заменяются на 512 МБ в интерфейсе.

<a name="1.944"></a>
# [1.944] - 18 Jul 2026

- Makes the Router card use one fresh Keenetic NDMC snapshot for used RAM, total RAM, percentage and CPU; Linux `MemAvailable` and the program RSS breakdown remain explicitly separate.
- Refreshes NDMC in compact status views by TTL and on `force=1`, including the first compact request, while retaining the independent `/proc` CPU sampler used by internal guards.
- Corrects the protocol-specific key/subscription import hint in both renderers, translates visible subscription messages, and keeps route popovers inside compact desktop viewports.

<a name="1.943"></a>
# [1.943] - 13 Jul 2026

- Rechecks overdue subscriptions every five minutes, so a protocol deferred by the shared resource guard does not wait another hour.
- Keeps the actual subscription network refresh interval at six hours; the shorter scheduler tick only evaluates whether work is due.
- Migrates the former one-hour scheduler check while preserving non-default custom intervals.

<a name="1.942"></a>
# [1.942] - 13 Jul 2026

- Feeds network exceptions caught inside TeleBot polling into Telegram key auto-failover instead of leaving a dead active key selected.
- Clears stale success and failure state around verified recovery, and marks the key owned by the actual Telegram route protocol.
- Refreshes HWID-enabled subscriptions every six hours by default and migrates the previous 24-hour default during updates.

<a name="1.941"></a>
# [1.941] - 13 Jul 2026

- Keeps Telegram MTProto TCP 5222 on the selected Telegram route while allowing APNs 5223 and FCM 5228-5230 to connect directly.
- Raises too-small established conntrack timeouts to at least 3600 seconds so idle mobile push channels survive longer than the vendor-required 30-minute NAT window.
- Removes stale push redirects during refresh and adds regression coverage for rule ordering, direct push ports and conntrack persistence.

<a name="1.940"></a>
# [1.940] - 12 Jul 2026

- Rebuilds the lightweight pool summary from the compact probe cache when the saved pool size no longer matches the current pools.
- Preserves lazy startup and avoids importing heavy pool modules while keeping checked-key and service counters accurate.
- Covers pool-size changes with a regression test and retains the persisted fast path after the one-time rebuild.

<a name="1.939"></a>
# [1.939] - 12 Jul 2026

- Parses lazy protocol-panel responses defensively, so a temporary HTML error during a mode restart cannot appear as a raw JSON exception.
- Retries the check panel through the restart window and leaves a clear manual retry action if the router remains unavailable.
- Covers the regression with a UI smoke that injects one HTML 404 before the successful check-panel response.

<a name="1.938"></a>
# [1.938] - 12 Jul 2026

- Keeps static assets, pool rows, route tools and unblock-list contents lazy and cached instead of rebuilding them during ordinary page requests.
- Samples router CPU in the background and reads ipset state in one snapshot, avoiding the web-request spike and repeated process calls.
- Coordinates allocator cleanup, removes stale runtime helpers and defers optional modules so simple, advanced and web-only modes retain lower steady RSS.
- Preserves trustworthy service results during incomplete checks, keeps YouTube ownership protocol-independent and removes duplicate health probes.
- Trims installed release artifacts while retaining full rollback coverage and the complete changelog in Git.

<a name="1.937"></a>
# [1.937] - 11 Jul 2026

- Runs one bounded allocator cleanup only after the entire process-isolated pool check finishes, without restarting the bot or clearing the visible status.
- Honors the configured `memory_malloc_trim_min_rss_kb` threshold instead of silently waiting for the watchdog soft threshold.
- Verifies dnsmasq YouTube ownership and priority ipset output for Vless 1, Vless 2, Vmess, Trojan and Shadowsocks.
- Removes stale source headers and safe unused helpers while preserving public compatibility imports.

<a name="1.936"></a>
# [1.936] - 11 Jul 2026

- Synchronizes the embedded bot release marker with the generated release counter, restoring the GitHub clean-smoke version invariant.

<a name="1.935"></a>
# [1.935] - 11 Jul 2026

- Moves transient health, failover and full pool-probe work into bounded runners, preserves the active key during checks, and prevents temporary-worker cleanup from affecting resident services.
- Serves ready JavaScript and CSS assets instead of compiling interface templates for requests; pool/status responses retain the last trustworthy service results during lightweight refreshes.
- Consolidates YouTube route ownership and priority ipset handling for every supported protocol, making route application event-driven rather than permanently warmed.
- Reduces repeated DNS/ipset, router-health and call-learning work while retaining simple, advanced and web-only mode behavior, TPROXY calls, subscriptions and clean-install compatibility.

<a name="1.934"></a>
# [1.934] - 8 Jul 2026

- Prevents temporary pool-probe cleanup from matching the separate full pool-probe worker, so a full pool check no longer exits with `code -15` when health or failover cleanup runs nearby.
- Keeps the post-check memory path intact: after the 120-key router probe finishes, temporary Xray/worker processes are gone and program RSS returns to the normal bot plus Xray baseline.

<a name="1.933"></a>
# [1.933] - 8 Jul 2026

- Keeps protocol service icons stable after idle live-status refreshes, including the lazy pool-load path where the short Telegram-only status arrives after the full service icons were shown.
- Adds a UI smoke check for the no-click idle refresh path, not only for key-apply refreshes.

<a name="1.932"></a>
# [1.932] - 8 Jul 2026

- Makes YouTube routing depend on the selected service route and cached edge restore instead of periodic background warm-up.
- Applies selected pool keys faster with a short first wait and a safe full fallback wait when Xray is slower to expose the local port.
- Keeps protocol service icons from being overwritten by lighter live-status payloads and covers the case in UI smoke.
- Skips the first CPU sample after router-health prime so the web UI does not display the short page-load/API spike as router load.

<a name="1.931"></a>
# [1.931] - 7 Jul 2026

- Keeps the service route desktop popover inside the viewport by capping its height and using internal scrolling.

<a name="1.930"></a>
# [1.930] - 7 Jul 2026

- Makes the web update download repo files from the direct GitHub codeload archive/API before trying raw.githubusercontent.com.
- Keeps local SOCKS/VPN download as the final fallback only when direct GitHub archive/API and raw downloads fail.

<a name="1.929"></a>
# [1.929] - 7 Jul 2026

- Keeps the router CPU value in the web UI from counting the page render itself by using the last stable CPU sample on initial HTML.
- Adds a lightweight `/api/router_health` refresh after page load so the router block updates without rebuilding statuses, pools, or the whole page.
- Covers the no-sample page render path and router-health endpoint with smoke tests.

<a name="1.928"></a>
# [1.928] - 7 Jul 2026

- Adds a clean-install GitHub archive fallback so the first bootstrap can continue when `raw.githubusercontent.com` is unavailable before any local proxy/key exists.
- Makes bootstrap download required runtime files and optional static assets from the archive fallback when raw GitHub downloads fail.
- Updates the README clean-install command to fetch `bootstrap/install.sh` from raw first, then from the GitHub archive.

<a name="1.927"></a>
# [1.927] - 7 Jul 2026

- Uses total program RSS as the hard background-task guard so bot + Xray + temporary helpers stay under the 100 MB program target.
- Keeps bot RSS as a soft economy signal for lighter status/pool fallbacks while preserving the 70 MB emergency bot threshold.
- Finishes post-pool cleanup when the total program RSS is back under target and adds update/install config migration for the new thresholds.

<a name="1.926"></a>
# [1.926] - 7 Jul 2026

- Restores Telegram, YouTube, and custom-service icons in the active key-pool status without letting optional service failures change the route-scoped protocol status.
- Renders Telegram and YouTube headers in the lightweight pool table before lazy pool data loads, keeping mobile rows aligned across all protocols.
- Keeps live protocol status text intact while merging the latest active-pool service icons after the pool is loaded.
- Keeps compact router health notes cached for DNS, proxy ports, and TPROXY calls, and records lightweight Telegram probe results without importing heavy pool modules.

<a name="1.925"></a>
# [1.925] - 7 Jul 2026

- Keeps the startup web header on a light active status snapshot so page load does not flash a false Telegram API warning.
- Preserves checked key-pool totals from the probe cache when the summary worker falls back, avoiding transient `Проверено: 0` after a full pool check.
- Defers route-tools rendering to a short-lived worker and avoids repeated service-catalog matching while annotating route intersections.
- Keeps the first advanced page lightweight and verifies router idle CPU/RSS after local install and all-mode UI smoke.

<a name="1.924"></a>
# [1.924] - 6 Jul 2026

- Skips unchanged dnsmasq full ipset refreshes for up to six hours, while explicit refresh/update still force a rebuild.
- Keeps YouTube edge warm-up from starting while unblock refresh or pool probe work is already running, and lowers the default watch-page warm-up budget.
- Releases lazy runtime modules from `sys.modules` during cleanup and keeps the last valid pool summary instead of replacing checked results with transient zero counts.
- Keeps pending Telegram startup/failover states neutral in the topbar, and recalculates unified key/subscription textarea heights only after visible panels are laid out.
- Updates README wording for key pools, subscription import, checks, and YouTube warm-up.

<a name="1.923"></a>
# [1.923] - 6 Jul 2026

- Changes the background unblock cron job from forced `refresh` to lightweight `tick`, so the scheduler is kept alive without rebuilding all ipset sets every 15 minutes.
- Keeps explicit `refresh` available for manual/update paths while routine background work only runs when the existing freshness checks say it is due.

<a name="1.922"></a>
# [1.922] - 6 Jul 2026

- Keeps Telegram auto-failover idle while Telegram polling is healthy and no confirmed failure is pending.
- Runs the high-RSS guard and post-cycle cleanup only when Telegram recovery actually has work to do, reducing idle CPU/RSS churn without disabling emergency key recovery.

<a name="1.921"></a>
# [1.921] - 5 Jul 2026

- Reduces the update timer restart padding from 15 seconds to 5 seconds.

<a name="1.920"></a>
# [1.920] - 5 Jul 2026

- Fixes the initial web page pool summary so saved key probe results are shown immediately instead of transient zero counts.
- Keeps lazy pool row loading intact while loading the lightweight probe cache only for the summary.

<a name="1.919"></a>
# [1.919] - 5 Jul 2026

- Makes the YouTube prefetch runner force `/opt/etc/bot` ahead of legacy `/opt/etc` even when the runner starts as a script from `/opt/etc/bot`.
- Keeps the active bot config authoritative for YouTube warm-up limits and URLs.

<a name="1.918"></a>
# [1.918] - 5 Jul 2026

- Fixes YouTube prefetch runner config precedence so `/opt/etc/bot/bot_config.py` overrides the legacy `/opt/etc/bot_config.py`.
- Ensures the new two-page/eight-host YouTube warm-up settings are actually used after update.

<a name="1.917"></a>
# [1.917] - 5 Jul 2026

- Improves YouTube warm-up for slow-start videos: live pages now participate in edge discovery.
- Routes observed `rr*---*.googlevideo.com` edge hosts as limited `/24` networks through the active YouTube protocol and its priority ipset.
- Restores cached YouTube edge networks after startup/update so warm routes survive runner restarts.

<a name="1.916"></a>
# [1.916] - 5 Jul 2026

- Keeps active-key and key/subscription import textareas fully visible without internal horizontal or vertical scrolling on desktop and mobile.
- Stretches the mobile protocol "Проверка" subtab across the full row and adds Playwright coverage for the layout.
- Prevents a transient zero pool-summary payload from replacing an already-known checked pool result in the web UI.
- Cleans the README capabilities list wording and removes internal implementation details from it.

<a name="1.915"></a>
# [1.915] - 5 Jul 2026

- Makes the unified "Key and subscription" tab compact on desktop and mobile: the active key editor no longer consumes the whole panel, and the import button stays visible in the first screen of the tab.
- Keeps the topbar on the neutral "Status is updating" state while Telegram polling is still being confirmed, instead of flashing a false Telegram warning during page load.
- Adds Playwright smoke coverage for the compact active-key editor height and visible import button.

<a name="1.914"></a>
# [1.914] - 5 Jul 2026

- Shows transient Telegram API key-selection states as a neutral refresh status while live status polling resolves them, keeping real Telegram/API errors as warnings.
- Merges the protocol Key and Subscription tabs into "Key and subscription" with one import form for key lists and subscription URLs; Vless imports stay in the open Vless pool and other protocols go to their own pools.
- Removes dead CSS for the old Subscription tab and extends Python and Playwright smoke coverage for the unified import layout.

<a name="1.913"></a>
# [1.913] - 5 Jul 2026

- Moves router runtime files, Python modules, route lists, static assets, and helper configs under `app/` while keeping root `script.sh`, `bootstrap/install.sh`, `version.md`, README, and changelog as stable GitHub install/update entry points.
- Updates clean install and GitHub update download paths so existing routers fetch runtime files from `app/` without changing the installed `/opt/etc/bot` layout.

<a name="1.912"></a>
# [1.912] - 5 Jul 2026

- Hydrates the already-rendered active Vless 1 pool when the Keys view opens, matching lazy Vless 2 panel loading so the first protocol cannot stay on "Загружаю пул ключей...".

<a name="1.911"></a>
# [1.911] - 4 Jul 2026

- Retries lazy protocol panel loading after transient fetch failures and replaces raw browser errors with a localised message, so flaky external access does not immediately strand the Keys view on an error card.

<a name="1.910"></a>
# [1.910] - 4 Jul 2026

- Queues lazy web pool refreshes by protocol so quickly opening Vless 1 and Vless 2 cannot cancel one pool request and leave it stuck on loading.

<a name="1.909"></a>
# [1.909] - 4 Jul 2026

- Fills inactive protocol statuses in the compact/active-mode snapshot from the cached pool probe result, preventing Vless 2 or another inactive protocol from staying on "Проверяется" after no pool probe is running.

<a name="1.908"></a>
# [1.908] - 4 Jul 2026

- Reduces idle router load by skipping Telegram auto-failover probes while polling is healthy, without suppressing recovery after a recorded Telegram failure.
- Avoids active YouTube failover probes while routed YouTube/Vless traffic is already flowing and no confirmed failure is cached.
- Applies a selected pool key immediately and moves its Telegram/YouTube/custom service recheck to a background single-key probe.
- Keeps deferred pool panels in a loading/retry state instead of rendering a false "pool empty" message when `/api/pools` is still loading or a fetch is retried.

<a name="1.907"></a>
# [1.907] - 4 Jul 2026

- Runs background Telegram and YouTube failover health checks in a short-lived worker process so periodic checks do not raise the main bot RSS after startup.

<a name="1.906"></a>
# [1.906] - 4 Jul 2026

- Defers importing the heavy HTTP client stack until subscription, status, Telegram API, YouTube, or custom service checks actually run, reducing idle bot memory pressure.

<a name="1.905"></a>
# [1.905] - 4 Jul 2026

- Moves Telegram/YouTube failover candidate checks into a short-lived worker process so temporary Xray probing does not inflate the main bot RSS.
- Makes debug memory timeline trimming interval-based instead of rereading the JSONL file on every sample during long monitoring runs.

<a name="1.904"></a>
# [1.904] - 4 Jul 2026

- Removes the unsafe runtime `sys.modules` unloading from 1.903 after live router testing showed concurrent web requests could hit module import races.
- Stops auto-fetching deferred pool data for every protocol during initial page load; pool data is still loaded when the user opens the relevant protocol/pool view or after pool actions.

<a name="1.903"></a>
# [1.903] - 4 Jul 2026

- Drops selected lazy UI, route, probe, and prefetch modules from `sys.modules` after heavy web/status/watchdog work.
- Keeps the unload scoped to idle pool/prefetch paths so active pool checks and YouTube prefetch runs are not interrupted.

<a name="1.902"></a>
# [1.902] - 4 Jul 2026

- Treats transient Telegram API recovery/key-selection messages as pending status so the header refreshes itself after update without a manual page reload.
- Makes live header status polling use a lightweight `/api/status` payload that does not rebuild the full router-health block on every poll.

<a name="1.901"></a>
# [1.901] - 4 Jul 2026

- Keeps lazy protocol panel and protocol check panel rendering on the lightweight status path when the status cache is cold.
- Avoids an extra full probe-cache warmup from opening protocol tabs, while preserving active-mode status refresh.

<a name="1.900"></a>
# [1.900] - 4 Jul 2026

- Keeps compact web status and the initial pool-mode page on the lightweight active-mode path so header refreshes do not load the full key probe cache in the main bot process.
- Starts background status refresh from compact status calls in active-only mode, reducing idle web polling memory and CPU pressure.

<a name="1.899"></a>
# [1.899] - 4 Jul 2026

- Stops caching large `/api/pools` and event-history payloads in the main bot process after they are rendered.
- Renders the initial pool page without loading the full probe cache; the existing `/api/pools` hydration fills detailed rows after the page loads.
- Builds `/api/pools` rows, summary and custom-check metadata in a short-lived worker process, so large probe-cache reads do not raise the long-lived bot RSS shelf.
- Reuses the Xray process id and compact router-metrics snapshots, and releases lazy module references without removing modules from `sys.modules`, reducing repeated `/proc` scans and import churn.

<a name="1.898"></a>
# [1.898] - 4 Jul 2026

- Preserves user bypass route lists during GitHub updates, matching rollback behavior for `vless.txt`, `vless-2.txt`, `vmess.txt`, `trojan.txt`, and `shadowsocks.txt`.
- Makes `/opt/etc/init.d/S99unblock refresh` run a real ipset refresh even when the scheduler process is active, so manual/web refresh no longer exits silently.

<a name="1.897"></a>
# [1.897] - 4 Jul 2026

- Stops shared runtime memory cleanup from removing lazy-loaded modules out of `sys.modules` while web requests are still active.
- Prevents transient protocol/status errors such as `key_pool_web` or `probe_cache` during concurrent status, protocol panel, and cleanup activity.
- Keeps the memory cleanup behavior focused on releasing bot-held module references and allocator trimming, without adding extra background work.

<a name="1.896"></a>
# [1.896] - 4 Jul 2026

- Restores active protocol key files and proxy config files during web/GitHub updates, matching rollback behavior for Vless 1, Vless 2, Vmess, Shadowsocks, and Trojan.
- Keeps the existing Telegram and YouTube failover paths responsible for switching to a better pool key only after the restored active key fails runtime checks.
- Adds smoke coverage so update restore cannot regress to preserving only pools/subscriptions while clobbering active keys.

<a name="1.895"></a>
# [1.895] - 4 Jul 2026

- Forces `malloc_trim` after heavy web UI module cleanup so memory released by pool, route, and check panels can return closer to the fresh-start baseline.
- Prevents pool-probe child workers from scheduling/reporting post-pool cleanup for themselves; the main bot process remains responsible for final memory diagnostics.
- Keeps the existing RSS/restart limits unchanged.

<a name="1.894"></a>
# [1.894] - 4 Jul 2026

- Releases heavy pool, route, and YouTube prefetch UI modules immediately after heavy web responses instead of waiting for the RSS cleanup threshold.
- Keeps expensive router-health subcaches during routine memory cleanup so status polling does not trigger avoidable `/proc`, DNS, ndmc, and proxy health work.
- Adds smoke coverage for the memory cleanup behavior so the bot can return closer to fresh-start RSS after web and route operations without changing limits.

<a name="1.893"></a>
# [1.893] - 4 Jul 2026

- Releases lazy pool/probe/route modules during memory cleanup so the bot can return closer to its fresh RSS after heavy UI and pool operations.
- Clears heavier router-health caches on forced cleanup and caches the lightweight YouTube prefetch snapshot to reduce idle UI polling CPU spikes.
- Reuses related-process snapshots briefly while pool probe is running so the router block does not rescan `/proc` on every status refresh.

<a name="1.892"></a>
# [1.892] - 4 Jul 2026

- Routes mixed key imports by protocol scheme so Vmess, Trojan, and Shadowsocks entries are saved into their own pools instead of Vless 2.
- Ignores non-key text lines without a supported URI scheme during manual pool import.
- Repairs saved pool files on write so existing cross-protocol pool pollution is cleaned without exposing key material.

<a name="1.891"></a>
# [1.891] - 3 Jul 2026

- Adds the remaining observed Googlevideo `.119` startup edge IPs to the YouTube route without broadening whole Google `/24` ranges.
- Keeps live YouTube startup traffic on the selected YouTube route while limiting route bleed into other Google services.

<a name="1.890"></a>
# [1.890] - 3 Jul 2026

- Adds live Googlevideo edge IPs observed during the YouTube load test to the YouTube route catalog and shipped Vless 2 list.
- Extends smoke coverage so these additional video startup addresses stay on the selected YouTube route.

<a name="1.889"></a>
# [1.889] - 3 Jul 2026

- Makes Vless priority refresh follow the selected YouTube route for shared Google static/ad domains such as `ssl.gstatic.com`, `fonts.gstatic.com`, and `www.googletagmanager.com`.
- Prevents priority refresh from deleting observed YouTube edge IPs from Vless 2 after the route list already assigned YouTube to Vless 2.

<a name="1.888"></a>
# [1.888] - 3 Jul 2026

- Adds observed YouTube/Google edge and ad-bootstrap IPs to the YouTube route catalog so the `YouTube -> Vless 2, rest -> Vless 1` split does not let Vless1 priority refresh steal part of YouTube page/video startup traffic.
- Covers the new edge entries in smoke tests to keep them in the shipped Vless 2 route list.

<a name="1.887"></a>
# [1.887] - 2 Jul 2026

- Runs the service-route catalog repair during GitHub updates so existing router installs migrate new YouTube route entries into the selected YouTube protocol instead of keeping old runtime lists.
- Re-runs the same repair after applying a route profile, keeping `YouTube -> Vless 2, rest -> Vless 1` complete even when later services would otherwise remove allowed shared Google entries.
- Extends route-profile smoke coverage so YouTube must be fully assigned to Vless 2 after the profile is applied.

<a name="1.886"></a>
# [1.886] - 2 Jul 2026

- Moves YouTube ad-decision domains such as DoubleClick and Google ad services into the YouTube route so the `YouTube -> Vless 2, rest -> Vless 1` profile keeps more of the YouTube playback context on Vless 2.
- Keeps Telegram auto-failover scoped to the protocol where Telegram is actually routed, preventing a Telegram recovery attempt from replacing the selected Vless 2 YouTube key.

<a name="1.885"></a>
# [1.885] - 2 Jul 2026

- Stops background status refresh from calling memory cleanup at the normal ~62 MB bot RSS shelf; it now waits for the same 65 MB light-response threshold as `/api/status`.
- Keeps heavy page/protocol cleanup unchanged so real memory pressure still releases caches and allocator pages.

<a name="1.884"></a>
# [1.884] - 2 Jul 2026

- Adds a separate 65 MB cleanup threshold for light web/API responses so `/api/status` polling does not trigger `gc.collect()`/`malloc_trim` at the normal ~62 MB bot RSS shelf.
- Keeps the lower 60 MB cleanup threshold for heavy HTML/protocol-panel responses where memory release is worth the work.

<a name="1.883"></a>
# [1.883] - 2 Jul 2026

- Reduces idle router CPU spikes by extending the recent-success window that lets Telegram auto-failover trust an already working active key instead of rechecking Bot API every few minutes.
- Keeps CPU backoff effective for emergency Telegram recovery: `allow_high_rss` can bypass only RSS pressure, not a CPU-busy cooldown.
- Routes async web status refresh through the background CPU/RSS guard and stretches router-health polling to 30 seconds, reducing self-load from an open web interface.

<a name="1.882"></a>
# [1.882] - 2 Jul 2026

- Lets Telegram auto-failover run even when the generic background RSS guard is holding non-critical jobs, so repeated bot API failures can still switch to a working pool key.
- Makes the active protocol status use authenticated Telegram Bot API checks when the Telegram bot is enabled, avoiding a false "Telegram works" state from a bare api.telegram.org reachability check.
- Prevents long Telegram API connection errors from leaking into the web status banner; technical details are logged, while the UI now shows the current recovery action.

<a name="1.881"></a>
# [1.881] - 1 Jul 2026

- Removes YouTube warmed edge IPs from the opposite Vless priority ipset so Google/gstatic priority refreshes cannot send YouTube startup traffic through the wrong Vless route.
- Adds YouTube startup/API domains to the existing Vless priority winner selection, so shared Google edge IPs follow the route where YouTube is assigned.
- Runs the Vless priority dedupe again after full ipset refresh rebuilds priority sets.
- Applies the same priority cleanup from the S99unblock scheduler without adding a new background job.
- Fixes S99unblock orphan-scheduler cleanup so `start`/`restart` no longer match and terminate their own command line.

<a name="1.880"></a>
# [1.880] - 1 Jul 2026

- Keeps the router card CPU label stable during the first page snapshot, showing `Нагрузка CPU: -` instead of switching to average load.
- Removes the extra blank paragraph inside the router card note so router, program, proxy and call lines keep even spacing.
- Restores the wider theme button layout for `Web only` headers on tablet-width screens.

<a name="1.879"></a>
# [1.879] - 1 Jul 2026

- Smooths router CPU in the status card so one short `/proc/stat` sample does not look like sustained idle load.
- Caches related process RSS scans while no pool probe is running, reducing `/proc` work from open web pages without hiding pool workers during checks.
- Reuses a fresh background CPU-guard sample across service checks, avoiding repeated short CPU samplings when guards run close together.
- Adds update/clean-install config defaults for the lighter router-health and background-guard behavior.
- Rotates bootstrap clean-install rollback backups to the latest copy; web-update backups already keep the latest rollback.
- Keeps pool probe behavior unchanged; long pool checks still require an explicit user start.

<a name="1.878"></a>
# [1.878] - 1 Jul 2026

- Keeps pool-only mutations from resetting the full active-mode status when the active key is unchanged.
- Includes background pool-probe progress in pool action responses so the UI follows checks started by add/subscription actions.
- Refreshes status once after pool mutations to clear stale topbar warnings without increasing idle polling.
- Keeps post-pool progress labels, MemAvailable checks and Telegram pool healthcheck helpers off the hot runtime path after a pool probe.
- Caches compact live-status API responses separately from full status payloads and skips temp Xray process scans when no pool probe is active, reducing CPU spikes from an open web interface.
- Records post-pool router cleanup snapshots in runtime/event logs instead of adding another web UI field.
- Serializes Telegram bot service start/stop/restart, stops all matching main.py processes, and adds a main.py singleton guard so overlapping or delayed restarts cannot leave a duplicate bot process on the router.
- Separates router-wide memory/CPU from program resource use in the router status card.
- Includes related helper RSS in the program line during diagnostics: Xray, pool workers, temporary Xray, YouTube prefetch and command workers.
- Preserves multiline router status text in the web UI so the compact card stays readable on desktop and mobile.

<a name="1.877"></a>
# [1.877] - 30 Jun 2026

- Defers expensive service-route intersection checks from the initial protocol-check HTML and loads them through the existing service-routes API, reducing first-render CPU/RSS pressure on the router.
- Optimizes service-route summaries by reading route files once per summary instead of once per service/protocol pair.
- Replaces route-intersection domain and network scans with indexed/sweep passes and avoids allocating a dummy list for runtime ipset overlap counts.
- Debounces app-mode service restarts so fast Advanced/Simple/Web-only switches do not schedule duplicate bot restarts.
- Releases lazy pool-probe modules after worker-process checks finish and skips post-pool force cleanup when RSS is already back at the target, preventing cleanup itself from raising the idle RSS shelf.

<a name="1.876"></a>
# [1.876] - 30 Jun 2026

- Uses lightweight router-health invalidation after memory cleanup, watchdog state changes and YouTube edge prefetch status updates, keeping DNS/core/ndmc health subcaches warm instead of rerunning heavier router checks unnecessarily.
- Keeps `stream_guard_defer` history events throttled across bot restarts, so mode switches and updates do not flood the history with repeated YouTube stream-guard deferrals.
- Prevents clearing or syncing one protocol pool from deleting probe-cache results that are still referenced by another pool or by the active installed key.
- Keeps the current protocol status recoverable under high RSS by allowing active-only status refreshes while heavier background refreshes stay guarded.
- Treats unchecked warn statuses with an empty Telegram API message as a pending recheck, avoiding a red header with an empty failure reason while the current mode is still being verified.
- Schedules post-pool memory cleanup after the external worker-process path, matching the in-process pool-check cleanup behavior.
- Keeps pool-check progress synchronized between the header status banner and the compact key-pool card.
- Updates the key-pool summary from `/api/pool_probe`, so it no longer waits for the slower `/api/pools` refresh during a running check.
- Ignores stale out-of-order pool progress snapshots from the same run, preventing visual regressions such as `156/158` in one block and `139/158` in another.

<a name="1.875"></a>
# [1.875] - 30 Jun 2026

- Runs full pool checks in a separate Python worker process, with the main bot only dispatching raw keys through a temporary `0600` input file and then following sanitized progress/result files.
- Keeps manual pool cancellation distinct from apply-key pauses: cancel writes `no-resume`, while apply-key pause can still preserve the remaining queue for continuation.
- Makes simple mode render a lightweight status snapshot without loading probe-cache, custom checks, service route summaries, or starting a background pool status refresh.
- Adds install/update config defaults for `pool_probe_process_worker_enabled` and `pool_probe_process_worker_poll_seconds`.

- Снижена регулярная нагрузка веб-интерфейса: live status использует компактный API-ответ без пересчёта summary пула.
- Добавлен кэш HTML истории событий, protocol-scoped `/api/pools` больше не пересчитывает общий summary, а `key_pool_store` загружается лениво.
- Ускорен анализ пересечений маршрутов: кэшируется индекс сервисов, pending auto-resolve не запускает повторные ipset-сканы, частично назначенные сервисы переносятся в доминирующий протокол.
- Исправлена мобильная форма добавления ключей/subscription: textarea больше не распирает сетку и не перекрывает соседний блок.
- Расширен post-pool отчёт по памяти и временный мониторинг RSS/CPU для роутера.

- Local archive updates now install `static/` assets, so service icons are not lost when testing a release before GitHub upload.
- Local archive updates now preserve explicit `UPDATE_ARCHIVE_ROOT`/`RAW_GITHUB_BYPASS`, so pre-GitHub router tests cannot silently fall back to the current GitHub `main`.
- UI smoke can authenticate against the real router without putting credentials in the tested URL.
- Mobile event history now locks page scroll and scrolls its own event list.
- Event history loading/fallback text is valid UTF-8, and UI smoke checks visible pages for mojibake markers.
- Repeated `stream_guard_defer` events are coalesced in event history, and expensive route diagnostics run only when an event is actually recorded.
- Post-pool memory cleanup keeps restart as a 70 MB emergency fallback while reducing repeated diagnostics and history churn.

<a name="1.874"></a>
# [1.874] - 30 Jun 2026

- Treats web rollback as an update-style background command and delays its worker by one second, so the browser receives the command-start response before the bot restarts during rollback.

<a name="1.873"></a>
# [1.873] - 30 Jun 2026

- Adds live route-ipset hashes to the `S99unblock` runtime-dedupe signature, so service route overlaps are cleaned right after the real ipset contents change instead of waiting for the force interval when route files and status timestamps stay unchanged.

<a name="1.872"></a>
# [1.872] - 30 Jun 2026

- Splits mixed runtime ipset intersections by service owner, so one overlap report containing YouTube and Telegram can clean each losing route separately instead of skipping the issue because the services target different protocols.

<a name="1.871"></a>
# [1.871] - 30 Jun 2026

- Makes runtime ipset intersection repair service-aware for the whole service catalog: live overlaps are cleaned from the losing route based on the service's selected protocol, without forcing a full `unblock_update.sh` rebuild for runtime-only conflicts.

<a name="1.870"></a>
# [1.870] - 30 Jun 2026

- Also cleans non-YouTube runtime ipsets when the selected YouTube route already contains a dynamic IP through a covering network, so prefetch cleanup runs even when no new target ipset entry has to be added.

<a name="1.869"></a>
# [1.869] - 30 Jun 2026

- Removes covering runtime ipset networks from non-YouTube routes when YouTube edge prefetch adds dynamic IPs to the selected YouTube route, so host-IP vs `/24` overlaps do not keep reappearing as runtime-only route intersections after refresh.

<a name="1.868"></a>
# [1.868] - 30 Jun 2026

- Clarifies the route-intersection UI for runtime-only ipset refreshes: when the list files are already clean and background auto-repair is applying routes, the Checks tab now shows a route-application status instead of exposing transient addresses as unresolved intersections.

<a name="1.867"></a>
# [1.867] - 30 Jun 2026

- Adds a cross-process lock and active unblock-update detection around automatic service-route intersection repair, preventing parallel protocol-check/service-route requests or bot restarts from spawning duplicate `unblock_update.sh` / `unblock_ipset.sh` refreshes.
- Enforces the route-intersection cache TTL so a pending auto-repair state is refreshed instead of being held indefinitely by an unchanged route signature.

<a name="1.866"></a>
# [1.866] - 30 Jun 2026

- Prevents the lazy protocol Checks tab from blocking on automatic service-route cleanup: known route/ipset intersections are now repaired in the background, the UI shows that cleanup was scheduled, and transient fetch failures are retried before displaying an error.
- Bumps the static asset revision so browsers load the fixed JavaScript instead of a cached 1.865 bundle.

<a name="1.865"></a>
# [1.865] - 29 Jun 2026

- Automatically repairs known service route/ipset intersections, such as YouTube being loaded into both Vless lists, when the service has one clear current target protocol; runtime-only overlaps trigger a route refresh with a cooldown instead of repeatedly asking for a manual move.

<a name="1.864"></a>
# [1.864] - 29 Jun 2026

- Raises the pool-check start/working RSS guard from the accidental 64 MiB default to the intended 65 MiB, migrates routers from the 1.863 value, and keeps the post-pool cleanup target at 62 MiB so a full check can finish near the normal shelf and still allow the next check without an update/restart.

<a name="1.863"></a>
# [1.863] - 29 Jun 2026

- Lowers the pool-check working RSS guard to 64 MB, migrates older 70/85 MB pool guard defaults, and forces cleanup after each pool key and batch so full checks back off before the bot reaches the 70 MB restart threshold.

<a name="1.862"></a>
# [1.862] - 29 Jun 2026

- Restores external runtime mode files during the normal web update path, keeping the selected app mode, proxy mode, and Telegram autostart flag across releases.

<a name="1.861"></a>
# [1.861] - 29 Jun 2026

- Lowers the pool-check process RSS guard to 70 MB and migrates the old 85 MB default so full key checks run cleanup or pause at the same threshold used by post-pool memory recovery.
- Makes long pool-check progress use lightweight `/api/pool_probe` polling and slows pool-list refreshes so an open web page does not keep forcing full status payload rebuilds during the check.
- Adds a separate post-pool cleanup target near 62 MB so the bot keeps trying `gc`/`malloc_trim` after a full pool check without restarting below the 70 MB restart threshold.

<a name="1.860"></a>
# [1.860] - 29 Jun 2026

- Fixes the Vless 2 Subscription tab layout on compact screens so the add-key textarea and button stay within their card and do not overlap the subscription form.
- Adds a UI smoke geometry check for the subscription import panel across desktop, compact desktop, and mobile.

<a name="1.859"></a>
# [1.859] - 29 Jun 2026

- Restores runtime state files from the update backup during the normal web update path, keeping HWID subscriptions, key pools, and custom checks across releases.

<a name="1.858"></a>
# [1.858] - 29 Jun 2026

- Lets HWID subscription refresh use a lightweight RSS/CPU/load guard so vless2 subscriptions can update even when heavier background checks are backed off.
- Preserves an active working managed subscription key if the site stops returning it, while still syncing new and removed subscription keys and keeping manual pool keys.
- Avoids building pool web-action callbacks in Simple mode, reduces Telegram bot worker threads to one by default, and starts the bot with malloc fragmentation guards.

<a name="1.857"></a>
# [1.857] - 28 Jun 2026

- Keeps only the latest automatic update/backup rollback artifacts after a successful update, matching the UI rollback behavior that restores the most recent update only.

<a name="1.856"></a>
# [1.856] - 28 Jun 2026

- Adds service hints and expanded address examples to the route-intersections report, so the user can see which catalog service an overlap likely belongs to before choosing a target protocol.

<a name="1.855"></a>
# [1.855] - 28 Jun 2026

- Restores the idle service restart threshold to 70 MB and adds RSS guards/cleanup around background status, Telegram failover, YouTube failover and subscription refresh checks so normal service work backs off before the bot reaches the restart threshold.

<a name="1.854"></a>
# [1.854] - 28 Jun 2026

- Lowers the idle bot RSS restart and router-metrics warning threshold to 64 MB, so web UI/history rendering spikes are reclaimed by an idle service restart instead of sitting near 70 MB.

<a name="1.853"></a>
# [1.853] - 28 Jun 2026

- Stops compact router-metrics polling from accumulating in-memory history samples, so the lightweight history monitoring panel does not grow bot RSS while it is open.

<a name="1.852"></a>
# [1.852] - 28 Jun 2026

- Lazily loads event history only when the history drawer is opened, reducing the initial web page render RSS pressure, and ensures event-history/router-metrics API responses enter the web-response cleanup path.
- Extends update config migration to lower stale legacy web-response cleanup defaults without touching secrets.

<a name="1.851"></a>
# [1.851] - 28 Jun 2026

- Keeps the 1.849 header/status layout unchanged while preserving the 1.850 router-load optimizations, and extends UI smoke so Advanced mode fails if the top header status block disappears.

<a name="1.850"></a>
# [1.850] - 28 Jun 2026

- Reduces router web-monitoring overhead by slowing idle status polling to 60 seconds, making compact router metrics omit the in-memory history array unless explicitly requested, and lowering web-response memory cleanup to start near 60 MB instead of waiting for 70+ MB.

<a name="1.849"></a>
# [1.849] - 28 Jun 2026

- Fixes the lazy protocol-check API fallback text so an invalid protocol reports a readable Russian error instead of mojibake.

<a name="1.848"></a>
# [1.848] - 28 Jun 2026

- Cleans the README by removing the obsolete "Что изменилось" section so the documentation starts with current capabilities instead of migration history.

<a name="1.846"></a>
# [1.846] - 28 Jun 2026

- Removes the separate Monitoring tab from the history drawer and embeds a compact on-demand CPU/RSS/load strip above the event history list, keeping the drawer focused on history while preserving router monitoring.

<a name="1.845"></a>
# [1.845] - 28 Jun 2026

- Keeps the history drawer opening on the History tab after router monitoring was viewed, gives the event list its own scroll area in the drawer, and extends UI smoke coverage so Simple mode fails if event history items are not visible.

<a name="1.844"></a>
# [1.844] - 28 Jun 2026

- Fixes the history drawer layout so the Monitoring tab starts directly under the tabs, and restores event history content in Simple mode without loading pool UI components.

<a name="1.843"></a>
# [1.843] - 28 Jun 2026

- Keeps the event history drawer and router monitoring tab available even when Simple mode has no pool event list, and lets Simple mode refresh the active status in the background instead of leaving Telegram API in the initial pending state.

<a name="1.842"></a>
# [1.842] - 28 Jun 2026

- Adds an on-demand router CPU/RSS monitoring tab inside the existing history drawer, extends update rollback backups to restore runtime state, keys, proxy configs, lists and mode files, preserves existing Shadowsocks/Trojan configs during install, and treats unused protocol slots as neutral instead of failed.
- Lowers router load from long-monitor findings: ipset DNS refresh now defaults to 4 parallel jobs with IPv6 DNS resolving in auto mode only when active IPv6 traffic already uses bypass IPv6 sets, ipset-triggered YouTube prefetch runs only when due and is skipped in simple mode, scheduler/ipset YouTube prefetch uses CPU/load guards and smaller batches, and pool probing now uses stricter CPU/loadavg pacing with smaller quality samples.

<a name="1.841"></a>
# [1.841] - 28 Jun 2026

- Makes Simple mode load a lightweight web/bot runtime: pool/probe/custom-check UI helpers, route tools, Telegram pool UI, call-learning, auto-failover, and YouTube prefetch are lazy-loaded only when advanced components are enabled, while Simple initial render avoids probe/custom status refresh work.

<a name="1.840"></a>
# [1.840] - 28 Jun 2026

- Adds a subscription client User-Agent and text Accept header for HWID subscription downloads, fixing providers that reject default Python requests with 403 while keeping the import scoped to the selected protocol.

<a name="1.839"></a>
# [1.839] - 28 Jun 2026

- Makes S99unblock route/ipset signatures portable on Keenetic systems without `cksum`, so runtime Vless dedupe and priority refresh throttling use file size/mtime signatures instead of falling back to an always-due blank state.

<a name="1.838"></a>
# [1.838] - 28 Jun 2026

- Fixes router HWID detection for Keenetic `hw_id`, guards automatic HWID subscription refresh under high CPU/RSS, backs off background checks after CPU-busy samples, quiets bot-side ipset lock contention, avoids retaining the large pool API cache under high RSS, and throttles runtime Vless dedupe when route/ipset signatures are unchanged.

<a name="1.837"></a>
# [1.837] - 26 Jun 2026

- Fixes the key subscription tab layout after the router HWID switch: desktop import cards align to the same height, and the mobile subscription button stays inside its card.

<a name="1.836"></a>
# [1.836] - 26 Jun 2026

- Reduces idle router load by backing off Telegram call-learning scans when no call clients are active, reusing route/intersection summaries by file/runtime signatures, avoiding extra pool API deep copies, and releasing large static web assets after responses.

<a name="1.835"></a>
# [1.835] - 26 Jun 2026

- Reduces idle router CPU/RSS pressure by making web response cleanup threshold-based, stretching web/pool status caches, throttling runtime route overlap refreshes, sampling router CPU without blocking, and skipping scheduled heavy YouTube prefetch when CPU is already busy.

<a name="1.834"></a>
# [1.834] - 26 Jun 2026

- Reduces web-status CPU load by reusing fresh successful active-key probe results instead of rechecking Telegram and YouTube on every status refresh while the cache is still current.

<a name="1.833"></a>
# [1.833] - 26 Jun 2026

- Reduces idle router CPU spikes by throttling Telegram auto-failover checks during the failure grace window, recording successful active Telegram probes, and caching the idle web pool API payload briefly.

<a name="1.832"></a>
# [1.832] - 26 Jun 2026

- Reduces router CPU spikes by skipping Telegram auto-failover checks while the active key has a recent successful Telegram probe, adding a CPU guard to background failover/drift watchdogs, and deferring YouTube UDP/QUIC drift fast-add while active streams are detected.

<a name="1.831"></a>
# [1.831] - 26 Jun 2026

- Releases heavy web JSON API payload references after responses and runs the existing RSS-threshold cleanup path, reducing idle memory left behind by status/pool/service API polling without adding cleanup work when RSS is already low.

<a name="1.830"></a>
# [1.830] - 26 Jun 2026

- Adds Chrome Remote Desktop and Google auth/API helper domains to protected Vless priority refreshes, reducing runtime overlap windows where broad YouTube ranges could temporarily capture exact CRD/auth destinations.

<a name="1.829"></a>
# [1.829] - 26 Jun 2026

- Keeps route-intersection diagnostics aligned with protected Vless priority ipsets, so Chrome Remote Desktop/Telegram exact Google IP pins do not appear as unsafe overlaps with broad YouTube ranges while real unprotected route conflicts still surface.

<a name="1.828"></a>
# [1.828] - 26 Jun 2026

- Restores Telegram/WhatsApp/Discord call routing through the existing narrow TPROXY path while keeping client-wide UDP routing disabled, renames the S99unblock background loop to `scheduler` for clearer diagnostics, and clears status/pool summary caches during RSS cleanup to reduce idle memory pressure.

<a name="1.827"></a>
# [1.827] - 26 Jun 2026

- Prevents Telegram auto-failover from selecting a key that is already active in another protocol, so Vless 1 and Vless 2 do not collapse onto the same subscription key and break both routes under concurrent traffic.

<a name="1.826"></a>
# [1.826] - 25 Jun 2026

- Lets Telegram auto-failover keep counting confirmed failures while the Vless traffic guard is active, then bypasses the guard after repeated failures so stuck CRD/Codex/Telegram outages do not block recovery indefinitely.

<a name="1.825"></a>
# [1.825] - 25 Jun 2026

- Removes the hardcoded api.telegram.org DNS override from generated Xray configs, letting Telegram API resolve normally like pool-probe checks. This prevents keys from passing temporary probes but timing out in the active bot/Xray config.

<a name="1.824"></a>
# [1.824] - 25 Jun 2026

- Clears stale GitHub update environment before downloads and before restarting the bot, preventing a later web update from reusing an older archive cache while reporting a newer commit.

<a name="1.823"></a>
# [1.823] - 25 Jun 2026

- Uses the GitHub archive/API fallback first after raw GitHub downloads have failed once, so web updates do not wait on every runtime file through a slow or broken local SOCKS route.

<a name="1.822"></a>
# [1.822] - 25 Jun 2026

- Stops the current pool-probe batch promptly when a key is applied, and refuses to restart the main Xray while a temporary pool probe is still active.
- Moves Reality endpoint repair behind startup/recent-success/repeated-failure guards so one transient Telegram timeout cannot rewrite the active Vless endpoint and break Chrome Remote Desktop/Codex traffic.
- Adds quieter cleanup paths for web rendering, event history, and the memory watchdog to reduce idle RSS growth after heavy UI/status work.

<a name="1.821"></a>
# [1.821] - 25 Jun 2026

- Refreshes pending active protocol statuses with a short backoff, so transient Telegram/YouTube probe warnings clear automatically instead of waiting for the full normal status interval.

<a name="1.820"></a>
# [1.820] - 25 Jun 2026

- Makes `S99unblock` stop stale fallback scheduler processes more robustly after consecutive updates, preventing duplicate refresh loops from staying alive.

<a name="1.819"></a>
# [1.819] - 25 Jun 2026

- Streams conntrack scans in Telegram call-learning and YouTube stream guards instead of loading the whole table into memory.
- Filters Telegram call-learning UDP candidates earlier and avoids rebuilding temporary client sets for every flow, reducing idle RSS churn when call-learning clients are present.

<a name="1.818"></a>
# [1.818] - 25 Jun 2026

- Adds optional router HWID forwarding for subscription imports and stores HWID-enabled subscriptions for daily sync.
- Scopes YouTube failover stream guard to the route being repaired, so Vless 1 traffic no longer blocks Vless 2 YouTube key switching.

<a name="1.817"></a>
# [1.817] - 25 Jun 2026

- Stops auto Telegram call-learning from applying active-media-only UDP candidates, which can include unrelated heavy UDP traffic from a Telegram-signaled client.
- Keeps automatic call learning limited to UDP clusters correlated with Telegram signaling.

<a name="1.816"></a>
# [1.816] - 25 Jun 2026

- Blocks Telegram call-learning from adding non-Telegram destinations that are already present in regular route ipsets.
- Orders Telegram call TPROXY rules so signal routes are handled first, regular bypass routes return next, and learned call destinations are applied last.

<a name="1.815"></a>
# [1.815] - 25 Jun 2026

- Requires Basic auth for non-local web hosts when `web_auth_token` is empty or missing, preventing public tunnel access from opening the interface without a password.
- Updates the installer and example config wording so the web password is treated as the known router web password, not a separate generated secret.

<a name="1.814"></a>
# [1.814] - 25 Jun 2026

- Makes Telegram call-learning and Telegram-call TPROXY opt-in instead of enabled by default, protecting normal Vless/Vless 2 site routing from learned call traffic.
- Updates install, bootstrap, update-generated UDP policy, and example config defaults to keep call-learning disabled unless explicitly enabled later.

<a name="1.813"></a>
# [1.813] - 25 Jun 2026

- Disables client-wide Telegram call UDP TPROXY routing while keeping destination-based learned Telegram call routing active.
- Writes `BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED=0` into generated UDP policy files so old runtime config cannot re-enable broad client UDP capture after restart.

<a name="1.812"></a>
# [1.812] - 25 Jun 2026

- Adds RuTracker domains to the protected Vless priority resolver so their exact IPs are placed into the priority set for whichever Vless list owns them.
- Keeps RuTracker on Vless 2 even when broad Cloudflare ranges remain in Vless 1 for other saved user routes.

<a name="1.811"></a>
# [1.811] - 25 Jun 2026

- Adds `unblockvlesspriority` and `unblockvless2priority` ipsets for protected service domains so exact route selections win over broad shared Google/YouTube CIDRs.
- Installs top NAT redirects for those priority sets before the normal Vless/Vless 2 redirects, keeping Chrome Remote Desktop on its configured route even when YouTube uses Vless 2.
- Keeps the priority sets out of the normal UI ipset counters while refreshing them from the existing ipset refresh/runtime-dedupe path.

<a name="1.810"></a>
# [1.810] - 25 Jun 2026

- Adds a protected-domain pass after Vless/Vless 2 ipset dedupe so Chrome Remote Desktop/Chromoting domains keep the route selected by the actual route list instead of being pulled into the YouTube route by shared Google IPs.
- Applies the same protected-domain pass in the lightweight scheduler dedupe, preventing runtime refresh from undoing the route a few seconds later.
- Moves RuTracker entries out of Vless 1 and into Vless 2 so GitHub updates preserve the intended split.

<a name="1.809"></a>
# [1.809] - 25 Jun 2026

- Replaces the router-card `Swap` line with Flash/Entware storage usage from `/opt`, keeping the check inside the existing lightweight status cache.
- Uses a text badge fallback for custom checks without an icon so protocol status rows never render a broken empty image.
- Shortens README install, DNS, UDP/443, and realtime-call sections and refreshes the documented web UI behavior.

<a name="1.808"></a>
# [1.808] - 24 Jun 2026

- Increases the router CPU percentage sampling window to avoid false `0/50/100%` jumps on low-tick routers while keeping the metric cached and lightweight.
- Keeps the 1.807 YouTube route-detection fix: active YouTube list detection now follows all supported route files instead of assuming Vless 2.

<a name="1.807"></a>
# [1.807] - 24 Jun 2026

- Shows real router CPU usage as a percentage in the web router block instead of displaying load average as `Нагрузка CPU`.
- Makes YouTube route detection count active route-list markers across Shadowsocks, Vmess, Vless 1, Vless 2, and Trojan in the bot watchdog, redirect priority script, scheduler, and ipset refresh.
- Keeps Vless/Vless 2 runtime overlap cleanup scoped to the actual YouTube list so moving YouTube to another protocol no longer makes Vless 1 the implicit fallback winner.

<a name="1.806"></a>
# [1.806] - 24 Jun 2026

- Polishes web update timing text, router health notes, proxy/call status wording, and ipset count labels/order.
- Makes the pool summary count checked rows and service successes per visible pool entry, including duplicate keys.
- Moves RuTracker route entries from Vless 2 to Vless 1 after Vless 2 connectivity timeout and adds ZazaZa image CDN domains to Vless 1.

<a name="1.805"></a>
# [1.805] - 24 Jun 2026

- Adds a bounded cache-restore phase before YouTube fast/full warmup: recently quality-approved YouTube edge IPs are put back into the active route ipset immediately after install/update/startup.
- Keeps the restore external and short-lived, requiring prior successful quality checks and preserving shared Google/Chrome Remote Desktop protection.

<a name="1.804"></a>
# [1.804] - 24 Jun 2026

- Expands the short external YouTube fast-warm set with `youtube.com`, `i.ytimg.com`, `s.ytimg.com`, and `yt3.ggpht.com`, matching the browser timing bottlenecks seen on the homepage.
- Adds a live YouTube watch URL to the external watch-edge warmup and raises the bounded watch page/edge-host defaults from 1/6 to 2/8 without adding persistent bot work.

<a name="1.803"></a>
# [1.803] - 24 Jun 2026

- Keeps the web header/top status banner refreshing automatically while the page is visible, using a low-frequency idle `/api/status` poll and the existing faster poll for pending checks, commands, and pool probes.

<a name="1.802"></a>
# [1.802] - 24 Jun 2026

- Makes install/update YouTube fast-warm prefer fresh bootstrap DNS candidates before older cache entries, so stale cache cannot crowd out the speed scoring pass.
- Scores already-present YouTube runtime ipset entries during fast-warm triggers, keeping the diagnostics internal while avoiding extra scheduler load.

<a name="1.801"></a>
# [1.801] - 24 Jun 2026

- Scores YouTube edge prefetch candidates through the active route before adding them to runtime ipsets, rejecting slow, TLS EOF, and timeout-prone addresses against the 1000 ms target.
- Uses a short fast-warm host set for install/update/first-run triggers while leaving scheduler runs on the full rotating host list.
- Skips shared Google/Chrome Remote Desktop hosts in YouTube edge prefetch so CRD/auth traffic is not pulled into YouTube route ipsets.

<a name="1.800"></a>
# [1.800] - 24 Jun 2026

- Stops cron-triggered `S99unblock refresh` calls from starting a second ipset refresh while the persistent unblock scheduler is already running.
- Runs scheduler-owned ipset refreshes with quiet lock-busy handling, reducing repeated `unblock_ipset is already running` log noise while preserving bot-side already-running detection for direct UDP/QUIC drift refreshes.
- Keeps the YouTube/CRD route lists unchanged; this release only tightens refresh coordination and does not add persistent bot memory load.

<a name="1.799"></a>
# [1.799] - 24 Jun 2026

- Stops `/api/pools?include_keys=1` from returning raw pool keys while keeping full keys visible in the server-rendered web form for copying.
- Treats a single transient quick-probe miss on the YouTube homepage or googlevideo endpoint as a soft diagnostic issue instead of failing otherwise working pool keys.
- Disables the persistent memory timeline by default and migrates existing default-enabled configs back to off while keeping the memory watchdog active.

<a name="1.798"></a>
# [1.798] - 24 Jun 2026

- Adds a delayed external YouTube edge prefetch retry after bot restart when the immediate post-update run skipped because memory was temporarily low or the runner lock was busy.
- Keeps the memory guard unchanged; the retry runs as a short background process and does not add persistent Telegram-bot RSS.

<a name="1.797"></a>
# [1.797] - 24 Jun 2026

- Runs the external YouTube edge prefetch once at the end of clean `script.sh -install`, then once after the first installer form starts the main bot, so fresh installs get the same immediate warmup path as GitHub updates.
- Keeps the existing `Post-update` prefetch path unchanged and covered by smoke tests.
- Updates README with the current GitHub bootstrap command and explains that YouTube warmup modules/config are installed from the first setup without adding persistent bot RSS.

<a name="1.796"></a>
# [1.796] - 24 Jun 2026

- Widens the short external YouTube prefetch pass from 4 to 12 bootstrap hosts, so homepage, player API, image/static, manifest, and video/live startup hosts warm in one run.
- Raises the bounded prefetch resolver/candidate/address caps from 12/32/8 to 32/64/16 for that external runner only.
- Migrates old default prefetch limits during update while leaving custom non-default values alone, keeping the work out of the long-running bot process.

<a name="1.795"></a>
# [1.795] - 24 Jun 2026

- Adds a bounded external YouTube watch-page warmup that fetches one public watch page through the active route SOCKS port, extracts real `*.googlevideo.com` / `*.c.youtube.com` edge hosts, and preloads their IPs into the active YouTube ipsets.
- Extends the external YouTube prefetch bootstrap set with mobile, player API, manifest, image, and static hosts used during homepage, video, and live startup.
- Merges the new bootstrap hosts at runner time even when an existing router config still has the older host tuple, without rewriting user route lists or keeping extra work in the bot RSS.

<a name="1.794"></a>
# [1.794] - 24 Jun 2026

- Extends the built-in memory timeline from 240 to 720 events, giving roughly 12 hours of one-minute samples without adding a separate monitor process.
- Skips scheduled ipset refresh attempts while a fresh `unblock_ipset.sh` lock is active, reducing repeated `already running` log spam and refresh collisions.
- Reworks the `ipset swap failed` fallback to save a backup, flush the target set, and restore the newly resolved entries before falling back to the old additive behavior.

<a name="1.793"></a>
# [1.793] - 24 Jun 2026

- Keeps Chrome Remote Desktop out of automatic route profiles and catalog drift repair, so YouTube profile actions do not re-add CRD signaling/auth routes to Vless.
- Removes Chrome Remote Desktop-specific entries from the default Vless route list while keeping the manual service preset available.
- Retries the external YouTube edge prefetch after low-memory skips in 180 seconds instead of waiting for the normal 15-minute interval.

<a name="1.792"></a>
# [1.792] - 24 Jun 2026

- Adds gzip compression for large HTML, JSON, and text web responses when the browser advertises `Accept-Encoding: gzip`.
- Supports `HEAD` requests through the existing web handler, returning headers without a response body instead of `501 Unsupported method`.
- Keeps web responses on `Connection: close` while reducing the payload sent through the external Netcraze HTTPS endpoint.

<a name="1.791"></a>
# [1.791] - 24 Jun 2026

- Lowers the external YouTube edge prefetch low-memory guard from 160 MB to 125 MB available.
- Migrates the old 160 MB config value during update, so the short external runner can warm YouTube on routers where post-update available memory is around 135 MB.
- Keeps the prefetch work outside the long-running bot process to avoid adding persistent bot RSS.

<a name="1.790"></a>
# [1.790] - 24 Jun 2026

- Moves YouTube edge prefetch from the long-running bot thread into a short external runner.
- Runs the YouTube edge prefetch after post-update ipset refresh and from the existing S99unblock scheduler.
- Lets the web/router health status read the external runner status JSON while keeping the runner protected by a lock and low-memory guard.

<a name="1.789"></a>
# [1.789] - 23 Jun 2026

- Forces memory cleanup when YouTube edge prefetch is skipped because bot RSS is above the prefetch guard.
- Keeps the high-RSS path from doing DNS/ipset work while still giving the bot a chance to return memory before the idle restart threshold.

<a name="1.788"></a>
# [1.788] - 23 Jun 2026

- Keeps visible YouTube status as working when a pool probe has `yt_ok=true`, even if diagnostic stability metrics are marked unstable.
- Leaves YouTube quality score penalties intact so sorting can still prefer cleaner keys without showing a false web warning.

<a name="1.787"></a>
# [1.787] - 23 Jun 2026

- Adds a bounded YouTube edge prefetcher that warms the active YouTube route ipsets from a tiny DNS/cache sample.
- Skips prefetch work while the bot is busy, router memory is low, or the bot RSS is near the idle restart threshold.
- Keeps YouTube edge IPs exclusive to the active YouTube route ipsets and exposes compact prefetch status in router health.

<a name="1.786"></a>
# [1.786] - 23 Jun 2026

- Keeps YouTube keys marked stable when required YouTube endpoints pass but several bootstrap diagnostics hit transient TLS/EOF failures.
- Preserves the diagnostic signal in metrics/error text so repeated bootstrap failures remain visible without incorrectly downgrading otherwise usable keys.
- Adds observed YouTube edge IPs from the router drift log to the static Vless2 route catalog, reducing first-load misses before the UDP/QUIC watchdog catches up.

<a name="1.785"></a>
# [1.785] - 23 Jun 2026

- Enables HTTP/TLS/QUIC sniffing on transparent Xray inbounds so routed YouTube traffic keeps domain context instead of relying only on locally resolved IPs, reducing slow TLS startup on transparent routing.

<a name="1.784"></a>
# [1.784] - 23 Jun 2026

- Reduces router memory drift from repeated status refreshes, repeated UDP/QUIC fast-add events, Telegram polling errors, event-history trimming, and orphaned ipset scheduler processes.

<a name="1.783"></a>
# [1.783] - 23 Jun 2026

- Stops including Telegram call-learning state in the frequently polled status API; the dedicated endpoint remains available while status payloads stay smaller.

<a name="1.782"></a>
# [1.782] - 23 Jun 2026

- Compacts router health JSON by keeping full Xray diagnostics out of healthy status API responses and avoiding duplicate Telegram-call health data, reducing web status memory churn.

<a name="1.781"></a>
# [1.781] - 23 Jun 2026

- Escapes the web JavaScript regex inside the Python template so router startup logs stay clean on Python versions that warn about invalid escape sequences.

<a name="1.780"></a>
# [1.780] - 23 Jun 2026

- Fixes pool-probe cache downgrades, strict probe boolean parsing, YouTube soft-diagnostic stability, unblock-list save whitelisting, subscription session cleanup, and Telegram auth log redaction.

<a name="1.779"></a>
# [1.779] - 23 Jun 2026

- Stores completed Telegram pool-probe failures as failed instead of unknown, so checked keys show a cross when Telegram API does not pass.

<a name="1.778"></a>
# [1.778] - 23 Jun 2026

- Renders unknown pool-row Telegram and YouTube states as unknown instead of treating truthy cache sentinels as OK, keeping HTML and API pool tables consistent after a fresh probe.

<a name="1.777"></a>
# [1.777] - 23 Jun 2026

- Shows active-key Telegram and YouTube icons from the actual key probe/status even when service routes are split across protocols, and makes pool Telegram checks require Bot API success so non-working Telegram keys no longer appear green.

<a name="1.776"></a>
# [1.776] - 23 Jun 2026

- Keeps Telegram and YouTube as permanent pool-row columns while scoping protocol summaries to complete route-list assignments, so partial route overlaps no longer make a protocol look partially working.

<a name="1.775"></a>
# [1.775] - 23 Jun 2026

- Scopes Telegram and YouTube pool-row statuses to the protocol route list, so cached checks from another service no longer show green icons where that service is not assigned.

<a name="1.774"></a>
# [1.774] - 23 Jun 2026

- Fixes false Telegram pending status when another service is still rechecking, limits live status polling to real pending states, adds a release metadata guard for CHANGELOG synchronization, and declares reproducible npm scripts for UI smoke tests.

<a name="1.773"></a>
# [1.773] - 23 Jun 2026

- Adds the current 173.194.73.198 YouTube CDN edge so www.youtube.com and redirector.googlevideo.com stay in the Vless2 route without overlapping Chrome Remote Desktop routes, keeps RuTracker only in Vless2, and stops GitHub updates from auto-repairing service route drift so user route lists are preserved unless changed explicitly.

<a name="1.772"></a>
# [1.772] - 22 Jun 2026

- Keeps desktop service-route popovers inside the viewport in GitHub UI smoke by rechecking placement after drop-up positioning and limiting popover height as a fallback.

<a name="1.771"></a>
# [1.771] - 22 Jun 2026

- Adds the overnight router memory and YouTube timing monitor to the repository and syncs version metadata so GitHub CI passes after the diagnostics commit.

<a name="1.769"></a>
# [1.769] - 22 Jun 2026

- Reduces key-pool probe RSS peaks with per-key and per-batch memory checkpoints, retry/trim handling before pausing on high RSS, final temporary xray cleanup, compact probe-cache error text, and extra memory timeline markers.

<a name="1.768"></a>
# [1.768] - 22 Jun 2026

- Scopes custom pool-check columns to complete service routes only, so services that only have partial/shared route overlap in Vless 2 do not appear as Vless 2 pool checks.

<a name="1.767"></a>
# [1.767] - 22 Jun 2026

- Renders unstable-but-working YouTube pool probes with the YouTube icon instead of a misleading exclamation mark and scopes custom service columns to each protocol's pool, so Vless 2 no longer inherits ChatGPT/Discord/Cloud columns that are not assigned to it.

<a name="1.766"></a>
# [1.766] - 22 Jun 2026

- Keeps shared service route entries such as accounts.google.com in every service route that needs them, preventing GitHub updates from moving YouTube bootstrap domains back to Vless 1 and making YouTube look partial.

<a name="1.765"></a>
# [1.765] - 22 Jun 2026

- Refreshes Telegram and YouTube service route catalogs from current public lists, preserves router-verified route entries for GitHub reinstalls, and normalizes mobile status-page spacing to an 8px rhythm without changing desktop layout.

<a name="1.764"></a>
# [1.764] - 22 Jun 2026

- Keeps the 1.763 lazy check-panel memory work and makes the CI UI smoke scroll desktop route popovers before measuring viewport clipping.

<a name="1.763"></a>
# [1.763] - 22 Jun 2026

- Lazy-loads protocol check panels and calls libc `malloc_trim` after heavy web cleanups, reducing router RSS spikes during web UI navigation.

<a name="1.762"></a>
# [1.762] - 22 Jun 2026

- Scopes deferred key-pool refreshes to only the protocol that needs rows, reducing `/api/pools` payload churn during protocol tab transitions.

<a name="1.761"></a>
# [1.761] - 22 Jun 2026

- Defers key-pool row HTML rendering to `/api/pools` for protocol panels and the initial key page, lowering web UI memory spikes while preserving Telegram/YouTube pool badges.

<a name="1.760"></a>
# [1.760] - 21 Jun 2026

- Restores Telegram and YouTube badges in every key-pool row while making protocol status route-scoped, so VLESS can be working by Telegram and VLESS2 by YouTube without showing a misleading partial badge.

<a name="1.759"></a>
# [1.759] - 21 Jun 2026

- Shows only route-assigned Telegram/YouTube columns in key pool tables and removes all/any-service pool summary wording, so split VLESS/VLESS2 pools are not presented as partial.

<a name="1.758"></a>
# [1.758] - 21 Jun 2026

- Scopes Telegram and YouTube pool status badges to the protocols where those services are actually routed, so unrelated protocol pools show not-applicable instead of misleading ok/fail states.

<a name="1.757"></a>
# [1.757] - 21 Jun 2026

- Self-updates the router-side /opt/root/script.sh during direct SSH updates so the update_status fix is deployed for future script.sh -update runs and rollback can restore the previous updater script.

<a name="1.756"></a>
# [1.756] - 21 Jun 2026

- Redacts credential IDs from install/apply failure diagnostics while preserving copyable full keys in the web UI, records direct SSH script updates in update_status.json, and rejects out-of-range browser_port values during installer setup.

<a name="1.755"></a>
# [1.755] - 21 Jun 2026

- Keeps raw proxy keys out of web action JSON responses, removes a local secret signature from the tracked secret scanner in favor of an optional local denylist, and makes core YouTube/Telegram service healthchecks reject HTTP 4xx responses instead of treating deny pages as working service access.

<a name="1.754"></a>
# [1.754] - 21 Jun 2026

- Treats transient YouTube endpoint timeouts as unstable warnings when the key has enough successful YouTube signals, confirms Telegram through lightweight SOCKS TCP probes to Telegram app endpoints when API/web checks are inconclusive, records pool-probe infrastructure failures as unknown/timeout, and exports a safe PATH in unblock refresh scripts so routers can always find system utilities such as sleep.

<a name="1.753"></a>
# [1.753] - 21 Jun 2026

- Allows the topbar status message to wrap to a bounded two-line note, saves route lists with background route application to avoid mobile fetch failures, and skips duplicate identical keys during pool probes.

<a name="1.752"></a>
# [1.752] - 21 Jun 2026

- Cleans empty ipset refresh lock directories with no active PID, fixing routers where a stale lock without pid kept automatic refreshes blocked.

<a name="1.751"></a>
# [1.751] - 21 Jun 2026

- Recovers stale ipset refresh locks even when an old unblock_ipset process is still alive, preventing automatic dnsmasq/ipset refreshes from staying blocked for days.

<a name="1.750"></a>
# [1.750] - 21 Jun 2026

- Removes unused legacy root assets and obsolete helper docs, and ignores local Codex/agent workspace files to keep GitHub releases clean.

<a name="1.744"></a>
# [1.744] - 21 Jun 2026

- Keeps Android/OS connectivity-check domains out of route files, dnsmasq rules, and static ipset refreshes, and cleans stale entries during route repair so clients do not report Wi-Fi without internet after updates.

<a name="1.743"></a>
# [1.743] - 21 Jun 2026

- Redacts IPv4 addresses from Telegram call learning events while preserving compact counts, so event history no longer exposes learned call IPs.

<a name="1.742"></a>
# [1.742] - 21 Jun 2026

- Stops optional quick pool probes after the first short YouTube pass instead of retrying the whole quick profile, reducing the time spent on slow Vless 2 candidates.

<a name="1.741"></a>
# [1.741] - 21 Jun 2026

- Separates the active pool-probe RSS ceiling from the lower post-pool restart threshold, allowing quick pool checks to continue after the first warmup keys while preserving post-pool memory cleanup.

<a name="1.740"></a>
# [1.740] - 21 Jun 2026

- Switches pool probes to the quick YouTube health profile by default and keeps long retry timeouts out of that fast path, so one slow candidate cannot hold a temporary Xray probe for minutes.
- Keeps the full YouTube health profile available for active-key and explicit diagnostic checks.

<a name="1.730"></a>
# [1.730] - 20 Jun 2026

- Generalizes realtime call routing from Telegram to Telegram, WhatsApp, and Discord with compact service-specific signal route sets and per-protocol TPROXY handling.
- Adds compact 50-row event history diagnostics, including auto-failover and stream-guard details without losing zero-valued fields.
- Requires repeated confirmed failures before automatic key failover, reducing route churn during transient YouTube or Telegram hiccups.
- Polishes the web UI spacing, typography, status blocks, and README coverage for the dnsmasq/DNS Override and realtime-call workflow.

<a name="1.726"></a>
# [1.726] - 17 Jun 2026

- Runs the lightweight runtime Vless/Vless 2 ipset dedupe every 10 seconds while checking full refresh due state separately, shrinking transient shared Google IP routing windows without adding heavy DNS refresh load.

<a name="1.725"></a>
# [1.725] - 17 Jun 2026

- Keeps runtime Vless/Vless 2 dnsmasq ipsets deduped after stale scheduler locks and preserved refresh sets, reducing slow YouTube starts caused by shared Google video IPs taking the wrong route.

<a name="1.724"></a>
# [1.724] - 17 Jun 2026

- Blocks QUIC/UDP 443 by default for YouTube-only routes so mobile clients fall back to the stable TCP bypass path immediately instead of waiting on failed QUIC attempts.

<a name="1.723"></a>
# [1.723] - 16 Jun 2026

- Adds observed YouTube short-link and thumbnail edge IPs to the YouTube/Vless 2 route so cached client DNS cannot miss the bypass on the first video load.

<a name="1.722"></a>
# [1.722] - 16 Jun 2026

- Pins YouTube player API frontends to the YouTube/Vless 2 route so selected videos do not wait on mismatched Google service routing before playback starts.

<a name="1.721"></a>
# [1.721] - 16 Jun 2026

- Fixes web rollback so version/readme metadata and scheduler files are restored together with Python runtime files.

<a name="1.720"></a>
# [1.720] - 16 Jun 2026

- Cleans Vixie cron metadata comments while reinstalling the active root crontab, preventing repeated GitHub update and rollback tests from accumulating duplicate generated comments.

<a name="1.719"></a>
# [1.719] - 16 Jun 2026

- Fixes GitHub update validation for the new `S99unblock refresh` crontab entry, so v1.718+ updates no longer fail while staging the cron file.

<a name="1.718"></a>
# [1.718] - 16 Jun 2026

- Documented dnsmasq operation, UDP/TPROXY responsibilities, and pool maintenance behavior.
- Installs the scheduled refresh into the active Entware root crontab through `S99unblock refresh` during install, update and rollback, so route intersections are cleaned on schedule instead of depending only on the saved `/opt/etc/crontab` file.
- Turns `S99unblock` into a lightweight fallback scheduler: 15-minute refresh for ndnproxy fallback, hourly full refresh for dnsmasq after a recent-status guard, plus 30-second runtime dedupe for `Vless 1` / `Vless 2` ipsets.

<a name="1.717"></a>
# [1.717] - 16 Jun 2026

- Lets long post-update ipset refreshes finish in the background instead of killing them, preventing partially swapped runtime sets while still letting web updates restart the bot promptly.

<a name="1.716"></a>
# [1.716] - 16 Jun 2026

- Uses BusyBox-safe CR stripping when detecting route markers, so YouTube protocol detection and runtime ipset dedupe work with CRLF route files on the router.

<a name="1.715"></a>
# [1.715] - 16 Jun 2026

- Bounds the post-update `unblock_update.sh` refresh and removes the duplicate foreground rebuild, so web updates can complete and restart the bot even when dnsmasq route resolution is slow.

<a name="1.714"></a>
# [1.714] - 16 Jun 2026

- Adds short `dig` timeouts to local DNS lookups during `unblock_ipset.sh`, so a slow or stalled domain resolve cannot hold GitHub update, DNS Override refresh, or scheduled dnsmasq route rebuilds for minutes.

<a name="1.713"></a>
# [1.713] - 16 Jun 2026

- Normalizes CRLF route files while detecting the selected YouTube protocol for runtime ipset dedupe, so DNS-resolved Google/YouTube IPs are removed from the non-YouTube Vless set instead of remaining in both `unblockvless` and `unblockvless2`.

<a name="1.712"></a>
# [1.712] - 16 Jun 2026

- Refreshes `dnsmasq`/`ipset` state immediately after DNS Override is enabled or disabled, so the router card no longer keeps stale ndnproxy refresh data after switching back to dnsmasq.
- Repairs preserved service route files during install/update when the shared service catalog gains new addresses, keeping YouTube, Telegram, Gemini and Chrome Remote Desktop fully assigned to their selected protocol instead of showing as partially routed.
- Keeps the source route files and live runtime ipsets free of cross-protocol intersections after GitHub update and rollback cycles.

<a name="1.711"></a>
# [1.711] - 15 Jun 2026

- Keeps DNS Override under the existing web and Telegram buttons, without hidden enable/disable during update or reboot.
- Preserves DNS Override during Entware DNS preparation and reports ndnproxy as a fallback until the user activates dnsmasq with the button and reboots.
- Removes the post-1.709 YouTube watch/manifest ipset preload and relies on route files plus dnsmasq dynamic ipset fills, avoiding long `dig`/`curl` bursts on the router.
- Reduces web status CPU pressure by reusing ipset counts from the refresh status file and caching router health/API status longer.
- Coalesces repeated Keenetic netfilter hook runs, removes external DNS probes from the UDP/QUIC drift watchdog, caches stream-guard conntrack scans, and skips full YouTube failover checks while the active key has a fresh successful probe.
- Fixes YouTube probe cache updates for the `yt_watch_ok` metric so background failover does not keep retrying after a successful watch-page healthcheck.

<a name="1.710"></a>
# [1.710] - 15 Jun 2026

- Adds a real YouTube watch-page healthcheck for the selected route.
- Follows live YouTube HLS manifests into variant playlists during ipset preload, adding real live chunk `googlevideo` hosts to the selected YouTube route.

<a name="1.704"></a>
# [1.704] - 12 Jun 2026

- Stores paused pool-probe resume queues as protocol plus key hash instead of raw proxy URLs, resolving them from current pools when checks resume.
- Splits pool-probe memory handling into a hard pause threshold and a low-memory slow mode, so checks continue carefully when the router still has enough RAM.
- Limits heavy YouTube throughput samples per run and skips them on low memory, while keeping lightweight service checks for every key.
- Requires a measured throughput sample before showing `Стабильно` or `Быстро` in the web pool UI.

<a name="1.703"></a>
# [1.703] - 11 Jun 2026

- Adds pool quality scoring for YouTube keys using Telegram/YouTube latency plus a short throughput sample, with 1600p and 4K thresholds for `Стабильно` and `Быстро`.
- Shows the quality label and measured details on hover before applying a key, without exposing the full key in the web UI.
- Uses the YouTube quality score when ordering failover candidates and the web pool's YouTube-first sort mode.

<a name="1.702"></a>
# [1.702] - 11 Jun 2026

- Reduces the default `unblock_ipset.sh` DNS parallelism so scheduled ipset refreshes put less pressure on the router while YouTube is playing.
- Defers UDP/QUIC drift-triggered ipset refreshes while active Vless/Vless2 stream traffic is visible, avoiding extra route rebuilds during playback.
- Gives ipset refresh commands a longer timeout and cleans lock metadata on early temp-directory failures.

<a name="1.701"></a>
# [1.701] - 11 Jun 2026

- Fixes `unblock_ipset.sh` cleanup so the lock directory is removed after a successful refresh even when PID metadata files were written.
- Reduces stale ipset lock recovery to 15 minutes, matching the cron refresh interval.

<a name="1.700"></a>
# [1.700] - 11 Jun 2026

- Recovers stale `unblock_ipset.sh` locks automatically when no recorded process is alive, allowing cron and watchdog refreshes to resume after an interrupted run.
- Logs UDP/QUIC drift refresh attempts as skipped when `unblock_ipset.sh` reports an active lock instead of reporting a false successful refresh.

<a name="1.699"></a>
# [1.699] - 09 Jun 2026

- Refreshes YouTube and Googlevideo route ipsets with a short priority cooldown when DNS drift is detected, avoiding stale transparent routes while the selected key itself still checks as working.

<a name="1.698"></a>
# [1.698] - 08 Jun 2026

- Enables page scrolling on desktop while long web commands such as update or rollback are running, so the command log no longer compresses the whole interface.
- Stretches the Status page router card to the bottom of the dashboard row, removing the visual gap before the service command panel.

<a name="1.697"></a>
# [1.697] - 08 Jun 2026

- Tightens wide desktop spacing between the header title, Telegram API status, theme switcher, version badge, and status attention block.
- Lets the Status quick-key panel fill the remaining desktop viewport instead of leaving unused space below it.
- Compacts the Key Check state card into a single row on desktop.
- Renames the Meta route shortcut label to `Instagram / Facebook`.

<a name="1.696"></a>
# [1.696] - 08 Jun 2026

- Fixes desktop status layout so router and key-pool cards keep their full height and service commands no longer overlap them.
- Moves the top Telegram API status closer to the title area and keeps the status subtitle on one line on desktop.
- Makes wide desktop service commands use a denser grid, reducing the gap before the quick key block.
- Lets Key and Subscription subtabs size to their content while the Check subtab uses internal scrolling for dense service controls.
- Renders bypass list headings as `Список обхода · <протокол>` on one line.
- Fixes the UI smoke failure where compact desktop service blocks intercepted the active-mode button click.

<a name="1.695"></a>
# [1.695] - 08 Jun 2026

- Moves event history out of the Status page flow into a drawer opened from the router card.
- Keeps the main page, protocol, and list headings on one line with consistent sizing across Status, Keys, and Lists.
- Constrains desktop Status, Keys, and Lists views to the viewport while allowing dense tables, route lists, and event history to scroll inside their own areas.

<a name="1.694"></a>
# [1.694] - 06 Jun 2026

- Creates a rollback script for regular GitHub updates and keeps a `/opt/root/bypass-last-update-rollback.sh` pointer to the latest update backup.
- Backs up installer and service files during update so rollback can restore the previous runtime instead of only restoring ipset scripts.

<a name="1.693"></a>
# [1.693] - 06 Jun 2026

- Makes UDP/QUIC policy follow the list that contains YouTube routes instead of treating Vless 2 as a special case.
- If YouTube is moved to Vless 1, Vless 2, Vmess, Trojan, or Shadowsocks, that protocol keeps UDP/QUIC open while the other protocol lists keep their configured fallback behavior.
- Pins Telegram's observed mobile TCP 5222 traffic to the Vless route that carries Telegram, alongside the existing mobile push ports.

<a name="1.692"></a>
# [1.692] - 06 Jun 2026

- Uses canonical `iptables` REDIRECT `--to-ports` rules when installing and deleting transparent proxy redirects.
- UDP/QUIC policy changes can now remove stale protocol-specific redirects reliably instead of leaving old rules active after updates or live policy changes.

<a name="1.691"></a>
# [1.691] - 06 Jun 2026

- A transient EOF on the primary YouTube healthcheck no longer marks a key as failed when other YouTube CDN endpoints already confirm the route.
- This reduces false negative YouTube statuses in the pool and web checks while keeping hard failures visible when the route is actually down.

<a name="1.690"></a>
# [1.690] - 06 Jun 2026

- Added hard-failure recovery for the active YouTube route before failover can switch keys.
- Reality endpoint repair now falls back to external DNS resolvers when local DNS misses the current endpoint domain.
- YouTube route recovery refreshes ipset routes after the current key is restored.
- Pool and apply-time YouTube checks now keep the concrete failed endpoint detail instead of replacing it with a generic primary-endpoint message.
- Added Telegram IPv6 DC ranges to the service catalog so mobile clients fall back to the routed IPv4 path faster when IPv6 cannot be proxied transparently.

<a name="1.689"></a>
# [1.689] - 06 Jun 2026

- Runs a second `unblock_update.sh` after the proxy core starts during GitHub updates.
- This lets the YouTube watch-page preload use the live Vless/Vless 2 SOCKS port and fill dynamic `*.googlevideo.com` CDN entries immediately after an update.

<a name="1.688"></a>
# [1.688] - 06 Jun 2026

- Added the observed missing YouTube video CDN range to the YouTube route.
- Added the `yt4.googleusercontent.com` avatar host without broad `googleusercontent.com` routing.
- Mirrored sampled YouTube video/image IPv6 CDN networks into the protocol IPv6 fallback sets so browsers fall back to the routed IPv4 path instead of bypassing through IPv6.

<a name="1.687"></a>
# [1.687] - 04 Jun 2026

- Added Reality endpoint repair to the active YouTube route before Vless/Vless 2 YouTube failover restarts Xray or switches keys.
- The temporary endpoint probe now validates the affected service, so YouTube repairs are checked with YouTube healthchecks instead of Telegram API.

<a name="1.686"></a>
# [1.686] - 04 Jun 2026

- Added active Reality endpoint repair for both Vless routes before Telegram auto-failover switches keys.
- The repair probes the current key endpoint, SNI domain, and SNI A-records through a temporary Xray and keeps the current key when any endpoint restores Telegram API.

<a name="1.685"></a>
# [1.685] - 04 Jun 2026

- Kept proxy connection addresses from the keys while using SNI/Host only as TLS/Reality serverName, restoring Vless/Vless 2/VMess/Trojan keys whose URL host is an IP address.
- Added a startup hold so Telegram auto-failover does not switch keys while Xray is still stabilizing after a bot restart.

<a name="1.684"></a>
# [1.684] - 04 Jun 2026

- Restored normal UDP transparent routing for the main Vless service sets while keeping the YouTube/QUIC reject mirror separate.

<a name="1.683"></a>
# [1.683] - 03 Jun 2026

- Kept Telegram routes out of the UDP/QUIC reject mirror so media and calls are not forced into browser-style QUIC fallback.

<a name="1.680"></a>
# [1.680] - 02 Jun 2026

- Scheduled rollback/app-mode restarts directly as detached shell processes so they survive web command workers.

<a name="1.679"></a>
# [1.679] - 02 Jun 2026

- Made rollback/app-mode restarts detached from the running bot process so restored files actually take effect after rollback.

<a name="1.678"></a>
# [1.678] - 02 Jun 2026

- Kept Xray health checks compatible with older updaters that do not yet download `xray_compat_runtime.py`.
- Added fallback startup validation so updates from 1.676/1.677 do not stop the bot when the new helper module is missing.

<a name="1.677"></a>
# [1.677] - 02 Jun 2026

- Added Xray config validation before core proxy restarts during updates/startup.
- Made rollback report core proxy validation and service health instead of only restoring files.
- Recorded pool-probe timeouts as `unknown/timeout` so stale HTTP requests cannot mark working keys as failed.
- Added core proxy health to the router status card in the web UI.

<a name="1.676"></a>
# [1.676] - 01 Jun 2026

- Removed the deprecated `allowInsecure` field from generated Xray outbound configs so Xray 26 can start.
- Clarified service route menu labels: preset checks that will be added on selection now show “перенести сюда” for the current protocol too.

<a name="1.675"></a>
# [1.675] - 01 Jun 2026

- Moved service route web glue into `web_route_tools_runtime.py` to reduce `bot.py` coupling.
- Changed desktop service route menus into popover layers while keeping mobile menus in-flow.
- Added a service-route fragment API and refreshed route/check changes without a full page reload.

<a name="1.674"></a>
# [1.674] - 01 Jun 2026

- Changed service route cards into one service button with a protocol menu.
- Selecting a protocol now adds the preset pool check when it is not already enabled.
- Moved preset check removal into the same service menu and hid duplicate preset delete cards below the route catalog.

<a name="1.673"></a>
# [1.673] - 01 Jun 2026

- Refined service route cards into menu-style protocol buttons and restored real Telegram/YouTube icons in the route catalog.

<a name="1.672"></a>
# [1.672] - 01 Jun 2026

- Added service route profiles, route intersection repair, event history for all protocols, persistent update progress, UI smoke checks for route controls, and CI secret scanning.
- Kept YouTube checks at the existing availability level; no real video playback probe was added.

<a name="2.2.0"></a>
# [2.2.0 - Поддержка KeenOS 4+](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.2.0) - 01 Oct 2023

- Добавлена поддержка KeenOS 4+
- Добавлена проверка версии KeenOS при установке и обновлении
- Обновлены основные скрипты
- Уменьшен размер бота
- Установка, обновление и удаление теперь идет через скрипт
- IP роутера вычисляется автоматически
- При обновлении через скрипт порты берутся из bot_config.py
- Добавлен список VPN в bot_config.py
- Поправлены скрипты для ключей trojan и v2ray
- Исправлена ошибка, если в имени VPN был дефис
- Проверена работа VPN на KeenOS 4+
- Добавлено сообщение перед перезагрузкой мостов
- Добавлено исправление при превышении списка > 4096 символов
- Добавлены информационные смайлы в меню

## What's Changed
* Update changelog for "2.1.9" by [@github-actions](https://github.com/github-actions) in https://github.com/znetworkx/bypass_keenetic/pull/13
* Update README.md by [@znetworkx](https://github.com/znetworkx) in https://github.com/znetworkx/bypass_keenetic/pull/15
* Update README.md by [@znetworkx](https://github.com/znetworkx) in https://github.com/znetworkx/bypass_keenetic/pull/16
* Update README.md by [@znetworkx](https://github.com/znetworkx) in https://github.com/znetworkx/bypass_keenetic/pull/17


**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.1.9...2.2.0

[Changes][2.2.0]


<a name="2.1.9"></a>
# [2.1.9 - fix vpn service, wireguard](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.1.9) - 03 May 2023

- *Исправлены ошибки в скриптах для VPN*
- *Протестирована и настроена работа с Wireguard*
- *Исправлены мелкие ошибки*
- *В бот добавлена информация `где брать ключи`*
- *Обновлено меню*
- *Добавлены реквизиты для доната*

**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.1.8...2.1.9

[Changes][2.1.9]


<a name="2.1.8"></a>
# [2.1.8 - fix update via bot, etc](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.1.8) - 01 Apr 2023

- Добавлено: вывод сообщений при обновлении
- Исправлены мелкие ошибки

## What's Changed
* Update changelog for "2.1.6" by [@github-actions](https://github.com/github-actions) in https://github.com/znetworkx/bypass_keenetic/pull/8
* Update changelog for "2.1.7" by [@github-actions](https://github.com/github-actions) in https://github.com/znetworkx/bypass_keenetic/pull/9


**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.1.7...2.1.8

[Changes][2.1.8]


<a name="2.1.7"></a>
# [2.1.7 - added update via bot](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.1.7) - 30 Mar 2023

- добавлено обновление через бот /update

**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.1.6...2.1.7

[Changes][2.1.7]


<a name="2.1.6"></a>
# [2.1.6 - fix check files exist](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.1.6) - 30 Mar 2023

- Добавлена проверка наличия файлов для vpn.

## What's Changed
* Update changelog for 2.1.1 by [@github-actions](https://github.com/github-actions) in https://github.com/znetworkx/bypass_keenetic/pull/4
* 2.1.5 by [@znetworkx](https://github.com/znetworkx) in https://github.com/znetworkx/bypass_keenetic/pull/5
* Update changelog for 2.1.5 by [@github-actions](https://github.com/github-actions) in https://github.com/znetworkx/bypass_keenetic/pull/7

## New Contributors
* [@github-actions](https://github.com/github-actions) made their first contribution in https://github.com/znetworkx/bypass_keenetic/pull/4

**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.1.5...2.1.6

[Changes][2.1.6]


<a name="2.1.5"></a>
# [2.1.5 - update bot, vpn service, etc](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.1.5) - 29 Mar 2023

- Добавлено меню сервис в бота
- Добавлена возможность перезагрузки мостов
- Добавлена возможность перезагрузки роутера
- Добавлена возможность просмотра обновлений
- Добавлена возможность вкл/выкл dns override
- Добавлена будущая возможность обновления через бот
- Доработан сервис VPN для более одного подключения
- Исправлены правила, из-за которых были отвалы TSMB и RCI API
- Доработан конфиг dnsmasq.conf
- Из установки убрано автоматическое получение ключей TOR
- Доработаны скрипты .sh
- Добавлен файл changelog.md
- Добавлена возможность выбора репозитория при установке

**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.1.1...2.1.5

[Changes][2.1.5]


<a name="2.1.1"></a>
# [2.1.1 - fix bot menu](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.1.1) - 04 Mar 2023

[#1](https://github.com/znetworkx/bypass_keenetic/issues/1) 2.1.1 - Изменено отображение меню добавления адресов в список, теперь компактно.

## What's Changed
* 2.1.0 - add VPN service, fix bugs by [@znetworkx](https://github.com/znetworkx) in https://github.com/znetworkx/bypass_keenetic/pull/1

## New Contributors
* [@znetworkx](https://github.com/znetworkx) made their first contribution in https://github.com/znetworkx/bypass_keenetic/pull/1

**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.1.0...2.1.1

[Changes][2.1.1]


<a name="2.1.0"></a>
# [2.1.0 - add VPN service, fix bugs](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.1.0) - 04 Mar 2023

[#8](https://github.com/znetworkx/bypass_keenetic/issues/8) 2.1.0
- Добавлена поддержка VPN
- Исправлены мелкие ошибки

**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.0.2...2.1.0

[Changes][2.1.0]


<a name="2.0.2"></a>
# [2.0.2 - update bot, add v2ray, trojan vpn, etc](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.0.2) - 02 Mar 2023

### 2.0.2 - NEW BOT 

- update bot, version 2.0.2
- update scripts, fix syntax posix
- add v2ray, trojan service
- add help how to install new 2.0.0 version or update

**Full Changelog**: https://github.com/znetworkx/bypass_keenetic/compare/2.0.0...2.0.2

[Changes][2.0.2]


<a name="2.0.0"></a>
# [2.0.0 - first release bot 2.0](https://github.com/znetworkx/bypass_keenetic/releases/tag/2.0.0) - 04 Mar 2023

- Добавлены сервисы v2ray. trojan vpn
- обновлены скрипты

[Changes][2.0.0]


[2.2.0]: https://github.com/znetworkx/bypass_keenetic/compare/2.1.9...2.2.0
[2.1.9]: https://github.com/znetworkx/bypass_keenetic/compare/2.1.8...2.1.9
[2.1.8]: https://github.com/znetworkx/bypass_keenetic/compare/2.1.7...2.1.8
[2.1.7]: https://github.com/znetworkx/bypass_keenetic/compare/2.1.6...2.1.7
[2.1.6]: https://github.com/znetworkx/bypass_keenetic/compare/2.1.5...2.1.6
[2.1.5]: https://github.com/znetworkx/bypass_keenetic/compare/2.1.1...2.1.5
[2.1.1]: https://github.com/znetworkx/bypass_keenetic/compare/2.1.0...2.1.1
[2.1.0]: https://github.com/znetworkx/bypass_keenetic/compare/2.0.2...2.1.0
[2.0.2]: https://github.com/znetworkx/bypass_keenetic/compare/2.0.0...2.0.2
[2.0.0]: https://github.com/znetworkx/bypass_keenetic/tree/2.0.0

<!-- Generated by https://github.com/rhysd/changelog-from-release v3.7.1 -->
