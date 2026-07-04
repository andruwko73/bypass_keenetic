#!/bin/sh

# 2023. Keenetic DNS bot /  Проект: bypass_keenetic / Автор: tas_unn
# GitHub: https://github.com/tas-unn/bypass_keenetic
# Данный бот предназначен для управления обхода блокировок на роутерах Keenetic
# Демо-бот: https://t.me/keenetic_dns_bot
#
# Файл: 100-redirect.sh, Версия 2.1.9, последнее изменение: 03.05.2023, 21:10
# Доработал: NetworK (https://github.com/znetworkx)

#!/bin/sh

ip4t() {
	if ! iptables -C "$@" &>/dev/null; then
		 iptables -A "$@" || exit 0
	fi
}

REDIRECT_LOCK_STALE_SECONDS="${REDIRECT_LOCK_STALE_SECONDS:-120}"
REDIRECT_LOCK_DIR="${REDIRECT_LOCK_DIR:-/tmp/bypass-redirect-${type:-iptables}-${table:-unknown}.lock}"
redirect_lock_acquired=0
if mkdir "$REDIRECT_LOCK_DIR" 2>/dev/null; then
	redirect_lock_acquired=1
	printf '%s\n' "$$" > "$REDIRECT_LOCK_DIR/pid" 2>/dev/null || true
	date +%s > "$REDIRECT_LOCK_DIR/started_at" 2>/dev/null || true
else
	lock_pid="$(cat "$REDIRECT_LOCK_DIR/pid" 2>/dev/null || true)"
	if [ -n "$lock_pid" ] && [ -d "/proc/$lock_pid" ]; then
		exit 0
	fi
	lock_started="$(cat "$REDIRECT_LOCK_DIR/started_at" 2>/dev/null || echo 0)"
	lock_now="$(date +%s 2>/dev/null || echo 0)"
	if [ "$lock_now" -gt 0 ] 2>/dev/null && [ "$lock_started" -gt 0 ] 2>/dev/null \
		&& [ $((lock_now - lock_started)) -gt "$REDIRECT_LOCK_STALE_SECONDS" ] 2>/dev/null; then
		rm -rf "$REDIRECT_LOCK_DIR" 2>/dev/null || true
		if mkdir "$REDIRECT_LOCK_DIR" 2>/dev/null; then
			redirect_lock_acquired=1
			printf '%s\n' "$$" > "$REDIRECT_LOCK_DIR/pid" 2>/dev/null || true
			date +%s > "$REDIRECT_LOCK_DIR/started_at" 2>/dev/null || true
		fi
	fi
	[ "$redirect_lock_acquired" = "1" ] || exit 0
fi
trap '[ "$redirect_lock_acquired" = "1" ] && rm -rf "$REDIRECT_LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

UDP_POLICY_CONFIG="${UDP_POLICY_CONFIG:-/opt/etc/bot/udp_policy.conf}"
[ -r "$UDP_POLICY_CONFIG" ] && . "$UDP_POLICY_CONFIG"
UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"
BYPASS_UDP_QUIC_BLOCK_SHADOWSOCKS="${BYPASS_UDP_QUIC_BLOCK_SHADOWSOCKS:-1}"
BYPASS_UDP_QUIC_BLOCK_VMESS="${BYPASS_UDP_QUIC_BLOCK_VMESS:-1}"
BYPASS_UDP_QUIC_BLOCK_VLESS="${BYPASS_UDP_QUIC_BLOCK_VLESS:-1}"
BYPASS_UDP_QUIC_BLOCK_VLESS2="${BYPASS_UDP_QUIC_BLOCK_VLESS2:-1}"
BYPASS_UDP_QUIC_BLOCK_TROJAN="${BYPASS_UDP_QUIC_BLOCK_TROJAN:-1}"
UDP_QUIC_REJECT_PORT="${UDP_QUIC_REJECT_PORT:-10944}"
BYPASS_IPV6_FALLBACK_ENABLED="${BYPASS_IPV6_FALLBACK_ENABLED:-1}"
BYPASS_TELEGRAM_CALL_LEARNING_ENABLED="${BYPASS_TELEGRAM_CALL_LEARNING_ENABLED:-0}"
BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT="${BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT:-14400}"
BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT="${BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT:-14400}"
BYPASS_TELEGRAM_CALL_TPROXY_ENABLED="${BYPASS_TELEGRAM_CALL_TPROXY_ENABLED:-0}"
BYPASS_TELEGRAM_CALL_TPROXY_MARK="${BYPASS_TELEGRAM_CALL_TPROXY_MARK:-0x71}"
BYPASS_TELEGRAM_CALL_TPROXY_TABLE="${BYPASS_TELEGRAM_CALL_TPROXY_TABLE:-100}"
BYPASS_TELEGRAM_CALL_TPROXY_PRIORITY="${BYPASS_TELEGRAM_CALL_TPROXY_PRIORITY:-100}"
BYPASS_TELEGRAM_CALL_UDP_REDIRECT_ENABLED="${BYPASS_TELEGRAM_CALL_UDP_REDIRECT_ENABLED:-0}"
BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED="${BYPASS_TELEGRAM_CALL_CLIENT_UDP_ROUTE_ENABLED:-0}"
BYPASS_TELEGRAM_CALL_SIGNAL_ROUTE_ENABLED="${BYPASS_TELEGRAM_CALL_SIGNAL_ROUTE_ENABLED:-1}"
BYPASS_TELEGRAM_CALL_ROUTE_SHADOWSOCKS="${BYPASS_TELEGRAM_CALL_ROUTE_SHADOWSOCKS:-0}"
BYPASS_TELEGRAM_CALL_ROUTE_VMESS="${BYPASS_TELEGRAM_CALL_ROUTE_VMESS:-0}"
BYPASS_TELEGRAM_CALL_ROUTE_VLESS="${BYPASS_TELEGRAM_CALL_ROUTE_VLESS:-0}"
BYPASS_TELEGRAM_CALL_ROUTE_VLESS2="${BYPASS_TELEGRAM_CALL_ROUTE_VLESS2:-0}"
BYPASS_TELEGRAM_CALL_ROUTE_TROJAN="${BYPASS_TELEGRAM_CALL_ROUTE_TROJAN:-0}"
BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_SHADOWSOCKS="${BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_SHADOWSOCKS:-$BYPASS_TELEGRAM_CALL_ROUTE_SHADOWSOCKS}"
BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VMESS="${BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VMESS:-$BYPASS_TELEGRAM_CALL_ROUTE_VMESS}"
BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS="${BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS:-$BYPASS_TELEGRAM_CALL_ROUTE_VLESS}"
BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS2="${BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS2:-$BYPASS_TELEGRAM_CALL_ROUTE_VLESS2}"
BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_TROJAN="${BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_TROJAN:-$BYPASS_TELEGRAM_CALL_ROUTE_TROJAN}"
TELEGRAM_CALL_CLIENT_SET="${TELEGRAM_CALL_CLIENT_SET:-bypass_tg_call_clients}"
TELEGRAM_CALL_SIGNAL_SET="${TELEGRAM_CALL_SIGNAL_SET:-bypass_tg_call_signal}"
CALL_CLIENT_SET_SHADOWSOCKS="${CALL_CLIENT_SET_SHADOWSOCKS:-bypass_call_clients_sh}"
CALL_CLIENT_SET_VMESS="${CALL_CLIENT_SET_VMESS:-bypass_call_clients_vmess}"
CALL_CLIENT_SET_VLESS="${CALL_CLIENT_SET_VLESS:-bypass_call_clients_vless}"
CALL_CLIENT_SET_VLESS2="${CALL_CLIENT_SET_VLESS2:-bypass_call_clients_vless2}"
CALL_CLIENT_SET_TROJAN="${CALL_CLIENT_SET_TROJAN:-bypass_call_clients_troj}"
CALL_SIGNAL_SET_SHADOWSOCKS="${CALL_SIGNAL_SET_SHADOWSOCKS:-bypass_call_signal_sh}"
CALL_SIGNAL_SET_VMESS="${CALL_SIGNAL_SET_VMESS:-bypass_call_signal_vmess}"
CALL_SIGNAL_SET_VLESS="${CALL_SIGNAL_SET_VLESS:-bypass_call_signal_vless}"
CALL_SIGNAL_SET_VLESS2="${CALL_SIGNAL_SET_VLESS2:-bypass_call_signal_vless2}"
CALL_SIGNAL_SET_TROJAN="${CALL_SIGNAL_SET_TROJAN:-bypass_call_signal_troj}"
TELEGRAM_CALL_LEARN_CHAIN="${TELEGRAM_CALL_LEARN_CHAIN:-BYPASS_TG_CALL_LEARN}"
TELEGRAM_CALL_ROUTE_CHAIN="${TELEGRAM_CALL_ROUTE_CHAIN:-BYPASS_TG_CALL_ROUTE}"
TELEGRAM_CALL_TPROXY_CHAIN="${TELEGRAM_CALL_TPROXY_CHAIN:-BYPASS_TG_CALL_TPROXY}"
TELEGRAM_CALL_TPROXY_PORT_SHADOWSOCKS="${TELEGRAM_CALL_TPROXY_PORT_SHADOWSOCKS:-11802}"
TELEGRAM_CALL_TPROXY_PORT_VMESS="${TELEGRAM_CALL_TPROXY_PORT_VMESS:-11815}"
TELEGRAM_CALL_TPROXY_PORT_VLESS="${TELEGRAM_CALL_TPROXY_PORT_VLESS:-11812}"
TELEGRAM_CALL_TPROXY_PORT_VLESS2="${TELEGRAM_CALL_TPROXY_PORT_VLESS2:-11814}"
TELEGRAM_CALL_TPROXY_PORT_TROJAN="${TELEGRAM_CALL_TPROXY_PORT_TROJAN:-11829}"

