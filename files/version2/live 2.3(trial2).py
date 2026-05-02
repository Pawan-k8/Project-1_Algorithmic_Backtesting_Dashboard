import requests
import pyotp
import time
from logzero import logger
import credentials as wd

# Angel One API URLs
SESSION_URL = "https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/login"
LIVE_DATA_URL = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/market/v1/quote/"

# Initialize credentials
api_key = wd.api_key
username = wd.username
pwd = wd.pwd
token = wd.token

# Function to generate session and get auth token
def generate_session():
    totp = pyotp.TOTP(token).now()
    payload = {
        "clientcode": username,
        "password": pwd,
        "totp": token
    }

    headers = {
        "Content-Type": "application/json",
        "X-ApiKey": api_key
    }

    try:
        response = requests.post(SESSION_URL, json=payload, headers=headers)
        print(f"Raw Response: {response.content}")
        print(f"Status Code: {response.status_code}")

        response.raise_for_status()
        data = response.json()

        if data.get("status") and data["status"]:
            auth_token = data["data"]["jwtToken"]
            logger.info("Session generated successfully!")
            return auth_token
        else:
            logger.error(f"Error generating session: {data}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        return None
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.error(f"Response content: {response.content}")
        return None

# Function to fetch live market data
def fetch_live_data(auth_token, symbol_token, exchange="NSE"):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": "127.0.0.1",
        "X-ClientPublicIP": "127.0.0.1",
        "Accept": "application/json"
    }

    payload = {
        "exchange": exchange,
        "symboltoken": symbol_token
    }

    try:
        response = requests.post(LIVE_DATA_URL, headers=headers, json=payload)
        print(f"Raw Response: {response.content}")
        print(f"Status Code: {response.status_code}")

        response.raise_for_status()
        data = response.json()

        if data.get("data"):
            market_data = data["data"]
            logger.info(f"Live Market Data: {market_data}")
            print(f"Symbol: {market_data.get('symbol', 'N/A')}")
            print(f"LTP: {market_data.get('ltp', 'N/A')}")
            print(f"Timestamp: {market_data.get('tradetime', 'N/A')}")
            print("-----------------------------")
        else:
            logger.error(f"Error fetching market data: {data}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
    except requests.exceptions.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.error(f"Response content: {response.content}")

# Main function to repeatedly fetch live data
def main():
    symbol_token = "3045"  # Replace with a valid symbol token
    auth_token = generate_session()

    if auth_token:
        while True:
            fetch_live_data(auth_token, symbol_token)
            time.sleep(10)  # Fetch data every 10 seconds
    else:
        print("Failed to authenticate. Please check your credentials.")

if __name__ == "__main__":
    main()
