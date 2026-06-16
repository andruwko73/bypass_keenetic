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