install_ipv6_fallback_rules() {
	command -v ip6tables >/dev/null 2>&1 || return 0

	for set_name in unblocksh6 unblockvmess6 unblockvless6 unblockvless2v6 unblocktroj6; do
		ipset list "$set_name" >/dev/null 2>&1 || continue
		for protocol in tcp udp; do
			while ip6tables -C FORWARD -w -p "$protocol" -m set --match-set "$set_name" dst --dport 443 -j REJECT 2>/dev/null; do
				ip6tables -D FORWARD -w -p "$protocol" -m set --match-set "$set_name" dst --dport 443 -j REJECT
			done
			while ip6tables -C FORWARD -w -p "$protocol" -m set --match-set "$set_name" dst --dport 443 -j DROP 2>/dev/null; do
				ip6tables -D FORWARD -w -p "$protocol" -m set --match-set "$set_name" dst --dport 443 -j DROP
			done
			if [ "$BYPASS_IPV6_FALLBACK_ENABLED" != "0" ]; then
				ip6tables -I FORWARD -w -p "$protocol" -m set --match-set "$set_name" dst --dport 443 -j REJECT 2>/dev/null \
					|| ip6tables -I FORWARD -w -p "$protocol" -m set --match-set "$set_name" dst --dport 443 -j DROP 2>/dev/null \
					|| true
			fi
		done
	done
}

# shellcheck disable=SC2154
if [ "$type" = "ip6tables" ]; then
	[ "$table" = "filter" ] || [ -z "$table" ] || exit 0
	install_ipv6_fallback_rules
	exit 0
fi
[ "$table" != "mangle" ] && [ "$table" != "nat" ] && exit 0

cleanup_legacy_redirect_set() {
	set_name="$1"
	port="$2"
	for protocol in tcp udp; do
		while iptables -t nat -C PREROUTING -w -p "$protocol" -m set --match-set "$set_name" dst -j REDIRECT --to-ports "$port" 2>/dev/null; do
			iptables -t nat -D PREROUTING -w -p "$protocol" -m set --match-set "$set_name" dst -j REDIRECT --to-ports "$port"
		done
	done
	ipset destroy "$set_name" 2>/dev/null || true
}

cleanup_legacy_redirect_set unblocktor 9141
ipset destroy unblockvpn 2>/dev/null || true

local_ip=$(ip -4 addr show br0 | grep -Eo '([0-9]{1,3}\.){3}[0-9]{1,3}' | head -n1)

if [ -z "$local_ip" ]; then
    echo "[100-redirect.sh] br0 has no IPv4 address, skip DNS redirect" >&2
    exit 0
fi

for protocol in udp tcp; do
	if [ -z "$(iptables-save 2>/dev/null | grep "$protocol --dport 53 -j DNAT")" ]; then
	iptables -I PREROUTING -w -t nat -p "$protocol" --dport 53 -j DNAT --to "$local_ip"; fi
done

refresh_transparent_udp_quic_reject() {
	reject_port="$1"
	reject_enabled="$2"
	while iptables -C INPUT -w -p udp --dport "$reject_port" -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
		iptables -D INPUT -w -p udp --dport "$reject_port" -j REJECT --reject-with icmp-port-unreachable
	done
	while iptables -C INPUT -w -p udp --dport "$reject_port" -j DROP 2>/dev/null; do
		iptables -D INPUT -w -p udp --dport "$reject_port" -j DROP
	done
	if [ "$reject_enabled" != "0" ]; then
		iptables -I INPUT -w -p udp --dport "$reject_port" -j REJECT --reject-with icmp-port-unreachable 2>/dev/null \
			|| iptables -I INPUT -w -p udp --dport "$reject_port" -j DROP 2>/dev/null \
			|| true
	fi
}

refresh_udp_quic_reject_port() {
	reject_enabled="$1"
	for reject_port in 10812 10814 "$UDP_QUIC_REJECT_PORT"; do
		while iptables -C INPUT -w -p udp --dport "$reject_port" -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
			iptables -D INPUT -w -p udp --dport "$reject_port" -j REJECT --reject-with icmp-port-unreachable
		done
		while iptables -C INPUT -w -p udp --dport "$reject_port" -j DROP 2>/dev/null; do
			iptables -D INPUT -w -p udp --dport "$reject_port" -j DROP
		done
	done
	if [ "$reject_enabled" != "0" ]; then
		iptables -I INPUT -w -p udp --dport "$UDP_QUIC_REJECT_PORT" -j REJECT --reject-with icmp-port-unreachable 2>/dev/null \
			|| iptables -I INPUT -w -p udp --dport "$UDP_QUIC_REJECT_PORT" -j DROP 2>/dev/null \
			|| true
	fi
}

