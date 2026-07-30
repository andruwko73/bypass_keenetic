*v1.987 (30 Jul 2026) -* main

*Routes each sniffed Chrome Remote Desktop domain to the one user-managed protocol list that owns that domain, so intentionally split Google/CRD catalogs keep working across shared edge IPs.*

*Leaves ambiguous or unowned domains, explicit IP entries, UDP/STUN, call routing, and ipsets under the existing policy; adds split-catalog and per-domain ownership regressions after live-update verification.*

*Keeps Chrome Remote Desktop online when a shared Google edge IP is already owned by the priority YouTube/Vless 2 ipset: Xray now recovers TCP signaling by the sniffed service domain and sends it to the single route list that fully owns Chrome Remote Desktop.*

*Creates the cross-inbound rule only for an unambiguous complete service assignment, reuses the existing Xray process and transparent inbounds, and leaves UDP/STUN, call routing, ipsets, and user-managed route files unchanged.*

*Uses the same guarded policy during normal configuration builds and recovery after an update, with regressions for shared IP ownership, ambiguous ownership, and atomic config recovery.*

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
