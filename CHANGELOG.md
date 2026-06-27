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
