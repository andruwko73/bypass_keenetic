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

UDP_POLICY_CONFIG="${UDP_POLICY_CONFIG:-/opt/etc/bot/udp_policy.conf}"
[ -r "$UDP_POLICY_CONFIG" ] && . "$UDP_POLICY_CONFIG"
UNBLOCK_DIR="${UNBLOCK_DIR:-/opt/etc/unblock}"
BYPASS_UDP_QUIC_BLOCK_VLESS="${BYPASS_UDP_QUIC_BLOCK_VLESS:-1}"
BYPASS_UDP_QUIC_BLOCK_VLESS2="${BYPASS_UDP_QUIC_BLOCK_VLESS2:-1}"
BYPASS_IPV6_FALLBACK_ENABLED="${BYPASS_IPV6_FALLBACK_ENABLED:-1}"

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
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblocksh dst -j REDIRECT --to-port 1082
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblocksh dst -j REDIRECT --to-port 1082

	# если у вас другой конфиг dnsmasq, и вы слушаете только определенный ip, раскоментируйте следующие строки, поставьте свой ip
	#iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1
	#iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1

	# если вы хотите что бы обход работал только для определнных интерфейсов, закоментируйте строки выше, и раскоментируйте эти (br0)
	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocksh dst -j REDIRECT --to-port 1082
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblocksh dst -j REDIRECT --to-port 1082
	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblocksh dst --dport 53 -j DNAT --to 192.168.1.1

	# если вы хотите, что бы у вас были проблемы с entware (stmb, rest api), раскоментируйте эту строку
	#iptables -A OUTPUT -t nat -p tcp -m set --match-set unblocksh dst -j REDIRECT --to-port 1082
fi


ipset create unblockvmess hash:net -exist 2>/dev/null
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10810 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10810
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10810 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10810
done
if ! iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10815 2>/dev/null; then
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10815
fi
if ! iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10815 2>/dev/null; then
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10815
fi

	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10815
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10815
	#iptables -A PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblockvmess dst -j REDIRECT --to-port 10815 #в целом не имеет смысла

ipset create unblockvless hash:net -exist 2>/dev/null
ipset create unblockvlessudp hash:net -exist 2>/dev/null
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10811 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10811
done
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812
done
if ! iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812 2>/dev/null; then
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812
fi
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-port 10811 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-port 10811
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REDIRECT --to-port 10812 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REDIRECT --to-port 10812
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
if [ "$BYPASS_UDP_QUIC_BLOCK_VLESS" != "0" ]; then
	if ! iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REDIRECT --to-port 10812 2>/dev/null; then
		iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvlessudp dst --dport 443 -j REDIRECT --to-port 10812
	fi
fi


ipset create unblockvless2 hash:net -exist 2>/dev/null
ipset create unblockvless2udp hash:net -exist 2>/dev/null
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10813 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10813
done
while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10813 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10813
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814
done
while iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REDIRECT --to-port 10814 2>/dev/null; do
	iptables -t nat -D PREROUTING -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REDIRECT --to-port 10814
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
	if ! iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814 2>/dev/null; then
		iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814
	fi
	if [ "$BYPASS_UDP_QUIC_BLOCK_VLESS2" != "0" ]; then
		if ! iptables -t nat -C PREROUTING -w -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REDIRECT --to-port 10814 2>/dev/null; then
			iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblockvless2udp dst --dport 443 -j REDIRECT --to-port 10814
		fi
	fi
fi

refresh_vless_tcp_priority() {
	# Shared Google IPs can land in both Vless sets. Keep Vless 1 first so
	# CRD/Telegram-style service routes do not get captured by the YouTube key.
	while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812 2>/dev/null; do
		iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812
	done
	while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814 2>/dev/null; do
		iptables -t nat -D PREROUTING -w -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814
	done
	if [ -n "$vless2_key_path" ]; then
		iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless2 dst -j REDIRECT --to-port 10814
	fi
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblockvless dst -j REDIRECT --to-port 10812
}

refresh_vless_tcp_priority

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

refresh_mobile_push_priority() {
	# Android FCM/mtalk uses TCP 5228-5230; iOS APNs keeps a persistent TCP 5223
	# connection and can fall back to 443. YouTube's broad Google IP ranges can
	# capture shared push IPs in the other Vless list, so pin push signaling
	# ports to whichever Vless list currently carries Telegram routes.
	telegram_route="$(telegram_route_protocol)"
	target_port=10812
	[ "$telegram_route" = "vless2" ] && [ -n "$vless2_key_path" ] && target_port=10814
	for push_port in 5223 5228 5229 5230; do
		for push_set in unblockvless unblockvless2; do
			for stale_port in 10812 10814; do
				while iptables -t nat -C PREROUTING -w -p tcp -m set --match-set "$push_set" dst --dport "$push_port" -j REDIRECT --to-port "$stale_port" 2>/dev/null; do
					iptables -t nat -D PREROUTING -w -p tcp -m set --match-set "$push_set" dst --dport "$push_port" -j REDIRECT --to-port "$stale_port"
				done
			done
			iptables -I PREROUTING -w -t nat -p tcp -m set --match-set "$push_set" dst --dport "$push_port" -j REDIRECT --to-port "$target_port"
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
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829

	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829
	#iptables -A PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829 #в целом не имеет смысла

fi


exit 0
