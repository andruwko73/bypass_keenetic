*v1.760 (21 Jun 2026) -* main

*Restores Telegram and YouTube badges in every key-pool row while making protocol status route-scoped, so VLESS can be working by Telegram and VLESS2 by YouTube without showing a misleading partial badge.*

*v1.759 (21 Jun 2026) -* main

*Shows only route-assigned Telegram/YouTube columns in key pool tables and removes all/any-service pool summary wording, so split VLESS/VLESS2 pools are not presented as partial.*

*v1.758 (21 Jun 2026) -* main

*Scopes Telegram and YouTube pool status badges to the protocols where those services are actually routed, so unrelated protocol pools show not-applicable instead of misleading ok/fail states.*

*v1.757 (21 Jun 2026) -* main

*Self-updates the router-side /opt/root/script.sh during direct SSH updates so the update_status fix is deployed for future script.sh -update runs and rollback can restore the previous updater script.*

*v1.756 (21 Jun 2026) -* main

*Redacts credential IDs from install/apply failure diagnostics while preserving copyable full keys in the web UI, records direct SSH script updates in update_status.json, and rejects out-of-range browser_port values during installer setup.*

*v1.755 (21 Jun 2026) -* main

*Keeps raw proxy keys out of web action JSON responses, moves local secret-literal checks to an optional private denylist, and rejects HTTP 4xx deny responses in core YouTube/Telegram healthchecks so pool probes do not mark blocked service pages as working access.*

*v1.754 (21 Jun 2026) -* main

*Marks one-off YouTube endpoint timeouts as unstable when other YouTube signals pass, confirms Telegram with lightweight SOCKS TCP probes to app endpoints when API/web checks are inconclusive, keeps temporary pool-probe infrastructure failures from poisoning key status, and fixes router refresh scripts when system utilities are missing from PATH.*

*v1.753 (21 Jun 2026) -* main

*Lets the topbar status use a bounded multi-line note, makes web route-list saves return before background route application, and avoids checking identical pool keys twice.*

*v1.752 (21 Jun 2026) -* main

*Recovers empty ipset refresh lock directories that have no active PID, covering routers where the lock mtime is not enough to identify a stale refresh.*

*v1.751 (21 Jun 2026) -* main

*Lets stale ipset refresh locks recover when an old unblock_ipset process is still alive, so automatic route refreshes do not stay stuck for days after a hung resolver run.*

*v1.750 (21 Jun 2026) -* main

*Removes unused legacy root assets and obsolete helper docs, and keeps local Codex/agent workspace files ignored so they cannot slip into GitHub releases.*

*v1.749 (21 Jun 2026) -* main

*Clears completed web update command blocks on the first post-update render, so the green "last command" panel no longer remains visible until the page is manually refreshed.*

*v1.748 (21 Jun 2026) -* main

*Makes the web update timer use a conservative successful-update median instead of a misleading remaining-time countdown, and suppresses background status refresh checks while a web update command is running to reduce router CPU spikes during installation.*

*v1.747 (21 Jun 2026) -* main

*Accepts and stores the YouTube short-link health metric in the key probe cache, fixing active key status refresh after the YouTube warn-state metrics were added.*

*v1.746 (21 Jun 2026) -* main

*Compacts legacy stream-guard route diagnostics when reading event history, so older reconnect diagnostics no longer expand into long rows after updating.*

*v1.745 (21 Jun 2026) -* main

*Treat transient YouTube googlevideo failures as a warning instead of a broken key, compact reconnect diagnostics in event history without exposing IP addresses, and show generalized realtime call TPROXY status for Telegram, WhatsApp, and Discord.*

*v1.744 (21 Jun 2026) -* main

*Keeps Android/OS connectivity-check domains out of route files, dnsmasq rules, and static ipset refreshes, and cleans stale entries during route repair so clients do not report Wi-Fi without internet after updates.*

*v1.743 (21 Jun 2026) -* main

*Redacts IPv4 addresses from Telegram call learning events while preserving compact counts, so event history no longer exposes learned call IPs.*

*v1.742 (21 Jun 2026) -* main

