import pyotp
import os
import sys
import time
import threading
from logzero import logger
from datetime import datetime
import requests
import credentials as wd

# Import SmartConnect API
root_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.append(root_directory)
from SmartApi.smartConnect import SmartConnect

# Initialize SmartConnect API
api_key = wd.api_key
username = wd.username
pwd = wd.pwd
token = wd.token
totp = pyotp.TOTP(token).now()
smart_api = SmartConnect(api_key)
data = smart_api.generateSession(username, pwd, totp)
authToken = data['data']['jwtToken']
feedToken = smart_api.getfeedToken()
refreshToken = data['data']['refreshToken']

# Global variables
live_market_data = {}
stop_fetching = False

# API URL
API_URL = "https://apiconnect.angelbroking.com/rest/secure/angelbroking/market/v1/quote/"

# Headers for API request
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {authToken}",
    "X-UserType": "USER",
    "X-SourceID": "WEB",
    "X-ClientLocalIP": "127.0.0.1",
    "X-ClientPublicIP": "127.0.0.1",
    "Accept": "application/json"
}

# Function to fetch market data for different intervals
def fetch_market_data():
    global live_market_data, stop_fetching
    intervals = ["1m", "3m", "5m", "15m"]
    symbol_token = "3045"  # Example token, replace with a valid one

    while not stop_fetching:
        try:
            for interval in intervals:
                payload = {
                    "exchange": "NSE",
                    "symboltoken": symbol_token,
                    "interval": interval
                }

                response = requests.post(API_URL, headers=HEADERS, json=payload)
                data = response.json()
                logger.info(f"{interval} Data Response: {data}")

                if data.get("data"):
                    market_entry = data["data"]
                    live_market_data[interval] = {
                        "symbol": market_entry.get("symbol", "N/A"),
                        "ltp": market_entry.get("ltp", "N/A"),
                        "interval": interval,
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "time": datetime.now().strftime("%H:%M:%S")
                    }

            # Log the fetched data
            log_market_data()
            logger.info("Fetched live market data successfully.")
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")

        time.sleep(20)  # Adjust the sleep interval if needed

# Function to log the market data
def log_market_data():
    for interval, data in live_market_data.items():
        logger.info(
            f"Interval: {interval}, Symbol: {data['symbol']}, LTP: {data['ltp']}, "
            f"Date: {data['date']}, Time: {data['time']}"
        )

# Function to logout
def auto_logout():
    global stop_fetching
    try:
        stop_fetching = True  # Stop the data-fetching thread
        smart_api.terminateSession(username)
        logger.info("Logged out successfully.")
    except Exception as e:
        logger.error(f"Error during logout: {e}")

# Start the periodic data fetch in a separate thread
thread = threading.Thread(target=fetch_market_data, daemon=True)
thread.start()

# Keep the script running to allow continuous data fetching
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logger.info("Stopping data fetch and logging out...")
    auto_logout()
