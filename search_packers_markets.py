import os
import requests
from datetime import datetime, timedelta, timezone

# Set your Kalshi API key here or as an environment variable
KALSHI_API_KEY = os.getenv('KALSHI_API_KEY','9254235b-531c-4fef-81a9-95a394fa5b01')
KALSHI_API_URL = 'https://api.elections.kalshi.com/v2/markets/list'



# Time window: next 7 days
now = datetime.now(timezone.utc)
end_time = now + timedelta(days=7)

# Format times for API (ISO8601)
start_str = now.strftime('%Y-%m-%dT%H:%M:%SZ')
end_str = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')

headers = {
    'Authorization': f'Bearer {KALSHI_API_KEY}',
    'Content-Type': 'application/json'
}

params = {
    'event_ticker': 'NFL',  # Pro football
    'status': 'open',
    'sort': 'asc',
    'min_end_datetime': start_str,
    'max_end_datetime': end_str
}

def main():
    response = requests.get(KALSHI_API_URL, headers=headers, params=params)
    if response.status_code != 200:
        print(f"Error: {response.status_code} {response.text}")
        return
    data = response.json()
    packers_markets = []
    for market in data.get('markets', []):
        if 'Packers' in market.get('title', '') or 'Green Bay' in market.get('title', ''):
            packers_markets.append(market)
    if not packers_markets:
        print("No Packers markets found in the next 7 days.")
    else:
        print("Packers markets in the next 7 days:")
        for m in packers_markets:
            print(f"- {m.get('title')} (Ends: {m.get('end_datetime')})")

if __name__ == '__main__':
    main()