*Stops optional quick pool probes after the first short YouTube pass instead of retrying the whole quick profile, so slow Vless 2 candidates are recorded and skipped faster while full diagnostics remain available for active-key checks.*

*v1.741 (21 Jun 2026) -* main

*Separates the active pool-probe RSS ceiling from the lower post-pool restart threshold, so quick Vless 2 checks can continue past the first warmup keys while the bot still cleans up after the pool finishes.*

*v1.740 (21 Jun 2026) -* main

*Makes pool checks use the quick YouTube health profile by default while preserving full YouTube diagnostics for active-key checks, so one slow Vless 2 candidate cannot hold the router in a long temporary-Xray probe.*

*v1.739 (21 Jun 2026) -* main

*Pauses long pool checks when the bot RSS reaches the router-safe threshold and resumes only after memory settles, preventing Vless 2 pool probes from sitting in “checking” while pushing the router above the post-pool restart limit.*

*v1.738 (20 Jun 2026) -* main

*Keeps YouTube drift repair focused on the affected Vless route, adds DNS-first fast ipset repair for youtu.be/youtubei/ytimg/ggpht/googlevideo, and expands YouTube-owned Google edge ranges seen on current watch/live CDN answers so Vless 1 traffic no longer delays Vless 2 route repair.*

*v1.737 (20 Jun 2026) -* main

*Keeps live YouTube short-link redirects on Vless 2 by assigning active Google frontend edge ranges 142.251.1.0/24, 172.253.152.0/24, 173.194.222.0/24, and 74.125.205.0/24 to the YouTube route owner instead of Chrome Remote Desktop point IPs.*

*v1.736 (20 Jun 2026) -* main

*Moves the active 64.233.162.0/24 Google video range into the YouTube/Vless 2 route owner and removes conflicting Chrome Remote Desktop point IPs from Vless 1 presets.*

*v1.735 (20 Jun 2026) -* main

*Replaces the misleading web update progress bar with an elapsed timer and a remaining-time hint based on recent real update durations from event history.*

*v1.734 (20 Jun 2026) -* main

*Moves tracker route domains and a shared Google video IP out of Vless 1 into Vless 2 so route intersection checks stay clean and YouTube/tracker traffic keeps one owner.*

*v1.733 (20 Jun 2026) -* main

*Cleaned dynamic web status text punctuation, restored wrapping for the key health row, and added compact route diagnostics to stream-guard events.*

*v1.732 (20 Jun 2026) -* main
*Removes the remaining trailing punctuation from static route/list helper descriptions so the web UI copy is consistent across status, keys, and lists pages.*

*v1.731 (20 Jun 2026) -* main
*Adds a visible web update progress timer/ETA, a pool sort mode by measured quality score, restores the neutral light-gray theme, removes trailing punctuation from static web descriptions, backs off idle Telegram-call conntrack learning scans, and stops logging benign Telegram auto-failover deferrals while Vless traffic is active.*

*v1.730 (20 Jun 2026) -* main
*Generalizes realtime TPROXY call routing for Telegram, WhatsApp, and Discord, adds compact 50-event diagnostics with failover reasons, keeps auto-failover conservative, and refreshes web UI/README release notes for the dnsmasq-based workflow.*

*v1.729 (18 Jun 2026) -* main
*Keeps the saved proxy mode active during startup if the SOCKS endpoint is briefly not confirmed after an app-mode restart, so switching Simple/Advanced/Web only does not leave the web UI in `none` until the user reapplies Vless.*

*v1.728 (18 Jun 2026) -* main
*Treats a single transient failure of a soft YouTube endpoint (`www.youtube.com/generate_204` or bootstrap hosts) as unstable but usable when home/watch/googlevideo still pass, avoiding false web UI YouTube failures for otherwise working keys.*

*v1.727 (18 Jun 2026) -* main
*Keeps refreshed web status snapshots after async status cleanup so inactive protocol tabs show the latest cached key checks instead of staying stuck on the pending state.*

*v1.726 (17 Jun 2026) -* main
*Runs the lightweight runtime Vless/Vless 2 ipset dedupe every 10 seconds while checking full refresh due state separately, shrinking transient shared Google IP routing windows without adding heavy DNS refresh load.*

