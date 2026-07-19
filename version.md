*v1.963 (19 Jul 2026) -* main

*Makes Xray configuration writes atomic and rebuilds the core proxy configuration from saved keys before an update validates and restarts Xray.*

*If an update fails after stopping the application, it automatically restores or restarts the previous runtime instead of leaving the bot and web interface offline.*
