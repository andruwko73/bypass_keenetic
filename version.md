*v1.647 (25 May 2026) -* main
*Refreshes pool probe cache semantics, retries transient custom-service probe errors, and treats one confirmed YouTube endpoint as enough for noisy keys.*

*v1.646 (25 May 2026) -* main
*Synchronizes custom service checks with add-to-bypass buttons and local service route lists so every checked preset can be added consistently.*

*v1.645 (25 May 2026) -* main
*Makes Discord pool status depend on the primary Discord gateway API probe and invalidates older lenient Discord check results.*

*v1.644 (25 May 2026) -* main
*Retries transient Telegram sendMessage failures after resetting the Bot API HTTP session and redacts Bot API tokens from surfaced send errors.*

*v1.643 (25 May 2026) -* main
*Invalidates pool probe cache entries written before the Telegram API DNS pin was removed, so old false Telegram failures are recalculated.*

*v1.642 (25 May 2026) -* main
*Stops temporary pool probes from pinning api.telegram.org to an outdated Telegram IP, preventing working keys from being marked as Telegram failures.*

*v1.641 (25 May 2026) -* main
*Versions the key-pool probe cache so stale ChatGPT/Codex and Claude results from older probe logic cannot keep marking region-blocked keys as working.*

*v1.640 (25 May 2026) -* main
*Includes the release history file in router GitHub updates so installed diagnostics show the same latest version notes as the repository.*

*v1.639 (25 May 2026) -* main
*Makes ChatGPT/Codex and Claude pool statuses depend on their primary API reachability checks so auxiliary domains cannot make region-blocked keys look healthy.*

*v1.638 (25 May 2026) -* main
*Tightens ChatGPT/Codex and Claude service probes so regional 403 responses and unavailable-region pages are treated as failures, while unauthenticated API 401 responses still confirm reachability.*

*v1.637 (25 May 2026) -* main
*Hardens Telegram pool checks and failover so API-only keys are not treated as working Telegram keys unless web.telegram.org or t.me also responds through the proxy.*

*v1.636 (24 May 2026) -* main
*Adds exact Telegram Mini App wallet and TON Connect endpoints, including wallet.tg, Tonkeeper, TonAPI bridge, and wallet registry routes, so ndnproxy/static ipset mode does not miss required subdomains.*

*v1.635 (24 May 2026) -* main
*Adds observed Codex/ChatGPT asset and feature-flag endpoints to the shared route catalog, Vless list, and service-check tests so Codex UI metadata can load through the bypass.*

*v1.634 (24 May 2026) -* main
*Keeps transient protocol placeholders from being shown as Telegram API failures and makes the status attention card treat explicit failure text as a warning.*

*v1.633 (24 May 2026) -* main
*Expands Claude and Gemini service routes, wires them into the service-add catalog and QUIC fallback policy, and keeps their custom checks, Vless list entries, and tests synchronized.*

*v1.632 (24 May 2026) -* main
*Adds observed Telegram Mini Apps CDN edges to Vless1 and enables QUIC fallback for the Telegram route set so WebView traffic returns to proxied TCP faster.*

*v1.631 (24 May 2026) -* main
*Expands Telegram Mini Apps routing with observed WebView/CDN dependencies and keeps the Telegram service button in sync with the shipped Vless list.*

*v1.630 (24 May 2026) -* main
*Adds missing Telegram Mini Apps and ChatGPT/Codex route dependencies, keeps shared Telegram/TON edge IPs out of the UDP/QUIC reject mirror, and adds IPv6 fallback sets so ndnproxy clients quickly return to proxied IPv4 for bypass domains.*

*v1.629 (22 May 2026) -* main
*Deduplicates router memory watchdog text so the idle restart threshold and active countdown are not shown as two separate warnings, and restores the README note that the bot/bootstrap does not replace Entware installation.*

