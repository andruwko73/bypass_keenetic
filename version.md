*v1.980 (29 Jul 2026) -* main

*Keeps the six-hour dnsmasq/ipset full refresh deadline anchored to the last real refresh: unchanged hourly checks no longer postpone it, and legacy skipped state is repaired on the next due run.*

*Убирает повтор «API отвечает» из нормального статуса работающего Telegram-бота: под заголовком остаётся только информация о памяти роутера.*

*Сразу после полной проверки пула сохраняет итоговую сводку всех строк, поэтому главная страница больше не показывает устаревшее число проверенных ключей.*

*Делает прозрачность блоков и кнопок одинаковой на всех вкладках при использовании пользовательского фона и сохраняет читаемость меню оформления.*

*Документирует темы и пользовательский фон, добавляет актуальные обезличенные скриншоты веб-интерфейса с текущего роутера.*

*В карточке обновления время «В среднем» теперь отображается отдельной строкой под «Прошло».*

*Keeps pool rows compact: they show the latest result and its time, while the source of the result remains available internally and in technical logs.*

*Keeps every YouTube address exclusively on its configured route, adds a guarded small CDN-quality preference, and makes key failover history clearer.*

*Uses only two or three freshly approved `i.ytimg.com` addresses for an optional DNS preference; normal DNS remains active whenever the quality threshold is not met.*
