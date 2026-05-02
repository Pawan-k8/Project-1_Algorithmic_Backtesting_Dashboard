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
        self.current_symbol_token = None
        self.current_exchange = None
        
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
            font=("Helvetica", 12)
        )
        self.market_status_label.pack(side=tk.LEFT, padx=5)
        
        self.live_data_label = ttk.Label(
            header_frame,
            text="Loading...",
            font=("Helvetica", 12)
        )
        self.live_data_label.pack(side=tk.LEFT, padx=5)
        
        logout_button = ttk.Button(
            header_frame,
            text="Logout",
            command=self.logout_session
        )
        logout_button.pack(side=tk.RIGHT, padx=5)
        
        # Create scrollable frame for charts
        self.scrollable_frame = ScrollableFrame(main_container)
        self.scrollable_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create charts in the scrollable frame
        self.create_charts(self.scrollable_frame.scrollable_frame)
        
        # Start market status updates
        self.update_market_status()
        
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
                # Refresh data with new symbol
                self.fetch_data()
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
        self.fig_1min, self.ax_1min = plt.subplots(figsize=(10, 4))
        self.fig_3min, self.ax_3min = plt.subplots(figsize=(10, 4))
        self.fig_5min, self.ax_5min = plt.subplots(figsize=(10, 4))
        
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
            return self.smart_api
        except Exception as e:
            logger.error(f"Error generating session: {e}")
            return None
            
    def fetch_data(self):
        if not self.smart_api or not self.current_symbol_token or not self.is_market_open():
            return
            
        now = datetime.now()
        from_date = (now - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M")
        to_date = now.strftime("%Y-%m-%d %H:%M")
        
        try:
            # Fetch data for different timeframes
            for interval, df_attr in [
                ("ONE_MINUTE", "candlestick_data"),
                ("THREE_MINUTE", "candlestick_data_3min"),
                ("FIVE_MINUTE", "candlestick_data_5min")
            ]:
                response = self.smart_api.getCandleData({
                    "exchange": self.current_exchange,
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
            if self.current_symbol_token:
                market_data = self.smart_api.getMarketData(
                    "FULL",
                    {self.current_exchange: [self.current_symbol_token]}
                )
                if market_data and "data" in market_data:
                    self.latest_data = market_data["data"][0]
                    
                    # Save LTP to JSON
                    self.save_ltp_to_json()
                
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            
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
                    f"Symbol: {ltp_data.get('symbol', 'N/A')} | "
                    f"LTP: {ltp_data.get('ltp', 'N/A')} | "
                    f"Time: {ltp_data.get('timestamp', 'N/A')}"
                )
            else:
                live_data_str = "No trade data available"
            
            self.live_data_label.config(text=live_data_str)
            
            # Update charts
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