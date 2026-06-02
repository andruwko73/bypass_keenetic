#!/bin/sh

DNS_HOST="${DNS_HOST:-127.0.0.1}"
DNS_PORT="${DNS_PORT:-53}"
DNS_WAIT_SECONDS="${DNS_WAIT_SECONDS:-60}"
PARALLEL_JOBS="${PARALLEL_JOBS:-20}"
UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"
TAG="${TAG:-unblock_ipset}"
LOCK_DIR="${LOCK_DIR:-/tmp/bypass-unblock-ipset.lock}"
STATUS_FILE="${IPSET_STATUS_FILE:-/opt/tmp/bypass_ipset_status.json}"
YOUTUBE_VIDEO_PRELOAD_ENABLED="${YOUTUBE_VIDEO_PRELOAD_ENABLED:-1}"
YOUTUBE_VIDEO_PRELOAD_URL="${YOUTUBE_VIDEO_PRELOAD_URL:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}"
YOUTUBE_VIDEO_PRELOAD_CONNECT_TIMEOUT="${YOUTUBE_VIDEO_PRELOAD_CONNECT_TIMEOUT:-6}"
YOUTUBE_VIDEO_PRELOAD_MAX_TIME="${YOUTUBE_VIDEO_PRELOAD_MAX_TIME:-18}"
YOUTUBE_VIDEO_PRELOAD_HOST_LIMIT="${YOUTUBE_VIDEO_PRELOAD_HOST_LIMIT:-80}"
SET_NAMES="unblocksh unblockvmess unblockvless unblockvless2 unblocktroj"
EXTRA_SET_NAMES="unblockshudp unblockvmessudp unblockvlessudp unblockvless2udp unblocktrojudp"
IPV6_SET_NAMES="unblocksh6 unblockvmess6 unblockvless6 unblockvless2v6 unblocktroj6"
UDP_QUIC_POLICY_FILE="${UDP_QUIC_POLICY_FILE:-/opt/etc/bot/udp_quic_routes.txt}"
UDP_QUIC_EXCLUDE_FILE="${UDP_QUIC_EXCLUDE_FILE:-/opt/etc/bot/udp_quic_exclude.txt}"

IPV4_RE='[0-9]{1,3}(\.[0-9]{1,3}){3}'
LOCAL_RE='localhost|^0\.|^127\.|^10\.|^172\.16\.|^192\.168\.|^::|^fc..:|^fd..:|^fe..:'

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
	echo "unblock_ipset is already running."
	exit 0
fi

start_ts="$(date +%s 2>/dev/null || echo 0)"
tmp_dir="$(mktemp -d /tmp/unblock-ipset.XXXXXX 2>/dev/null || echo "/tmp/unblock-ipset.$$")"
mkdir -p "$tmp_dir" || { rmdir "$LOCK_DIR" >/dev/null 2>&1 || true; exit 1; }
restore_file="$tmp_dir/restore"
sorted_restore_file="$tmp_dir/restore.sorted"
temp_sets_file="$tmp_dir/temp_sets"
: > "$restore_file"
: > "$temp_sets_file"

cleanup() {
	if [ -f "$temp_sets_file" ]; then
		while IFS= read -r tmp_set; do
			[ -n "$tmp_set" ] && ipset destroy "$tmp_set" >/dev/null 2>&1 || true
		done < "$temp_sets_file"
	fi
	rm -rf "$tmp_dir"
	rmdir "$LOCK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cut_local() {
	grep -vE "$LOCAL_RE"
}

