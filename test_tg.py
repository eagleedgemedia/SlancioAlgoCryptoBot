import asyncio
from core.notifications.telegram_bot import TelegramNotifier

async def main():
    bot = TelegramNotifier()
    await bot.send_system_alert(
        "🚀 *System Update* 🚀\n\n"
        "Your Slancio Crypto Engine is LIVE and fully configured!\n"
        "The Dashboard Mini-App is ready for use.\n\n"
        "I am now monitoring the markets for you 24/7."
    )
    print("Sent!")

if __name__ == "__main__":
    asyncio.run(main())
