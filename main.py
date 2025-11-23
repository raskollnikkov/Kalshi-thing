import os
from dotenv import load_dotenv
from cryptography.hazmat.primitives import serialization
import asyncio

from clients import KalshiHttpClient, KalshiWebSocketClient, Environment

# Load environment variables from .env (if present)
load_dotenv()

# Allow switching environments via the KALSHI_ENV variable ("demo" or "prod").
# Defaults to demo to keep the current branch safe for testing.
kalshi_env = os.getenv('KALSHI_ENV', 'demo').lower()
env = Environment.PROD if kalshi_env == 'prod' else Environment.DEMO

# Pick the appropriate key ID and key file from environment variables
KEYID = os.getenv('PROD_KEYID') if env == Environment.PROD else os.getenv('DEMO_KEYID')
KEYFILE = os.getenv('PROD_KEYFILE') if env == Environment.PROD else os.getenv('DEMO_KEYFILE')

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

# Connect via WebSocket
asyncio.run(ws_client.connect())