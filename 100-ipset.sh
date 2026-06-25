#!/bin/sh
[ "$1" != "start" ] && exit 0
ipset create unblocksh hash:net -exist
ipset create unblockshudp hash:net -exist
ipset create unblockvmess hash:net -exist
ipset create unblockvmessudp hash:net -exist
ipset create unblockvless hash:net -exist
ipset create unblockvlesspriority hash:net -exist
ipset create unblockvlessudp hash:net -exist
ipset create unblockvless2 hash:net -exist
ipset create unblockvless2priority hash:net -exist
ipset create unblockvless2udp hash:net -exist
ipset create unblocktroj hash:net -exist
ipset create unblocktrojudp hash:net -exist
ipset create bypass_call_signal_sh hash:net -exist
ipset create bypass_call_signal_vmess hash:net -exist
ipset create bypass_call_signal_vless hash:net -exist
ipset create bypass_call_signal_vless2 hash:net -exist
ipset create bypass_call_signal_troj hash:net -exist
ipset create unblocksh6 hash:net family inet6 -exist
ipset create unblockvmess6 hash:net family inet6 -exist
ipset create unblockvless6 hash:net family inet6 -exist
ipset create unblockvlesspriority6 hash:net family inet6 -exist
ipset create unblockvless2v6 hash:net family inet6 -exist
ipset create unblockvless2priority6 hash:net family inet6 -exist
ipset create unblocktroj6 hash:net family inet6 -exist

#script0
#script1
#script2
#script3
#script4
#script5
#script6
#script7
#script8
#script9
exit 0