*v1.628 (22 May 2026) -* main
*Shows the pending idle memory watchdog restart in router health and refreshes pool service statuses immediately after a key is selected.*

*v1.627 (21 May 2026) -* main
*Prevented GitHub update workers from leaking command-worker mode into the restarted Telegram bot service.*

*v1.626 (21 May 2026) -* main
*Protected active YouTube Vless2 streams from background switching while still allowing dead-key failover, made Vless2 status match the selected bot mode, and kept the active pool row pinned above the real source order.*

*v1.624 (20 May 2026) -* main
*Restored Playwright Linux dependency installation for CI after confirming Chromium needs system libraries such as libnspr4 on Ubuntu.*

*v1.623 (20 May 2026) -* main
*Pinned CI UI smoke to current Playwright 1.60.0 and removed the apt dependency install from the workflow so Chromium smoke can run reliably on ubuntu-latest.*

*v1.622 (20 May 2026) -* main
*Added a real Playwright UI smoke run to CI using a local fixture server, covering desktop, compact, mobile, lazy protocol panels, and pool key masking.*

*v1.621 (20 May 2026) -* main
*Reduced Vless pool panel payloads by using short `key_id` form actions instead of embedding full pool keys, accepted both `proto` and `protocol` API aliases, and added deterministic post-pool memory cleanup restart retries.*

*v1.620 (20 May 2026) -* main
*Prevented timed-out pool probes from recording false failures or overwriting newer successful probe results, refreshed the legacy `/opt/etc/bot/bot.py` path as a link to `main.py`, and moved QUIC/UDP mirror policy generation into `service_catalog.py`.*

*v1.619 (20 May 2026) -* main
*Exposed ChatGPT / Codex in the service-add buttons and `/getlist` source catalog, using the same updated route list as the custom service check preset.*

*v1.618 (20 May 2026) -* main
*Added ChatGPT/Codex edge domains and observed edge IPs to Vless 1, and mirrored OpenAI/Codex QUIC targets into the UDP block set so the desktop app falls back to TCP through the proxy for usage-limit requests.*

*v1.617 (20 May 2026) -* main
*Restored the existing manual Vless 2 bypass list entries, including Rutracker, while keeping the Vless 1 priority and CRD fallback IP fixes from v1.616.*

*v1.616 (20 May 2026) -* main
*Prioritized Vless 1 transparent TCP redirects ahead of Vless 2 when the same Google IP appears in both sets, added CRD/mtalk fallback IPs to Vless 1, and cleaned the Vless 2 default list down to YouTube routes.*

*v1.615 (19 May 2026) -* main
*Fixed Chrome Remote Desktop routing by keeping CRD signaling on Vless 1 instead of xray direct exceptions, and expanded the CRD route list with auth, gstatic, mtalk, and talkgadget endpoints.*

*v1.614 (19 May 2026) -* main
*Объединены дополнительные проверки ChatGPT и Codex в один сервис ChatGPT / Codex; старая отдельная проверка Codex автоматически мигрирует в объединённую*
*Добавлен Chrome Remote Desktop в список обхода Vless 1, пресеты дополнительных проверок и кнопки добавления сервисов в списки*

*v1.613 (18 May 2026) -* main

*Restored concise pool-check progress in the header while keeping detailed progress in the key-pool card.*

*v1.605 (18 May 2026) -* main

*Synced ChatGPT/Codex route lists with Vless1 and added a separate Codex custom service check.*

*v1.604 (18 May 2026) -* main
*Moved stale Vless2 YouTube confirmation to a background check that accepts 2 of 3 YouTube endpoints, keeping the web status responsive while correcting missing pool cache results.*

*v1.603 (18 May 2026) -* main
*Confirmed the current Vless2 YouTube port when its pool cache is missing or stale, so the interface can show a working YouTube key immediately after updates.*

*v1.602 (18 May 2026) -* main
*Rechecked the permanent Vless2 YouTube port before showing a cached pool failure, preventing stale pool results from marking a working YouTube key as broken.*

