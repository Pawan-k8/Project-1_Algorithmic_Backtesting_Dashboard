import tkinter as tk
from tkinter import messagebox
import pandas as pd
import credentials as wd
import time
import threading
import pyotp
from datetime import datetime, timedelta
from logzero import logger
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from SmartApi.smartConnect import SmartConnect

# Load the Excel file into a pandas DataFrame
XLpath = wd.XLpath  # Change the path as per your file location
df = pd.read_excel(XLpath, sheet_name='NSE Token & Multiplier')

# Initialize credentials
api_key, username, pwd, token = wd.api_key, wd.username, wd.pwd, wd.Token
candlestick_data, candlestick_data_3min, candlestick_data_5min, latest_data = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}
session_active = True  # Flag to track session status
smart_api = None       # Global reference to the SmartConnect API
market_closed = False  # Flag to track market status
last_valid_ltp = "N/A"  # Global variable to store the last valid LTP

# Function to generate session and authenticate
def generate_session():
    global smart_api
    try:
        totp = pyotp.TOTP(token).now()
        smart_api = SmartConnect(api_key)
        smart_api.generateSession(username, pwd, totp)
        logger.info("Session generated successfully!")
        return smart_api
    except Exception as e:
        logger.error(f"Error generating session: {e}")
        return None