remove_udp_quic_block_rule() {
	set_name="$1"
	for reject_port in 1082 10812 10814 10815 10829 "$UDP_QUIC_REJECT_PORT"; do
		while iptables -t nat -C PREROUTING -w -p udp -m set --match-set "$set_name" dst -m udp --dport 443 -j REDIRECT --to-ports "$reject_port" 2>/dev/null; do
			iptables -t nat -D PREROUTING -w -p udp -m set --match-set "$set_name" dst -m udp --dport 443 -j REDIRECT --to-ports "$reject_port"
		done
	done
}

install_udp_quic_block_rule() {
	set_name="$1"
	block_enabled="$2"
	ipset create "$set_name" hash:net -exist 2>/dev/null
	remove_udp_quic_block_rule "$set_name"
	if [ "$block_enabled" != "0" ]; then
		iptables -I PREROUTING -w -t nat -p udp -m set --match-set "$set_name" dst -m udp --dport 443 -j REDIRECT --to-ports "$UDP_QUIC_REJECT_PORT"
	fi
}

refresh_udp_quic_block_rules() {
	reject_enabled=0
	for flag in \
		"$BYPASS_UDP_QUIC_BLOCK_SHADOWSOCKS" \
		"$BYPASS_UDP_QUIC_BLOCK_VMESS" \
		"$BYPASS_UDP_QUIC_BLOCK_VLESS" \
		"$BYPASS_UDP_QUIC_BLOCK_VLESS2" \
		"$BYPASS_UDP_QUIC_BLOCK_TROJAN"
	do
		[ "$flag" != "0" ] && reject_enabled=1
	done
	refresh_udp_quic_reject_port "$reject_enabled"
	install_udp_quic_block_rule unblockshudp "$BYPASS_UDP_QUIC_BLOCK_SHADOWSOCKS"
	install_udp_quic_block_rule unblockvmessudp "$BYPASS_UDP_QUIC_BLOCK_VMESS"
	install_udp_quic_block_rule unblockvlessudp "$BYPASS_UDP_QUIC_BLOCK_VLESS"
	install_udp_quic_block_rule unblockvless2udp "$BYPASS_UDP_QUIC_BLOCK_VLESS2"
	install_udp_quic_block_rule unblocktrojudp "$BYPASS_UDP_QUIC_BLOCK_TROJAN"
}

telegram_call_route_enabled() {
	case "$1" in
		shadowsocks) [ "$BYPASS_TELEGRAM_CALL_ROUTE_SHADOWSOCKS" = "1" ] ;;
		vmess) [ "$BYPASS_TELEGRAM_CALL_ROUTE_VMESS" = "1" ] ;;
		vless) [ "$BYPASS_TELEGRAM_CALL_ROUTE_VLESS" = "1" ] ;;
		vless2) [ "$BYPASS_TELEGRAM_CALL_ROUTE_VLESS2" = "1" ] ;;
		trojan) [ "$BYPASS_TELEGRAM_CALL_ROUTE_TROJAN" = "1" ] ;;
		*) return 1 ;;
	esac
}

telegram_call_telegram_route_enabled() {
	case "$1" in
		shadowsocks) [ "$BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_SHADOWSOCKS" = "1" ] ;;
		vmess) [ "$BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VMESS" = "1" ] ;;
		vless) [ "$BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS" = "1" ] ;;
		vless2) [ "$BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_VLESS2" = "1" ] ;;
		trojan) [ "$BYPASS_TELEGRAM_CALL_TELEGRAM_ROUTE_TROJAN" = "1" ] ;;
		*) return 1 ;;
	esac
}

telegram_call_base_set() {
	case "$1" in
		shadowsocks) printf '%s\n' unblocksh ;;
		vmess) printf '%s\n' unblockvmess ;;
		vless) printf '%s\n' unblockvless ;;
		vless2) printf '%s\n' unblockvless2 ;;
		trojan) printf '%s\n' unblocktroj ;;
	esac
}

telegram_call_client_set() {
	case "$1" in
		shadowsocks) printf '%s\n' "$CALL_CLIENT_SET_SHADOWSOCKS" ;;
		vmess) printf '%s\n' "$CALL_CLIENT_SET_VMESS" ;;
		vless) printf '%s\n' "$CALL_CLIENT_SET_VLESS" ;;
		vless2) printf '%s\n' "$CALL_CLIENT_SET_VLESS2" ;;
		trojan) printf '%s\n' "$CALL_CLIENT_SET_TROJAN" ;;
	esac
}

telegram_call_signal_set() {
	case "$1" in
		shadowsocks) printf '%s\n' "$CALL_SIGNAL_SET_SHADOWSOCKS" ;;
		vmess) printf '%s\n' "$CALL_SIGNAL_SET_VMESS" ;;
		vless) printf '%s\n' "$CALL_SIGNAL_SET_VLESS" ;;
		vless2) printf '%s\n' "$CALL_SIGNAL_SET_VLESS2" ;;
		trojan) printf '%s\n' "$CALL_SIGNAL_SET_TROJAN" ;;
	esac
}

telegram_call_all_client_sets() {
	printf '%s\n' "$TELEGRAM_CALL_CLIENT_SET" "$CALL_CLIENT_SET_SHADOWSOCKS" "$CALL_CLIENT_SET_VMESS" "$CALL_CLIENT_SET_VLESS" "$CALL_CLIENT_SET_VLESS2" "$CALL_CLIENT_SET_TROJAN"
}

telegram_call_all_signal_sets() {
	printf '%s\n' "$TELEGRAM_CALL_SIGNAL_SET" "$CALL_SIGNAL_SET_SHADOWSOCKS" "$CALL_SIGNAL_SET_VMESS" "$CALL_SIGNAL_SET_VLESS" "$CALL_SIGNAL_SET_VLESS2" "$CALL_SIGNAL_SET_TROJAN"
}

telegram_call_learned_set() {
	case "$1" in
		shadowsocks) printf '%s\n' bypass_tg_call_sh ;;
		vmess) printf '%s\n' bypass_tg_call_vmess ;;
		vless) printf '%s\n' bypass_tg_call_vless ;;
		vless2) printf '%s\n' bypass_tg_call_vless2 ;;
		trojan) printf '%s\n' bypass_tg_call_troj ;;
	esac
}

telegram_call_target_port() {
	case "$1" in
		shadowsocks) printf '%s\n' 1082 ;;
		vmess) printf '%s\n' 10815 ;;
		vless) printf '%s\n' 10812 ;;
		vless2) [ -n "$vless2_key_path" ] && printf '%s\n' 10814 ;;
		trojan) printf '%s\n' 10829 ;;
	esac
}

telegram_call_tproxy_port() {
	case "$1" in
		shadowsocks) printf '%s\n' "$TELEGRAM_CALL_TPROXY_PORT_SHADOWSOCKS" ;;
		vmess) printf '%s\n' "$TELEGRAM_CALL_TPROXY_PORT_VMESS" ;;
		vless) printf '%s\n' "$TELEGRAM_CALL_TPROXY_PORT_VLESS" ;;
		vless2) [ -n "$vless2_key_path" ] && printf '%s\n' "$TELEGRAM_CALL_TPROXY_PORT_VLESS2" ;;
		trojan) printf '%s\n' "$TELEGRAM_CALL_TPROXY_PORT_TROJAN" ;;
	esac
}

telegram_call_excluded_destinations() {
	cat <<'EOF'
0.0.0.0/8
10.0.0.0/8
100.64.0.0/10
127.0.0.0/8
169.254.0.0/16
172.16.0.0/12
192.168.0.0/16
224.0.0.0/4
240.0.0.0/4
EOF
}