*v1.725 (17 Jun 2026) -* main
*Keeps runtime Vless/Vless 2 dnsmasq ipsets deduped after stale scheduler locks and preserved refresh sets, reducing slow YouTube starts caused by shared Google video IPs taking the wrong route.*

*v1.724 (17 Jun 2026) -* main
*Blocks QUIC/UDP 443 by default for YouTube-only routes so mobile clients fall back to the stable TCP bypass path immediately instead of waiting on failed QUIC attempts.*

*v1.723 (16 Jun 2026) -* main
*Adds observed YouTube short-link and thumbnail edge IPs to the YouTube/Vless 2 route so cached client DNS cannot miss the bypass on the first video load.*

*v1.722 (16 Jun 2026) -* main
*Pins YouTube player API frontends to the YouTube/Vless 2 route so selected videos do not wait on mismatched Google service routing before playback starts.*

*v1.721 (16 Jun 2026) -* main
*Fixes web rollback so version/readme metadata and scheduler files are restored together with Python runtime files.*

*v1.720 (16 Jun 2026) -* main
*Cleans generated Vixie cron metadata comments when reinstalling the active root crontab, keeping repeated update and rollback tests tidy while preserving real cron jobs.*

*v1.719 (16 Jun 2026) -* main
*Fixes GitHub update validation for the new `S99unblock refresh` crontab entry, so router updates can stage the cron file successfully.*

*v1.718 (16 Jun 2026) -* main
*Documents dnsmasq/UDP/TPROXY behavior, installs scheduled refresh through S99unblock, and adds adaptive dnsmasq/ndnproxy refresh plus 30-second runtime Vless dedupe so route intersections are cleaned without constant heavy DNS refreshes.*

*v1.717 (16 Jun 2026) -* main
*Lets long post-update ipset refreshes finish in the background instead of killing them, preventing partially swapped runtime sets while still letting web updates restart the bot promptly.*

*v1.716 (16 Jun 2026) -* main
*Uses BusyBox-safe CR stripping when detecting route markers, so YouTube protocol detection and runtime ipset dedupe work with CRLF route files on the router.*

*v1.715 (16 Jun 2026) -* main
*Bounds the post-update ipset refresh and removes the duplicate foreground rebuild, so web updates can finish and restart the bot even when dnsmasq route resolution is slow.*

*v1.714 (16 Jun 2026) -* main
*Adds short timeouts to local DNS lookups during ipset refresh, preventing GitHub updates from hanging on slow domain resolution and reducing router load during dnsmasq route rebuilds.*

*v1.713 (16 Jun 2026) -* main
*Normalizes CRLF route files while detecting the selected YouTube protocol for runtime ipset dedupe, keeping live `unblockvless` and `unblockvless2` sets free of shared DNS-resolved IPs.*

*v1.712 (16 Jun 2026) -* main
*Refreshes route/ipset state immediately after DNS Override changes and repairs preserved service route files when the shared service catalog gains new addresses, preventing partially routed YouTube/Telegram service cards after updates.*

*v1.711 (15 Jun 2026) -* main
*Keeps the transition to dnsmasq controlled by the existing DNS Override buttons, removes the heavy YouTube watch/manifest ipset preload, and reduces router CPU pressure in web status, netfilter hooks, UDP/QUIC drift checks, stream guard, and background YouTube failover.*

*v1.710 (15 Jun 2026) -* main
*Adds a real YouTube watch-page healthcheck and follows live HLS manifests into variant playlists during ipset preload, so live streams like `BhvS39zQAnE` can populate real chunk `googlevideo` hosts in the selected YouTube route instead of spinning on playback.*

*v1.709 (14 Jun 2026) -* main
*Adds Telegram Call TPROXY diagnostics to the router card, keeps learned call media on the selected Telegram route, expands observed YouTube CDN coverage, and aligns desktop web spacing and typography across Status, Keys, and Lists.*

*v1.708 (12 Jun 2026) -* main
*Keeps Telegram route UDP open for native calls, even when Telegram and YouTube share one route list, and adds memory timeline diagnostics with stricter cleanup markers.*

*v1.707 (12 Jun 2026) -* main
*Lets YouTube route detection follow any supported protocol list while keeping stream-activity guard scoped to Vless routes.*

