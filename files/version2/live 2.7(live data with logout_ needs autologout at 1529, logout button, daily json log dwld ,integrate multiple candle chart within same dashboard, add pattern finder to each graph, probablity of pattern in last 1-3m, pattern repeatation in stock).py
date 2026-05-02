import time
import threading
import pandas as pd
import pyotp
from datetime import datetime, timedelta
from logzero import logger
import credentials as wd

# Import Dash components
from dash import Dash, dcc, html, Output, Input, State
from SmartApi.smartConnect import SmartConnect

# Initialize credentials
api_key, username, pwd, token = wd.api_key, wd.username, wd.pwd, wd.token
candlestick_data_1min, candlestick_data_3min, candlestick_data_5min = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
latest_data = {}
session_active = True  # Flag to track session status
smart_api = None       # Global reference to the SmartConnect API
historical_data_downloaded = False  # Flag to track if historical data was downloaded

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

# Function to fetch historical candlestick data for different intervals
def fetch_candlestick_data(api, exchange, symbol_token, interval, data_store):
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=30)  # Fetch last 30 minutes of data

    try:
        response = api.getCandleData({
            "exchange": exchange,
            "symboltoken": symbol_token,
            "interval": interval,
            "fromdate": start_time.strftime("%Y-%m-%d %H:%M"),
            "todate": end_time.strftime("%Y-%m-%d %H:%M")
        })
        logger.debug(f"{interval} candle data response: {response}")

        candles = response.get("data", [])
        if candles:
            data = pd.DataFrame(candles, columns=["datetime", "open", "high", "low", "close", "volume"])
            data["datetime"] = pd.to_datetime(data["datetime"])
            data_store.clear()
            data_store.update(data)
    except Exception as e:
        logger.error(f"Error fetching {interval} candlestick data: {e}")

# Function to fetch the latest live market data
def fetch_live_data(api, exchange, symbol_token):
    global latest_data
    try:
        market_response = api.getMarketData("FULL", {exchange: [symbol_token]})
        latest_data = market_response.get("data", [{}])[0]
    except Exception as e:
        logger.error(f"Error fetching live market data: {e}")

# Background thread to periodically fetch data
def update_data_thread():
    global historical_data_downloaded
    api = generate_session()
    if api:
        exchange, symbol_token = "NSE", "3045"
        while session_active:
            fetch_candlestick_data(api, exchange, symbol_token, "ONE_MINUTE", candlestick_data_1min)
            fetch_candlestick_data(api, exchange, symbol_token, "THREE_MINUTE", candlestick_data_3min)
            fetch_candlestick_data(api, exchange, symbol_token, "FIVE_MINUTE", candlestick_data_5min)
            fetch_live_data(api, exchange, symbol_token)
            historical_data_downloaded = True
            time.sleep(10)

# Function to handle logout logic
def logout_session():
    global session_active
    try:
        current_time = datetime.now()
        if (current_time.hour == 15 and current_time.minute >= 25) or historical_data_downloaded:
            smart_api.terminateSession(username)
            logger.info("Logout successful.")
    except Exception as e:
        logger.exception(f"Logout failed: {e}")
    finally:
        session_active = False

# Start background thread
threading.Thread(target=update_data_thread, daemon=True).start()

# Initialize Dash app
app = Dash(__name__)
app.layout = html.Div([
    html.H1("Live Market Data Dashboard", style={"textAlign": "center"}),
    html.Div(id="live-data", style={"fontSize": 24, "marginBottom": 30, "textAlign": "center"}),
    html.Div([
        dcc.Graph(id="candlestick-chart-1min", style={"width": "33%", "display": "inline-block"}),
        dcc.Graph(id="candlestick-chart-3min", style={"width": "33%", "display": "inline-block"}),
        dcc.Graph(id="candlestick-chart-5min", style={"width": "33%", "display": "inline-block"})
    ]),
    html.Button("Logout", id="logout-btn", style={"marginTop": 20}),
    dcc.Interval(id="update-interval", interval=10 * 1000)  # Update every 10 seconds
])

# Combined callback to handle data updates and logout
@app.callback(
    [Output("live-data", "children"),
     Output("candlestick-chart-1min", "figure"),
     Output("candlestick-chart-3min", "figure"),
     Output("candlestick-chart-5min", "figure")],
    [Input("update-interval", "n_intervals"), Input("logout-btn", "n_clicks")]
)
def update_dashboard(n_intervals, logout_clicks):
    if logout_clicks:
        logout_session()
        return "You have been logged out. Session closed.", {"data": []}, {"data": []}, {"data": []}

    # Live data string
    live_data_str = f"Symbol: {latest_data.get('symbol', 'N/A')} | LTP: {latest_data.get('ltp', 'N/A')} | Timestamp: {latest_data.get('tradetime', 'N/A')}"

    # Function to create candlestick figure
    def create_figure(data, title):
        if not data.empty:
            return {
                "data": [{
                    "x": data["datetime"],
                    "open": data["open"],
                    "high": data["high"],
                    "low": data["low"],
                    "close": data["close"],
                    "type": "candlestick"
                }],
                "layout": {"title": title, "xaxis": {"rangeslider": {"visible": False}}, "yaxis": {"title": "Price"}}
            }
        return {"data": [], "layout": {"title": "No Data Available"}}

    # Create figures for each interval
    fig_1min = create_figure(candlestick_data_1min, "1-Minute Candlestick Chart")
    fig_3min = create_figure(candlestick_data_3min, "3-Minute Candlestick Chart")
    fig_5min = create_figure(candlestick_data_5min, "5-Minute Candlestick Chart")

    return live_data_str, fig_1min, fig_3min, fig_5min

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)
