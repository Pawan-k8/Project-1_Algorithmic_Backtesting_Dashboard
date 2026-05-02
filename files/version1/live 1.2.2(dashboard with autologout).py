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

# Global variable to store market data
live_market_data = {}

# Function to fetch live market data
def fetch_market_data():
    global live_market_data
    mode = "FULL"
    exchangeTokens = {"NSE": ["3045"]}
    try:
        marketData = smart_api.getMarketData(mode, exchangeTokens)
        if "data" in marketData and marketData["data"]:
            market_entry = marketData["data"][0]
            live_market_data = {
                "symbol": market_entry.get("symbol"),
                "token": market_entry.get("token"),
                "ltp": market_entry.get("ltp"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S")
            }
            update_ui()
            logger.info("Fetched live market data.")
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")

# Function to fetch candlestick data and plot using mplfinance
def fetch_candle_data():
    candleParams = {
        "exchange": "NSE",
        "symboltoken": "3045",
        "interval": "FIVE_MINUTE",
        "fromdate": "2023-10-18 09:15",
        "todate": "2023-10-18 15:30"
    }
    try:
        candledetails = smart_api.getCandleData(candleParams)
        data = candledetails.get('data', [])
        if data:
            # Create DataFrame for mplfinance
            df = pd.DataFrame(data, columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)

            # Plot candlestick chart in a new window
            new_window = Toplevel(root)
            new_window.title("Candlestick Chart")
            new_window.geometry("800x600")

            # Plot the chart
            fig, ax = mpf.plot(df, type='candle', style='charles', title='Candlestick Chart', ylabel='Price', returnfig=True)
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            canvas = FigureCanvasTkAgg(fig, master=new_window)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            messagebox.showinfo("Info", "No candlestick data available.")
    except Exception as e:
        logger.error(f"Error fetching candlestick data: {e}")
        messagebox.showerror("Error", f"Error fetching candlestick data: {e}")

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
    try:
        smart_api.terminateSession(username)
        logger.info("Logged out successfully.")
        messagebox.showinfo("Logout", "You have been logged out successfully.")
        root.destroy()
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        messagebox.showerror("Error", f"Error during logout: {e}")

# Function to periodically fetch market data
def periodic_fetch():
    while True:
        fetch_market_data()
        time.sleep(10)

# Tkinter UI Setup
root = tk.Tk()
root.title("Live Market Data Dashboard")

# Market Data Display
market_data_text = tk.StringVar()
market_data_label = tk.Label(root, textvariable=market_data_text, font=("Helvetica", 14), justify="left", padx=10, pady=10)
market_data_label.pack(pady=20)

# Button to Fetch Candlestick Data
candle_button = tk.Button(root, text="Show Candlestick Chart", command=fetch_candle_data, font=("Helvetica", 14))
candle_button.pack(pady=10)

# Logout Button
logout_button = tk.Button(root, text="Auto Logout", command=auto_logout, font=("Helvetica", 14), fg="white", bg="red")
logout_button.pack(pady=20)

# Start the periodic data fetch in a separate thread
thread = threading.Thread(target=periodic_fetch, daemon=True)
thread.start()

# Run the Tkinter event loop
root.mainloop()
