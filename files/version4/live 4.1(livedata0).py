import time
import threading
import pandas as pd
import pyotp
from datetime import datetime, timedelta
from logzero import logger
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.ttk import Label
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from SmartApi.smartConnect import SmartConnect
import credentials as wd
import http
import json
import socket
import platform

class ScrollableFrame(ttk.Frame):
    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.canvas = tk.Canvas(self)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind('<Enter>', self._bind_mouse_scroll)
        self.canvas.bind('<Leave>', self._unbind_mouse_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.bind('<Configure>', self._on_canvas_configure)

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
    
    def _bind_mouse_scroll(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mouse_scroll)
    
    def _unbind_mouse_scroll(self, event):
        self.canvas.unbind_all("<MouseWheel>")
    
    def _on_mouse_scroll(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

class TradeStratergy:
    def __init__(self):
        self.patterns= {
            "Hammer": self.detect_hammer,
        }
        
    def detect_hammer(self,row):
        open_price = row['open']
        close_price = row['close']
        high = row['high']
        low = row['low']
        return False

class MarketDashboard:
    def __init__(self):
        # Initialize variables
        self.api_key = wd.api_key
        self.username = wd.username
        self.pwd = wd.pwd
        self.token = wd.Token
        self.smart_api = None
        self.session_active = True
        self.current_symbol_token = None
        self.current_exchange = None
        self.last_ltp = "N/A"
        self.last_timestamp = "N/A"
        
        # Load symbol data
        self.df_symbols = pd.read_excel(wd.XLpath, sheet_name='NSE Token & Multiplier')
        
        # Initialize data frames
        self.candlestick_data = pd.DataFrame()
        self.candlestick_data_3min = pd.DataFrame()
        self.candlestick_data_5min = pd.DataFrame()
        self.latest_data = {}
        
        # Setup main window
        self.root = tk.Tk()
        self.root.title("Market Data Dashboard")
        self.root.geometry("1200x800")
        
        self.setup_ui()
        self.start_data_thread()
        
    def is_market_open(self):
        now = datetime.now()
        current_time = now.time()
        market_start = datetime.strptime("09:15:00", "%H:%M:%S").time()
        market_end = datetime.strptime("15:30:00", "%H:%M:%S").time()
        return market_start <= current_time <= market_end
        
    def setup_ui(self):
        # Create main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create search frame
        search_frame = ttk.LabelFrame(main_container, text="Symbol Search")
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(search_frame, text="Enter Symbol:").pack(side=tk.LEFT, padx=5)
        self.entry_symbol = ttk.Entry(search_frame, width=20)
        self.entry_symbol.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(search_frame, text="Search", command=self.search_symbol).pack(side=tk.LEFT, padx=5)
        self.label_symbol_info = ttk.Label(search_frame, text="")
        self.label_symbol_info.pack(side=tk.LEFT, padx=5)
        
        # Create header frame
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.market_status_label = ttk.Label(
            header_frame,
            text="Market Status: Checking...",
            font=("Helvetica", 10)
        )
        self.market_status_label.pack(side=tk.LEFT, padx=5)
        
        #setup live data label in the header frame
        self.live_data_label = ttk.Label(
            header_frame,
            text= "LTP: Loading... | Time: Loading...",
            font=("Helvetica",10)
        )
        self.live_data_label.pack(side=tk.LEFT, padx=5)
        self.update_ltp_label()
        
        logout_button = ttk.Button(
            header_frame,
            text="Logout",
            command=self.logout_session
        )
        logout_button.pack(side=tk.RIGHT, padx=5)
        
        # Create scrollable frame for 
        self.scrollable_frame = ScrollableFrame(main_container)
        self.scrollable_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create in the scrollable frame
        self.create_charts(self.scrollable_frame.scrollable_frame)
        
        # Start market status updates
        self.update_market_status()
        self.update_ltp_label()
        
    def search_symbol(self):
        symbol = self.entry_symbol.get().strip().upper()
        if symbol:
            result = self.df_symbols[self.df_symbols['SymbolName'].str.upper() == symbol]
            if not result.empty:
                self.current_symbol_token = str(result['token'].values[0])
                self.current_exchange = result['Exchange'].values[0]
                multiplier = result['Multiplier'].values[0]
                self.label_symbol_info.config(
                    text=f"Token: {self.current_symbol_token} | "
                    f"Multiplier: {multiplier} | "
                    f"Exchange: {self.current_exchange}"
                )
                self.tradingsymbol= f"{symbol}-EQ"
                # Refresh data with new symbol
                self.fetch_LTP_data()
            else:
                messagebox.showinfo("No Result", f"No data found for symbol: {symbol}")
        else:
            messagebox.showinfo("Input Error", "Please enter a symbol to search.")

    def update_market_status(self):
        is_open = self.is_market_open()
        status_text = "Market Status: OPEN" if is_open else "Market Status: CLOSED"
        status_color = "green" if is_open else "red"
        self.market_status_label.config(text=status_text, foreground=status_color)
        self.root.after(1000, self.update_market_status)  # Update every second
    
    def fetch_LTP_data(self):
        if not self.smart_api or not self.current_symbol_token or not self.is_market_open():
            return
        self.fetch_ltp()
        
    def fetch_ltp(self):
        try:
            conn = http.client.HTTPSConnection("apiconnect.angelone.in")
            payload= json.dumps({
                "exchange":"NSE",
                "tradingsymbol":self.tradingsymbol,
                "symboltoken":self.current_symbol_token
            })
            headers = {
                'Authorization': f'{self.authToken}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': self.local_ip,
                'X-ClientPublicIP': self.public_ip,
                'X-MACAddress': self.mac_address,
                'X-PrivateKey': self.api_key
            }
            conn.request("POST","/order-service/rest/secure/angelbroking/order/v1/getLtpData",payload ,headers)
            res = conn.getresponse()
            data = res.read()
            response = json.loads(data.decode("utf-8"))                    

            if response.get("data") and "ltp" in response["data"]:
                ltp = response["data"]["ltp"]
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.last_ltp = ltp
                self.last_timestamp = timestamp
                self.live_data_label.config(text=f"LTP:{ltp} |Time: {timestamp}")
                #self.live_data_label.config(text=f"Time: {timestamp}")
            else:
                self.live_data_label.config(text= f"LTP: {self.last_ltp} | Time:{self.last_timestamp}")
        except Exception as e:
            logger.error(f"Error fetching LTP: {e}")
            self.live_data_label.config(text= f"LTP: {self.last_ltp} | Time:{self.last_timestamp}")
        
    def update_ltp_label(self):
        #ltp, timestamp = self.fetch_ltp()
        #live_data_str = f"LTP: {ltp}| Time: {timestamp}"
        #self.live_data_label.config(text= live_data_str)
        try:
            self.fetch_ltp()
        except Exception as e:
            logger.error(f"Error in update_ltp_label:{e}")
            self.live_data_label.config(text="LTP:Error | Time:Error")
        finally:
            self.root.after(2500,self.update_ltp_label)
        
    def start_ltp_upate(self):
        self.update_ltp_label()

    def create_charts(self, parent):
        # Create control panel
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, pady=5)
        
        refresh_button = ttk.Button(
            control_frame,
            text="Refresh Data",
            command=self.fetch_data
        )
        refresh_button.pack(side=tk.LEFT, padx=5)
        
        # Create figures with specific sizes
        self.fig_1min, self.ax_1min = plt.subplots(figsize=(10, 5))
        self.fig_3min, self.ax_3min = plt.subplots(figsize=(10, 5))
        self.fig_5min, self.ax_5min = plt.subplots(figsize=(10, 5))
        
        # Create frames for each chart section
        chart_frames = []
        for i in range(3):
            frame = ttk.LabelFrame(parent)
            frame.pack(fill=tk.X, pady=10, padx=5)
            chart_frames.append(frame)
        
        # Create and pack canvases into frames
        self.canvas_1min = FigureCanvasTkAgg(self.fig_1min, chart_frames[0])
        self.canvas_1min.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        self.canvas_3min = FigureCanvasTkAgg(self.fig_3min, chart_frames[1])
        self.canvas_3min.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        self.canvas_5min = FigureCanvasTkAgg(self.fig_5min, chart_frames[2])
        self.canvas_5min.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
    def generate_session(self):
        try:
            totp = pyotp.TOTP(self.token).now()
            self.smart_api = SmartConnect(self.api_key)
            data = self.smart_api.generateSession(self.username, self.pwd, totp)
            logger.info("Session generated successfully!")
            self.authToken = data['data']['jwtToken']
            self.refreshToken = data['data']['refreshToken']
            
            # Get local IP, public IP, and MAC address
            self.local_ip = socket.gethostbyname(socket.gethostname())  # Local IP
            self.public_ip = "your_public_ip"  # Replace with actual public IP
            self.mac_address = ":".join(["{:02x}".format((platform.uname().node.encode())[i]) for i in range(6)])

            return self.smart_api
        except Exception as e:
            logger.error(f"Error generating session: {e}")
            return None
        
        
    def fetch_data(self):
        if not self.smart_api or not self.current_symbol_token or not self.is_market_open():
            return
    
        now = datetime.now()
    
        # Define intervals and their respective timeframes
        intervals = [
            {"interval": "ONE_MINUTE", "df_attr": "candlestick_data", "hours": 0.8},
            {"interval": "THREE_MINUTE", "df_attr": "candlestick_data_3min", "hours": 3},
            {"interval": "FIVE_MINUTE", "df_attr": "candlestick_data_5min", "hours": 8},
        ]
    
        try:
            for interval in intervals:
                from_date = (now - timedelta(hours=interval["hours"])).strftime("%Y-%m-%d %H:%M")
                to_date = now.strftime("%Y-%m-%d %H:%M")
    
                response = self.smart_api.getCandleData({
                    "exchange": self.current_exchange,
                    "symboltoken": self.current_symbol_token,
                    "interval": interval["interval"],
                    "fromdate": from_date,
                    "todate": to_date
                })
    
                if response and "data" in response:
                    df = pd.DataFrame(
                        response["data"],
                        columns=["datetime", "open", "high", "low", "close", "volume"]
                    )
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    setattr(self, interval["df_attr"], df)
    
            # Fetch live market data
            if self.current_symbol_token:
                market_data = self.smart_api.getMarketData(
                    "FULL",
                    {self.current_exchange: [self.current_symbol_token]}
                )
                if market_data and "data" in market_data:
                    self.latest_data = market_data["data"][0]
                    
                    # Save LTP to JSON
                    self.save_ltp_to_json()
                    
                    #return LTP and timestamp data
                    return self.latest_data.get('ltp','N/A'), self.latest_data.get('timestamp','N/A')
                else:
                    return "LTP not available" , "N/A"
    
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return "Error", "N/A"

                
    def save_ltp_to_json(self):
        try:
            ltp_data = {
                'symbol': self.latest_data.get('symbol', 'N/A'),
                'ltp': self.latest_data.get('ltp', 'N/A'),
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open('last_trade.json', 'w') as f:
                json.dump(ltp_data, f)
        except Exception as e:
            logger.error(f"Error saving LTP to JSON: {e}")

    def load_ltp_from_json(self):
        try:
            with open('last_trade.json', 'r') as f:
                return json.load(f)
        except:
            return None
            
    def update_charts(self):
        if not self.session_active:
            return
    
        try:
            # Load last trade price from JSON
            ltp_data = self.load_ltp_from_json()
    
            # Update live data label
            if ltp_data:
                live_data_str = (
                    f"LTP: {ltp_data.get('ltp', 'N/A')} | "
                    f"Time: {ltp_data.get('timestamp', 'N/A')}"
                )
            else:
                live_data_str = "LTP: N/A | Time: N/A"
    
            self.live_data_label.config(text=live_data_str)
    
            # Update charts with candlestick plots
            for df, canvas, title, is_one_min in [
                (self.candlestick_data, self.canvas_1min, "1-Minute Chart", True),
                (self.candlestick_data_3min, self.canvas_3min, "3-Minute Chart", False),
                (self.candlestick_data_5min, self.canvas_5min, "5-Minute Chart", False),
            ]:
                if not df.empty:
                    # Format the DataFrame for mplfinance
                    df_mpf = df.set_index("datetime")[["open", "high", "low", "close", "volume"]]
                    
                    # Create a new figure
                    fig = plt.figure(figsize=(10, 5))
                    
                    # Define grid layout for candle and volume plots
                    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.1)
                    
                    # Create axes for candlestick and volume
                    ax_candle = fig.add_subplot(gs[0])
                    ax_volume = fig.add_subplot(gs[1], sharex=ax_candle)
                    
                    # Define visual style
                    candle_style = mpf.make_mpf_style(
                        marketcolors=mpf.make_marketcolors(
                            up='#26a69a', down='#ef5350',
                            wick='inherit', edge='inherit',
                            volume={'up': '#26a69a', 'down': '#ef5350'}
                        ),
                        gridstyle='--',
                        gridcolor='#e0e0e0',
                        rc={'axes.edgecolor': '#c0c0c0'}
                    )
                    
                    # Additional formatting for 1-minute chart
                    if is_one_min:
                        # More data points in 1-min chart, adjust date formatting
                        date_format = '%H:%M'
                        # For higher resolution, we'll use more locators
                        ax_candle.xaxis.set_major_locator(plt.MaxNLocator(10))
                    else:
                        date_format = '%H:%M'
                        ax_candle.xaxis.set_major_locator(plt.MaxNLocator(8))
                    
                    # Plot the candlestick chart
                    mpf.plot(
                        df_mpf,
                        type='candle',
                        style=candle_style,
                        ax=ax_candle,
                        volume=ax_volume,
                        show_nontrading=False,
                        datetime_format=date_format,
                        axtitle=title
                    )
                    
                    # Format x-axis to show datetime at bottom
                    plt.setp(ax_candle.get_xticklabels(), visible=False)  # Hide x-tick labels for candlestick chart
                    plt.setp(ax_volume.get_xticklabels(), rotation=45, ha='right')  # Rotate datetime labels on volume chart
                    
                    # Enhance gridlines and labels
                    ax_candle.grid(True, alpha=0.3)
                    ax_volume.grid(True, alpha=0.3, axis='x')
                    
                    # Set tight layout
                    fig.tight_layout()
                    
                    # Embed the updated figure in the canvas
                    canvas.figure = fig
                    canvas.draw()
    
        except Exception as e:
            logger.error(f"Error updating charts: {e}")
    
        finally:
            # Schedule next update
            self.root.after(1000, self.update_charts)
            
    def data_thread(self):
        while self.session_active and self.is_market_open():
            self.fetch_data()
            time.sleep(10)
            
    def start_data_thread(self):
        if self.generate_session():
            self.data_thread = threading.Thread(
                target=self.data_thread,
                daemon=True
            )
            self.data_thread.start()
            self.update_charts()
            
    def logout_session(self):
        self.session_active = False
        if self.smart_api:
            try:
                logout = self.smart_api.terminateSession(wd.username)
                logger.info("Logout Successful")
            except Exception as e:
                logger.exception(f"Logout failed: {e}")
        else:
            logger.warning("No active session to logout.")
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    dashboard = MarketDashboard()
    dashboard.run()