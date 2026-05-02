import time
import threading
import pandas as pd
import pyotp
from datetime import datetime, timedelta
from logzero import logger
import credentials as wd

# Import Dash and Plotly components
from dash import Dash, dcc, html
from dash.dependencies import Output, Input

# Import SmartConnect API
from SmartApi.smartConnect import SmartConnect

# Initialize SmartConnect API with credentials
api_key = wd.api_key
username = wd.username
pwd = wd.pwd
token = wd.Token

# Initialize global variables for storing data
candlestick_data = pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
latest_data = {}

# Function to generate session and authenticate
def generate_session():
    try:
        totp = pyotp.TOTP(token).now()
        smart_api = SmartConnect(api_key)
        data = smart_api.generateSession(username, pwd, totp)
        logger.info("Session generated successfully!")
        return smart_api
    except Exception as e:
        logger.error(f"Error generating session: {e}")
        return None

# Fetch historical candlestick data
def fetch_candlestick_data(smart_api, exchange, symbol_token, interval="ONE_MINUTE"):
    global candlestick_data
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=30)  # Fetch last 30 minutes of data

    candle_params = {
        "exchange": exchange,
        "symboltoken": symbol_token,
        "interval": interval,
        "fromdate": start_time.strftime("%Y-%m-%d %H:%M"),
        "todate": end_time.strftime("%Y-%m-%d %H:%M")
    }

    try:
        data = smart_api.getCandleData(candle_params)
        if data and "data" in data and data["data"]:
            candles = data["data"]
            candlestick_data = pd.DataFrame(candles, columns=["datetime", "open", "high", "low", "close", "volume"])
            candlestick_data["datetime"] = pd.to_datetime(candlestick_data["datetime"])
            logger.info("Candlestick data fetched successfully!")
        else:
            logger.error("Invalid or empty candlestick data response.")
    except Exception as e:
        logger.error(f"Error fetching candlestick data: {e}")

# Fetch the latest live market data
def fetch_live_data(smart_api, exchange, symbol_token):
    global latest_data
    mode = "FULL"
    exchange_tokens = {exchange: [symbol_token]}

    try:
        market_data = smart_api.getMarketData(mode, exchange_tokens)
        if market_data and "data" in market_data and market_data["data"]:
            entry = market_data["data"][0]
            latest_data = {
                "symbol": entry.get("symbol", "N/A"),
                "ltp": entry.get("ltp", "N/A"),
                "tradetime": entry.get("tradetime", "N/A"),
            }
            logger.info("Live market data fetched successfully!")
        else:
            logger.error("Invalid or empty live market data response.")
    except Exception as e:
        logger.error(f"Error fetching live market data: {e}")

# Background thread to periodically fetch data
def update_data_thread():
    smart_api = generate_session()
    exchange = "NSE"
    symbol_token = "3045"  # Replace with a valid symbol token
    while True:
        fetch_candlestick_data(smart_api, exchange, symbol_token)
        fetch_live_data(smart_api, exchange, symbol_token)
        time.sleep(10)

# Start the background data-fetching thread
thread = threading.Thread(target=update_data_thread, daemon=True)
thread.start()

# Initialize Dash app
app = Dash(__name__)

app.layout = html.Div([
    html.H1("Live Market Data Dashboard", style={"textAlign": "center"}),
    html.Div(id="live-data", style={"fontSize": 24, "marginBottom": 30, "textAlign": "center"}),
    dcc.Graph(id="candlestick-chart"),
    dcc.Interval(id="update-interval", interval=10 * 1000)  # Update every 10 seconds
])

# Callback to update live data and candlestick chart
@app.callback(
    [Output("live-data", "children"), Output("candlestick-chart", "figure")],
    Input("update-interval", "n_intervals")
)
def update_dashboard(n):
    # String output for live market data
    live_data_str = f"""
        Symbol: {latest_data.get('symbol', 'N/A')} | 
        LTP: {latest_data.get('ltp', 'N/A')} | 
        Timestamp: {latest_data.get('tradetime', 'N/A')}
    """

    # Plotly candlestick chart
    if not candlestick_data.empty:
        fig = {
            "data": [{
                "x": candlestick_data["datetime"],
                "open": candlestick_data["open"],
                "high": candlestick_data["high"],
                "low": candlestick_data["low"],
                "close": candlestick_data["close"],
                "type": "candlestick",
                "name": "Candlestick Chart"
            }],
            "layout": {
                "title": "Last 30 Candles",
                "xaxis": {"rangeslider": {"visible": False}},
                "yaxis": {"title": "Price"}
            }
        }
    else:
        fig = {"data": [], "layout": {"title": "No Data Available"}}

    return live_data_str, fig

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)
