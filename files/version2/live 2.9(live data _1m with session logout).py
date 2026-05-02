import time
import threading
import pandas as pd
import pyotp
from datetime import datetime, timedelta
from logzero import logger
import credentials as wd

# Import Dash components
from dash import Dash, dcc, html, Output, Input, State, no_update
from SmartApi.smartConnect import SmartConnect

# Initialize credentials
api_key, username, pwd, token = wd.api_key, wd.username, wd.pwd, wd.Token
candlestick_data, candlestick_data_3min, candlestick_data_5min, latest_data = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}
session_active = True  # Flag to track session status
smart_api = None       # Global reference to the SmartConnect API

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

# Function to log out of the session by terminating
def logout_session():
    global session_active, smart_api
    if smart_api:
        try:
            # Logout via terminateSession method
            smart_api.terminateSession(wd.username)
            logger.info("Session logged out successfully!")
        except Exception as e:
            logger.error(f"Error logging out session: {e}")
    session_active = False

# Function to fetch historical candlestick data and live market data
def fetch_data(api, exchange="NSE", symbol_token="3045"):
    global candlestick_data, candlestick_data_3min, candlestick_data_5min, latest_data
    now = datetime.now()
    try:
        # Fetch 1-minute candlestick data
        response_1min = api.getCandleData({
            "exchange": exchange,
            "symboltoken": symbol_token,
            "interval": "ONE_MINUTE",
            "fromdate": (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            "todate": now.strftime("%Y-%m-%d %H:%M")
        })
        logger.debug(f"1-minute Candle data response: {response_1min}")
        candles_1min = response_1min.get("data", [])
        if candles_1min:
            candlestick_data = pd.DataFrame(candles_1min, columns=["datetime", "open", "high", "low", "close", "volume"])
            candlestick_data["datetime"] = pd.to_datetime(candlestick_data["datetime"])

        # Fetch 3-minute candlestick data
        response_3min = api.getCandleData({
            "exchange": exchange,
            "symboltoken": symbol_token,
            "interval": "THREE_MINUTE",
            "fromdate": (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            "todate": now.strftime("%Y-%m-%d %H:%M")
        })
        logger.debug(f"3-minute Candle data response: {response_3min}")
        candles_3min = response_3min.get("data", [])
        if candles_3min:
            candlestick_data_3min = pd.DataFrame(candles_3min, columns=["datetime", "open", "high", "low", "close", "volume"])
            candlestick_data_3min["datetime"] = pd.to_datetime(candlestick_data_3min["datetime"])

        # Fetch 5-minute candlestick data
        response_5min = api.getCandleData({
            "exchange": exchange,
            "symboltoken": symbol_token,
            "interval": "FIVE_MINUTE",
            "fromdate": (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            "todate": now.strftime("%Y-%m-%d %H:%M")
        })
        logger.debug(f"5-minute Candle data response: {response_5min}")
        candles_5min = response_5min.get("data", [])
        if candles_5min:
            candlestick_data_5min = pd.DataFrame(candles_5min, columns=["datetime", "open", "high", "low", "close", "volume"])
            candlestick_data_5min["datetime"] = pd.to_datetime(candlestick_data_5min["datetime"])

        # Fetch live market data
        market_response = api.getMarketData("FULL", {exchange: [symbol_token]})
        logger.debug(f"Market data response: {market_response}")
        latest_data = market_response.get("data", [{}])[0]
    except Exception as e:
        logger.error(f"Error fetching data: {e}")

# Background thread to periodically fetch data
def update_data_thread():
    api = generate_session()
    if api:
        while session_active:
            fetch_data(api)
            time.sleep(10)

# Start background thread
threading.Thread(target=update_data_thread, daemon=True).start()

# Initialize Dash app
app = Dash(__name__)
app.layout = html.Div([
    html.H1("Live Market Data Dashboard", style={"textAlign": "center"}),
    html.Div(id="live-data", style={"fontSize": 24, "marginBottom": 30, "textAlign": "center"}),
    dcc.Graph(id="candlestick-chart-1min"),
    dcc.Graph(id="candlestick-chart-3min"),
    dcc.Graph(id="candlestick-chart-5min"),
    html.Button("Logout", id="logout-btn", style={"marginTop": 20}),
    dcc.Interval(id="update-interval", interval=10 * 1000)  # Update every 10 seconds
])

# Combined callback to handle data updates and logout
@app.callback(
    [Output("live-data", "children"), 
     Output("candlestick-chart-1min", "figure"),
     Output("candlestick-chart-3min", "figure"),
     Output("candlestick-chart-5min", "figure")],
    [Input("update-interval", "n_intervals"), Input("logout-btn", "n_clicks")],
    [State("live-data", "children")]
)
def update_dashboard(n_intervals, logout_clicks, current_live_data):
    if logout_clicks:
        logout_session()
        return "You have been logged out. Session closed.", {"data": [], "layout": {"title": "Logged Out"}}, {"data": [], "layout": {"title": "Logged Out"}}, {"data": [], "layout": {"title": "Logged Out"}}

    # Live data string
    live_data_str = f"Symbol: {latest_data.get('symbol', 'N/A')} | LTP: {latest_data.get('ltp', 'N/A')} | Timestamp: {latest_data.get('tradetime', 'N/A')}"

    # 1-minute candlestick chart
    fig_1min = {
        "data": [{
            "x": candlestick_data["datetime"],
            "open": candlestick_data["open"],
            "high": candlestick_data["high"],
            "low": candlestick_data["low"],
            "close": candlestick_data["close"],
            "type": "candlestick"
        }],
        "layout": {"title": "1-Minute Candlestick Chart", "xaxis": {"rangeslider": {"visible": False}}, "yaxis": {"title": "Price"}}
    }

    # 3-minute candlestick chart
    fig_3min = {
        "data": [{
            "x": candlestick_data_3min["datetime"],
            "open": candlestick_data_3min["open"],
            "high": candlestick_data_3min["high"],
            "low": candlestick_data_3min["low"],
            "close": candlestick_data_3min["close"],
            "type": "candlestick"
        }],
        "layout": {"title": "3-Minute Candlestick Chart", "xaxis": {"rangeslider": {"visible": False}}, "yaxis": {"title": "Price"}}
    }

    # 5-minute candlestick chart
    fig_5min = {
        "data": [{
            "x": candlestick_data_5min["datetime"],
            "open": candlestick_data_5min["open"],
            "high": candlestick_data_5min["high"],
            "low": candlestick_data_5min["low"],
            "close": candlestick_data_5min["close"],
            "type": "candlestick"
        }],
        "layout": {"title": "5-Minute Candlestick Chart", "xaxis": {"rangeslider": {"visible": False}}, "yaxis": {"title": "Price"}}
    }

    return live_data_str, fig_1min, fig_3min, fig_5min

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)