*v1.601 (18 May 2026) -* main
*Pinned GitHub updates to the resolved commit SHA so all router files are downloaded from one fresh immutable revision instead of a potentially cached main branch.*

*v1.600 (18 May 2026) -* main
*Kept the detected ipset type synchronized for both 100-ipset.sh and 100-redirect.sh during GitHub updates.*

*v1.599 (18 May 2026) -* main
*Fixed GitHub update preparation so the router keeps the detected ipset type in 100-redirect.sh during self-update.*

*v1.598 (18 May 2026) -* main
*Added smart QUIC/UDP sets for both Vless lists, throttled full pool checks when router CPU is high, lowered the idle memory restart threshold to match post-pool cleanup, disabled inactive pool probe controls, and covered web Basic auth checks in smoke tests.*

*v1.597 (18 May 2026) -* main
*Made pool YouTube checks retry with the longer proxy timeout budget before marking Vless keys as YouTube failures, so slow-but-working pool keys are no longer shown as broken after one short probe.*

*v1.596 (18 May 2026) -* main
*Clarified router DNS diagnostics for ndnproxy installations, removed duplicate ipset completion text from the router health note, and updated the README with the current DNS/ipset and Vless 2 YouTube routing behavior.*

*v1.595 (18 May 2026) -* main
*Translated router DNS/ipset health details to Russian, made Vless 2 YouTube checks less twitchy on slow keys, and split Vless 2 UDP rejection from broader TCP CDN routing for YouTube under ndnproxy.*

*v1.594 (17 May 2026) -* main
*Made DNS updates aware of Keenetic ndnproxy, refreshed ipsets with a lock and temporary-set swap to avoid empty windows, scheduled 15-minute ipset refreshes, and exposed DNS/ipset health in the web status.*

*v1.593 (17 May 2026) -* main
*Narrowed the Vless 2 YouTube route from broad Google API and IP ranges to explicit YouTube domains, and routed Chrome Remote Desktop SNI directly when shared Google IPs still enter the transparent proxy.*

*v1.592 (17 May 2026) -* main
*Optimized large key-pool status updates, pool probing queues, pool API payloads, and bounded log-tail reading for lower router CPU and memory use.*

*v1.591 (17 May 2026) -* main
*Silenced harmless web response write tracebacks when a browser closes the connection during refreshes.*

*v1.590 (17 May 2026) -* main
*Added an idle memory watchdog restart for sustained Python RSS growth and made router memory text emphasize available RAM instead of treating reclaimable cache as lost memory.*

*v1.589 (16 May 2026) -* main
*Stabilized the Vless 2 YouTube monitor by using a durable googlevideo endpoint, confirming the current key before failover, and avoiding Telegram-only verification for Vless 2 while the bot mode is Vless 1.*

*v1.588 (16 May 2026) -* main
*Require Vless 2 YouTube recovery to confirm youtube.com, googlevideo.com, and ytimg.com on the permanent Vless 2 port before accepting a candidate key.*

*v1.587 (16 May 2026) -* main
*Split frequent web status polling from heavy pool row snapshots, added a dedicated pool snapshot API, added automatic post-pool memory recovery when Python RSS remains high after cleanup, and added service-specific failover that keeps Telegram on the selected bot mode while recovering YouTube on Vless 2.*

*v1.586 (15 May 2026) -* main
*Switched YouTube health checks to the lightweight generate_204 endpoint so the web panel and bot status do not report false YouTube failures from a slow full homepage load.*

*v1.585 (15 May 2026) -* main
*Synchronized the tested router Vless 1 and Vless 2 domain lists, keeping YouTube domains on Vless 2 and enforcing LF line endings for text lists.*

*v1.584 (15 May 2026) -* main
*Kept YouTube routing on Vless 2, normalized unblock list lines before generating dnsmasq rules, and prevented CRLF markers from breaking domain-to-ipset entries.*

