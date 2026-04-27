#!/bin/sh
[ "$1" != "start" ] && exit 0
ipset create unblocksh hash:net -exist
ipset create unblockvmess hash:net -exist
ipset create unblockvless hash:net -exist
ipset create unblockvless2 hash:net -exist
ipset create unblocktroj hash:net -exist

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
