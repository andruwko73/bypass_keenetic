#!/bin/sh

# 2023. Keenetic DNS bot /  Проект: bypass_keenetic / Автор: tas_unn
# GitHub: https://github.com/tas-unn/bypass_keenetic
# Данный бот предназначен для управления обхода блокировок на роутерах Keenetic
# Демо-бот: https://t.me/keenetic_dns_bot
#
# Файл: 100-redirect.sh, Версия 2.1.9, последнее изменение: 03.05.2023, 21:10
# Доработал: NetworK (https://github.com/znetworkx)

#!/bin/sh

# shellcheck disable=SC2154
[ "$type" = "ip6tables" ] && exit 0
[ "$table" != "mangle" ] && [ "$table" != "nat" ] && exit 0

ip4t() {
	if ! iptables -C "$@" &>/dev/null; then
		 iptables -A "$@" || exit 0
	fi
}

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

	# Redirect rules are intentionally not bound to an interface, so router VPN clients use the same bypass.
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
if ! iptables -C FORWARD -w -p udp -m set --match-set unblockvless dst --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; then
	iptables -I FORWARD -w -p udp -m set --match-set unblockvless dst --dport 443 -j REJECT --reject-with icmp-port-unreachable
fi


ipset create unblockvless2 hash:net -exist 2>/dev/null
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
while iptables -C FORWARD -w -p udp -m set --match-set unblockvless2 dst --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; do
	iptables -D FORWARD -w -p udp -m set --match-set unblockvless2 dst --dport 443 -j REJECT --reject-with icmp-port-unreachable
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
	if ! iptables -C FORWARD -w -p udp -m set --match-set unblockvless2 dst --dport 443 -j REJECT --reject-with icmp-port-unreachable 2>/dev/null; then
		iptables -I FORWARD -w -p udp -m set --match-set unblockvless2 dst --dport 443 -j REJECT --reject-with icmp-port-unreachable
	fi
fi


if [ -z "$(iptables-save 2>/dev/null | grep unblocktroj)" ]; then
  ipset create unblocktroj hash:net -exist 2>/dev/null
	iptables -I PREROUTING -w -t nat -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829
	iptables -I PREROUTING -w -t nat -p udp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829

	#iptables -I PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829
	#iptables -I PREROUTING -w -t nat -i br0 -p udp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829
	#iptables -A PREROUTING -w -t nat -i br0 -p tcp -m set --match-set unblocktroj dst -j REDIRECT --to-port 10829 #в целом не имеет смысла

fi


exit 0