*v1.583 (15 May 2026) -* main
*Added a memory watchdog with guarded service restart, explicit cleanup after heavy web/pool/update operations, lazy loading for pool probing/repo updates/web template rendering, and token redaction in Telegram API diagnostics.*

*v1.582 (13 May 2026) -* main
*Fixed CI history checkout for version smoke tests and added Telegram menu/button smoke coverage before GitHub update verification.*

*v1.581 (13 May 2026) -* main
*Hardened installer CSRF and password handling, fixed uninstall cleanup, synced bootstrap versioning, ignored runtime status dumps, and added CI smoke checks.*

*v1.580 (13 May 2026) -* main
*Made full key-pool checks finish the whole queue on low-memory routers by lowering the default memory guard, auto-resuming paused checks, and updating checked timestamps even for timeout/SOCKS startup failures.*

*v1.579 (12 May 2026) -* main
*Reduced Web only startup overhead by skipping Telegram imports, limited Python thread stack reservations, and stopped runtime bytecode/log growth on the router flash.*

*v1.578 (12 May 2026) -* main
*Split app runtime mode and router health logic out of bot.py for safer maintenance.*

*v1.577 (12 May 2026) -* main
*Refreshed README screenshots from Advanced mode with sanitized desktop and mobile captures.*

*v1.576 (12 May 2026) -* main
*Aligned the Web only version badge with the regular header, refreshed the cache revision, and updated README screenshots for desktop and mobile.*

*v1.575 (12 May 2026) -* main
*Made Web only mode hide Telegram-only header/status controls and focus copy, with a compact header centered on router health, key pool, and service commands.*

*v1.574 (12 May 2026) -* main
*Removed the duplicate Telegram API status card, renamed the active mode card, swapped it with Quick start, aligned the status dashboard into compact columns, moved Stop check next to Check pool, and kept the no-issues summary shorter.*

*v1.573 (12 May 2026) -* main
*Equalized the desktop status dashboard columns so the left and right cards align with the service command grid.*

*v1.572 (12 May 2026) -* main
*Fixed pool-check resume after low-memory pauses, restored static assets during web rollback, tightened the desktop health/pool layout, themed pool sorting, and made pool search match display names immediately.*

*v1.571 (12 May 2026) -* main
*Added low-memory pool-check pausing and manual stop, a cached router health card, pool search/sort controls, Telegram-first failover ordering, update rollback from the web UI, and a Playwright UI smoke test while keeping the existing features intact.*

*v1.570 (12 May 2026) -* main
*Kept the Liquid Glass side navigation aligned with the overview card on desktop while preserving the global lens above the header.*

*v1.569 (12 May 2026) -* main
*Normalized the header-to-content spacing and made pool checks stop temporary xray probes when router memory drops below the safe threshold.*

*v1.568 (12 May 2026) -* main
*Raised the Liquid Glass lens above the compact topbar so it remains visible while moving across the header.*

*v1.567 (12 May 2026) -* main
*Optimized web assets and router load: static cached JS with inline runtime config, pool checks pause and resume around key application, auto-failover waits for active pool checks, fixed waits during key install were replaced with readiness checks, and Liquid Glass avoids pointer work outside the glass theme.*

*v1.566 (11 May 2026) -* main
*Made header dropdowns more opaque so they read clearly above the page content.*

*v1.560 (11 May 2026) -* main
*Liquid Glass visual pass: softer surfaces, calmer borders and hover states, clearer active controls, and a lighter lens treatment while keeping the mobile lens size.*

*v1.559 (11 May 2026) -* main
*Topbar pool-check status now grows vertically for long progress text instead of clipping wrapped lines.*

