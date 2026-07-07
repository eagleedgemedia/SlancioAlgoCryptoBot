import asyncio
from core.notifications.telegram_bot import TelegramNotifier

async def test_telegram():
    bot = TelegramNotifier()
    await bot.send_system_alert("✅ Slancio Crypto Algo Engine is Online! Successfully connected to your Telegram.")

if __name__ == "__main__":
    asyncio.run(test_telegram())