telegram_call_signal_tcp_ports() {
	printf '%s\n' 80 88 443 5222 5223 5228 5229 5230
}

telegram_call_client_udp_ports() {
	# Client-wide UDP routing is intentionally disabled: learned clients are too broad
	# and can hijack unrelated Vless traffic for the whole timeout window.
	return 0
}

telegram_call_client_udp_cleanup_ports() {
	printf '%s\n' 443 1024:65535
}

telegram_call_known_route_sets() {
	cat <<'EOF'
unblocksh
unblockvmess
unblockvless
unblockvless2
unblocktroj
unblockshudp
unblockvmessudp
unblockvlessudp
unblockvless2udp
unblocktrojudp
EOF
}

telegram_call_ipset_has_entries() {
	set_name="$1"
	ipset list "$set_name" 2>/dev/null | awk -F': ' '
		/^Number of entries:/ {
			if (($2 + 0) > 0) found = 1
		}
		/^Members:/ {
			members = 1
			next
		}
		members && NF {
			found = 1
		}
		END { exit(found ? 0 : 1) }
	'
}

telegram_call_chains_installed() {
	iptables -t mangle -L "$TELEGRAM_CALL_LEARN_CHAIN" >/dev/null 2>&1 || return 1
	iptables -t mangle -L "$TELEGRAM_CALL_TPROXY_CHAIN" >/dev/null 2>&1 || return 1
	iptables -t nat -L "$TELEGRAM_CALL_ROUTE_CHAIN" >/dev/null 2>&1 || return 1
}

load_tproxy_module() {
	module_name="$1"
	module_path="/lib/modules/$(uname -r)/${module_name}.ko"
	[ -f "$module_path" ] || return 1
	for insmod_bin in /sbin/insmod /opt/sbin/insmod insmod; do
		command -v "$insmod_bin" >/dev/null 2>&1 || continue
		"$insmod_bin" "$module_path" >/dev/null 2>&1 || true
		return 0
	done
	return 1
}

ensure_telegram_call_tproxy_support() {
	[ "$BYPASS_TELEGRAM_CALL_TPROXY_ENABLED" != "0" ] || return 1
	grep -qx socket /proc/net/ip_tables_matches 2>/dev/null || load_tproxy_module xt_socket || return 1
	grep -qx TPROXY /proc/net/ip_tables_targets 2>/dev/null || load_tproxy_module xt_TPROXY || return 1
	grep -qx socket /proc/net/ip_tables_matches 2>/dev/null || return 1
	grep -qx TPROXY /proc/net/ip_tables_targets 2>/dev/null || return 1
	command -v ip >/dev/null 2>&1 || return 1
	ip rule show 2>/dev/null | grep -q "fwmark $BYPASS_TELEGRAM_CALL_TPROXY_MARK .*lookup $BYPASS_TELEGRAM_CALL_TPROXY_TABLE" \
		|| ip rule add fwmark "$BYPASS_TELEGRAM_CALL_TPROXY_MARK" lookup "$BYPASS_TELEGRAM_CALL_TPROXY_TABLE" priority "$BYPASS_TELEGRAM_CALL_TPROXY_PRIORITY" >/dev/null 2>&1 \
		|| true
	ip route show table "$BYPASS_TELEGRAM_CALL_TPROXY_TABLE" 2>/dev/null | grep -q '^local default dev lo' \
		|| ip route add local 0.0.0.0/0 dev lo table "$BYPASS_TELEGRAM_CALL_TPROXY_TABLE" >/dev/null 2>&1 \
		|| true
	ip rule show 2>/dev/null | grep -q "fwmark $BYPASS_TELEGRAM_CALL_TPROXY_MARK .*lookup $BYPASS_TELEGRAM_CALL_TPROXY_TABLE" || return 1
	ip route show table "$BYPASS_TELEGRAM_CALL_TPROXY_TABLE" 2>/dev/null | grep -q '^local default dev lo' || return 1
	return 0
}

ensure_timeout_ipset() {
	set_name="$1"
	timeout_value="$2"
	maxelem="${3:-256}"
	current_timeout="$(
		ipset list "$set_name" 2>/dev/null \
			| awk '/^Header:/ { for (i = 1; i <= NF; i++) if ($i == "timeout") { print $(i + 1); exit } }'
	)"
	if [ -n "$current_timeout" ] && [ "$current_timeout" != "$timeout_value" ]; then
		ipset destroy "$set_name" >/dev/null 2>&1 || true
	fi
	ipset create "$set_name" hash:ip timeout "$timeout_value" maxelem "$maxelem" -exist >/dev/null 2>&1 && return 0
	ipset destroy "$set_name" >/dev/null 2>&1 || true
	ipset create "$set_name" hash:ip timeout "$timeout_value" maxelem "$maxelem" -exist >/dev/null 2>&1
}

refresh_telegram_call_signal_set() {
	ipset create "$TELEGRAM_CALL_SIGNAL_SET" hash:net -exist >/dev/null 2>&1 || return 1
	ipset flush "$TELEGRAM_CALL_SIGNAL_SET" >/dev/null 2>&1 || true
	for proto in shadowsocks vmess vless vless2 trojan; do
		signal_set="$(telegram_call_signal_set "$proto")"
		[ -n "$signal_set" ] || continue
		ipset create "$signal_set" hash:net -exist >/dev/null 2>&1 || continue
		ipset flush "$signal_set" >/dev/null 2>&1 || true
		telegram_call_telegram_route_enabled "$proto" || continue
		for telegram_network in 91.108.0.0/16 149.154.160.0/20 95.161.64.0/20; do
			ipset add "$signal_set" "$telegram_network" -exist >/dev/null 2>&1 || true
			ipset add "$TELEGRAM_CALL_SIGNAL_SET" "$telegram_network" -exist >/dev/null 2>&1 || true
		done
	done
}

reset_iptables_chain() {
	table_name="$1"
	chain_name="$2"
	iptables -t "$table_name" -N "$chain_name" 2>/dev/null || true
	iptables -t "$table_name" -F "$chain_name" 2>/dev/null || true
}