*v1.706 (12 Jun 2026) -* main
*Checks YouTube first-load and googlevideo stability more strictly, adds scoped bootstrap routes, and makes YouTube QUIC policy configurable.*

*v1.705 (12 Jun 2026) -* main
*Left-aligns key names in the mobile key-pool table so short pool labels read like a list again.*

*v1.704 (12 Jun 2026) -* main
*Keeps pool checks resumable without storing raw keys, continues cautiously in low-memory slow mode, limits heavy YouTube throughput samples, and only shows `Стабильно` / `Быстро` after a real speed sample.*

*v1.703 (11 Jun 2026) -* main
*Adds quality scoring for pool keys, shows `Стабильно` / `Быстро` details before applying a key, and uses the score for YouTube candidate ordering.*

*v1.702 (11 Jun 2026) -* main
*Reduces ipset refresh pressure during YouTube playback, defers watchdog route rebuilds while Vless/Vless2 stream traffic is active, and gives refresh commands enough time to finish cleanly.*

*v1.701 (11 Jun 2026) -* main
*Fixes the ipset lock cleanup introduced in v1.700 and recovers interrupted refresh locks after 15 minutes instead of one hour.*

*v1.700 (11 Jun 2026) -* main
*Recovers stale ipset refresh locks automatically and logs skipped refresh attempts accurately, so scheduled ipset updates cannot stay blocked silently.*

*v1.699 (09 Jun 2026) -* main
*Refreshes YouTube/Googlevideo route ipsets with a short priority cooldown when DNS drift is detected, so a working key does not appear broken while transparent routes are stale.*

*v1.698 (08 Jun 2026) -* main
*Allows the desktop web interface to scroll while an update or rollback command is running, and stretches the router card to remove the visual gap before service commands.*

*v1.697 (08 Jun 2026) -* main
*Tightens desktop web spacing in the status header, service area, and quick-key block; compacts the key check status row; and renames the Meta service shortcut to Instagram / Facebook.*

*v1.696 (08 Jun 2026) -* main
*Fixes the desktop web layout after the event-history refactor: status cards no longer overlap service commands, service actions are denser on wide screens, key and subscription tabs size to their content, the check tab scrolls internally, and bypass-list headings stay on one line.*

*v1.695 (08 Jun 2026) -* main
*Refines the web dashboard layout: event history opens from the router card, page and protocol headings stay on one line, and desktop Status, Keys, and Lists views fit within the viewport with internal scrolling for dense content.*

*v1.694 (06 Jun 2026) -* main
*Adds a rollback script for regular GitHub updates and backs up installer/service files so the previous runtime can be restored after an update.*

*v1.693 (06 Jun 2026) -* main
*Makes UDP/QUIC policy follow the list that contains YouTube routes, so YouTube can work from Vless 1, Vless 2, Vmess, Trojan, or Shadowsocks instead of depending on a hard-coded Vless 2 exception, and pins Telegram mobile TCP 5222 to the Telegram route.*

*v1.692 (06 Jun 2026) -* main
*Uses canonical iptables REDIRECT --to-ports rules so UDP/QUIC policy changes remove stale redirect rules instead of leaving old protocol-specific redirects active.*

*v1.691 (06 Jun 2026) -* main
*Treats a transient primary YouTube healthcheck EOF as successful when other YouTube CDN endpoints already confirm the route, reducing false pool and status failures on working keys.*

*v1.690 (06 Jun 2026) -* main
*Repairs hard YouTube route resets before switching keys by resolving Reality endpoint candidates through fallback DNS, refreshing routes after recovery, and adding Telegram IPv6 DC coverage so clients fall back to the routed IPv4 path faster.*

*v1.689 (06 Jun 2026) -* main
*Runs a second ipset refresh after the proxy core starts during GitHub updates, so YouTube watch-page preload can populate dynamic googlevideo CDN entries instead of leaving only static routes.*

*v1.688 (06 Jun 2026) -* main
*Stabilizes YouTube transparent routing by adding the observed missing video CDN range, routing the yt4 avatar host, and mirroring sampled YouTube video/image IPv6 CDN networks for IPv4 fallback.*