*v1.558 (11 May 2026) -* main
*Доработаны фоновые команды и пул ключей: веб-команды получили сохраняемый статус после рестарта, update/remove блокируются общим job-файлом с Telegram, JSON пулов и проверок пишется атомарно, auto-failover сначала перебирает ключи текущего Vless/Vless 2, а веб применяет ключ из пула с проверкой сразу. Веб-страница вынесла CSS/JS в отдельные ассеты, status API не прячет старт проверки пула за кэшем, Liquid Glass получил более лёгкую лупу по всему интерфейсу.*

*v1.556 (11 May 2026) -* main
*Шапка веб-интерфейса на промежуточных desktop-разрешениях получила больше места под кнопки режима и темы, чтобы текст не обрезался при Liquid Glass.*

*v1.555 (11 May 2026) -* main
*Веб-интерфейс теперь лениво загружает тяжелые панели протоколов: первичная страница отдаёт только активную вкладку, а остальные пулы подтягиваются при открытии, чтобы снизить расход памяти и ускорить старт страницы.*

*v1.554 (11 May 2026) -* main
*Liquid Glass на ПК теперь реагирует на события мыши и пера независимо от touch/coarse media-query, чтобы эффект появлялся при движении курсора, а не только после нажатия.*

*v1.553 (11 May 2026) -* main
*Снижена нагрузка на роутер: статусный API кэшируется на короткий интервал, технические опросы больше не засоряют лог, polling веб-интерфейса останавливается сразу после завершения проверки пула, auto-failover проверяет связь реже и с меньшими таймаутами. Liquid Glass снова реагирует на движение мыши, а шапка плотнее укладывается на промежуточных разрешениях.*

*v1.552 (11 May 2026) -* main
*Доработан веб-интерфейс: компактная шапка на ПК, облегчённый Liquid Glass, уменьшенная лупа, восстановлен значок удаления ключа в мобильном пуле. Transparent inbound теперь принимает TCP и UDP.*

*v1.549 (10 May 2026) -* main
*Liquid Glass теперь воспринимает нижнее меню, боковую навигацию и сегментированные вкладки как единые стеклянные поверхности: лупа движется по группе непрерывнее, а локальный ореол на touch-экранах стал легче*

*v1.548 (10 May 2026) -* main
*Liquid Glass получил жёсткий сброс световых слоёв после жеста, а активная кнопка нижнего меню стала спокойным индикатором вкладки вместо похожего на залипшую лупу свечения*

*v1.547 (10 May 2026) -* main
*На touch-экранах Liquid Glass больше не оставляет hover-выделение на кнопках после жеста: hover-стили включаются только для мыши, а focus-подсветка не запускается от касания*

*v1.546 (10 May 2026) -* main
*Liquid Glass стал безопаснее при прокрутке: во время scroll лупа сбрасывается, а кнопка не применяется случайно при отпускании пальца*
*После начала прокрутки Liquid Glass больше не включает лупу на последующих touchmove этого же жеста*

*v1.545 (10 May 2026) -* main
*Лог обновления стал тише: сообщение о скачивании через локальный SOCKS-порт выводится один раз, а не для каждого файла*

*v1.544 (10 May 2026) -* main
*На touch-экранах убран залипающий hover-ореол Liquid Glass: подсветка кнопки теперь живёт только во время активного движения*

*v1.543 (10 May 2026) -* main
*Лупа Liquid Glass теперь не уходит за края экрана: у нижнего меню и верхней панели пузырь смещается внутрь viewport, оставаясь видимым целиком*

*v1.542 (10 May 2026) -* main
*После применения кнопки через Liquid Glass подсветка и лупа сразу сбрасываются, чтобы на кнопке не оставался засвет*

*v1.541 (10 May 2026) -* main
*Liquid Glass применяет обычную UI-кнопку при отпускании после движения над ней, но не автозапускает submit/danger-команды*

*v1.540 (10 May 2026) -* main
*Liquid Glass стал легче: убраны динамическое вращение и растяжение лупы, свет теперь стабильно падает сверху слева без визуального подлагивания*