trim_line() {
	sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

json_escape() {
	printf '%s' "$1" | sed 's/\\/\\\\/g;s/"/\\"/g'
}

detect_dns_backend() {
	dns_lines="$(netstat -lnptu 2>/dev/null | grep -E ':53[[:space:]]' || true)"
	if printf '%s\n' "$dns_lines" | grep -q 'dnsmasq'; then
		printf '%s\n' dnsmasq
		return 0
	fi
	if printf '%s\n' "$dns_lines" | grep -q 'ndnproxy'; then
		printf '%s\n' ndnproxy
		return 0
	fi
	if [ -n "$dns_lines" ]; then
		printf '%s\n' unknown
		return 0
	fi
	if pidof dnsmasq >/dev/null 2>&1; then
		printf '%s\n' dnsmasq
		return 0
	fi
	if pidof ndnproxy >/dev/null 2>&1; then
		printf '%s\n' ndnproxy
		return 0
	fi
	printf '%s\n' none
}

ipset_count() {
	ipset list "$1" 2>/dev/null | awk '
		/^Number of entries:/ { print $4; found_number=1; exit }
		found_members && length($0) { count++ }
		/^Members:/ { found_members=1 }
		END {
			if (!found_number) {
				print count + 0
			}
		}
	'
}

status_counts_json() {
	first=1
	printf '{'
	for set_name in $SET_NAMES $EXTRA_SET_NAMES; do
		count="$(ipset_count "$set_name")"
		[ -n "$count" ] || count=0
		if [ "$first" -eq 0 ]; then
			printf ','
		fi
		first=0
		printf '"%s":%s' "$set_name" "$count"
	done
	printf '}'
}

write_status() {
	state="$1"
	message="$2"
	now_ts="$(date +%s 2>/dev/null || echo 0)"
	duration=0
	if [ "$start_ts" -gt 0 ] 2>/dev/null && [ "$now_ts" -gt "$start_ts" ] 2>/dev/null; then
		duration=$((now_ts - start_ts))
	fi
	backend="$(detect_dns_backend)"
	counts_json="$(status_counts_json)"
	status_dir="${STATUS_FILE%/*}"
	[ "$status_dir" = "$STATUS_FILE" ] || mkdir -p "$status_dir" >/dev/null 2>&1 || true
	tmp_status="${STATUS_FILE}.$$"
	escaped_message="$(json_escape "$message")"
	printf '{"status":"%s","message":"%s","updated_at":%s,"duration_seconds":%s,"dns_host":"%s","dns_port":%s,"dns_backend":"%s","counts":%s}\n' \
		"$state" "$escaped_message" "$now_ts" "$duration" "$DNS_HOST" "$DNS_PORT" "$backend" "$counts_json" > "$tmp_status" 2>/dev/null \
		&& mv "$tmp_status" "$STATUS_FILE" >/dev/null 2>&1 || rm -f "$tmp_status"
}

fail_status() {
	message="$1"
	logger -t "$TAG" "$message"
	write_status failure "$message"
	echo "$message"
	exit 1
}

append_restore() {
	tmp_set="$1"
	value="$2"
	[ -n "$tmp_set" ] && [ -n "$value" ] && printf 'add %s %s\n' "$tmp_set" "$value" >> "$restore_file"
}

extract_direct_entry() {
	line="$1"
	cidr="$(printf '%s\n' "$line" | grep -Eo "$IPV4_RE/[0-9]{1,2}" | cut_local | head -n 1)"
	if [ -n "$cidr" ]; then
		printf '%s\n' "$cidr"
		return 0
	fi

	range="$(printf '%s\n' "$line" | grep -Eo "$IPV4_RE-$IPV4_RE" | cut_local | head -n 1)"
	if [ -n "$range" ]; then
		printf '%s\n' "$range"
		return 0
	fi

	addr="$(printf '%s\n' "$line" | grep -Eo "$IPV4_RE" | cut_local | head -n 1)"
	if [ -n "$addr" ]; then
		printf '%s\n' "$addr"
		return 0
	fi

	return 1
}

normalize_domain() {
	printf '%s\n' "$1" \
		| sed 's/\r//g;s/^DOMAIN-SUFFIX,//;s/^DOMAIN,//;s/^HOST-SUFFIX,//;s/^+\.//;s/^\*\.//;s/[[:space:]].*$//;s/,.*$//;s#^/##;s#/$##' \
		| trim_line
}

udp_quic_policy_source() {
	if [ -s "$UDP_QUIC_POLICY_FILE" ]; then
		printf '%s\n' "$UDP_QUIC_POLICY_FILE"
		return 0
	fi
	python_bin="/opt/bin/python3"
	[ -x "$python_bin" ] || python_bin="$(command -v python3 2>/dev/null || true)"
	[ -n "$python_bin" ] || return 1
	generated_policy_file="$tmp_dir/udp_quic_routes.generated"
	if PYTHONPATH="/opt/etc/bot" "$python_bin" - <<'PY' > "$generated_policy_file" 2>/dev/null; then
from service_catalog import UDP_QUIC_ROUTE_ENTRIES
for entry in UDP_QUIC_ROUTE_ENTRIES:
    print(entry)
PY
		[ -s "$generated_policy_file" ] && printf '%s\n' "$generated_policy_file" && return 0
	fi
	return 1
}

udp_quic_exclude_source() {
	if [ -s "$UDP_QUIC_EXCLUDE_FILE" ]; then
		printf '%s\n' "$UDP_QUIC_EXCLUDE_FILE"
		return 0
	fi
	python_bin="/opt/bin/python3"
	[ -x "$python_bin" ] || python_bin="$(command -v python3 2>/dev/null || true)"
	[ -n "$python_bin" ] || return 1
	generated_exclude_file="$tmp_dir/udp_quic_exclude.generated"
	if PYTHONPATH="/opt/etc/bot" "$python_bin" - <<'PY' > "$generated_exclude_file" 2>/dev/null; then
from service_catalog import UDP_QUIC_EXCLUDE_ENTRIES
for entry in UDP_QUIC_EXCLUDE_ENTRIES:
    print(entry)
PY
		[ -s "$generated_exclude_file" ] && printf '%s\n' "$generated_exclude_file" && return 0
	fi
	return 1
}

udp_quic_excluded_direct_entry() {
	direct_entry="$(printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]')"
	[ -n "$direct_entry" ] || return 1
	[ -s "$UDP_QUIC_EXCLUDE_SOURCE" ] || return 1
	grep -Fx "$direct_entry" "$UDP_QUIC_EXCLUDE_SOURCE" >/dev/null 2>&1
}

udp_quic_domain() {
	domain="$(normalize_domain "$1" | tr '[:upper:]' '[:lower:]')"
	[ -n "$domain" ] || return 1
	[ -s "$UDP_QUIC_POLICY_SOURCE" ] || return 1
	awk -v domain="$domain" '
		function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
		function norm(s) {
			s=tolower(s); sub(/\r/, "", s); sub(/#.*/, "", s); s=trim(s)
			sub(/^domain-suffix,/, "", s); sub(/^domain,/, "", s); sub(/^host-suffix,/, "", s)
			sub(/^\+\./, "", s); sub(/^\*\./, "", s); sub(/\/$/, "", s)
			return s
		}
		{
			entry=norm($0)
			if (entry == "" || entry ~ /[:\/]/ || entry ~ /^[0-9.]+$/) next
			if (domain == entry || domain ~ ("\\." entry "$")) found=1
		}
		END { exit found ? 0 : 1 }
	' "$UDP_QUIC_POLICY_SOURCE"
}

udp_quic_direct_entry() {
	direct_entry="$(printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]')"
	[ -n "$direct_entry" ] || return 1
	[ -s "$UDP_QUIC_POLICY_SOURCE" ] || return 1
	udp_quic_excluded_direct_entry "$direct_entry" && return 1
	awk -v direct_entry="$direct_entry" '
		function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
		{
			entry=tolower($0); sub(/\r/, "", entry); sub(/#.*/, "", entry); entry=trim(entry)
			if (entry == direct_entry && entry ~ /^[0-9.]+(\/[0-9]+)?$/) found=1
		}
		END { exit found ? 0 : 1 }
	' "$UDP_QUIC_POLICY_SOURCE"
}

wait_for_dns() {
	deadline=0
	now_ts="$(date +%s 2>/dev/null || echo 0)"
	if [ "$DNS_WAIT_SECONDS" -gt 0 ] 2>/dev/null && [ "$now_ts" -gt 0 ] 2>/dev/null; then
		deadline=$((now_ts + DNS_WAIT_SECONDS))
	fi

	while :; do
		if dig +short google.com @"$DNS_HOST" -p "$DNS_PORT" 2>/dev/null | grep -Eq "$IPV4_RE"; then
			return 0
		fi
		now_ts="$(date +%s 2>/dev/null || echo 0)"
		if [ "$deadline" -gt 0 ] 2>/dev/null && [ "$now_ts" -ge "$deadline" ] 2>/dev/null; then
			return 1
		fi
		sleep 5
	done
}

xargs_parallel_flag() {
	if printf 'test\n' | xargs -n 1 -P 1 echo >/dev/null 2>&1; then
		printf '%s\n' "-P $PARALLEL_JOBS"
	fi
}

resolve_domains() {
	tmp_set="$1"
	domain_file="$2"
	mirror_tmp_set="$3"
	mirror_domain_file="$4"
	[ -s "$domain_file" ] || return 0

	export DNS_HOST DNS_PORT IPV4_RE LOCAL_RE tmp_set mirror_tmp_set mirror_domain_file UDP_QUIC_EXCLUDE_SOURCE
	parallel_flag="$(xargs_parallel_flag)"

	# shellcheck disable=SC2086
	sort -u "$domain_file" | xargs -n 1 $parallel_flag sh -c '
		for domain do
			mirror_for_domain=""
			if [ -n "$mirror_tmp_set" ] && [ -s "$mirror_domain_file" ] && grep -Fx "$domain" "$mirror_domain_file" >/dev/null 2>&1; then
				mirror_for_domain="$mirror_tmp_set"
			fi
			dig +short "$domain" @"$DNS_HOST" -p "$DNS_PORT" 2>/dev/null \
				| grep -Eo "$IPV4_RE" \
				| grep -vE "$LOCAL_RE" \
				| awk -v tmp_set="$tmp_set" -v mirror_tmp_set="$mirror_for_domain" -v exclude_file="$UDP_QUIC_EXCLUDE_SOURCE" "
					BEGIN {
						if (exclude_file != \"\") {
							while ((getline excluded < exclude_file) > 0) excluded_ip[excluded]=1;
							close(exclude_file);
						}
					}
					{
					print \"add \" tmp_set \" \" \$1;
					if (mirror_tmp_set != \"\" && !(\$1 in excluded_ip)) print \"add \" mirror_tmp_set \" \" \$1;
				}"
		done
	' sh >> "$restore_file"
}

resolve_ipv6_domains() {
	ipv6_tmp_set="$1"
	domain_file="$2"
	[ -n "$ipv6_tmp_set" ] || return 0
	[ -s "$domain_file" ] || return 0

	export DNS_HOST DNS_PORT LOCAL_RE ipv6_tmp_set
	parallel_flag="$(xargs_parallel_flag)"

	# shellcheck disable=SC2086
	sort -u "$domain_file" | xargs -n 1 $parallel_flag sh -c '
		for domain do
			dig +short AAAA "$domain" @"$DNS_HOST" -p "$DNS_PORT" 2>/dev/null \
				| grep -E "^[0-9A-Fa-f:]+$" \
				| grep ":" \
				| grep -vE "$LOCAL_RE" \
				| awk -v tmp_set="$ipv6_tmp_set" "{ print \"add \" tmp_set \" \" \$1 }"
		done
	' sh >> "$restore_file"
}

youtube_socks_port_for_set() {
	case "$1" in
		unblocksh) printf '%s\n' "${YOUTUBE_SOCKS_PORT_SHADOWSOCKS:-10820}" ;;
		unblockvmess) printf '%s\n' "${YOUTUBE_SOCKS_PORT_VMESS:-10810}" ;;
		unblockvless) printf '%s\n' 10811 ;;
		unblockvless2) printf '%s\n' 10813 ;;
		unblocktroj) printf '%s\n' "${YOUTUBE_SOCKS_PORT_TROJAN:-10830}" ;;
		*) return 1 ;;
	esac
}