*v1.687 (04 Jun 2026) -* main
*Adds service-aware Reality endpoint repair for the active YouTube route before Vless/Vless 2 YouTube failover restarts Xray or switches keys.*

*v1.686 (04 Jun 2026) -* main
*Adds active Reality endpoint repair for both Vless routes: before Telegram auto-failover switches keys, the bot probes the current key endpoint, SNI domain, and SNI A-records through a temporary Xray and keeps the key if any endpoint works.*

*v1.685 (04 Jun 2026) -* main
*Keeps proxy connection addresses from the keys while using SNI/Host only as TLS/Reality serverName, and adds a startup hold so Telegram auto-failover does not switch keys while Xray is still stabilizing.*

*v1.684 (04 Jun 2026) -* main
*Restores normal UDP transparent routing for the main Vless service sets while keeping the narrow YouTube/QUIC reject mirror separate, so Telegram media and calls keep a UDP path after the Telegram QUIC policy split.*

*v1.683 (03 Jun 2026) -* main
*Keeps Telegram routes out of the UDP/QUIC reject mirror so media and calls are not forced into the browser-style QUIC fallback path while mobile push TCP port priority remains in place.*

*v1.682 (02 Jun 2026) -* main
*Adds YouTube video IPv6 fallback coverage for preloaded googlevideo hosts and direct IPv6 CIDRs, samples YouTube edge DNS through several resolvers to catch browser/DoH address drift, keeps newly observed video CDN IPv4 routes, and adds a missing Telegram media range for vless1.*

*v1.681 (02 Jun 2026) -* main
*Adds observed YouTube video CDN ranges to the YouTube route, mirrors QUIC/UDP sets for Shadowsocks, Vmess, both Vless routes, and Trojan, and uses one local QUIC reject path so browser video falls back to TCP through the selected protocol.*

*v1.680 (02 Jun 2026) -* main
*Schedules rollback and app-mode restarts directly as detached shell processes, so the restart survives web command workers and restored files take effect.*

*v1.679 (02 Jun 2026) -* main
*Makes rollback and app-mode restarts detached from the running bot process so restored files actually take effect after rollback.*

*v1.678 (02 Jun 2026) -* main
*Keeps Xray health validation compatible with older updater scripts that do not yet download the new helper module, preventing bot startup failures during GitHub updates from 1.676/1.677.*

*v1.677 (02 Jun 2026) -* main
*Validates Xray before core proxy restarts, reports core proxy health after rollback, records pool probe timeouts as unknown instead of failed, and shows Xray health in the router status card.*

*v1.676 (01 Jun 2026) -* main
*Restores compatibility with Xray 26 by removing the deprecated allowInsecure field from generated configs, and shows “перенести сюда” for preset services that will be added to checks on selection.*

*v1.675 (01 Jun 2026) -* main
*Moves service route web glue out of bot.py, makes route service menus pop over the desktop grid while staying in-flow on mobile, and refreshes the route-tools fragment after route/check changes without reloading the whole page.*

*v1.674 (01 Jun 2026) -* main
*Turns the service route catalog into one button per service: opening a service chooses the target protocol, adds its pool check when needed, and keeps removal next to the same service control instead of duplicating controls below.*

*v1.673 (01 Jun 2026) -* main
*Refines the service route catalog UI into one menu-style card per service with protocol buttons and real Telegram/YouTube icons, removing the duplicate select-plus-transfer control.*

*v1.672 (01 Jun 2026) -* main
*Adds service route profiles, list intersection repair, all-protocol event history, persistent update progress, UI smoke coverage for route controls, and a CI secret scan without adding a real YouTube video playback probe.*

*v1.671 (31 May 2026) -* main
*Replaces the broad `google.com` ChatGPT/Codex route with `www.google.com` so primary Vless service routes no longer overlap YouTube `*.l.google.com` domains from the Vless 2 list.*

*v1.670 (31 May 2026) -* main
*Preloads currently advertised YouTube video CDN hosts into the selected Vless ipset so `*.googlevideo.com` streams follow the YouTube route under ndnproxy without broadly routing all Google networks.*

