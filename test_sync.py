
import asyncio
from backend.admin.router import _delta_request

async def test():
    # Pass an invalid key so it throws invalid_api_key or expired_signature
    resp = await _delta_request('edgmXafwgU5XtXPXAHnEYyNUfMTHA4', 'rbC1MS90pykUKY7P4XzwxEF4lFw8LbgSHxYVVFxnqvltqa9FGTyzhUAOCexK', 'GET', '/v2/wallet/balances')
    print(resp)

asyncio.run(test())

