# slack.py

from datetime import datetime
import json
import secrets
import time
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import httpx
import asyncio
import base64
import requests
from integrations.integration_item import IntegrationItem

from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = 'f561caff-d3b8-43e8-87e1-b167299a16fa'
CLIENT_SECRET = '7fabfac8-bf25-4759-93cb-5eca2c0eaa8c'

REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
authorization_url = f'https://app-na2.hubspot.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri=http://localhost:8000/integrations/hubspot/oauth2callback&scope=crm.objects.contacts.write%20oauth%20crm.objects.contacts.read'

async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    raw_state = json.dumps(state_data)
    # Hubspot expects urlsafe encoded state to identify and manage states in the app
    encoded_state = base64.urlsafe_b64encode(raw_state.encode()).decode()
    await add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', raw_state, expire=600)

    return f'{authorization_url}&state={encoded_state}'

async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error'))
    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    decoded_state = base64.urlsafe_b64decode(encoded_state).decode()
    state_data = json.loads(decoded_state)

    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')

    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')

    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                'https://api.hubapi.com/oauth/v1/token',
                # Hubspot accepts form-data
                data={
                    'grant_type': 'authorization_code',
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'redirect_uri': REDIRECT_URI,
                    'code': code,
                }, 
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            ),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        )
    
    response = {
        'created_at': time.time(),
        **response.json()
    }

    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(response), expire=600)

    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)

async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')

    return credentials

def create_integration_item_metadata_object(
    response_json: str
) -> IntegrationItem:
    """Parses a list of HubSpot-like contact responses into IntegrationItem objects."""

    contact_id = response_json.get('id')
    properties = response_json.get('properties', {})

    firstname = properties.get('firstname', '')
    lastname = properties.get('lastname', '')
    name = f"{firstname} {lastname}".strip()

    creation_time = response_json.get('createdAt')
    last_modified_time = response_json.get('updatedAt')
    visibility = not response_json.get('archived', False)


    # Convert string timestamps to datetime objects
    if creation_time:
        creation_time = datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
    if last_modified_time:
        last_modified_time = datetime.fromisoformat(last_modified_time.replace("Z", "+00:00"))

    integration_item_metadata = IntegrationItem(
        id=contact_id,
        type='contact',
        name=name,
        creation_time=creation_time,
        last_modified_time=last_modified_time,
        visibility=visibility,
    )

    return integration_item_metadata

async def get_items_hubspot(credentials) -> list[IntegrationItem]:
    credentials = json.loads(credentials)
    response = requests.post(
        'https://api.hubapi.com/crm/v3/objects/contacts/search',
        json=
            {
            "filterGroups": [
                {
                "filters": []
                }
            ],
        },
        headers={
            'Authorization': f'Bearer {credentials.get("access_token")}',
            'Content-Type': 'application/json',
        }
    )

    if response.status_code == 200:
        results = response.json()['results']
        list_of_integration_item_metadata = []
        for result in results:
            list_of_integration_item_metadata.append(
                create_integration_item_metadata_object(result)
            )

        for item in list_of_integration_item_metadata:
            print(item)

    return JSONResponse(
        content={ 
            'integration': [item.to_dict() for item in list_of_integration_item_metadata]
        }
    )