import time
import threading
import pandas as pd
import pyotp
from datetime import datetime, timedelta
from logzero import logger
import tkinter as tk
from tkinter import ttk, messagebox
import mplfinance as mpf
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from SmartApi.smartConnect import SmartConnect
import credentials as wd
import json

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

class MarketDashboard:
    def __init__(self):
        # Initialize variables
        self.api_key = wd.api_key
        self.username = wd.username
        self.pwd = wd.pwd
        self.token = wd.Token
        self.smart_api = None
        self.session_active = True
        self.current_symbol_token = "3045"  # Default token
        
        # Load symbol data
        self.load_symbol_data()
        
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
        
    def load_symbol_data(self):
        try:
            self.symbol_df = pd.read_excel(wd.XLpath, sheet_name='NSE Token & Multiplier')
        except Exception as e:
            logger.error(f"Error loading symbol data: {e}")
            self.symbol_df = pd.DataFrame()

    def is_market_open(self):
        now = datetime.now().time()
        market_start = datetime.strptime("09:15:00", "%H:%M:%S").time()
        market_end = datetime.strptime("15:30:00", "%H:%M:%S").time()
        return market_start <= now <= market_end

    def update_market_status(self):
        if self.is_market_open():
            self.market_status_label.config(text="Market Status: OPEN", foreground="green")
        else:
            self.market_status_label.config(text="Market Status: CLOSED", foreground="red")
        self.root.after(1000, self.update_market_status)  # Update every second

    def setup_ui(self):
        # Create main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create symbol search frame
        search_frame = ttk.LabelFrame(main_container, text="Symbol Search")
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(search_frame, text="Enter Symbol:").pack(side=tk.LEFT, padx=5)
        self.symbol_entry = ttk.Entry(search_frame)
        self.symbol_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(search_frame, text="Search", command=self.search_symbol).pack(side=tk.LEFT, padx=5)
        self.search_result_label = ttk.Label(search_frame, text="")
        self.search_result_label.pack(side=tk.LEFT, padx=5)
        
        # Market status and data label frame
        status_frame = ttk.Frame(main_container)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.market_status_label = ttk.Label(status_frame, text="Market Status: --")
        self.market_status_label.pack(side=tk.LEFT, padx=5)
        
        self.live_data_label = ttk.Label(status_frame, text="Loading...", font=("Helvetica", 12))
        self.live_data_label.pack(side=tk.LEFT, padx=20)
        
        ttk.Button(status_frame, text="Logout", command=self.logout_session).pack(side=tk.RIGHT, padx=5)
        
        # Create scrollable frame for charts
        self.scrollable_frame = ScrollableFrame(main_container)
        self.scrollable_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create charts in the scrollable frame
        self.create_charts(self.scrollable_frame.scrollable_frame)
        
        # Start market status updates
        self.update_market_status()

    def search_symbol(self):
        symbol = self.symbol_entry.get().strip()
        if symbol:
            result = self.symbol_df[self.symbol_df['SymbolName'].str.upper() == symbol.upper()]
            if not result.empty:
                token = str(result['token'].values[0])
                multiplier = result['Multiplier'].values[0]
                exchange = result['Exchange'].values[0]
                self.search_result_label.config(
                    text=f"Token: {token} | Multiplier: {multiplier} | Exchange: {exchange}"
                )
                self.current_symbol_token = token
                self.fetch_data()  # Refresh data for new symbol
            else:
                messagebox.showinfo("No Result", f"No data found for symbol: {symbol}")
        else:
            messagebox.showinfo("Input Error", "Please enter a symbol to search.")

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
        
        # Create figures
        self.fig_1min, self.ax_1min = plt.subplots(figsize=(10, 4))
        self.fig_3min, self.ax_3min = plt.subplots(figsize=(10, 4))
        self.fig_5min, self.ax_5min = plt.subplots(figsize=(10, 4))
        
        # Create frames for each chart
        chart_frames = []
        for i in range(3):
            frame = ttk.LabelFrame(parent)
            frame.pack(fill=tk.X, pady=10, padx=5)
            chart_frames.append(frame)
        
        # Create and pack canvases
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
            return self.smart_api
        except Exception as e:
            logger.error(f"Error generating session: {e}")
            return None
            
    def fetch_data(self):
        if not self.smart_api or not self.is_market_open():
            return
            
        now = datetime.now()
        from_date = (now - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")
        to_date = now.strftime("%Y-%m-%d %H:%M")
        
        try:
            # Fetch data for different timeframes
            for interval, df_attr in [
                ("ONE_MINUTE", "candlestick_data"),
                ("THREE_MINUTE", "candlestick_data_3min"),
                ("FIVE_MINUTE", "candlestick_data_5min")
            ]:
                response = self.smart_api.getCandleData({
                    "exchange": "NSE",
                    "symboltoken": self.current_symbol_token,
                    "interval": interval,
                    "fromdate": from_date,
                    "todate": to_date
                })
                
                if response and "data" in response:
                    df = pd.DataFrame(
                        response["data"],
                        columns=["datetime", "open", "high", "low", "close", "volume"]
                    )
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    setattr(self, df_attr, df)
            
            # Fetch live market data
            market_data = self.smart_api.getMarketData(
                "FULL", 
                {"NSE": [self.current_symbol_token]}
            )
            if market_data and "data" in market_data:
                self.latest_data = market_data["data"][0]
                
                # Save LTP to JSON
                try:
                    with open('latest_price.json', 'w') as f:
                        json.dump({'ltp': self.latest_data.get('ltp', 'N/A')}, f)
                except Exception as e:
                    logger.error(f"Error saving LTP to JSON: {e}")
                
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            
    def update_charts(self):
        if not self.session_active:
            return
            
        try:
            # Update live data label with LTP from JSON
            try:
                with open('latest_price.json', 'r') as f:
                    ltp_data = json.load(f)
                    ltp = ltp_data.get('ltp', 'N/A')
            except:
                ltp = self.latest_data.get('ltp', 'N/A')
                
            live_data_str = (
                f"Symbol: {self.latest_data.get('symbol', 'N/A')} | "
                f"LTP: {ltp} | "
                f"Time: {self.latest_data.get('tradetime', 'N/A')}"
            )
            self.live_data_label.config(text=live_data_str)
            
            # Only update charts if market is open
            if self.is_market_open():
                for df, ax, canvas, title in [
                    (self.candlestick_data, self.ax_1min, self.canvas_1min, "1-Minute Chart"),
                    (self.candlestick_data_3min, self.ax_3min, self.canvas_3min, "3-Minute Chart"),
                    (self.candlestick_data_5min, self.ax_5min, self.canvas_5min, "5-Minute Chart")
                ]:
                    if not df.empty:
                        ax.clear()
                        ax.plot(df["datetime"], df["close"], label="Price", color="blue")
                        ax.set_title(title)
                        ax.set_xlabel("Time")
                        ax.set_ylabel("Price")
                        ax.legend()
                        ax.tick_params(axis='x', rotation=45)
                        canvas.draw()
                    
        except Exception as e:
            logger.error(f"Error updating charts: {e}")
            
        finally:
            # Schedule next update
            self.root.after(10000, self.update_charts)
            
    def data_thread(self):
        while self.session_active:
            if self.is_market_open():
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
                self.smart_api.terminateSession(self.username)
                logger.info("Session logged out successfully!")
            except Exception as e:
                logger.error(f"Error logging out: {e}")
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    dashboard = MarketDashboard()
    dashboard.run()