import time
import pyotp
from logzero import logger
import credentials as wd

# Import SmartConnect API
from SmartApi.smartConnect import SmartConnect

# Initialize SmartConnect API with credentials
api_key = wd.api_key
username = wd.username
pwd = wd.pwd
token = wd.Token

# Function to generate session and get auth token
def generate_session():
    try:
        totp = pyotp.TOTP(token).now()
        smart_api = SmartConnect(api_key)
        data = smart_api.generateSession(username, pwd, totp)

        auth_token = data['data']['jwtToken']
        feed_token = smart_api.getfeedToken()
        refresh_token = data['data']['refreshToken']

        logger.info("Session generated successfully!")
        return smart_api, auth_token, feed_token, refresh_token

    except Exception as e:
        logger.error(f"Error generating session: {e}")
        return None, None, None, None

# Function to fetch live market data
def fetch_live_data(smart_api, exchange, symbol_token):
    mode = "FULL"
    exchange_tokens = {exchange: [symbol_token]}

    try:
        market_data = smart_api.getMarketData(mode, exchange_tokens)
        logger.info(f"Market Data Response: {market_data}")

        if market_data and "data" in market_data and market_data["data"]:
            entry = market_data["data"][0]
            symbol = entry.get("symbol", "N/A")
            ltp = entry.get("ltp", "N/A")
            tradetime = entry.get("tradetime", "N/A")

            print(f"Symbol: {symbol}")
            print(f"LTP: {ltp}")
            print(f"Timestamp: {tradetime}")
            print("-----------------------------")
        else:
            logger.error("Invalid or empty market data response.")

    except Exception as e:
        logger.error(f"Error fetching market data: {e}")

# Main function to repeatedly fetch live data
def main():
    exchange = "NSE"
    symbol_token = "3045"  # Replace with a valid symbol token

    # Generate session
    smart_api, auth_token, feed_token, refresh_token = generate_session()

    if auth_token:
        while True:
            fetch_live_data(smart_api, exchange, symbol_token)
            time.sleep(10)  # Fetch data every 10 seconds
    else:
        print("Failed to authenticate. Please check your credentials.")

if __name__ == "__main__":
    main()