# Function to fetch historical candlestick data and live market data
def fetch_data(api, exchange="NSE", symbol_token="3045"):
    global candlestick_data, candlestick_data_3min, candlestick_data_5min, latest_data, market_closed, last_valid_ltp
    now = datetime.now()
    try:
        # Check if the market is closed
        market_close_time = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
        market_open_time = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
        if now < market_open_time or now > market_close_time:
            market_closed = True
            return
        else:
            market_closed = False

        # Fetch 1-minute candlestick data
        response_1min = api.getCandleData({
            "exchange": exchange,
            "symboltoken": symbol_token,
            "interval": "ONE_MINUTE",
            "fromdate": (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            "todate": now.strftime("%Y-%m-%d %H:%M")
        })
        candles_1min = response_1min.get("data", [])
        if candles_1min:
            candlestick_data = pd.DataFrame(candles_1min, columns=["datetime", "open", "high", "low", "close", "volume"])
            candlestick_data["datetime"] = pd.to_datetime(candlestick_data["datetime"])

        # Fetch live market data
        market_response = api.getMarketData("FULL", {exchange: [symbol_token]})
        latest_data = market_response.get("data", [{}])[0]

        # Update the last valid LTP if available
        ltp = latest_data.get("ltp")
        if ltp is not None:
            last_valid_ltp = ltp
    except Exception as e:
        logger.error(f"Error fetching data: {e}")

# Function to search for the symbol and show the token, multiplier, and exchange
def search_symbol():
    symbol = entry_symbol.get().strip()
    
    if symbol:
        # Filter the DataFrame based on the symbol
        result = df[df['SymbolName'].str.upper() == symbol.upper()]
        
        if not result.empty:
            token = result['token'].values[0]
            multiplier = result['Multiplier'].values[0]
            exchange = result['Exchange'].values[0]
            label_result.config(text=f"Token: {token}\nMultiplier: {multiplier}\nExchange: {exchange}")
            
            # Use token and exchange to fetch live market data
            api = generate_session()
            if api:
                fetch_data(api, exchange, str(token))  # Fetch live data using token and exchange
                update_dashboard()  # Update dashboard with the fetched data
        else:
            messagebox.showinfo("No Result", f"No data found for symbol: {symbol}")
    else:
        messagebox.showinfo("Input Error", "Please enter a symbol to search.")
    
    # Ensure the scroll region is updated after adding widgets (for proper scrolling)
    update_scrollable_frame()

# Function to update the dashboard (LTP and live data)
def update_dashboard():
    global market_closed, last_valid_ltp

    # If the market is closed
    if market_closed:
        ltp_label.config(text=f"LTP: {last_valid_ltp} (Market Closed)")
        live_data_label.config(text="Market is closed. Showing last available data.")
    else:
        # Extract LTP or fallback to the last valid LTP
        ltp = latest_data.get('ltp', last_valid_ltp)
        live_data_str = f"Symbol: {latest_data.get('symbol', 'N/A')} | LTP: {ltp} | Timestamp: {latest_data.get('tradetime', 'N/A')}"
        ltp_label.config(text=f"LTP: {ltp}")
        live_data_label.config(text=live_data_str)

    # Plot the candlestick charts
    plot_candlestick_chart(candlestick_data, chart_type="1min")
    plot_candlestick_chart(candlestick_data_3min, chart_type="3min")
    plot_candlestick_chart(candlestick_data_5min, chart_type="5min")

# Function to plot candlestick chart using matplotlib
def plot_candlestick_chart(candlestick_data, chart_type="1min"):
    fig = plt.Figure(figsize=(8, 4), dpi=100)
    ax = fig.add_subplot(111)
    
    if chart_type == "1min":
        data = candlestick_data
    elif chart_type == "3min":
        data = candlestick_data_3min
    else:
        data = candlestick_data_5min
    
    if not data.empty:
        ax.plot(data["datetime"], data["close"], label="Close", color="blue")
        ax.set_title(f"{chart_type} Candlestick Chart")
        ax.set_xlabel("Time")
        ax.set_ylabel("Price")
        ax.legend()

    # Display the chart on Tkinter
    canvas = FigureCanvasTkAgg(fig, master=chart_frame)
    canvas.draw()
    canvas.get_tk_widget().pack()

# Function to log out of the session
def logout_session():
    global session_active, smart_api
    if smart_api:
        try:
            # Logout via terminateSession method
            smart_api.terminateSession(wd.username)
            logger.info("Session logged out successfully!")
            messagebox.showinfo("Logged Out", "You have been logged out.")
        except Exception as e:
            logger.error(f"Error logging out session: {e}")
    session_active = False

# Set up the Tkinter root window
root = tk.Tk()
root.title("Symbol Search and Live Data Dashboard")

# Create a canvas and a scrollbar for scrollable content
canvas = tk.Canvas(root)
scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
canvas.configure(yscrollcommand=scrollbar.set)

# Create a frame to hold the widgets inside the canvas
scrollable_frame = tk.Frame(canvas)

# Create a window inside the canvas for the scrollable content
canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
scrollbar.pack(side="right", fill="y")
canvas.pack(side="left", fill="both", expand=True)

# Create widgets for symbol search
label_prompt = tk.Label(scrollable_frame, text="Enter Symbol:")
label_prompt.pack(pady=10)

entry_symbol = tk.Entry(scrollable_frame, width=20)
entry_symbol.pack(pady=5)

button_search = tk.Button(scrollable_frame, text="Search", command=search_symbol)
button_search.pack(pady=10)

label_result = tk.Label(scrollable_frame, text="", font=("Arial", 12))
label_result.pack(pady=10)

# Create widgets for live data display
ltp_label = tk.Label(scrollable_frame, text="LTP: Loading...", font=("Helvetica", 24))
ltp_label.pack(pady=10)

live_data_label = tk.Label(scrollable_frame, text="Live Data: Loading...", font=("Helvetica", 16))
live_data_label.pack(pady=10)

# Create a frame for the candlestick charts
chart_frame = tk.Frame(scrollable_frame)
chart_frame.pack(pady=20)

# Create the logout button at the bottom of the scrollable frame
logout_button = tk.Button(scrollable_frame, text="Logout", command=logout_session, font=("Helvetica", 14), fg="red")
logout_button.pack(pady=20)

# Function to update the scrollable frame height after widgets are added
def update_scrollable_frame():
    scrollable_frame.update_idletasks()
    canvas.config(scrollregion=canvas.bbox("all"))

root.after(100, update_scrollable_frame)  # Ensure the scroll region is updated

# Start the Tkinter main loop
root.mainloop()
