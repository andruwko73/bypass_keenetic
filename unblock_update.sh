#!/bin/sh

ensure_set() {
	ipset create "$1" hash:net -exist >/dev/null 2>&1
}

flush_set() {
	ensure_set "$1"
	ipset flush "$1" >/dev/null 2>&1
}

[ -x /opt/etc/ndm/fs.d/100-ipset.sh ] && /opt/etc/ndm/fs.d/100-ipset.sh start

flush_set unblocksh
flush_set unblockvmess
flush_set unblockvless
flush_set unblockvless2
flush_set unblocktroj

[ -x /opt/etc/ndm/netfilter.d/100-redirect.sh ] && table=nat /opt/etc/ndm/netfilter.d/100-redirect.sh
[ -x /opt/etc/ndm/netfilter.d/100-redirect.sh ] && table=mangle /opt/etc/ndm/netfilter.d/100-redirect.sh

/opt/bin/unblock_dnsmasq.sh
/opt/etc/init.d/S56dnsmasq restart
/opt/bin/unblock_ipset.sh &