remove_telegram_call_prerouting_jumps() {
	while iptables -t "$table_name" -C PREROUTING -j "$chain_name" 2>/dev/null; do
		iptables -t "$table_name" -D PREROUTING -j "$chain_name"
	done
	if [ "$table_name" = "mangle" ] && [ "$chain_name" = "$TELEGRAM_CALL_LEARN_CHAIN" ]; then
		for signal_set in $(telegram_call_all_signal_sets); do
			ipset list "$signal_set" >/dev/null 2>&1 || continue
			for signal_port in $(telegram_call_signal_tcp_ports); do
				while iptables -t mangle -C PREROUTING -p tcp -m tcp --dport "$signal_port" -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN" 2>/dev/null; do
					iptables -t mangle -D PREROUTING -p tcp -m tcp --dport "$signal_port" -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"
				done
			done
			while iptables -t mangle -C PREROUTING -p udp -m udp --dport 3478:3497 -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN" 2>/dev/null; do
				iptables -t mangle -D PREROUTING -p udp -m udp --dport 3478:3497 -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"
			done
			while iptables -t mangle -C PREROUTING -p udp -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN" 2>/dev/null; do
				iptables -t mangle -D PREROUTING -p udp -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"
			done
		done
		for client_set in $(telegram_call_all_client_sets); do
			ipset list "$client_set" >/dev/null 2>&1 || continue
			for client_udp_port in $(telegram_call_client_udp_cleanup_ports); do
				while iptables -t mangle -C PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j "$TELEGRAM_CALL_LEARN_CHAIN" 2>/dev/null; do
					iptables -t mangle -D PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j "$TELEGRAM_CALL_LEARN_CHAIN"
				done
			done
		done
		for learned_set in bypass_tg_call_sh bypass_tg_call_vmess bypass_tg_call_vless bypass_tg_call_vless2 bypass_tg_call_troj; do
			while iptables -t mangle -C PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN" 2>/dev/null; do
				iptables -t mangle -D PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"
			done
		done
	fi
	if [ "$table_name" = "mangle" ] && [ "$chain_name" = "$TELEGRAM_CALL_TPROXY_CHAIN" ]; then
		for client_set in $(telegram_call_all_client_sets); do
			ipset list "$client_set" >/dev/null 2>&1 || continue
			for client_udp_port in $(telegram_call_client_udp_cleanup_ports); do
				while iptables -t mangle -C PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j "$TELEGRAM_CALL_TPROXY_CHAIN" 2>/dev/null; do
					iptables -t mangle -D PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j "$TELEGRAM_CALL_TPROXY_CHAIN"
				done
			done
		done
		for signal_set in $(telegram_call_all_signal_sets); do
			ipset list "$signal_set" >/dev/null 2>&1 || continue
			while iptables -t mangle -C PREROUTING -p udp -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_TPROXY_CHAIN" 2>/dev/null; do
				iptables -t mangle -D PREROUTING -p udp -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_TPROXY_CHAIN"
			done
		done
		for learned_set in bypass_tg_call_sh bypass_tg_call_vmess bypass_tg_call_vless bypass_tg_call_vless2 bypass_tg_call_troj; do
			while iptables -t mangle -C PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_TPROXY_CHAIN" 2>/dev/null; do
				iptables -t mangle -D PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_TPROXY_CHAIN"
			done
		done
	fi
	if [ "$table_name" = "nat" ] && [ "$chain_name" = "$TELEGRAM_CALL_ROUTE_CHAIN" ]; then
		while iptables -t nat -C PREROUTING -p udp -j "$TELEGRAM_CALL_ROUTE_CHAIN" 2>/dev/null; do
			iptables -t nat -D PREROUTING -p udp -j "$TELEGRAM_CALL_ROUTE_CHAIN"
		done
		for client_set in $(telegram_call_all_client_sets); do
			ipset list "$client_set" >/dev/null 2>&1 || continue
			for client_udp_port in $(telegram_call_client_udp_cleanup_ports); do
				while iptables -t nat -C PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j "$TELEGRAM_CALL_ROUTE_CHAIN" 2>/dev/null; do
					iptables -t nat -D PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j "$TELEGRAM_CALL_ROUTE_CHAIN"
				done
				while iptables -t nat -C PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j RETURN 2>/dev/null; do
					iptables -t nat -D PREROUTING -p udp -m udp --dport "$client_udp_port" -m set --match-set "$client_set" src -j RETURN
				done
			done
		done
		for signal_set in $(telegram_call_all_signal_sets); do
			ipset list "$signal_set" >/dev/null 2>&1 || continue
			for signal_port in $(telegram_call_signal_tcp_ports); do
				while iptables -t nat -C PREROUTING -p tcp -m tcp --dport "$signal_port" -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN" 2>/dev/null; do
					iptables -t nat -D PREROUTING -p tcp -m tcp --dport "$signal_port" -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN"
				done
			done
			while iptables -t nat -C PREROUTING -p udp -m udp --dport 1024:65535 -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN" 2>/dev/null; do
				iptables -t nat -D PREROUTING -p udp -m udp --dport 1024:65535 -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN"
			done
			while iptables -t nat -C PREROUTING -p udp -m set --match-set "$signal_set" dst -j RETURN 2>/dev/null; do
				iptables -t nat -D PREROUTING -p udp -m set --match-set "$signal_set" dst -j RETURN
			done
		done
		for learned_set in bypass_tg_call_sh bypass_tg_call_vmess bypass_tg_call_vless bypass_tg_call_vless2 bypass_tg_call_troj; do
			while iptables -t nat -C PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN" 2>/dev/null; do
				iptables -t nat -D PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN"
			done
			while iptables -t nat -C PREROUTING -p udp -m set --match-set "$learned_set" dst -j RETURN 2>/dev/null; do
				iptables -t nat -D PREROUTING -p udp -m set --match-set "$learned_set" dst -j RETURN
			done
		done
	fi
}

remove_iptables_chain() {
	table_name="$1"
	chain_name="$2"
	remove_telegram_call_prerouting_jumps
	iptables -t "$table_name" -F "$chain_name" 2>/dev/null || true
	iptables -t "$table_name" -X "$chain_name" 2>/dev/null || true
}

install_telegram_call_prerouting_jumps() {
	for proto in shadowsocks vmess vless vless2 trojan; do
		telegram_call_route_enabled "$proto" || continue
		signal_set="$(telegram_call_signal_set "$proto")"
		[ -n "$signal_set" ] || continue
		ipset list "$signal_set" >/dev/null 2>&1 || continue
		for signal_port in $(telegram_call_signal_tcp_ports); do
			iptables -t mangle -I PREROUTING -p tcp -m tcp --dport "$signal_port" -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"
		done
		iptables -t mangle -I PREROUTING -p udp -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"
	done
	for proto in shadowsocks vmess vless vless2 trojan; do
		telegram_call_route_enabled "$proto" || continue
		learned_set="$(telegram_call_learned_set "$proto")"
		[ -n "$learned_set" ] || continue
		ipset list "$learned_set" >/dev/null 2>&1 || continue
		iptables -t mangle -I PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_LEARN_CHAIN"
	done
	if [ "$BYPASS_TELEGRAM_CALL_UDP_REDIRECT_ENABLED" != "0" ]; then
		for proto in shadowsocks vmess vless vless2 trojan; do
			telegram_call_route_enabled "$proto" || continue
			learned_set="$(telegram_call_learned_set "$proto")"
			[ -n "$learned_set" ] || continue
			ipset list "$learned_set" >/dev/null 2>&1 || continue
			iptables -t nat -I PREROUTING -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN"
		done
	else
		for proto in shadowsocks vmess vless vless2 trojan; do
			telegram_call_route_enabled "$proto" || continue
			learned_set="$(telegram_call_learned_set "$proto")"
			[ -n "$learned_set" ] || continue
			ipset list "$learned_set" >/dev/null 2>&1 || continue
			iptables -t nat -I PREROUTING -p udp -m set --match-set "$learned_set" dst -j RETURN
		done
		for proto in shadowsocks vmess vless vless2 trojan; do
			telegram_call_route_enabled "$proto" || continue
			signal_set="$(telegram_call_signal_set "$proto")"
			[ -n "$signal_set" ] && ipset list "$signal_set" >/dev/null 2>&1 \
				&& iptables -t nat -I PREROUTING -p udp -m set --match-set "$signal_set" dst -j RETURN
		done
	fi
	if [ "$BYPASS_TELEGRAM_CALL_SIGNAL_ROUTE_ENABLED" != "0" ]; then
		for proto in shadowsocks vmess vless vless2 trojan; do
			telegram_call_route_enabled "$proto" || continue
			signal_set="$(telegram_call_signal_set "$proto")"
			[ -n "$signal_set" ] || continue
			ipset list "$signal_set" >/dev/null 2>&1 || continue
			for signal_port in $(telegram_call_signal_tcp_ports); do
				iptables -t nat -I PREROUTING -p tcp -m tcp --dport "$signal_port" -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN"
			done
			if [ "$BYPASS_TELEGRAM_CALL_UDP_REDIRECT_ENABLED" != "0" ]; then
				iptables -t nat -I PREROUTING -p udp -m udp --dport 1024:65535 -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_ROUTE_CHAIN"
			fi
		done
	fi
}

