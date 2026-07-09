
import httpx
import asyncio

async def test_live():
    async with httpx.AsyncClient() as client:
        # Login
        r = await client.post('https://slancioalgotradebot.onrender.com/api/auth/login', data={'username': 'Admin', 'password': 'SlancioAdmin!2025'})
        token = r.json().get('access_token')
        
        # Get keys
        headers = {'Authorization': f'Bearer {token}'}
        r = await client.get('https://slancioalgotradebot.onrender.com/api/users/keys', headers=headers)
        keys = r.json()
        print('Keys:', keys)
        
        if keys:
            key_id = keys[0]['id']
            print(f'Fetching balance for key {key_id}...')
            r = await client.get(f'https://slancioalgotradebot.onrender.com/api/users/keys/{key_id}/balance', headers=headers)
            print('Balance Status:', r.status_code)
            print('Balance Response:', r.text)
            
asyncio.run(test_live())

