#!/bin/sh

DNS_HOST="${DNS_HOST:-127.0.0.1}"
DNS_PORT="${DNS_PORT:-53}"
PARALLEL_JOBS="${PARALLEL_JOBS:-20}"
UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"
TAG="${TAG:-unblock_ipset}"

IPV4_RE='[0-9]{1,3}(\.[0-9]{1,3}){3}'
LOCAL_RE='localhost|^0\.|^127\.|^10\.|^172\.16\.|^192\.168\.|^::|^fc..:|^fd..:|^fe..:'

tmp_dir="$(mktemp -d /tmp/unblock-ipset.XXXXXX 2>/dev/null || echo "/tmp/unblock-ipset.$$")"
mkdir -p "$tmp_dir" || exit 1
restore_file="$tmp_dir/restore"
: > "$restore_file"

cleanup() {
	rm -rf "$tmp_dir"
}
trap cleanup EXIT INT TERM

cut_local() {
	grep -vE "$LOCAL_RE"
}

trim_line() {
	sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

append_restore() {
	set_name="$1"
	value="$2"
	[ -n "$set_name" ] && [ -n "$value" ] && printf 'add %s %s\n' "$set_name" "$value" >> "$restore_file"
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

wait_for_dns() {
	while :; do
		if dig +short google.com @"$DNS_HOST" -p "$DNS_PORT" 2>/dev/null | grep -Eq "$IPV4_RE"; then
			return 0
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
	set_name="$1"
	domain_file="$2"
	[ -s "$domain_file" ] || return 0

	export DNS_HOST DNS_PORT IPV4_RE LOCAL_RE set_name
	parallel_flag="$(xargs_parallel_flag)"

	# shellcheck disable=SC2086
	sort -u "$domain_file" | xargs -n 1 $parallel_flag sh -c '
		for domain do
			dig +short "$domain" @"$DNS_HOST" -p "$DNS_PORT" 2>/dev/null \
				| grep -Eo "$IPV4_RE" \
				| grep -vE "$LOCAL_RE" \
				| awk -v set_name="$set_name" "{print \"add \" set_name \" \" \$1}"
		done
	' sh >> "$restore_file"
}

load_file_to_set() {
	list_path="$1"
	set_name="$2"
	[ -f "$list_path" ] || return 0

	ipset create "$set_name" hash:net -exist >/dev/null 2>&1
	domain_file="$tmp_dir/${set_name}.domains"
	: > "$domain_file"

	while IFS= read -r raw_line || [ -n "$raw_line" ]; do
		line="$(printf '%s\n' "$raw_line" | trim_line)"
		case "$line" in
			''|\#*) continue ;;
		esac

		if direct_entry="$(extract_direct_entry "$line")"; then
			append_restore "$set_name" "$direct_entry"
			continue
		fi

		domain="$(normalize_domain "$line")"
		[ -n "$domain" ] && printf '%s\n' "$domain" >> "$domain_file"
	done < "$list_path"

	resolve_domains "$set_name" "$domain_file"
}

wait_for_dns

load_file_to_set "$UNBLOCK_DIR/shadowsocks.txt" unblocksh
load_file_to_set "$UNBLOCK_DIR/vmess.txt" unblockvmess
load_file_to_set "$UNBLOCK_DIR/vless.txt" unblockvless
load_file_to_set "$UNBLOCK_DIR/vless-2.txt" unblockvless2
load_file_to_set "$UNBLOCK_DIR/trojan.txt" unblocktroj

if [ -s "$restore_file" ]; then
	sort -u "$restore_file" > "$restore_file.sorted"
	if ! ipset restore -exist < "$restore_file.sorted" >/dev/null 2>&1; then
		logger -t "$TAG" "ipset restore failed, falling back to sequential add"
		while read -r action set_name value; do
			[ "$action" = "add" ] && ipset -exist add "$set_name" "$value" >/dev/null 2>&1
		done < "$restore_file.sorted"
	fi
fi

exit 0
