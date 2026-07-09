
import asyncio
import hashlib
import hmac
import time
import httpx

DELTA_INDIA_BASE = 'https://api.india.delta.exchange'

async def _delta_request(api_key: str, api_secret: str, method: str, path: str, body: dict = None, time_offset: int = 0) -> dict:
    timestamp = int(time.time()) + time_offset
    signature = hmac.new(
        api_secret.encode(),
        f'{method}{timestamp}{path}'.encode(),
        hashlib.sha256
    ).hexdigest()

    headers = {
        'api-key': api_key,
        'timestamp': str(timestamp),
        'signature': signature,
        'Content-Type': 'application/json',
    }
    url = f'{DELTA_INDIA_BASE}{path}'
    
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers=headers)
        data = resp.json()
        print(f'Attempt with offset {time_offset}:', data)
        
        if not data.get('success') and data.get('error', {}).get('code') == 'expired_signature' and time_offset == 0:
            context = data.get('error', {}).get('context', {})
            server_time = context.get('server_time')
            request_time = context.get('request_time')
            if server_time and request_time:
                drift = server_time - request_time
                print(f'Drift detected: {drift}')
                return await _delta_request(api_key, api_secret, method, path, body, time_offset=drift)
        return data

# Using the keys from the new screenshot
asyncio.run(_delta_request('edgmXafwgU5XtXPXAHnEYyNUfMTHA4', 'rbC1MS90pykUKY7P4XzwxEF4lFw8LbgSHxYVVFxnqvltqa9FGTyzhUAOCexK', 'GET', '/v2/wallet/balances'))

