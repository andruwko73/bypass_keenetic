#!/bin/sh

DNS_HOST="${DNS_HOST:-127.0.0.1}"
DNS_PORT="${DNS_PORT:-53}"
DNS_WAIT_SECONDS="${DNS_WAIT_SECONDS:-60}"
PARALLEL_JOBS="${PARALLEL_JOBS:-20}"
UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"
TAG="${TAG:-unblock_ipset}"
LOCK_DIR="${LOCK_DIR:-/tmp/bypass-unblock-ipset.lock}"
STATUS_FILE="${IPSET_STATUS_FILE:-/opt/tmp/bypass_ipset_status.json}"
SET_NAMES="unblocksh unblockvmess unblockvless unblockvless2 unblocktroj"
EXTRA_SET_NAMES="unblockvlessudp unblockvless2udp"

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

udp_quic_domain() {
	domain="$(printf '%s\n' "$1" | tr '[:upper:]' '[:lower:]')"
	case "$domain" in
		youtube.com|*.youtube.com|youtu.be|*.youtu.be|yt.be|*.yt.be|googlevideo.com|*.googlevideo.com|ytimg.com|*.ytimg.com|ggpht.com|*.ggpht.com|youtube-nocookie.com|*.youtube-nocookie.com|youtube.googleapis.com|*.youtube.googleapis.com|youtubei.googleapis.com|*.youtubei.googleapis.com|youtubeembeddedplayer.googleapis.com|*.youtubeembeddedplayer.googleapis.com|googleusercontent.com|*.googleusercontent.com|gvt1.com|*.gvt1.com|gvt2.com|*.gvt2.com|video.google.com|*.video.google.com|youtubeeducation.com|*.youtubeeducation.com|youtubekids.com|*.youtubekids.com|chatgpt.com|*.chatgpt.com|openai.com|*.openai.com|oaistatic.com|*.oaistatic.com|oaiusercontent.com|*.oaiusercontent.com|statsig.com|*.statsig.com|statsigapi.net|*.statsigapi.net|featuregates.org|*.featuregates.org|featureassets.org|*.featureassets.org|datadoghq.com|*.datadoghq.com|sentry.io|*.sentry.io|workos.com|*.workos.com|challenges.cloudflare.com|gateway.ai.cloudflare.com|*.gateway.ai.cloudflare.com)
			return 0
			;;
	esac
	return 1
}

udp_quic_direct_entry() {
	case "$1" in
		8.6.112.6|8.47.69.6|35.190.80.1|64.239.109.65|104.18.32.47|172.64.155.209)
			return 0
			;;
	esac
	return 1
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

	export DNS_HOST DNS_PORT IPV4_RE LOCAL_RE tmp_set mirror_tmp_set mirror_domain_file
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
				| awk -v tmp_set="$tmp_set" -v mirror_tmp_set="$mirror_for_domain" "{
					print \"add \" tmp_set \" \" \$1;
					if (mirror_tmp_set != \"\") print \"add \" mirror_tmp_set \" \" \$1;
				}"
		done
	' sh >> "$restore_file"
}

prepare_temp_set() {
	prepare_set_name="$1"
	prepare_tmp_set="$2"
	ipset create "$prepare_set_name" hash:net -exist >/dev/null 2>&1 || fail_status "Cannot create ipset $prepare_set_name."
	ipset destroy "$prepare_tmp_set" >/dev/null 2>&1 || true
	ipset create "$prepare_tmp_set" hash:net -exist >/dev/null 2>&1 || fail_status "Cannot create temporary ipset $prepare_tmp_set."
	ipset flush "$prepare_tmp_set" >/dev/null 2>&1 || true
	printf '%s\n' "$prepare_tmp_set" >> "$temp_sets_file"
}

load_file_to_set() {
	list_path="$1"
	set_name="$2"
	main_tmp_set="$3"
	mirror_set_name="$4"
	mirror_tmp_set="$5"
	prepare_temp_set "$set_name" "$main_tmp_set"
	if [ -n "$mirror_set_name" ] && [ -n "$mirror_tmp_set" ]; then
		prepare_temp_set "$mirror_set_name" "$mirror_tmp_set"
	fi

	if [ ! -f "$list_path" ]; then
		: > "$tmp_dir/${set_name}.missing"
		[ -n "$mirror_set_name" ] && : > "$tmp_dir/${mirror_set_name}.missing"
		return 0
	fi

	domain_file="$tmp_dir/${set_name}.domains"
	source_file="$tmp_dir/${set_name}.source"
	mirror_source_file="$tmp_dir/${mirror_set_name}.source"
	mirror_domain_file="$tmp_dir/${mirror_set_name}.domains"
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
			if [ -n "$mirror_set_name" ] && udp_quic_domain "$domain"; then
				: > "$mirror_source_file"
				printf '%s\n' "$domain" >> "$mirror_domain_file"
			fi
		fi
	done < "$list_path"

	resolve_domains "$main_tmp_set" "$domain_file" "$mirror_tmp_set" "$mirror_domain_file"
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

wait_for_dns || fail_status "DNS $DNS_HOST:$DNS_PORT did not answer in ${DNS_WAIT_SECONDS}s; old ipset contents preserved."

load_file_to_set "$UNBLOCK_DIR/shadowsocks.txt" unblocksh "tmp_unblocksh_$$"
load_file_to_set "$UNBLOCK_DIR/vmess.txt" unblockvmess "tmp_unblockvmess_$$"
load_file_to_set "$UNBLOCK_DIR/vless.txt" unblockvless "tmp_unblockvless_$$" unblockvlessudp "tmp_unblockvlessudp_$$"
load_file_to_set "$UNBLOCK_DIR/vless-2.txt" unblockvless2 "tmp_unblockvless2_$$" unblockvless2udp "tmp_unblockvless2udp_$$"
load_file_to_set "$UNBLOCK_DIR/trojan.txt" unblocktroj "tmp_unblocktroj_$$"

sort -u "$restore_file" > "$sorted_restore_file"
if [ -s "$sorted_restore_file" ]; then
	ipset restore -exist < "$sorted_restore_file" >/dev/null 2>&1 || fail_status "ipset restore to temporary sets failed; old ipset contents preserved."
fi

swap_or_preserve_set unblocksh "tmp_unblocksh_$$"
swap_or_preserve_set unblockvmess "tmp_unblockvmess_$$"
swap_or_preserve_set unblockvless "tmp_unblockvless_$$"
swap_or_preserve_set unblockvlessudp "tmp_unblockvlessudp_$$"
swap_or_preserve_set unblockvless2 "tmp_unblockvless2_$$"
swap_or_preserve_set unblockvless2udp "tmp_unblockvless2udp_$$"
swap_or_preserve_set unblocktroj "tmp_unblocktroj_$$"

if [ -s "$tmp_dir/skipped_sets" ] || [ -s "$tmp_dir/fallback_sets" ]; then
	message="ipset refresh completed with preserved/fallback sets."
	logger -t "$TAG" "$message"
	write_status partial "$message"
	exit 0
fi

write_status success "ipset refresh completed."
exit 0