*v1.539 (10 May 2026) -* main
*Liquid Glass стал отзывчивее: лупа больше не догоняет курсор с задержкой, а на мобильном отключена тяжёлая анимация кромки*

*v1.538 (10 May 2026) -* main
*Liquid Glass получил плавное догоняющее движение лупы и живую световую кромку, чтобы пузырь перетекал по интерфейсу мягче*

*v1.537 (10 May 2026) -* main
*Лупа Liquid Glass увеличена ещё в полтора раза, а верхняя панель режима и темы получила общий glass-слой без разрыва между кнопками*

*v1.536 (10 May 2026) -* main
*Пузырь Liquid Glass увеличен и сделан прозрачнее: крупная лупа сильнее похожа на выпуклое стекло, но меньше закрывает текст заливкой*

*v1.535 (10 May 2026) -* main
*Liquid Glass стал ближе к стеклянному материалу: добавлена световая кромка, локальное преломление на кнопках и мягкое растяжение лупы по направлению движения*

*v1.534 (10 May 2026) -* main
*Лупа Liquid Glass увеличена: эффект стал заметнее на телефоне и ПК без возврата тяжёлых бликов и задержек*

*v1.533 (10 May 2026) -* main
*Liquid Glass снова отслеживает касания на мобильных устройствах: включена легкая прозрачная линза без принудительного отключения touch-режима*

*v1.532 (09 May 2026) -* main
*Telegram-бот сбрасывает HTTP-сессию Bot API после смены прокси и ошибок polling, чтобы не зависать на старом SOCKS-порту*

*v1.531 (09 May 2026) -* main
*На touch-устройствах Liquid Glass переведен в статичный режим без движущейся линзы, чтобы мобильное меню не ломалось и не тормозило*

*v1.530 (09 May 2026) -* main
*Liquid Glass сделан легче для мобильного: линза уменьшена, стала прозрачнее, а движение обрабатывается через requestAnimationFrame без лишнего отставания*

*v1.529 (09 May 2026) -* main
*Liquid Glass переведен на единую глобальную линзу: эффект плавно переходит между кнопками и не залипает на мобильном меню*

*v1.528 (09 May 2026) -* main
*Исправлено зависание блока «Результат» после запуска веб-команд: успешные сообщения скрываются автоматически, а статус команды продолжает обновляться отдельно*

*v1.527 (09 May 2026) -* main
*Усилен Liquid Glass: добавлена видимая lens-область под курсором/пальцем и touch-tracking для мобильного интерфейса*

*v1.526 (09 May 2026) -* main
- *Добавлена отдельная тема интерфейса Liquid Glass с живыми бликами, blur/fallback и настройками доступности*
- *Первичная настройка installer теперь сохраняет только параметры Telegram-бота и web-доступа; пул ключей доступен после запуска основного интерфейса*
- *Обновлены скриншоты README по текущему интерфейсу единой ветки*
- *Исправлено перекрытие меню выбора режима работы программы на ПК*
- *Подготовлен переход проекта на единственную ветку main*
- *Обновления из старых веток переводят установку на unified-версию main без сброса ключей, пулов и списков*
- *Старые имена веток сохраняются как совместимые ref-метки для плавной миграции уже установленных версий*
- *Добавлен выбор режима программы: Простой, Сложный, Web only*
- *Простой режим скрывает пул ключей и расширенные проверки, Сложный оставляет полный Telegram-бот и web-интерфейс*
- *Web only запускает тот же web-интерфейс без Telegram-бота*
- *Версия считается по числу коммитов ветки с префиксом v1.*

- [Releases](https://github.com/andruwko73/bypass_keenetic/releases) | [Changelog](https://github.com/andruwko73/bypass_keenetic/blob/main/CHANGELOG.md) | [Issues](https://github.com/andruwko73/bypass_keenetic/issues)