*v1.669 (30 May 2026) -* main
*Scoped the Vless 2 bypass list back to YouTube-specific routes and moved the old non-YouTube Vless 2 entries to the primary Vless list so broad service ranges no longer overload the YouTube key.*

*v1.668 (30 May 2026) -* main

*Removes Gmail/Google Mail domains from the primary Vless list because overlapping Google IPs can capture YouTube traffic away from Vless 2.*

*v1.667 (30 May 2026) -* main

*Routes Gmail/Google Mail domains through the primary Vless list so mail.google.com no longer depends on overlapping YouTube IPs in Vless 2.*

*v1.666 (29 May 2026) -* main

*Rejects redirected Vless UDP/443 QUIC traffic at the transparent port so YouTube and other browser services fall back to proxied TCP immediately instead of waiting on unanswered UDP attempts.*

*v1.665 (29 May 2026) -* main

*Combines the Meta AI, Instagram, and Facebook service buttons into one shared Meta platform preset and keeps the Telegram route button available from the same service-add menu.*

*v1.664 (29 May 2026) -* main

*Hides legacy helper lists such as socialnet.txt and backup .txt files from the web list editor so only real routed bypass lists are shown.*

*v1.663 (28 May 2026) -* main

*Adds the tracker static asset hosts to the primary Vless list so the page loads styles, scripts, logos, and feed assets through the same working route as the main tracker domain.*

*v1.662 (28 May 2026) -* main

*Moves the torrent tracker route from the YouTube Vless list to the primary Vless list after live checks showed the current primary key opens it while the current YouTube key times out.*

*v1.661 (28 May 2026) -* main

*Keeps failed pool probe results short-lived so transient YouTube or service check failures are automatically rechecked instead of staying red for a full cache hour.*
*Requires the primary YouTube connectivity check plus a second YouTube endpoint before a key is cached as YouTube-working, preventing partial keys from staying marked `yt=ok`.*
*Makes YouTube monitoring follow the Vless list that currently contains YouTube routes, preserves the Reality fingerprint and spiderX defaults from Vless keys, treats one confirmed YouTube endpoint as enough during key apply, restarts and rechecks xray before replacing a YouTube key, requires repeated YouTube failures before failover, skips candidates already active in the other Vless slot, fixes dokodemo-door REDIRECT sockopt and disables transparent inbound sniffing for Vless traffic, supports local Reality endpoint overrides for unstable DNS backends, routes UDP/QUIC mirror sets through transparent Vless ports, stops first web loads from blocking on live Telegram checks, uses public Telegram reachability for web status, audits key switches, raises the idle/post-pool RSS restart threshold to 70 MB, skips auto-failover after recent successful checks, and refreshes ipset when UDP/QUIC mirrors drift from the active service lists.*

*v1.657 (26 May 2026) -* main
*Removes the redundant active-first pool sort option and shows pool check timestamps in mobile key rows.*

*v1.656 (26 May 2026) -* main
*Restores the Telegram Information button by parsing the current README sections and shipping README.md with router installs and updates for offline fallback.*

*v1.655 (26 May 2026) -* main
*Also uses the Telegram auto-failover's own recent-success timestamp to skip transient switches even when the UI probe cache is stale.*

*v1.654 (26 May 2026) -* main
*Prevents Telegram auto-failover from switching away from a recently healthy active key after a transient TLS EOF or timeout probe.*

*v1.653 (26 May 2026) -* main
*Treats Telegram Bot API TLS EOF responses as transient status checks so a recent successful active-key result is not overwritten by one flaky probe.*

*v1.652 (26 May 2026) -* main
*Adds ChatGPT registration/auth challenge dependencies to the Vless service routes.*

*v1.651 (26 May 2026) -* main
*Blocks ChatGPT/Codex Cloudflare edge QUIC leaks so browser traffic falls back to TCP through the selected Vless route.*

*v1.650 (25 May 2026) -* main
*Persists paused pool-check queues across memory-watchdog bot restarts so a full check can resume instead of disappearing.*

*v1.649 (25 May 2026) -* main
*Keeps pool-check progress when a key apply pauses and resumes the queue, and refreshes pool rows live while checks are running.*

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