telegram_call_mangle_tproxy_insert_index() {
	learn_jump_count="$(
		iptables-save -t mangle 2>/dev/null \
			| grep -c -- "^-A PREROUTING .* -j $TELEGRAM_CALL_LEARN_CHAIN"
	)"
	printf '%s\n' "$((learn_jump_count + 1))"
}

install_telegram_call_tproxy_prerouting_rule() {
	insert_index="$(telegram_call_mangle_tproxy_insert_index)"
	iptables -t mangle -I PREROUTING "$insert_index" "$@"
}

install_telegram_call_tproxy_prerouting_jumps() {
	[ "$telegram_call_tproxy_ready" = "1" ] || return 0
	for proto in shadowsocks vmess vless vless2 trojan; do
		telegram_call_route_enabled "$proto" || continue
		signal_set="$(telegram_call_signal_set "$proto")"
		[ -n "$signal_set" ] && ipset list "$signal_set" >/dev/null 2>&1 \
			&& install_telegram_call_tproxy_prerouting_rule -p udp -m set --match-set "$signal_set" dst -j "$TELEGRAM_CALL_TPROXY_CHAIN"
	done
	for proto in shadowsocks vmess vless vless2 trojan; do
		telegram_call_route_enabled "$proto" || continue
		learned_set="$(telegram_call_learned_set "$proto")"
		[ -n "$learned_set" ] || continue
		ipset list "$learned_set" >/dev/null 2>&1 || continue
		install_telegram_call_tproxy_prerouting_rule -p udp -m set --match-set "$learned_set" dst -j "$TELEGRAM_CALL_TPROXY_CHAIN"
	done
}

refresh_telegram_call_prerouting_jumps() {
	table_name=mangle chain_name="$TELEGRAM_CALL_LEARN_CHAIN" remove_telegram_call_prerouting_jumps
	table_name=mangle chain_name="$TELEGRAM_CALL_TPROXY_CHAIN" remove_telegram_call_prerouting_jumps
	table_name=nat chain_name="$TELEGRAM_CALL_ROUTE_CHAIN" remove_telegram_call_prerouting_jumps
	install_telegram_call_prerouting_jumps
	install_telegram_call_tproxy_prerouting_jumps
}

cleanup_telegram_call_learning_rules() {
	remove_iptables_chain mangle "$TELEGRAM_CALL_LEARN_CHAIN"
	remove_iptables_chain mangle "$TELEGRAM_CALL_TPROXY_CHAIN"
	remove_iptables_chain nat "$TELEGRAM_CALL_ROUTE_CHAIN"
	for learned_set in bypass_tg_call_sh bypass_tg_call_vmess bypass_tg_call_vless bypass_tg_call_vless2 bypass_tg_call_troj; do
		ipset destroy "$learned_set" >/dev/null 2>&1 || true
	done
	for client_set in $(telegram_call_all_client_sets); do
		ipset destroy "$client_set" >/dev/null 2>&1 || true
	done
	for signal_set in $(telegram_call_all_signal_sets); do
		ipset destroy "$signal_set" >/dev/null 2>&1 || true
	done
	ipset destroy "$TELEGRAM_CALL_SIGNAL_SET" >/dev/null 2>&1 || true
	ipset destroy "$TELEGRAM_CALL_CLIENT_SET" >/dev/null 2>&1 || true
}

telegram_call_active_protocols() {
	for proto in shadowsocks vmess vless vless2 trojan; do
		telegram_call_route_enabled "$proto" && printf '%s\n' "$proto"
	done
}

refresh_telegram_call_learning_rules() {
	if [ "$BYPASS_TELEGRAM_CALL_LEARNING_ENABLED" = "0" ]; then
		cleanup_telegram_call_learning_rules
		return
	fi

	active_protocols="$(telegram_call_active_protocols)"
	if [ -z "$active_protocols" ]; then
		cleanup_telegram_call_learning_rules
		return
	fi

	reset_iptables_chain mangle "$TELEGRAM_CALL_LEARN_CHAIN"
	reset_iptables_chain mangle "$TELEGRAM_CALL_TPROXY_CHAIN"
	reset_iptables_chain nat "$TELEGRAM_CALL_ROUTE_CHAIN"
	ensure_timeout_ipset "$TELEGRAM_CALL_CLIENT_SET" "$BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT" 64 || return 0
	refresh_telegram_call_signal_set || return 0
	for proto in $active_protocols; do
		client_set="$(telegram_call_client_set "$proto")"
		[ -n "$client_set" ] || continue
		ensure_timeout_ipset "$client_set" "$BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT" 64 || return 0
	done
	telegram_call_tproxy_ready=0
	if ensure_telegram_call_tproxy_support; then
		telegram_call_tproxy_ready=1
	fi

	for excluded_destination in $(telegram_call_excluded_destinations); do
		iptables -t mangle -A "$TELEGRAM_CALL_LEARN_CHAIN" -d "$excluded_destination" -j RETURN
		iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -d "$excluded_destination" -j RETURN
		iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -d "$excluded_destination" -j RETURN
	done

	for proto in $active_protocols; do
		client_set="$(telegram_call_client_set "$proto")"
		signal_set="$(telegram_call_signal_set "$proto")"
		[ -n "$client_set" ] && [ -n "$signal_set" ] || continue
		ipset list "$client_set" >/dev/null 2>&1 || continue
		ipset list "$signal_set" >/dev/null 2>&1 || continue
		for signal_port in $(telegram_call_signal_tcp_ports); do
			iptables -t mangle -A "$TELEGRAM_CALL_LEARN_CHAIN" -p tcp -m tcp -m set --match-set "$signal_set" dst --dport "$signal_port" \
				-j SET --add-set "$client_set" src --exist --timeout "$BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT"
		done
		iptables -t mangle -A "$TELEGRAM_CALL_LEARN_CHAIN" -p udp -m set --match-set "$signal_set" dst \
			-j SET --add-set "$client_set" src --exist --timeout "$BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT"
	done
	for known_set in $(telegram_call_known_route_sets); do
		ipset list "$known_set" >/dev/null 2>&1 || continue
		iptables -t mangle -A "$TELEGRAM_CALL_LEARN_CHAIN" -p udp -m set --match-set "$known_set" dst -j RETURN
	done

	for proto in $active_protocols; do
		[ -n "$proto" ] || continue
		base_set="$(telegram_call_base_set "$proto")"
		client_set="$(telegram_call_client_set "$proto")"
		signal_set="$(telegram_call_signal_set "$proto")"
		learned_set="$(telegram_call_learned_set "$proto")"
		target_port="$(telegram_call_target_port "$proto")"
		tproxy_port="$(telegram_call_tproxy_port "$proto")"
		[ -n "$base_set" ] && [ -n "$client_set" ] && [ -n "$signal_set" ] && [ -n "$learned_set" ] && [ -n "$target_port" ] || continue
		ipset list "$base_set" >/dev/null 2>&1 || continue
		ipset list "$client_set" >/dev/null 2>&1 || continue
		ipset list "$signal_set" >/dev/null 2>&1 || continue
		ensure_timeout_ipset "$learned_set" "$BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT" 256 || continue
		iptables -t mangle -A "$TELEGRAM_CALL_LEARN_CHAIN" -p udp -m set --match-set "$learned_set" dst \
			-j SET --add-set "$client_set" src --exist --timeout "$BYPASS_TELEGRAM_CALL_CLIENT_TIMEOUT"
		iptables -t mangle -A "$TELEGRAM_CALL_LEARN_CHAIN" -p udp -m set --match-set "$learned_set" dst \
			-j SET --add-set "$learned_set" dst --exist --timeout "$BYPASS_TELEGRAM_CALL_ADDRESS_TIMEOUT"
		if [ "$telegram_call_tproxy_ready" = "1" ] && [ -n "$tproxy_port" ]; then
			iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m set --match-set "$signal_set" dst \
				-j TPROXY --on-port "$tproxy_port" --tproxy-mark "$BYPASS_TELEGRAM_CALL_TPROXY_MARK/$BYPASS_TELEGRAM_CALL_TPROXY_MARK"
		fi
		if [ "$BYPASS_TELEGRAM_CALL_SIGNAL_ROUTE_ENABLED" != "0" ]; then
			for signal_port in $(telegram_call_signal_tcp_ports); do
				iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -p tcp -m tcp -m set --match-set "$signal_set" dst --dport "$signal_port" \
					-j REDIRECT --to-ports "$target_port"
			done
			if [ "$BYPASS_TELEGRAM_CALL_UDP_REDIRECT_ENABLED" != "0" ]; then
				iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -p udp -m udp -m set --match-set "$signal_set" dst --dport 1024:65535 \
					-j REDIRECT --to-ports "$target_port"
			fi
		fi
	done
	for known_set in $(telegram_call_known_route_sets); do
		ipset list "$known_set" >/dev/null 2>&1 || continue
		iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m set --match-set "$known_set" dst -j RETURN
		iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -p udp -m set --match-set "$known_set" dst -j RETURN
	done
	for proto in $active_protocols; do
		learned_set="$(telegram_call_learned_set "$proto")"
		target_port="$(telegram_call_target_port "$proto")"
		tproxy_port="$(telegram_call_tproxy_port "$proto")"
		[ -n "$learned_set" ] || continue
		ipset list "$learned_set" >/dev/null 2>&1 || continue
		if [ "$telegram_call_tproxy_ready" = "1" ] && [ -n "$tproxy_port" ]; then
			iptables -t mangle -A "$TELEGRAM_CALL_TPROXY_CHAIN" -p udp -m set --match-set "$learned_set" dst \
				-j TPROXY --on-port "$tproxy_port" --tproxy-mark "$BYPASS_TELEGRAM_CALL_TPROXY_MARK/$BYPASS_TELEGRAM_CALL_TPROXY_MARK"
		fi
		if [ "$BYPASS_TELEGRAM_CALL_UDP_REDIRECT_ENABLED" != "0" ] && [ -n "$target_port" ]; then
			iptables -t nat -A "$TELEGRAM_CALL_ROUTE_CHAIN" -p udp -m set --match-set "$learned_set" dst -j REDIRECT --to-ports "$target_port"
		fi
	done
	refresh_telegram_call_prerouting_jumps
}


