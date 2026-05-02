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

class TradeStrategy:
    def __init__(self):
        self.patterns = {
            "Hammer": self.detect_hammer,
            "Bullish Engulfing": self.detect_bullish_engulfing,
            "High Volume Breakout": self.detect_volume_breakout,
            "Golden Cross": self.detect_golden_cross,
            "RSI Oversold": self.detect_rsi_oversold
        }
        
    def detect_hammer(self, df):
        if len(df) < 1:
            return False
        
        row = df.iloc[-1]
        open_price = row['open']
        close_price = row['close']
        high = row['high']
        low = row['low']
        
        body_size = abs(close_price - open_price)
        total_range = high - low
        
        # Check if the body is small
        if body_size <= total_range * 0.3:
            # Check if lower shadow is at least 2x the body
            lower_shadow = min(open_price, close_price) - low
            if lower_shadow >= body_size * 2:
                # Check if upper shadow is small
                upper_shadow = high - max(open_price, close_price)
                if upper_shadow <= body_size:
                    return True
        
        return False
    
    def detect_bullish_engulfing(self, df):
        if len(df) < 2:
            return False
        
        prev_row = df.iloc[-2]
        curr_row = df.iloc[-1]
        
        # Previous candle should be bearish (close < open)
        if prev_row['close'] >= prev_row['open']:
            return False
        
        # Current candle should be bullish (close > open)
        if curr_row['close'] <= curr_row['open']:
            return False
        
        # Current candle should engulf previous candle
        if (curr_row['open'] > prev_row['close'] or 
            curr_row['close'] < prev_row['open']):
            return False
        
        return True
    
    def detect_volume_breakout(self, df):
        if len(df) < 5:
            return False
        
        # Check if current volume is significantly higher than average
        avg_volume = df.iloc[-5:-1]['volume'].mean()
        current_volume = df.iloc[-1]['volume']
        
        # Check if price is also increasing
        is_bullish = df.iloc[-1]['close'] > df.iloc[-1]['open']
        
        if current_volume > avg_volume * 2 and is_bullish:
            return True
        
        return False
    
    def detect_golden_cross(self, df):
        if len(df) < 50:  # Need enough data for 50-day MA
            return False
        
        # Calculate 20-day and 50-day moving averages
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        
        # Check if 20MA crosses above 50MA
        if (df['ma20'].iloc[-2] <= df['ma50'].iloc[-2] and 
            df['ma20'].iloc[-1] > df['ma50'].iloc[-1]):
            return True
        
        return False
    
    def detect_rsi_oversold(self, df):
        if len(df) < 15:
            return False
        
        # Calculate RSI (14 periods)
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Check if RSI is oversold (below 30) and starting to rise
        if rsi.iloc[-1] < 30 and rsi.iloc[-1] > rsi.iloc[-2]:
            return True
        
        return False

