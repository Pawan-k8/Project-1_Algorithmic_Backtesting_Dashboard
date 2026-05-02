import requests
import pyotp
import time
from logzero import logger
import credentials as wd  # Make sure this file contains your credentials

# Angel One API URL for fetching live data
API_URL = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/market/v1/quote/"

# Initialize credentials
api_key = wd.api_key
username = wd.username
pwd = wd.pwd
token = wd.Token
totp = pyotp.TOTP(token).now()

# Function to generate session and get auth token
def generate_session():
    session_url = "https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/login"

    payload = {
        "clientcode": username,
        "password": pwd,
        "totp": totp
    }

    headers = {
        "Content-Type": "application/json",
        "X-ApiKey": api_key
    }

    response = requests.post(session_url, json=payload, headers=headers)
    data = response.json()

    if data.get("status") and data["status"] == True:
        auth_token = data["data"]["jwtToken"]
        logger.info("Session generated successfully!")
        return auth_token
    else:
        logger.error(f"Error generating session: {data}")
        return None

# Function to fetch live market data
def fetch_live_data(auth_token, symbol_token, exchange="NSE"):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"{auth_token}",
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
        response = requests.post(API_URL, headers=headers, json=payload)
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
    except Exception as e:
        logger.error(f"Exception occurred: {e}")

# Main function to repeatedly fetch live data
def main():
    symbol_token = "3045"  # Example token, replace with a valid one for the stock you want
    auth_token = generate_session()

    if auth_token:
        while True:
            fetch_live_data(auth_token, symbol_token)
            time.sleep(10)  # Fetch data every 10 seconds
    else:
        print("Failed to authenticate. Please check your credentials.")

if __name__ == "__main__":
    main()
