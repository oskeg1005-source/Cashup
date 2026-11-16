# Cashup — Telegram mini app (кейсы, краш, мины, рулетка, апгрейд)

## Запуск на Render
1. Залей папку в GitHub (репозиторий).
2. Render → New → Blueprint → выбери репозиторий (подхватит render.yaml: сервис + Postgres).
3. Введи BOT_TOKEN (из @BotFather) и ADMIN_ID (твой Telegram id).
4. После деплоя открой бота и жми /start. WEBAPP_URL ставить не нужно — берётся RENDER_EXTERNAL_URL автоматически.
5. Чтобы сервис не засыпал: заведи бесплатный монитор на UptimeRobot на https://ТВОЙ-СЕРВИС.onrender.com/health (каждые 5 мин).

Важно: бесплатная база Render живёт 30 дней — потом перейди на платный план или перенеси DATABASE_URL на Neon/Supabase.
Команда админа: /give id сумма
