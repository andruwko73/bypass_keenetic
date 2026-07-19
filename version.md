*v1.960 (19 Jul 2026) -* main

*Runs a full pool-key verification once a day in the local 03:00–06:00 window, after a recent successful subscription refresh.*

*The task is deferred when an update, another memory-sensitive operation, or a pool probe is already running; it uses the existing external worker and memory/CPU guards.*
