import pyotp
import os
import sys
import time
from dash import Dash, dcc, html, callback, Output, Input, State
import plotly.graph_objs as go
import credentials as wd
from logzero import logger
from datetime import datetime
from SmartApi.smartConnect import SmartConnect

# Import SmartConnect API
root_directory = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.append(root_directory)

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

# Dash App Initialization
app = Dash(__name__)
app.title = "Live Market Data Dashboard"

# Global variable to store market and candlestick data
live_market_data = {}
candlestick_data = []

# Fetch Market Data
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
            logger.info("Fetched live market data.")
    except Exception as e:
        logger.error(f"Error fetching market data: {e}")

# Fetch Candle Data
def fetch_candle_data():
    global candlestick_data
    candleParams = {
        "exchange": "NSE",
        "symboltoken": "3045",
        "interval": "FIVE_MINUTE",
        "fromdate": "2023-10-18 09:15",
        "todate": "2023-10-18 15:30"
    }
    try:
        candledetails = smart_api.getCandleData(candleParams)
        candlestick_data = candledetails.get('data', [])
        logger.info("Fetched candlestick data.")
    except Exception as e:
        logger.error(f"Error fetching candlestick data: {e}")

# Initial Data Fetch
fetch_market_data()
fetch_candle_data()

# Layout for the Dashboard
app.layout = html.Div([
    html.H1("Live Market Data and Candlestick Dashboard", style={'textAlign': 'center'}),

    # Live Market Data Section
    html.Div([
        html.H2("Live Market Data"),
        html.Pre(id='live-market-data', style={'whiteSpace': 'pre-wrap', 'fontSize': '18px'})
    ]),

    # Candlestick Chart Section
    html.Div([
        html.H2("Candlestick Chart"),
        dcc.Graph(id='candlestick-chart')
    ]),

    # Interval Component to Refresh Data
    dcc.Interval(
        id='interval-component',
        interval=10 * 1000,  # Update every 10 seconds
        n_intervals=0
    ),

    # Logout Button
    html.Div([
        html.Button('Auto Logout', id='logout-button', n_clicks=0, style={'fontSize': '18px', 'marginTop': '20px'}),
        html.Div(id='logout-message', style={'color': 'red', 'fontSize': '16px', 'marginTop': '10px'})
    ], style={'textAlign': 'center', 'marginTop': '30px'})
])

# Callbacks to Update Data and Charts
@app.callback(
    Output('live-market-data', 'children'),
    Output('candlestick-chart', 'figure'),
    Input('interval-component', 'n_intervals')
)
def update_dashboard(n_intervals):
    fetch_market_data()
    fetch_candle_data()
    
    # Live Market Data Formatting
    if live_market_data:
        live_data_str = (
            f"Symbol: {live_market_data['symbol']}\n"
            f"Token: {live_market_data['token']}\n"
            f"LTP: {live_market_data['ltp']}\n"
            f"Date: {live_market_data['date']}\n"
            f"Time: {live_market_data['time']}"
        )
    else:
        live_data_str = "No live market data available."

    # Candlestick Chart Formatting
    if candlestick_data:
        df = {
            "datetime": [entry[0] for entry in candlestick_data],
            "open": [float(entry[1]) for entry in candlestick_data],
            "high": [float(entry[2]) for entry in candlestick_data],
            "low": [float(entry[3]) for entry in candlestick_data],
            "close": [float(entry[4]) for entry in candlestick_data]
        }

        figure = go.Figure(
            data=[
                go.Candlestick(
                    x=df["datetime"],
                    open=df["open"],
                    high=df["high"],
                    low=df["low"],
                    close=df["close"]
                )
            ]
        )
        figure.update_layout(
            title="Candlestick Chart",
            xaxis_title="Time",
            yaxis_title="Price",
            xaxis_rangeslider_visible=False
        )
    else:
        figure = go.Figure()
        figure.update_layout(title="No Data Available")

    return live_data_str, figure

# Callback for Auto Logout
@app.callback(
    Output('logout-message', 'children'),
    Input('logout-button', 'n_clicks')
)
def handle_logout(n_clicks):
    if n_clicks > 0:
        try:
            smart_api.terminateSession(wd.username)
            logger.info("Logged out successfully.")
            return "You have been logged out successfully. Please close the window."
        except Exception as e:
            logger.error(f"Error during logout: {e}")
            return "Error during logout. Please try again."

# Run the App
if __name__ == '__main__':
    app.run_server(debug=True)
