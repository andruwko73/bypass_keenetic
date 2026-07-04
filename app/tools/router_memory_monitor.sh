#!/bin/sh

OUT_DIR=${BKM_OUT_DIR:-/opt/tmp}
PID_FILE=${BKM_PID_FILE:-/opt/tmp/bypass_memory_monitor.pid}
LATEST_FILE=${BKM_LATEST_FILE:-/opt/tmp/bypass_memory_monitor.latest}
TIMELINE_FILE=${BKM_TIMELINE_FILE:-/opt/tmp/bypass_memory_timeline.jsonl}
DEFAULT_DURATION=${BKM_DURATION:-43200}
DEFAULT_INTERVAL=${BKM_INTERVAL:-60}
YT_ENABLED=${BKM_YT_ENABLED:-1}
YT_PORT=${BKM_YT_PORT:-10813}
YT_INTERVAL=${BKM_YT_INTERVAL:-300}
YT_HOME_INTERVAL=${BKM_YT_HOME_INTERVAL:-900}
YT_WATCH_INTERVAL=${BKM_YT_WATCH_INTERVAL:-900}
YT_SMALL_URL=${BKM_YT_SMALL_URL:-https://www.youtube.com/generate_204}
YT_HOME_URL=${BKM_YT_HOME_URL:-https://www.youtube.com/}
YT_WATCH_URL=${BKM_YT_WATCH_URL:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}

now_stamp() {
    date '+%Y%m%d_%H%M%S'
}

iso_time() {
    date '+%Y-%m-%dT%H:%M:%S%z'
}

file_size() {
    if [ -f "$1" ]; then
        wc -c < "$1" 2>/dev/null | tr -d ' '
    else
        printf '0'
    fi
}

dir_count() {
    if [ -d "$1" ]; then
        ls "$1" 2>/dev/null | wc -l | tr -d ' '
    else
        printf '0'
    fi
}

meminfo_value() {
    awk -v key="$1:" '$1 == key {print $2; found=1; exit} END {if (!found) print 0}' /proc/meminfo 2>/dev/null
}

status_value() {
    pid=$1
    key=$2
    if [ -n "$pid" ] && [ -r "/proc/$pid/status" ]; then
        awk -v key="$key:" '$1 == key {print $2; found=1; exit} END {if (!found) print 0}' "/proc/$pid/status" 2>/dev/null
    else
        printf '0'
    fi
}

find_bot_pid() {
    for pid_file in /opt/var/run/S99telegram_bot.pid /opt/tmp/S99telegram_bot.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file" 2>/dev/null | tr -dc '0-9' | head -c 16)
            if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
                printf '%s' "$pid"
                return
            fi
        fi
    done
    if command -v pgrep >/dev/null 2>&1; then
        pid=$(pgrep -f '/opt/etc/bot/main.py' 2>/dev/null | head -n 1)
        if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
            printf '%s' "$pid"
            return
        fi
        pid=$(pgrep -f '/opt/etc/bot/bot.py' 2>/dev/null | head -n 1)
        if [ -n "$pid" ] && [ -d "/proc/$pid" ]; then
            printf '%s' "$pid"
            return
        fi
    fi
    ps w 2>/dev/null | awk '/python3 .*\/opt\/etc\/bot\/(main|bot)\.py/ && $0 !~ /awk/ {print $1; exit}'
}

find_xray_pid() {
    ps w 2>/dev/null | awk '/xray run -c \/opt\/etc\/xray\/config\.json/ && $0 !~ /awk/ {print $1; exit}'
}

ps_count() {
    ps w 2>/dev/null | grep "$1" | grep -v grep | wc -l | tr -d ' '
}

system_ticks() {
    awk '/^cpu / {sum=0; for (i=2; i<=NF; i++) sum += $i; print sum; found=1; exit} END {if (!found) print 0}' /proc/stat 2>/dev/null
}

proc_ticks() {
    pid=$1
    if [ -n "$pid" ] && [ -r "/proc/$pid/stat" ]; then
        awk '{print $14 + $15}' "/proc/$pid/stat" 2>/dev/null
    else
        printf '0'
    fi
}

app_mode() {
    if [ -f /opt/etc/bot_app_mode ]; then
        tr -d '\r\n\t ' < /opt/etc/bot_app_mode 2>/dev/null
    else
        printf ''
    fi
}

app_version() {
    if [ -f /opt/etc/bot/app_version.py ]; then
        awk -F= '/^APP_VERSION_COUNTER/ {gsub(/[[:space:]]/, "", $2); print $2; found=1; exit} END {if (!found) print ""}' /opt/etc/bot/app_version.py 2>/dev/null
    else
        printf ''
    fi
}

temp_pool_probe_count() {
    ls /tmp 2>/dev/null | grep '^bypass_pool_probe_' | wc -l | tr -d ' '
}

json_value() {
    field=$1
    line=$2
    printf '%s\n' "$line" | sed -n "s/.*\"$field\":\([^,}]*\).*/\1/p" | head -n 1 | tr -d '"'
}

json_file_value() {
    field=$1
    path=$2
    if [ -f "$path" ]; then
        line=$(tr -d '\n\r' < "$path" 2>/dev/null | head -c 8192)
        json_value "$field" "$line"
    else
        printf ''
    fi
}

safe_text() {
    printf '%s' "$1" | tr '\t\r\n' '   '
}

monitor_running() {
    if [ ! -f "$PID_FILE" ]; then
        return 1
    fi
    pid=$(cat "$PID_FILE" 2>/dev/null | tr -dc '0-9' | head -c 16)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

write_headers() {
    log_file=$1
    yt_log_file=$2
    if [ ! -f "$log_file" ]; then
        printf '%s\n' 'ts	epoch	app_version	app_mode	pid	bot_alive	rss_kb	hwm_kb	vmdata_kb	threads	fds	bot_ticks	total_ticks	load1	load5	load15	mem_available_kb	mem_free_kb	swap_free_kb	xray_pid	xray_rss_kb	xray_hwm_kb	xray_ticks	xray_count	scheduler_count	unblock_ipset_count	temp_pool_probe_count	pool_probe_running	pool_probe_checked	pool_probe_total	status_refresh_count	key_probe_cache_bytes	event_history_bytes	route_intersections_count	route_intersections_runtime_count	timeline_marker	timeline_reason' > "$log_file"
    fi
    if [ "$YT_ENABLED" = "1" ] && [ ! -f "$yt_log_file" ]; then
        printf '%s\n' 'ts	epoch	kind	port	http_code	connect_s	tls_s	starttransfer_s	total_s	size_download	probe_exit	error_type' > "$yt_log_file"
    fi
}

collect_sample() {
    log_file=$1
    ts=$(iso_time)
    epoch=$(date +%s)
    bot_pid=$(find_bot_pid)
    bot_alive=0
    if [ -n "$bot_pid" ] && [ -d "/proc/$bot_pid" ]; then
        bot_alive=1
    else
        bot_pid=0
    fi

    rss_kb=$(status_value "$bot_pid" VmRSS)
    hwm_kb=$(status_value "$bot_pid" VmHWM)
    vmdata_kb=$(status_value "$bot_pid" VmData)
    threads=$(dir_count "/proc/$bot_pid/task")
    fds=$(dir_count "/proc/$bot_pid/fd")
    bot_ticks=$(proc_ticks "$bot_pid")
    total_ticks=$(system_ticks)
    set -- $(cat /proc/loadavg 2>/dev/null)
    load1=${1:-0}
    load5=${2:-0}
    load15=${3:-0}
    mem_available=$(meminfo_value MemAvailable)
    mem_free=$(meminfo_value MemFree)
    swap_free=$(meminfo_value SwapFree)
    xray_pid=$(find_xray_pid)
    if [ -z "$xray_pid" ]; then
        xray_pid=0
    fi
    xray_rss_kb=$(status_value "$xray_pid" VmRSS)
    xray_hwm_kb=$(status_value "$xray_pid" VmHWM)
    xray_ticks=$(proc_ticks "$xray_pid")
    xray_count=$(ps_count 'xray run')
    scheduler_count=$(ps_count 'S99unblock scheduler')
    unblock_ipset_count=$(ps_count 'unblock_ipset.sh')
    temp_count=$(temp_pool_probe_count)
    route_intersections_count=$(json_file_value count /opt/tmp/bypass_route_intersections.json)
    route_intersections_runtime_count=$(json_file_value runtime_count /opt/tmp/bypass_route_intersections.json)

    timeline_line=''
    if [ -f "$TIMELINE_FILE" ]; then
        timeline_line=$(tail -n 1 "$TIMELINE_FILE" 2>/dev/null)
    fi
    pool_running=$(json_value pool_probe_running "$timeline_line")
    pool_checked=$(json_value pool_probe_checked "$timeline_line")
    pool_total=$(json_value pool_probe_total "$timeline_line")
    status_refresh_count=$(json_value status_refresh_count "$timeline_line")
    key_probe_cache_bytes=$(json_value key_probe_cache_bytes "$timeline_line")
    event_history_bytes=$(json_value event_history_bytes "$timeline_line")
    timeline_marker=$(safe_text "$(json_value marker "$timeline_line")")
    timeline_reason=$(safe_text "$(json_value reason "$timeline_line")")

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$ts" "$epoch" "$(app_version)" "$(app_mode)" "$bot_pid" "$bot_alive" "$rss_kb" "$hwm_kb" "$vmdata_kb" "$threads" "$fds" \
        "$bot_ticks" "$total_ticks" "$load1" "$load5" "$load15" "$mem_available" "$mem_free" "$swap_free" \
        "$xray_pid" "$xray_rss_kb" "$xray_hwm_kb" "$xray_ticks" "$xray_count" "$scheduler_count" "$unblock_ipset_count" "$temp_count" \
        "${pool_running:-}" "${pool_checked:-}" "${pool_total:-}" "${status_refresh_count:-}" \
        "${key_probe_cache_bytes:-}" "${event_history_bytes:-}" "${route_intersections_count:-}" "${route_intersections_runtime_count:-}" "$timeline_marker" "$timeline_reason" >> "$log_file"
}

curl_probe() {
    kind=$1
    url=$2
    port=$3
    yt_log_file=$4
    ts=$(iso_time)
    epoch=$(date +%s)
    if command -v python3 >/dev/null 2>&1; then
        out=$(python3 - "$url" "$port" <<'PY' 2>/dev/null
import sys
import time

url = sys.argv[1]
port = sys.argv[2]
started = time.monotonic()
try:
    import requests

    proxies = {
        'http': f'socks5h://127.0.0.1:{port}',
        'https': f'socks5h://127.0.0.1:{port}',
    }
    response = requests.get(
        url,
        proxies=proxies,
        headers={'User-Agent': 'Mozilla/5.0'},
        timeout=(8, 25),
        stream=True,
        allow_redirects=True,
    )
    first_byte = time.monotonic()
    size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if chunk:
            size += len(chunk)
    finished = time.monotonic()
    print(
        f'{response.status_code}\t0\t0\t{first_byte - started:.6f}\t'
        f'{finished - started:.6f}\t{size}\t0\t'
    )
except Exception:
    error_type = type(sys.exc_info()[1]).__name__
    finished = time.monotonic()
    print(f'000\t0\t0\t0\t{finished - started:.6f}\t0\t1\t{error_type}')
PY
)
        if [ -n "$out" ]; then
            printf '%s\t%s\t%s\t%s\t%s\n' "$ts" "$epoch" "$kind" "$port" "$out" >> "$yt_log_file"
            return
        fi
    fi
    if ! command -v curl >/dev/null 2>&1; then
        printf '%s\t%s\t%s\t%s\t000\t0\t0\t0\t0\t0\t127\tno_curl\n' "$ts" "$epoch" "$kind" "$port" >> "$yt_log_file"
        return
    fi
    out=$(curl -L --socks5-hostname "127.0.0.1:$port" -A 'Mozilla/5.0' -o /dev/null -s \
        -w '%{http_code}\t%{time_connect}\t%{time_appconnect}\t%{time_starttransfer}\t%{time_total}\t%{size_download}' \
        --connect-timeout 8 --max-time 25 "$url" 2>/dev/null)
    rc=$?
    if [ -z "$out" ]; then
        out='000	0	0	0	0	0'
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\tcurl\n' "$ts" "$epoch" "$kind" "$port" "$out" "$rc" >> "$yt_log_file"
}

run_loop() {
    duration=${1:-$DEFAULT_DURATION}
    interval=${2:-$DEFAULT_INTERVAL}
    log_file=${3:-}
    yt_log_file=${4:-}
    mkdir -p "$OUT_DIR"
    if [ -z "$log_file" ]; then
        run_id=$(now_stamp)
        log_file="$OUT_DIR/bypass_memory_monitor_$run_id.tsv"
    fi
    if [ -z "$yt_log_file" ]; then
        run_id=$(now_stamp)
        yt_log_file="$OUT_DIR/bypass_youtube_monitor_$run_id.tsv"
    fi

    echo $$ > "$PID_FILE"
    cat > "$LATEST_FILE" <<EOF
pid=$$
started_at=$(iso_time)
duration_s=$duration
interval_s=$interval
log_file=$log_file
yt_log_file=$yt_log_file
yt_enabled=$YT_ENABLED
yt_port=$YT_PORT
EOF
    trap 'rm -f "$PID_FILE"; exit 0' INT TERM
    write_headers "$log_file" "$yt_log_file"
    start_epoch=$(date +%s)
    end_epoch=$((start_epoch + duration))
    next_yt=0
    next_yt_home=0
    next_yt_watch=0
    while :; do
        now=$(date +%s)
        if [ "$now" -gt "$end_epoch" ]; then
            break
        fi
        collect_sample "$log_file"
        if [ "$YT_ENABLED" = "1" ]; then
            if [ "$now" -ge "$next_yt" ]; then
                curl_probe generate_204 "$YT_SMALL_URL" "$YT_PORT" "$yt_log_file"
                next_yt=$((now + YT_INTERVAL))
            fi
            if [ "$now" -ge "$next_yt_home" ]; then
                curl_probe home "$YT_HOME_URL" "$YT_PORT" "$yt_log_file"
                next_yt_home=$((now + YT_HOME_INTERVAL))
            fi
            if [ "$now" -ge "$next_yt_watch" ]; then
                curl_probe watch "$YT_WATCH_URL" "$YT_PORT" "$yt_log_file"
                next_yt_watch=$((now + YT_WATCH_INTERVAL))
            fi
        fi
        sleep "$interval"
    done
    rm -f "$PID_FILE"
}

start_monitor() {
    duration=${1:-$DEFAULT_DURATION}
    interval=${2:-$DEFAULT_INTERVAL}
    mkdir -p "$OUT_DIR"
    if monitor_running; then
        echo "already_running"
        show_status
        exit 0
    fi
    run_id=$(now_stamp)
    log_file="$OUT_DIR/bypass_memory_monitor_$run_id.tsv"
    yt_log_file="$OUT_DIR/bypass_youtube_monitor_$run_id.tsv"
    if command -v nohup >/dev/null 2>&1; then
        nohup "$0" run "$duration" "$interval" "$log_file" "$yt_log_file" >/dev/null 2>&1 &
    else
        /bin/sh "$0" run "$duration" "$interval" "$log_file" "$yt_log_file" > "$OUT_DIR/bypass_memory_monitor.run.log" 2>&1 &
    fi
    pid=$!
    echo "$pid" > "$PID_FILE"
    cat > "$LATEST_FILE" <<EOF
pid=$pid
started_at=$(iso_time)
duration_s=$duration
interval_s=$interval
log_file=$log_file
yt_log_file=$yt_log_file
yt_enabled=$YT_ENABLED
yt_port=$YT_PORT
EOF
    echo "started pid=$pid log_file=$log_file yt_log_file=$yt_log_file"
}

stop_monitor() {
    if ! monitor_running; then
        echo "not_running"
        rm -f "$PID_FILE"
        exit 0
    fi
    pid=$(cat "$PID_FILE" 2>/dev/null | tr -dc '0-9' | head -c 16)
    kill "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "stopped pid=$pid"
}

show_status() {
    if monitor_running; then
        pid=$(cat "$PID_FILE" 2>/dev/null | tr -dc '0-9' | head -c 16)
        echo "running pid=$pid"
    else
        echo "not_running"
    fi
    if [ -f "$LATEST_FILE" ]; then
        cat "$LATEST_FILE"
        log_file=$(awk -F= '$1=="log_file"{print $2}' "$LATEST_FILE" 2>/dev/null)
        yt_log_file=$(awk -F= '$1=="yt_log_file"{print $2}' "$LATEST_FILE" 2>/dev/null)
        if [ -n "$log_file" ] && [ -f "$log_file" ]; then
            echo "last_memory_sample:"
            tail -n 1 "$log_file"
        fi
        if [ -n "$yt_log_file" ] && [ -f "$yt_log_file" ]; then
            echo "last_youtube_sample:"
            tail -n 1 "$yt_log_file"
        fi
    fi
}

case "${1:-start}" in
    start)
        start_monitor "${2:-$DEFAULT_DURATION}" "${3:-$DEFAULT_INTERVAL}"
        ;;
    run)
        run_loop "${2:-$DEFAULT_DURATION}" "${3:-$DEFAULT_INTERVAL}" "${4:-}" "${5:-}"
        ;;
    stop)
        stop_monitor
        ;;
    status)
        show_status
        ;;
    once)
        mkdir -p "$OUT_DIR"
        tmp_log="$OUT_DIR/bypass_memory_monitor_once.tsv"
        tmp_yt="$OUT_DIR/bypass_youtube_monitor_once.tsv"
        write_headers "$tmp_log" "$tmp_yt"
        collect_sample "$tmp_log"
        if [ "$YT_ENABLED" = "1" ]; then
            curl_probe generate_204 "$YT_SMALL_URL" "$YT_PORT" "$tmp_yt"
            curl_probe home "$YT_HOME_URL" "$YT_PORT" "$tmp_yt"
            curl_probe watch "$YT_WATCH_URL" "$YT_PORT" "$tmp_yt"
        fi
        tail -n 1 "$tmp_log"
        tail -n 3 "$tmp_yt" 2>/dev/null
        ;;
    *)
        echo "usage: $0 start [duration_s] [interval_s] | stop | status | once"
        exit 2
        ;;
esac