#if [ -z "$(iptables-save 2>/dev/null | grep "--dport 53 -j DNAT")" ]; then
#    iptables -w -t nat -I PREROUTING -p udp --dport 53 -j DNAT --to 192.168.1.1
#    iptables -w -t nat -I PREROUTING -p tcp --dport 53 -j DNAT --to 192.168.1.1
#fi

# перенаправление 53 порта для br0 на определенный IP
#if [ -z "$(iptables-save 2>/dev/null | grep "udp --dport 53 -j DNAT")" ]; then
#    iptables -w -t nat -I PREROUTING -i br0 -p udp --dport 53 -j DNAT --to 192.168.1.1
#    iptables -w -t nat -I PREROUTING -i br0 -p tcp --dport 53 -j DNAT --to 192.168.1.1
#fi

if [ -z "$(iptables-save 2>/dev/null | grep unblocksh)" ]; then
	ipset create unblocksh hash:net -exist 2>/dev/null

	# Redirect rules are intentionally not bound to an interface, so router clients use the same bypass.
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblocksh dst -j REDIRECT --to-ports 1082
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblocksh dst -j REDIRECT --to-ports 1082

	# если у вас другой конфиг dnsmasq, и вы слушаете только определенный ip, раскоментируйте следующие строки, поставьте свой ip
	#iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1
	#iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1

	# если вы хотите что бы обход работал только для определнных интерфейсов, закоментируйте строки выше, и раскоментируйте эти (br0)
	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocksh dst -j REDIRECT --to-ports 1082
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblocksh dst -j REDIRECT --to-ports 1082
	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1

	# если вы хотите, что бы у вас были проблемы с entware (stmb, rest api), раскоментируйте эту строку
	#iptables -A OUTPUT -t nat -p tcp -m set --match-set unblocksh dst -j REDIRECT --to-ports 1082
fi


ipset create unblockvmess hash:net -exist 2>/dev/null
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10810 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10810
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10810 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10810
done
if ! iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10815 2>/dev/null; then
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10815
fi
if ! iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10815 2>/dev/null; then
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10815
fi

	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10815
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10815
	#iptables -A PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-ports 10815 #в целом не имеет смысла

ipset create unblockvless hash:net -exist 2>/dev/null
ipset create unblockvlessudp hash:net -exist 2>/dev/null
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10811 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10811
done
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812
done
if ! iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812 2>/dev/null; then
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812
fi
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10811 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10811
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812
done
if ! iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812 2>/dev/null; then
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812
fi
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REDIRECT --to-ports 10812 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REDIRECT --to-ports 10812
done
while iptables -C FORWARD -w -p udp -m set --match-set unblockvless dst --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
	iptables -D FORWARD -w -p udp -m set --match-set unblockvless dst --dport 443 -j REJECT --reject-with icmp-port-unreachable
done
while iptables -C FORWARD -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
	iptables -D FORWARD -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REJECT --reject-with icmp-port-unreachable
done
while iptables -C FORWARD -w -p udp -m set --match-set unblockvlessudp dst -m udp --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
	iptables -D FORWARD -w -p udp -m set --match-set unblockvlessudp dst -m udp --dport 443 -j REJECT --reject-with icmp-port-unreachable
done
refresh_transparent_udp_quic_reject 10812 "$BYPASS_UDP_QUIC_BLOCK_VLESS"


ipset create unblockvless2 hash:net -exist 2>/dev/null
ipset create unblockvless2udp hash:net -exist 2>/dev/null
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10813 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10813
done
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10813 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10813
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REDIRECT --to-ports 10814 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REDIRECT --to-ports 10814
done
while iptables -C FORWARD -w -p udp -m set --match-set unblockvless2 dst --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
	iptables -D FORWARD -w -p udp -m set --match-set unblockvless2 dst --dport 443 -j REJECT --reject-with icmp-port-unreachable
done
while iptables -C FORWARD -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
	iptables -D FORWARD -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REJECT --reject-with icmp-port-unreachable
