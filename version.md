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