class StockScanner:
    def __init__(self):
        # Initialize variables
        self.api_key = wd.api_key
        self.username = wd.username
        self.pwd = wd.pwd
        self.token = wd.Token
        self.smart_api = None
        self.session_active = False
        self.last_scan_time = None
        self.scan_interval = 5  # minutes
        
        # Initialize strategy
        self.strategy = TradeStrategy()
        
        # Load symbol data
        self.df_symbols = pd.read_excel(wd.XLpath, sheet_name='Multiplier_5')
        
        # Setup main window
        self.root = tk.Tk()
        self.root.title("Stock Pattern Scanner")
        self.root.geometry("1200x800")
        
        self.setup_ui()
        self.generate_session()
        self.start_scanner_thread()
        
    def is_market_open(self):
        now = datetime.now()
        current_time = now.time()
        market_start = datetime.strptime("09:15:00", "%H:%M:%S").time()
        market_end = datetime.strptime("15:30:00", "%H:%M:%S").time()
        return market_start <= current_time <= market_end# and now.weekday() < 5
        
    def setup_ui(self):
        # Create main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Create header frame
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.market_status_label = ttk.Label(
            header_frame,
            text="Market Status: Checking...",
            font=("Helvetica", 10)
        )
        self.market_status_label.pack(side=tk.LEFT, padx=5)
        
        # Add start/stop scanner buttons
        self.start_button = ttk.Button(
            header_frame,
            text="Start Scanner",
            command=self.start_scanner
        )
        self.start_button.pack(side=tk.LEFT, padx=10)
        
        self.stop_button = ttk.Button(
            header_frame,
            text="Stop Scanner",
            command=self.stop_scanner,
            state=tk.DISABLED  # Disabled initially
        )
        self.stop_button.pack(side=tk.LEFT, padx=10)
        
        self.last_scan_label = ttk.Label(
            header_frame,
            text="Last Scan: Never",
            font=("Helvetica", 10)
        )
        self.last_scan_label.pack(side=tk.LEFT, padx=20)
        
        # Create scan button
        self.scan_button = ttk.Button(
            header_frame,
            text="Run Manual Scan",
            command=self.run_manual_scan
        )
        self.scan_button.pack(side=tk.LEFT, padx=10)
        
        # Create interval selection
        ttk.Label(header_frame, text="Scan Interval (min):").pack(side=tk.LEFT, padx=10)
        self.interval_var = tk.StringVar(value=str(self.scan_interval))
        interval_combo = ttk.Combobox(
            header_frame,
            textvariable=self.interval_var,
            values=["1", "3", "5", "10", "15", "30"],
            width=5
        )
        interval_combo.pack(side=tk.LEFT)
        interval_combo.bind("<<ComboboxSelected>>", self.update_scan_interval)
        
        # Create timeframe selection
        ttk.Label(header_frame, text="Timeframe:").pack(side=tk.LEFT, padx=10)
        self.timeframe_var = tk.StringVar(value="5min")
        timeframe_combo = ttk.Combobox(
            header_frame,
            textvariable=self.timeframe_var,
            values=["1min", "3min", "5min", "15min", "30min", "1hour"],
            width=5
        )
        timeframe_combo.pack(side=tk.LEFT)
        
        # Create logout button
        logout_button = ttk.Button(
            header_frame,
            text="Logout",
            command=self.logout_session
        )
        logout_button.pack(side=tk.RIGHT, padx=5)
        
        # Create pattern selection frame
        pattern_frame = ttk.LabelFrame(main_container, text="Select Patterns to Scan")
        pattern_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Create pattern checkboxes
        self.pattern_vars = {}
        for i, pattern in enumerate(self.strategy.patterns.keys()):
            var = tk.BooleanVar(value=True)
            self.pattern_vars[pattern] = var
            cb = ttk.Checkbutton(
                pattern_frame,
                text=pattern,
                variable=var
            )
            cb.grid(row=0, column=i, padx=10, pady=5, sticky="w")
        
        # Create frame for the results table
        table_frame = ttk.Frame(main_container)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create treeview for the results table
        self.results_table = ttk.Treeview(
            table_frame,
            columns=("symbol", "pattern", "price", "change", "volume", "timestamp"),
            show="headings"
        )
        self.results_table.heading("symbol", text="Symbol")
        self.results_table.heading("pattern", text="Pattern")
        self.results_table.heading("price", text="Current Price")
        self.results_table.heading("change", text="% Change")
        self.results_table.heading("volume", text="Volume")
        self.results_table.heading("timestamp", text="Detected At")
        
        self.results_table.column("symbol", width=100)
        self.results_table.column("pattern", width=150)
        self.results_table.column("price", width=100)
        self.results_table.column("change", width=100)
        self.results_table.column("volume", width=100)
        self.results_table.column("timestamp", width=150)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.results_table.yview)
        self.results_table.configure(yscrollcommand=scrollbar.set)
        
        # Pack table and scrollbar
        self.results_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Start market status updates
        self.update_market_status()
        
    
def start_scanner(self):
    if not self.session_active:
        self.session_active = True
        self.start_scanner_thread()
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        logger.info("Scanner started")