done
while iptables -C FORWARD -w -p udp -m set --match-set unblockvless2udp dst -m udp --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
	iptables -D FORWARD -w -p udp -m set --match-set unblockvless2udp dst -m udp --dport 443 -j REJECT --reject-with icmp-port-unreachable
done

vless2_key_path=""
for candidate in /opt/etc/xray/vless2.key /opt/etc/v2ray/vless2.key; do
	if [ -s "$candidate" ]; then
		vless2_key_path="$candidate"
		break
	fi
done

if [ -n "$vless2_key_path" ]; then
	if ! iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814 2>/dev/null; then
		iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814
	fi
	if ! iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814 2>/dev/null; then
		iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814
	fi
	refresh_transparent_udp_quic_reject 10814 "$BYPASS_UDP_QUIC_BLOCK_VLESS2"
fi

remove_vless_priority_redirect_rules() {
	for priority_set in unblockvlesspriority unblockvless2priority; do
		for priority_port in 10812 10814; do
			while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set "$priority_set" dst -j REDIRECT --to-ports "$priority_port" 2>/dev/null; do
				iptables -t nat -D PREROUTING -w -p tcp -m set --match-set "$priority_set" dst -j REDIRECT --to-ports "$priority_port"
			done
			while iptables -t nat -C PREROUTING -w -p udp -m set --match-set "$priority_set" dst -j REDIRECT --to-ports "$priority_port" 2>/dev/null; do
				iptables -t nat -D PREROUTING -w -p udp -m set --match-set "$priority_set" dst -j REDIRECT --to-ports "$priority_port"
			done
		done
	done
}

refresh_vless_priority_redirects() {
	ipset create unblockvlesspriority hash:net -exist 2>/dev/null
	ipset create unblockvless2priority hash:net -exist 2>/dev/null
	remove_vless_priority_redirect_rules
	if [ -n "$vless2_key_path" ]; then
		iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless2priority dst -j REDIRECT --to-ports 10814
		iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvless2priority dst -j REDIRECT --to-ports 10814
	fi
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvlesspriority dst -j REDIRECT --to-ports 10812
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvlesspriority dst -j REDIRECT --to-ports 10812
}

refresh_vless_tcp_priority() {
	youtube_route="$(youtube_route_protocol)"
	while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812 2>/dev/null; do
		iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812
	done
	while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814 2>/dev/null; do
		iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814
	done
	if [ "$youtube_route" = "vless2" ] && [ -n "$vless2_key_path" ]; then
		# Shared Google IPs must follow the YouTube route for video streams.
		# Telegram mobile push ports are pinned separately below.
		iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812
		iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814
	else
		if [ -n "$vless2_key_path" ]; then
			iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-ports 10814
		fi
		iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-ports 10812
	fi
}

route_file_marker_count() {
	route_file="$1"
	shift
	[ -s "$route_file" ] || {
		printf '%s\n' 0
		return
	}
	awk '
		BEGIN {
			file_arg = ARGC - 1
			for (idx = 1; idx < file_arg; idx++) {
				markers[ARGV[idx]] = 1
				ARGV[idx] = ""
			}
		}
		{
			value = $0
			sub(/#.*/, "", value)
			gsub(/\r/, "", value)
			gsub(/^[ \t]+|[ \t]+$/, "", value)
			if (value == "") next
			sub(/^full:/, "", value)
			sub(/^domain:/, "", value)
			sub(/^\+\./, "", value)
			sub(/^\*\./, "", value)
			sub(/^\./, "", value)
			for (marker in markers) {
				suffix = "." marker
				if (value == marker || (length(value) > length(suffix) && substr(value, length(value) - length(suffix) + 1) == suffix)) {
					count++
					break
				}
			}
		}
		END { print count + 0 }
	' "$@" "$route_file"
}

telegram_route_protocol() {
	telegram_markers="api.telegram.org 149.154.160.0/20 mtalk.google.com 17.249.0.0/16"
	for marker in $telegram_markers; do
		if grep -Fxs "$marker" "$UNBLOCK_DIR/vless-2.txt" >/dev/null 2>&1; then
			printf '%s\n' "vless2"
			return
		fi
	done
	printf '%s\n' "vless"
}

youtube_route_protocol() {
	youtube_markers="youtube.com www.youtube.com googlevideo.com ytimg.com youtubei.googleapis.com yt3.ggpht.com"
	best_protocol=""
	best_count=0
	for route_spec in \
		"shadowsocks:$UNBLOCK_DIR/shadowsocks.txt" \
		"vmess:$UNBLOCK_DIR/vmess.txt" \
		"vless:$UNBLOCK_DIR/vless.txt" \
		"vless2:$UNBLOCK_DIR/vless-2.txt" \
		"trojan:$UNBLOCK_DIR/trojan.txt"; do
		protocol="${route_spec%%:*}"
		route_file="${route_spec#*:}"
		count="$(route_file_marker_count "$route_file" $youtube_markers)"
		case "$count" in ''|*[!0-9]*) count=0 ;; esac
		if [ "$count" -gt "$best_count" ] 2>/dev/null; then
			best_count="$count"
			best_protocol="$protocol"
		fi
	done
	printf '%s\n' "${best_protocol:-vless}"
}

refresh_vless_tcp_priority
refresh_vless_priority_redirects

refresh_mobile_push_priority() {
	# Telegram mobile can use MTProto TCP 5222; Android FCM/mtalk uses TCP
	# 5228-5230; iOS APNs keeps a persistent TCP 5223 connection and can fall
	# back to 443. YouTube's broad Google IP ranges can capture shared push IPs
	# in the other Vless list, so pin mobile signaling
	# ports to whichever Vless list currently carries Telegram routes.
	telegram_route="$(telegram_route_protocol)"
	target_port=10812
	[ "$telegram_route" = "vless2" ] && [ -n "$vless2_key_path" ] && target_port=10814
	for push_port in 5222 5223 5228 5229 5230; do
		for push_set in unblockvless unblockvless2; do
			for stale_port in 10812 10814; do
				while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set "$push_set" dst --dport "$push_port" -j REDIRECT --to-ports "$stale_port" 2>/dev/null; do
					iptables -t nat -D PREROUTING -w -p tcp -m set --match-set "$push_set" dst --dport "$push_port" -j REDIRECT --to-ports "$stale_port"
				done
			done
			iptables -I PREROUTING -w -t nat -p tcp -m set --match-set "$push_set" dst --dport "$push_port" -j REDIRECT --to-ports "$target_port"
		done
	done
}

refresh_mobile_push_priority

remove_vless_tcp_forward_guard() {
	for guard_set in unblockvless unblockvless2; do
		while iptables -C FORWARD -w -p tcp -m set --match-set "$guard_set" dst -j REJECT --reject-with tcp-reset 2>/dev/null; do
			iptables -D FORWARD -w -p tcp -m set --match-set "$guard_set" dst -j REJECT --reject-with tcp-reset
		done
	done
}

remove_vless_tcp_forward_guard

install_ipv6_fallback_rules


if [ -z "$(iptables-save 2>/dev/null | grep unblocktroj)" ]; then
  ipset create unblocktroj hash:net -exist 2>/dev/null
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-ports 10829
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblocktroj dst -j REDIRECT --to-ports 10829

	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-ports 10829
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblocktroj dst -j REDIRECT --to-ports 10829
	#iptables -A PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-ports 10829 #в целом не имеет смысла

fi

refresh_udp_quic_block_rules

refresh_telegram_call_learning_rules

exit 0
