"""
Slancio Crypto Algo Treding Engine — Telegram Notifications
===============================================
Async wrapper for the Telegram Bot API.
Sends real-time trading alerts.
"""

import asyncio
from loguru import logger
from telegram import Bot
from telegram.error import TelegramError
from core.config import get_settings


class TelegramNotifier:
    def __init__(self):
        self.settings = get_settings()
        self.token = self.settings.telegram_bot_token
        self.default_chat_id = self.settings.telegram_chat_id
        
        if self.token:
            self.bot = Bot(token=self.token)
            self.is_enabled = True
        else:
            self.bot = None
            self.is_enabled = False
            logger.warning("Telegram Bot Token not configured. Notifications disabled.")

    async def _send_message(self, message: str, chat_id: str = None, parse_mode: str = "HTML"):
        """Internal helper to send a message safely"""
        if not self.is_enabled:
            return
            
        target_chat = chat_id or self.default_chat_id
        if not target_chat:
            logger.warning("No target Chat ID provided for Telegram message.")
            return

        try:
            await self.bot.send_message(
                chat_id=target_chat, 
                text=message, 
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            logger.debug("Telegram message sent successfully.")
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in Telegram bot: {e}")

    async def send_entry_alert(
        self, 
        symbol: str, 
        side: str, 
        entry_price: float, 
        size: int, 
        stop_loss: float, 
        take_profit: float,
        chat_id: str = None
    ):
        """Send a formatted alert when a trade is entered."""
        emoji = "🔴" if side.lower() == "sell" else "🟢"
        
        msg = (
            f"🚀 <b>NEW {side.upper()} EXECUTED</b>\n\n"
            f"<b>Pair:</b> {symbol} {emoji}\n"
            f"<b>Size:</b> {size} contracts\n"
            f"<b>Entry Price:</b> {entry_price:,.2f}\n"
            f"<b>Stop Loss:</b> {stop_loss:,.2f}\n"
            f"<b>Take Profit (Dyn):</b> {take_profit:,.2f}\n\n"
            f"<i>Slancio Crypto Algo Treding Engine</i>"
        )
        await self._send_message(msg, chat_id)

    async def send_exit_alert(
        self, 
        symbol: str, 
        side: str, 
        exit_price: float, 
        pnl: float, 
        reason: str,
        chat_id: str = None
    ):
        """Send a formatted alert when a trade is closed."""
        emoji = "🎉" if pnl > 0 else "💔"
        
        msg = (
            f"🛑 <b>POSITION CLOSED</b>\n\n"
            f"<b>Pair:</b> {symbol}\n"
            f"<b>Type:</b> {side.upper()}\n"
            f"<b>Exit Price:</b> {exit_price:,.2f}\n"
            f"<b>Reason:</b> {reason}\n"
            f"<b>PnL:</b> {pnl:,.2f} {emoji}\n\n"
            f"<i>Slancio Crypto Algo Treding Engine</i>"
        )
        await self._send_message(msg, chat_id)

    async def send_system_alert(self, message: str, chat_id: str = None):
        """Send general system alerts (e.g., bot started, errors)."""
        msg = f"⚙️ <b>SYSTEM ALERT</b>\n\n{message}"
        await self._send_message(msg, chat_id)


# Singleton instance for global access
notifier = TelegramNotifier()
