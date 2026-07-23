*v1.975 (23 Jul 2026) -* main

*Makes pool screening match the working Xray foundation and confirms automatic failover candidates only after they work through the permanent Xray.*

*Keeps pool rows compact: they show the latest result and its time, while the source of the result remains available internally and in technical logs.*

*Keeps every YouTube address exclusively on its configured route, adds a guarded small CDN-quality preference, and makes key failover history clearer.*

*Uses only two or three freshly approved `i.ytimg.com` addresses for an optional DNS preference; normal DNS remains active whenever the quality threshold is not met.*
