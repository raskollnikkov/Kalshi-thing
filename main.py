import os
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization
import asyncio

from clients import KalshiHttpClient, KalshiWebSocketClient, Environment

# Load environment variables
load_dotenv()
env = Environment.DEMO # toggle environment here
KEYID = os.getenv('DEMO_KEYID') if env == Environment.DEMO else os.getenv('PROD_KEYID')
KEYFILE = os.getenv('DEMO_KEYFILE') if env == Environment.DEMO else os.getenv('PROD_KEYFILE')

try:
    with open(KEYFILE, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None  # Provide the password if your key is encrypted
        )
except FileNotFoundError:
    raise FileNotFoundError(f"Private key file not found at {KEYFILE}")
except Exception as e:
    raise Exception(f"Error loading private key: {str(e)}")

# Initialize the HTTP client
client = KalshiHttpClient(
    key_id=KEYID,
    private_key=private_key,
    environment=env
)

# Get account balance
balance = client.get_balance()
print("Balance:", balance)

# Initialize the WebSocket client
ws_client = KalshiWebSocketClient(
    key_id=KEYID,
    private_key=private_key,
    environment=env
)

# BEGIN ADDED: run an initial HTTP one-shot search for Packers markets in next 7 days
# This uses the HTTP client to list markets and locally filter titles for Packers / Green Bay.
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
end_time = now + timedelta(days=7)
start_str = now.strftime('%Y-%m-%dT%H:%M:%SZ')
end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
try:
    params = {'min_end_datetime': start_str, 'max_end_datetime': end_str}
    markets_resp = client.list_markets(params=params)
    markets_list = markets_resp.get('markets', []) if isinstance(markets_resp, dict) else []
    print(f"HTTP search found {len(markets_list)} markets in next 7 days (filtering for Packers)...")
    for m in markets_list:
        title = m.get('title', '')
        if 'packers' in title.lower() or 'green bay' in title.lower():
            print("[http-packers] ", title, m.get('end_datetime'), m.get('id') or m.get('market_id'))
except Exception as e:
    print("HTTP market list/search failed:", e)
# END ADDED

# Connect via WebSocket with a timeout so the demo run won't stream forever.
# Use the RUN_SECONDS environment variable to control duration (default 10 seconds).
RUN_SECONDS = int(os.getenv('RUN_SECONDS', '10'))

try:
    # Run the connect coroutine but cancel after RUN_SECONDS to keep the demo short
    asyncio.run(asyncio.wait_for(ws_client.connect(), timeout=RUN_SECONDS))
except asyncio.TimeoutError:
    print(f"Reached timeout of {RUN_SECONDS} seconds, shutting down demo websocket.")
except Exception as e:
    print("WebSocket error or shutdown:", e)