import requests
import base64
import time
from typing import Any, Dict, Optional
from datetime import datetime, timedelta
from enum import Enum
import json

from requests.exceptions import HTTPError

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

import websockets
import asyncio

class Environment(Enum):
    DEMO = "demo"
    PROD = "prod"

class KalshiBaseClient:
    """Base client class for interacting with the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: Environment = Environment.DEMO,
    ):
        """Initializes the client with the provided API key and private key.

        Args:
            key_id (str): Your Kalshi API key ID.
            private_key (rsa.RSAPrivateKey): Your RSA private key.
            environment (Environment): The API environment to use (DEMO or PROD).
        """
        self.key_id = key_id
        self.private_key = private_key
        self.environment = environment
        self.last_api_call = datetime.now()

        if self.environment == Environment.DEMO:
            self.HTTP_BASE_URL = "https://demo-api.kalshi.co"
            self.WS_BASE_URL = "wss://demo-api.kalshi.co"
        elif self.environment == Environment.PROD:
            self.HTTP_BASE_URL = "https://api.elections.kalshi.com"
            self.WS_BASE_URL = "wss://api.elections.kalshi.com"
        else:
            raise ValueError("Invalid environment")

    def request_headers(self, method: str, path: str) -> Dict[str, Any]:
        """Generates the required authentication headers for API requests."""
        current_time_milliseconds = int(time.time() * 1000)
        timestamp_str = str(current_time_milliseconds)

        # Remove query params from path
        path_parts = path.split('?')

        msg_string = timestamp_str + method + path_parts[0]
        # Generate signature
        signature = self.sign_pss_text(msg_string)

        # DEBUG: print signing inputs and headers for troubleshooting auth issues.
        # This will not print the private key, only the message being signed and headers.
        try:
            print("[kalshi-debug] msg_string=", msg_string)
            print("[kalshi-debug] KALSHI-ACCESS-KEY=", self.key_id)
            print("[kalshi-debug] KALSHI-ACCESS-TIMESTAMP=", timestamp_str)
            print("[kalshi-debug] KALSHI-ACCESS-SIGNATURE=", signature[:32] + '...' )
        except Exception:
            # Ensure debug prints never raise
            pass

        headers = {
            "Content-Type": "application/json",
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
        }
        return headers

    def sign_pss_text(self, text: str) -> str:
        """Signs the text using RSA-PSS and returns the base64 encoded signature."""
        message = text.encode('utf-8')
        try:
            signature = self.private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode('utf-8')
        except InvalidSignature as e:
            raise ValueError("RSA sign PSS failed") from e

class KalshiHttpClient(KalshiBaseClient):
    """Client for handling HTTP connections to the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: Environment = Environment.DEMO,
    ):
        super().__init__(key_id, private_key, environment)
        self.host = self.HTTP_BASE_URL
        self.exchange_url = "/trade-api/v2/exchange"
        self.markets_url = "/trade-api/v2/markets"
        self.portfolio_url = "/trade-api/v2/portfolio"

    def rate_limit(self) -> None:
        """Built-in rate limiter to prevent exceeding API rate limits."""
        THRESHOLD_IN_MILLISECONDS = 100
        now = datetime.now()
        threshold_in_microseconds = 1000 * THRESHOLD_IN_MILLISECONDS
        threshold_in_seconds = THRESHOLD_IN_MILLISECONDS / 1000
        if now - self.last_api_call < timedelta(microseconds=threshold_in_microseconds):
            time.sleep(threshold_in_seconds)
        self.last_api_call = datetime.now()

    def raise_if_bad_response(self, response: requests.Response) -> None:
        """Raises an HTTPError if the response status code indicates an error."""
        if response.status_code not in range(200, 299):
            # Print response details to help debug authentication issues.
            try:
                req_headers = getattr(response.request, 'headers', None)
                print('[kalshi-debug] Request headers sent:')
                if req_headers:
                    for k, v in req_headers.items():
                        print(f'  {k}: {v}')
                print('[kalshi-debug] Response status:', response.status_code)
                print('[kalshi-debug] Response body:', response.text)
            except Exception:
                pass
            response.raise_for_status()

    def post(self, path: str, body: dict) -> Any:
        """Performs an authenticated POST request to the Kalshi API."""
        self.rate_limit()
        response = requests.post(
            self.host + path,
            json=body,
            headers=self.request_headers("POST", path)
        )
        self.raise_if_bad_response(response)
        return response.json()

    def get(self, path: str, params: Dict[str, Any] = {}) -> Any:
        """Performs an authenticated GET request to the Kalshi API."""
        self.rate_limit()
        response = requests.get(
            self.host + path,
            headers=self.request_headers("GET", path),
            params=params
        )
        self.raise_if_bad_response(response)
        return response.json()

    def delete(self, path: str, params: Dict[str, Any] = {}) -> Any:
        """Performs an authenticated DELETE request to the Kalshi API."""
        self.rate_limit()
        response = requests.delete(
            self.host + path,
            headers=self.request_headers("DELETE", path),
            params=params
        )
        self.raise_if_bad_response(response)
        return response.json()

    def get_balance(self) -> Dict[str, Any]:
        """Retrieves the account balance."""
        return self.get(self.portfolio_url + '/balance')

    def get_exchange_status(self) -> Dict[str, Any]:
        """Retrieves the exchange status."""
        return self.get(self.exchange_url + "/status")

    def get_trades(
        self,
        ticker: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        max_ts: Optional[int] = None,
        min_ts: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Retrieves trades based on provided filters."""
        params = {
            'ticker': ticker,
            'limit': limit,
            'cursor': cursor,
            'max_ts': max_ts,
            'min_ts': min_ts,
        }
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        return self.get(self.markets_url + '/trades', params=params)

    # BEGIN ADDED: list_markets helper
    def list_markets(self, params: Dict[str, Any] = {}) -> Any:
        """List markets using the markets endpoint with optional query params.

        ADDED: helper to fetch markets; callers can filter results locally.
        """
        return self.get(self.markets_url, params=params)

    def get_market(self, market_id: str) -> Any:
        """Get metadata for a single market by id.

        ADDED: helper to fetch a single market's metadata.
        """
        return self.get(self.markets_url + f"/{market_id}")
    # END ADDED

class KalshiWebSocketClient(KalshiBaseClient):
    """Client for handling WebSocket connections to the Kalshi API."""
    def __init__(
        self,
        key_id: str,
        private_key: rsa.RSAPrivateKey,
        environment: Environment = Environment.DEMO,
    ):
        super().__init__(key_id, private_key, environment)
        self.ws = None
        self.url_suffix = "/trade-api/ws/v2"
        self.message_id = 1  # Add counter for message IDs
        # BEGIN ADDED: HTTP client for metadata lookup and storage for found markets
        # Create an HTTP client instance so the websocket client can look up market
        # metadata (title, end time) when a ticker arrives.
        self.http_client = KalshiHttpClient(key_id=key_id, private_key=private_key, environment=environment)
        # found_markets will hold markets that match our Packers filter
        self.found_markets: Dict[str, Any] = {}
        # keep track of which market_ids we've already inspected
        self._inspected_market_ids = set()
        # END ADDED

    async def connect(self):
        """Establishes a WebSocket connection using authentication."""
        host = self.WS_BASE_URL + self.url_suffix
        auth_headers = self.request_headers("GET", self.url_suffix)
        async with websockets.connect(host, additional_headers=auth_headers) as websocket:
            self.ws = websocket
            await self.on_open()
            await self.handler()

    async def on_open(self):
        """Callback when WebSocket connection is opened."""
        print("WebSocket connection opened.")
        await self.subscribe_to_tickers()

    async def subscribe_to_tickers(self):
        """Subscribe to ticker updates for all markets."""
        subscription_message = {
            "id": self.message_id,
            "cmd": "subscribe",
            "params": {
                "channels": ["ticker"]
            }
        }
        await self.ws.send(json.dumps(subscription_message))
        self.message_id += 1

    async def handler(self):
        """Handle incoming messages."""
        try:
            async for message in self.ws:
                await self.on_message(message)
        except websockets.ConnectionClosed as e:
            await self.on_close(e.code, e.reason)
        except Exception as e:
            await self.on_error(e)

    async def on_message(self, message):
        """Callback for handling incoming messages."""
        # ADDED: parse ticker messages and filter for Packers/Green Bay markets
        try:
            data = json.loads(message)
        except Exception:
            print("Received message (non-JSON):", message)
            return

        # If this is a ticker message, it contains a market_id we can inspect
        if data.get('type') == 'ticker' and isinstance(data.get('msg'), dict):
            msg = data['msg']
            market_id = msg.get('market_id')
            # Avoid re-checking the same market repeatedly
            if market_id and market_id not in self._inspected_market_ids:
                self._inspected_market_ids.add(market_id)
                try:
                    market = self.http_client.get_market(market_id)
                except Exception:
                    market = None

                if market:
                    # The API may return market metadata either as the object itself
                    # or wrapped in {'market': {...}} depending on endpoint shape.
                    candidate = market.get('market') if isinstance(market, dict) and 'market' in market else market
                    title = (candidate.get('title') or '') if isinstance(candidate, dict) else ''
                    # Check for Packers / Green Bay (case-insensitive)
                    if 'packers' in title.lower() or 'green bay' in title.lower():
                        # Check end time if present to ensure it's within next 7 days
                        end_ts = None
                        end_dt = candidate.get('end_datetime') if isinstance(candidate, dict) else None
                        within_window = True
                        if end_dt:
                            try:
                                # Try parsing ISO timestamp
                                from datetime import datetime, timezone, timedelta
                                end_parsed = datetime.fromisoformat(end_dt.replace('Z', '+00:00'))
                                now = datetime.now(timezone.utc)
                                within_window = end_parsed <= (now + timedelta(days=7)) and end_parsed >= now
                            except Exception:
                                within_window = True

                        if within_window:
                            # Save the candidate market
                            self.found_markets[market_id] = candidate
                            print(f"[packers-debug] Found Packers market: {title} (id={market_id})")
        else:
            # For non-ticker messages, print for visibility
            print("Received message:", message)

    async def on_error(self, error):
        """Callback for handling errors."""
        print("WebSocket error:", error)

    async def on_close(self, close_status_code, close_msg):
        """Callback when WebSocket connection is closed."""
        print("WebSocket connection closed with code:", close_status_code, "and message:", close_msg)