def stop_scanner(self):
    if self.session_active:
        self.session_active = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        logger.info("Scanner stopped")
        
    def update_market_status(self):
        is_open = self.is_market_open()
        status_text = "Market Status: OPEN" if is_open else "Market Status: CLOSED"
        status_color = "green" if is_open else "red"
        self.market_status_label.config(text=status_text, foreground=status_color)
        self.root.after(60000, self.update_market_status)  # Update every minute
    
    def update_scan_interval(self, event):
        try:
            self.scan_interval = int(self.interval_var.get())
            logger.info(f"Scan interval updated to {self.scan_interval} minutes")
        except ValueError:
            self.interval_var.set(str(self.scan_interval))
    
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
            try:
                # You might want to use an external service to get public IP
                self.public_ip = "127.0.0.1"  # Placeholder
            except:
                self.public_ip = "127.0.0.1"
                
            self.mac_address = ":".join(["{:02x}".format((platform.uname().node.encode())[i]) for i in range(6)])
            
            return True
        except Exception as e:
            logger.error(f"Error generating session: {e}")
            messagebox.showerror("Login Error", f"Failed to log in: {str(e)}")
            return False
    
    

    def fetch_candle_data(self, symbol, token, exchange, interval):
        try:
            # Check if we're about to exceed rate limits
            current_time = time.time()
            if hasattr(self, 'last_request_time') and hasattr(self, 'request_count'):
                time_diff = current_time - self.last_request_time
                
                # If we're within the same minute and approaching 500 requests
                if time_diff < 60 and self.request_count >= 500:
                    sleep_time = 60 - time_diff
                    logger.warning(f"Approaching rate limit. Sleeping for {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                    # Reset counter after sleeping
                    self.request_count = 0
                    self.last_request_time = time.time()
                
                # If we're making more than 10 requests per second
                elif time_diff < 1 and self.request_count % 10 == 0:
                    sleep_time = 1.0 - time_diff
                    if sleep_time > 0:
                        time.sleep(sleep_time)
            else:
                # Initialize request tracking
                self.last_request_time = current_time
                self.request_count = 0
            
            # Increment request counter
            self.request_count += 1
            
            # Convert timeframe to API format
            api_interval = {
                "1min": "ONE_MINUTE",
                "3min": "THREE_MINUTE",
                "5min": "FIVE_MINUTE",
                "15min": "FIFTEEN_MINUTE",
                "30min": "THIRTY_MINUTE",
                "1hour": "ONE_HOUR"
            }.get(interval, "FIVE_MINUTE")
            
            # Calculate from_date based on interval
            now = datetime.now()
            hours_lookup = {
                "1min": 1,
                "3min": 3,
                "5min": 8,
                "15min": 24,
                "30min": 48,
                "1hour": 72
            }
            hours = hours_lookup.get(interval, 8)
            from_date = (now - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
            to_date = now.strftime("%Y-%m-%d %H:%M")
            
            response = self.smart_api.getCandleData({
                "exchange": exchange,
                "symboltoken": token,
                "interval": api_interval,
                "fromdate": from_date,
                "todate": to_date
            })
            
            if response and "data" in response:
                df = pd.DataFrame(
                    response["data"],
                    columns=["datetime", "open", "high", "low", "close", "volume"]
                )
                df["datetime"] = pd.to_datetime(df["datetime"])
                return df  # Don't set index to keep it compatible with pattern functions
            else:
                logger.warning(f"No candle data received for {symbol}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"Error fetching candle data for {symbol}: {e}")
            return pd.DataFrame()
    

    def fetch_ltp(self, symbol, token, exchange):
        try:
            # Check rate limits
            current_time = time.time()
            time_diff = current_time - self.last_request_time
            
            # If we're within the same minute and approaching 500 requests
            if time_diff < 60 and self.request_count >= 490:
                sleep_time = 60 - time_diff
                logger.warning(f"Approaching rate limit. Sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
                # Reset counter after sleeping
                self.request_count = 0
                self.last_request_time = time.time()
            
            # If we're making more than 10 requests per second
            elif time_diff < 1 and self.request_count % 10 == 0:
                sleep_time = 1.0 - time_diff
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            # Increment request counter
            self.request_count += 1
            self.last_request_time = current_time
            
            trading_symbol = f"{symbol}-EQ"
            
            conn = http.client.HTTPSConnection("apiconnect.angelone.in")
            payload = json.dumps({
                "exchange": exchange,
                "tradingsymbol": trading_symbol,
                "symboltoken": token
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
            conn.request("POST", "/order-service/rest/secure/angelbroking/order/v1/getLtpData", payload, headers)
            res = conn.getresponse()
            data_response = res.read()
            response = json.loads(data_response.decode("utf-8"))
            
            # Check for rate limit in response
            if response.get("message") and "rate limit" in response.get("message").lower():
                logger.warning(f"Rate limit warning from API: {response.get('message')}")
                time.sleep(1)  # Add extra delay
                return None
            
            if response.get("data") and "ltp" in response["data"]:
                ltp = response["data"]["ltp"]
                close = response["data"].get("close", 0)
                volume = response["data"].get("volume", "N/A")
                
                # Calculate percentage change
                if close and close > 0:
                    change_pct = ((ltp - close) / close) * 100
                else:
                    change_pct = 0
                
                return {
                    "ltp": ltp,
                    "volume": volume,
                    "change_pct": round(change_pct, 2)
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error fetching LTP for {symbol}: {e}")
            return None    

    def scan_for_patterns(self):
        if not self.smart_api:
            messagebox.showinfo("Session Error", "No active session. Please restart the application.")
            return
        
        # Get selected patterns
        selected_patterns = [pattern for pattern, var in self.pattern_vars.items() if var.get()]
        if not selected_patterns:
            messagebox.showinfo("No Selection", "Please select at least one pattern to scan for.")
            return
        
        # Get selected timeframe
        timeframe = self.timeframe_var.get()
        
        # Update last scan time
        self.last_scan_time = datetime.now()
        self.last_scan_label.config(text=f"Last Scan: {self.last_scan_time.strftime('%H:%M:%S')}")
        
        # Clear previous results
        for i in self.results_table.get_children():
            self.results_table.delete(i)
        
        # Scan each symbol
        total_symbols = len(self.df_symbols)
        patterns_found = 0
        
        for index, row in self.df_symbols.iterrows():
            if not self.session_active:
                break
                
            try:
                symbol = row['SymbolName']
                token = str(row['token'])
                exchange = row['Exchange']
                
                # Update scan progress
                self.last_scan_label.config(text=f"Scanning: {index+1}/{total_symbols} - {symbol}")
                self.root.update_idletasks()
                
                # Fetch candle data
                df = self.fetch_candle_data(symbol, token, exchange, timeframe)
                if df.empty:
                    logger.warning(f"Empty dataframe for {symbol}, skipping")
                    continue
                
                # Debug log
                logger.info(f"Scanning {symbol} with {len(df)} candles")
                
                # Check each selected pattern
                for pattern in selected_patterns:
                    pattern_func = self.strategy.patterns[pattern]
                    try:
                        if pattern_func(df):
                            logger.info(f"Pattern {pattern} detected for {symbol}")
                            # Pattern detected, get current price and add to results
                            ltp_data = self.fetch_ltp(symbol, token, exchange)
                            if ltp_data:
                                self.results_table.insert(
                                    "",
                                    "end",
                                    values=(
                                        symbol,
                                        pattern,
                                        ltp_data["ltp"],
                                        f"{ltp_data['change_pct']}%",
                                        ltp_data["volume"],
                                        datetime.now().strftime("%H:%M:%S")
                                    )
                                )
                                patterns_found += 1
                    except Exception as pattern_err:
                        logger.error(f"Error checking pattern {pattern} for {symbol}: {pattern_err}")
                
                # Rate limiting - sleep to avoid hitting API limits
                time.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")
        
        # Update scan complete
        self.last_scan_label.config(text=f"Last Scan: {self.last_scan_time.strftime('%H:%M:%S')} (Complete)")
        
        # Show summary with actual count
        messagebox.showinfo("Scan Complete", f"Found {patterns_found} pattern matches across {total_symbols} symbols.")
    
    
    
    def run_manual_scan(self):
        if not self.is_market_open():
            response = messagebox.askyesno(
                "Market Closed",
                "The market is currently closed. Run the scan anyway?"
            )
            if not response:
                return
        
        # Run scan in a separate thread to keep UI responsive
        scan_thread = threading.Thread(target=self.scan_for_patterns)
        scan_thread.daemon = True
        scan_thread.start()
    
    def scanner_thread_func(self):
        while self.session_active:
            if self.is_market_open():
                current_time = datetime.now()
                
                # Check if it's time for a scan
                if (self.last_scan_time is None or
                    (current_time - self.last_scan_time).total_seconds() >= self.scan_interval * 60):
                    self.root.after(0, self.run_manual_scan)
            
            # Sleep for a minute before checking again
            time.sleep(60)
    
    def start_scanner_thread(self):
        self.scanner_thread = threading.Thread(
            target=self.scanner_thread_func,
            daemon=True
        )
        self.scanner_thread.start()
    
    def logout_session(self):
        self.session_active = False
        if self.smart_api:
            try:
                self.smart_api.terminateSession(self.username)
            except:
                pass
            self.smart_api = None
            logger.info("Logged out successfully!")
        
        self.root.destroy()
    
    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.logout_session)
        self.root.mainloop()

if __name__ == "__main__":
    scanner = StockScanner()
    scanner.run()