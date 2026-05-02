import pyotp
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import messagebox, Toplevel
from logzero import logger
from datetime import datetime
import pandas as pd
import mplfinance as mpf
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

# Function to fetch live market data
def fetch_market_data():
    global live_market_data, stop_fetching
    while not stop_fetching:
        mode = "FULL"
        exchangeTokens = {"NSE": ["3045"]}

        try:
            marketData = smart_api.getMarketData(mode, exchangeTokens)
            logger.info(f"Market Data Response: {marketData}")

            if marketData and "data" in marketData and isinstance(marketData["data"], list) and marketData["data"]:
                market_entry = marketData["data"][0]
                live_market_data = {
                    "symbol": market_entry.get("symbol", "N/A"),
                    "token": market_entry.get("token", "N/A"),
                    "ltp": market_entry.get("ltp", "N/A"),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "time": datetime.now().strftime("%H:%M:%S")
                }
                update_ui()
                logger.info("Fetched live market data successfully.")
            else:
                logger.error("Invalid or empty market data response.")
                messagebox.showerror("Error", "Invalid or empty market data response.")
        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            messagebox.showerror("Error", f"Error fetching market data: {e}")

        time.sleep(20)

# Function to update the UI with the latest market data
def update_ui():
    if live_market_data:
        market_data_text.set(
            f"Symbol: {live_market_data['symbol']}\n"
            f"Token: {live_market_data['token']}\n"
            f"LTP: {live_market_data['ltp']}\n"
            f"Date: {live_market_data['date']}\n"
            f"Time: {live_market_data['time']}"
        )

# Function to logout
def auto_logout():
    global stop_fetching
    try:
        stop_fetching = True  # Stop the data-fetching thread
        smart_api.terminateSession(username)
        logger.info("Logged out successfully.")
        messagebox.showinfo("Logout", "You have been logged out successfully.")
        root.destroy()
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        messagebox.showerror("Error", f"Error during logout: {e}")

# Tkinter UI Setup
root = tk.Tk()
root.title("Live Market Data Dashboard")

# Market Data Display
market_data_text = tk.StringVar()
market_data_label = tk.Label(root, textvariable=market_data_text, font=("Helvetica", 14), justify="left", padx=10, pady=10)
market_data_label.pack(pady=20)

# Button to Fetch Candlestick Data
#candle_button = tk.Button(root, text="Show Candlestick Chart", command=fetch_candle_data, font=("Helvetica", 14))
#candle_button.pack(pady=10)

# Logout Button
logout_button = tk.Button(root, text="Auto Logout", command=auto_logout, font=("Helvetica", 14), fg="white", bg="red")
logout_button.pack(pady=20)

# Start the periodic data fetch in a separate thread
thread = threading.Thread(target=fetch_market_data, daemon=True)
thread.start()

# Run the Tkinter event loop
root.mainloop()
