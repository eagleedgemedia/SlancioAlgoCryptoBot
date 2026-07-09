
import asyncio
from core.config import get_settings
from core.engine import TradingEngine
from database.models import TradeLog

async def send_test():
    settings = get_settings()
    if not settings.telegram_bot_token:
        print('No telegram bot token found in .env')
        return
        
    engine = TradingEngine(api_key='mock', api_secret='mock', user_id='mock')
    
    msg = (
        f'?? *NEW TRADE EXECUTED (TEST)*\n'
        f'?????????????????????\n'
        f'?? Pair: BTCUSD\n'
        f'?? Type: *?? LONG*\n'
        f'?? Entry Price: 64200.50\n'
        f'?? Stoploss: 63800.00\n'
        f'? Target: 65000.00\n'
        f'?????????????????????\n'
        f'?? Margin Required: 125.50 USDT\n'
        f'?? SL Risk Amount: -40.00 USDT\n'
        f'?? Target Reward: +80.00 USDT\n'
        f'?? Conditions: Liquidity Sweep + MTF Trend Alignment\n'
    )
    
    print('Sending telegram alert...')
    engine._send_telegram_alert(msg)
    print('Done.')

asyncio.run(send_test())