domain_file_has_googlevideo() {
	[ -s "$1" ] || return 1
	awk '
		function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
		{
			entry=tolower($0); sub(/\r/, "", entry); sub(/#.*/, "", entry); entry=trim(entry)
			if (entry == "googlevideo.com" || entry ~ /\.googlevideo\.com$/) found=1
		}
		END { exit found ? 0 : 1 }
	' "$1"
}

preload_youtube_video_hosts() {
	set_name="$1"
	tmp_set="$2"
	mirror_tmp_set="$3"
	domain_file="$4"
	[ "$YOUTUBE_VIDEO_PRELOAD_ENABLED" = "0" ] && return 0
	domain_file_has_googlevideo "$domain_file" || return 0
	socks_port="$(youtube_socks_port_for_set "$set_name" 2>/dev/null || true)"
	[ -n "$socks_port" ] || return 0
	curl_bin="/opt/bin/curl"
	[ -x "$curl_bin" ] || curl_bin="$(command -v curl 2>/dev/null || true)"
	[ -n "$curl_bin" ] || return 0

	page_file="$tmp_dir/${set_name}.youtube_video.html"
	hosts_file="$tmp_dir/${set_name}.youtube_video.hosts"
	if ! "$curl_bin" -k -L -sS \
		--socks5-hostname "127.0.0.1:$socks_port" \
		-A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36" \
		--connect-timeout "$YOUTUBE_VIDEO_PRELOAD_CONNECT_TIMEOUT" \
		--max-time "$YOUTUBE_VIDEO_PRELOAD_MAX_TIME" \
		"$YOUTUBE_VIDEO_PRELOAD_URL" -o "$page_file" >/dev/null 2>&1; then
		return 0
	fi

	grep -Eo '[A-Za-z0-9.-]+\.googlevideo\.com' "$page_file" 2>/dev/null \
		| tr '[:upper:]' '[:lower:]' \
		| sort -u \
		| head -n "$YOUTUBE_VIDEO_PRELOAD_HOST_LIMIT" > "$hosts_file"
	[ -s "$hosts_file" ] || return 0

	mirror_for_video=""
	if [ -n "$mirror_tmp_set" ] && udp_quic_domain "googlevideo.com"; then
		mirror_for_video="$mirror_tmp_set"
	fi

	while IFS= read -r video_host || [ -n "$video_host" ]; do
		[ -n "$video_host" ] || continue
		dig +short A "$video_host" @"$DNS_HOST" -p "$DNS_PORT" 2>/dev/null
	done < "$hosts_file" \
		| grep -Eo "$IPV4_RE" \
		| grep -vE "$LOCAL_RE" \
		| sort -u \
		| awk -v tmp_set="$tmp_set" -v mirror_tmp_set="$mirror_for_video" -v exclude_file="$UDP_QUIC_EXCLUDE_SOURCE" '
			function cidr24(ip) {
				sub(/\.[0-9]+$/, ".0/24", ip)
				return ip
			}
			BEGIN {
				if (exclude_file != "") {
					while ((getline excluded < exclude_file) > 0) excluded_ip[excluded]=1;
					close(exclude_file);
				}
			}
			{
				print "add " tmp_set " " $1;
				print "add " tmp_set " " cidr24($1);
				if (mirror_tmp_set != "" && !($1 in excluded_ip)) print "add " mirror_tmp_set " " $1;
				if (mirror_tmp_set != "" && !($1 in excluded_ip)) print "add " mirror_tmp_set " " cidr24($1);
			}
		' >> "$restore_file"
}

prepare_temp_set() {
	prepare_set_name="$1"
	prepare_tmp_set="$2"
	prepare_family="$3"
	if [ -n "$prepare_family" ]; then
		ipset create "$prepare_set_name" hash:net family "$prepare_family" -exist >/dev/null 2>&1 || fail_status "Cannot create ipset $prepare_set_name."
	else
		ipset create "$prepare_set_name" hash:net -exist >/dev/null 2>&1 || fail_status "Cannot create ipset $prepare_set_name."
	fi
	ipset destroy "$prepare_tmp_set" >/dev/null 2>&1 || true
	if [ -n "$prepare_family" ]; then
		ipset create "$prepare_tmp_set" hash:net family "$prepare_family" -exist >/dev/null 2>&1 || fail_status "Cannot create temporary ipset $prepare_tmp_set."
	else
		ipset create "$prepare_tmp_set" hash:net -exist >/dev/null 2>&1 || fail_status "Cannot create temporary ipset $prepare_tmp_set."
	fi
	ipset flush "$prepare_tmp_set" >/dev/null 2>&1 || true
	printf '%s\n' "$prepare_tmp_set" >> "$temp_sets_file"
}

load_file_to_set() {
	list_path="$1"
	set_name="$2"
	main_tmp_set="$3"
	mirror_set_name="$4"
	mirror_tmp_set="$5"
	ipv6_set_name="$6"
	ipv6_tmp_set="$7"
	prepare_temp_set "$set_name" "$main_tmp_set"
	if [ -n "$mirror_set_name" ] && [ -n "$mirror_tmp_set" ]; then
		prepare_temp_set "$mirror_set_name" "$mirror_tmp_set"
	fi
	if [ -n "$ipv6_set_name" ] && [ -n "$ipv6_tmp_set" ]; then
		prepare_temp_set "$ipv6_set_name" "$ipv6_tmp_set" inet6
	fi

	if [ ! -f "$list_path" ]; then
		: > "$tmp_dir/${set_name}.missing"
		[ -n "$mirror_set_name" ] && : > "$tmp_dir/${mirror_set_name}.missing"
		[ -n "$ipv6_set_name" ] && : > "$tmp_dir/${ipv6_set_name}.missing"
		return 0
	fi

	domain_file="$tmp_dir/${set_name}.domains"
	source_file="$tmp_dir/${set_name}.source"
	mirror_source_file="$tmp_dir/${mirror_set_name}.source"
	mirror_domain_file="$tmp_dir/${mirror_set_name}.domains"
	ipv6_source_file="$tmp_dir/${ipv6_set_name}.source"
	: > "$domain_file"
	[ -n "$mirror_set_name" ] && : > "$mirror_domain_file"

	while IFS= read -r raw_line || [ -n "$raw_line" ]; do
		line="$(printf '%s\n' "$raw_line" | trim_line)"
		case "$line" in
			''|\#*) continue ;;
		esac

		if direct_entry="$(extract_direct_entry "$line")"; then
			: > "$source_file"
			append_restore "$main_tmp_set" "$direct_entry"
			if [ -n "$mirror_set_name" ] && [ -n "$mirror_tmp_set" ] && udp_quic_direct_entry "$direct_entry"; then
				: > "$mirror_source_file"
				append_restore "$mirror_tmp_set" "$direct_entry"
			fi
			continue
		fi

		domain="$(normalize_domain "$line")"
		if [ -n "$domain" ]; then
			: > "$source_file"
			printf '%s\n' "$domain" >> "$domain_file"
			[ -n "$ipv6_set_name" ] && : > "$ipv6_source_file"
			if [ -n "$mirror_set_name" ] && udp_quic_domain "$domain"; then
				: > "$mirror_source_file"
				printf '%s\n' "$domain" >> "$mirror_domain_file"
			fi
		fi
	done < "$list_path"

	resolve_domains "$main_tmp_set" "$domain_file" "$mirror_tmp_set" "$mirror_domain_file"
	preload_youtube_video_hosts "$set_name" "$main_tmp_set" "$mirror_tmp_set" "$domain_file"
	resolve_ipv6_domains "$ipv6_tmp_set" "$domain_file"
}

entry_count_for_tmp_set() {
	tmp_set="$1"
	awk -v tmp_set="$tmp_set" '$1 == "add" && $2 == tmp_set { count++ } END { print count + 0 }' "$sorted_restore_file"
}

swap_or_preserve_set() {
	set_name="$1"
	swap_tmp_set="$2"
	entry_count="$(entry_count_for_tmp_set "$swap_tmp_set")"
	current_count="$(ipset_count "$set_name")"
	[ -n "$current_count" ] || current_count=0

	if [ -f "$tmp_dir/${set_name}.missing" ] && [ "$current_count" -gt 0 ] 2>/dev/null; then
		printf '%s\n' "$set_name" >> "$tmp_dir/skipped_sets"
		echo "$set_name: list file is missing, preserving $current_count existing entries."
		return 0
	fi

	if [ -f "$tmp_dir/${set_name}.source" ] && [ "$entry_count" -eq 0 ] 2>/dev/null && [ "$current_count" -gt 0 ] 2>/dev/null; then
		printf '%s\n' "$set_name" >> "$tmp_dir/skipped_sets"
		echo "$set_name: resolved to zero entries, preserving $current_count existing entries."
		return 0
	fi

	if ipset swap "$swap_tmp_set" "$set_name" >/dev/null 2>&1; then
		ipset destroy "$swap_tmp_set" >/dev/null 2>&1 || true
		return 0
	fi

	printf '%s\n' "$set_name" >> "$tmp_dir/fallback_sets"
	awk -v from="$swap_tmp_set" -v to="$set_name" '$1 == "add" && $2 == from { print "add " to " " $3 }' "$sorted_restore_file" > "$tmp_dir/${set_name}.fallback"
	if [ -s "$tmp_dir/${set_name}.fallback" ]; then
		ipset restore -exist < "$tmp_dir/${set_name}.fallback" >/dev/null 2>&1 || true
	fi
	echo "$set_name: ipset swap failed, added new entries without flushing old entries."
	return 0
}

UDP_QUIC_POLICY_SOURCE="$(udp_quic_policy_source || true)"
UDP_QUIC_EXCLUDE_SOURCE="$(udp_quic_exclude_source || true)"

wait_for_dns || fail_status "DNS $DNS_HOST:$DNS_PORT did not answer in ${DNS_WAIT_SECONDS}s; old ipset contents preserved."

load_file_to_set "$UNBLOCK_DIR/shadowsocks.txt" unblocksh "tmp_unblocksh_$$" unblockshudp "tmp_unblockshudp_$$" unblocksh6 "tmp_unblocksh6_$$"
load_file_to_set "$UNBLOCK_DIR/vmess.txt" unblockvmess "tmp_unblockvmess_$$" unblockvmessudp "tmp_unblockvmessudp_$$" unblockvmess6 "tmp_unblockvmess6_$$"
load_file_to_set "$UNBLOCK_DIR/vless.txt" unblockvless "tmp_unblockvless_$$" unblockvlessudp "tmp_unblockvlessudp_$$" unblockvless6 "tmp_unblockvless6_$$"
load_file_to_set "$UNBLOCK_DIR/vless-2.txt" unblockvless2 "tmp_unblockvless2_$$" unblockvless2udp "tmp_unblockvless2udp_$$" unblockvless2v6 "tmp_unblockvless2v6_$$"
load_file_to_set "$UNBLOCK_DIR/trojan.txt" unblocktroj "tmp_unblocktroj_$$" unblocktrojudp "tmp_unblocktrojudp_$$" unblocktroj6 "tmp_unblocktroj6_$$"

sort -u "$restore_file" > "$sorted_restore_file"
if [ -s "$sorted_restore_file" ]; then
	ipset restore -exist < "$sorted_restore_file" >/dev/null 2>&1 || fail_status "ipset restore to temporary sets failed; old ipset contents preserved."
fi

swap_or_preserve_set unblocksh "tmp_unblocksh_$$"
swap_or_preserve_set unblockshudp "tmp_unblockshudp_$$"
swap_or_preserve_set unblockvmess "tmp_unblockvmess_$$"
swap_or_preserve_set unblockvmessudp "tmp_unblockvmessudp_$$"
swap_or_preserve_set unblockvless "tmp_unblockvless_$$"
swap_or_preserve_set unblockvlessudp "tmp_unblockvlessudp_$$"
swap_or_preserve_set unblockvless2 "tmp_unblockvless2_$$"
swap_or_preserve_set unblockvless2udp "tmp_unblockvless2udp_$$"
swap_or_preserve_set unblocktroj "tmp_unblocktroj_$$"
swap_or_preserve_set unblocktrojudp "tmp_unblocktrojudp_$$"
swap_or_preserve_set unblocksh6 "tmp_unblocksh6_$$"
swap_or_preserve_set unblockvmess6 "tmp_unblockvmess6_$$"
swap_or_preserve_set unblockvless6 "tmp_unblockvless6_$$"
swap_or_preserve_set unblockvless2v6 "tmp_unblockvless2v6_$$"
swap_or_preserve_set unblocktroj6 "tmp_unblocktroj6_$$"

if [ -s "$tmp_dir/skipped_sets" ] || [ -s "$tmp_dir/fallback_sets" ]; then
	message="ipset refresh completed with preserved/fallback sets."
	logger -t "$TAG" "$message"
	write_status partial "$message"
	exit 0
fi

write_status success "ipset refresh completed."
exit 0
