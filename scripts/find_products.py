"""Quick script to find BTC/USDT products and test candle fetch."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange.client import DeltaExchangeClient

c = DeltaExchangeClient()
prods = c.get_products()

# Find BTC products
btc = [p for p in prods if "BTC" in p.get("symbol", "") and "USD" in p.get("symbol", "")]
print(f"\nFound {len(btc)} BTC/USD products:")
for p in btc[:15]:
    print(f"  ID: {p['id']:>6} | Symbol: {p['symbol']:<20} | {p.get('description', 'N/A')}")

# Try fetching candles with first matching symbol
if btc:
    sym = btc[0]["symbol"]
    print(f"\nTesting candle fetch for: {sym}")
    import time
    end = int(time.time())
    start = end - 100 * 3600
    candles = c.get_candles(sym, "1h", start=start, end=end)
    print(f"Candles returned: {len(candles) if candles else 0}")
    if candles:
        print(f"First candle: {candles[0]}")
        print(f"Last candle:  {candles[-1]}")
