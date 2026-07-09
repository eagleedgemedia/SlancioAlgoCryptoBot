
import httpx
import asyncio

async def inject():
    base = 'https://slancioalgotradebot.onrender.com'
    async with httpx.AsyncClient() as client:
        # 1. Login
        print('Logging in...')
        r = await client.post(f'{base}/api/auth/login', data={'username': 'Admin', 'password': 'RagiKaushal@2616'})
        token = r.json().get('access_token')
        if not token:
            print('Login failed!', r.json())
            return
            
        headers = {'Authorization': f'Bearer {token}'}
        
        # 2. Get existing keys
        print('Fetching existing keys...')
        r = await client.get(f'{base}/api/users/keys', headers=headers)
        keys = r.json()
        print('Found keys:', keys)
        
        # 3. Delete all existing keys
        for k in keys:
            kid = k.get('id')
            print(f'Deleting key {kid}...')
            r_del = await client.delete(f'{base}/api/users/keys/{kid}', headers=headers)
            print('Delete result:', r_del.text)
            
        # 4. Add new key
        print('Adding new key...')
        payload = {
            'api_name': 'Kaushal API',
            'api_key': 'edgmXafwgU5XtXPXAHnEYyNUfMTHA4',
            'api_secret': 'rbC1MS90pykUKY7P4XzwxEF4lFw8LbgsHxYVVFxnqvltqa9FGTyzhUAOCexK',
            'exchange': 'delta_india'
        }
        r = await client.post(f'{base}/api/users/keys', json=payload, headers=headers)
        print('Add Key Result:', r.json())
        
        # 5. Fetch new keys to get the ID
        r = await client.get(f'{base}/api/users/keys', headers=headers)
        new_keys = r.json()
        if new_keys:
            new_id = new_keys[0]['id']
            # 6. Verify Balance
            print('Verifying balance...')
            r = await client.get(f'{base}/api/users/keys/{new_id}/balance', headers=headers)
            print('Balance Result:', r.json())
            
            # 7. Select it
            print('Selecting key as active...')
            r = await client.post(f'{base}/api/users/keys/{new_id}/select', headers=headers)
            print('Select Result:', r.json())

asyncio.run(inject())

