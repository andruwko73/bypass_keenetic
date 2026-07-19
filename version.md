*v1.962 (19 Jul 2026) -* main

*Stops the bot and all pool-probe workers before replacing program files during an update, preventing a partial runtime update when a background check is active.*

*If the program cannot stop cleanly, the update is cancelled before any runtime file is changed.*
