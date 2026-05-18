#!/bin/sh

SET_NAMES="unblocksh unblockvmess unblockvless unblockvless2 unblocktroj"
EXTRA_SET_NAMES="unblockvlessudp unblockvless2udp"

ensure_set() {
	ipset create "$1" hash:net -exist >/dev/null 2>&1
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

refresh_dns_backend() {
	backend="$1"
	[ -x /opt/bin/unblock_dnsmasq.sh ] && /opt/bin/unblock_dnsmasq.sh

	case "$backend" in
		dnsmasq)
			echo "DNS backend: dnsmasq, restarting S56dnsmasq."
			[ -x /opt/etc/init.d/S56dnsmasq ] && /opt/etc/init.d/S56dnsmasq restart
			;;
		ndnproxy)
			echo "DNS backend: ndnproxy (Keenetic). Using Keenetic ndnproxy, preloading ipset."
			;;
		none)
			echo "DNS backend: none detected, trying S56dnsmasq."
			if [ -x /opt/etc/init.d/S56dnsmasq ]; then
				/opt/etc/init.d/S56dnsmasq restart || echo "S56dnsmasq restart failed; continuing with static ipset preload."
			fi
			;;
		*)
			echo "DNS backend: unknown, leaving current listener untouched."
			;;
	esac
}

[ -x /opt/etc/ndm/fs.d/100-ipset.sh ] && /opt/etc/ndm/fs.d/100-ipset.sh start

for set_name in $SET_NAMES $EXTRA_SET_NAMES; do
	ensure_set "$set_name"
done

[ -x /opt/etc/ndm/netfilter.d/100-redirect.sh ] && table=nat /opt/etc/ndm/netfilter.d/100-redirect.sh
[ -x /opt/etc/ndm/netfilter.d/100-redirect.sh ] && table=mangle /opt/etc/ndm/netfilter.d/100-redirect.sh

backend="$(detect_dns_backend)"
refresh_dns_backend "$backend"

if /opt/bin/unblock_ipset.sh; then
	echo "ipset refresh completed."
	exit 0
fi

echo "ipset refresh failed; previous ipset contents were preserved."
exit 1
