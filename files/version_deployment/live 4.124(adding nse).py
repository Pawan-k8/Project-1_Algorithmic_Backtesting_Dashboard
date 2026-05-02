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
import pyperclip
import telegram
from matplotlib.figure import Figure
import asyncio
import nest_asyncio
nest_asyncio.apply()

from trading_strategies import TradeStrategy  # Import the TradeStrategy class

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
        self.scan_interval = 1.5  # minutes
        
        # Flag to track if a scan is currently running
        self.scan_in_progress = False
        self.scan_lock = threading.Lock()  # Lock for thread safety
        
        # Initialize strategy
        self.strategy = TradeStrategy()
        self.strategy.set_max_price(250)  # Change to any value you want
        self.available_patterns = self.strategy.get_patterns()
        
        # Load symbol data
        self.df_symbols = pd.read_excel(wd.XLpath, sheet_name='Multiplier_5')
        
        # Setup main window
        self.root = tk.Tk()
        self.root.title("Stock Pattern Scanner")
        self.root.geometry("1200x800")
        
        self.setup_ui()
        self.generate_session()
    
    def is_market_open(self):
        now = datetime.now()
        current_time = now.time()
        market_start = datetime.strptime("00:00:00", "%H:%M:%S").time()
        market_end = datetime.strptime("20:30:00", "%H:%M:%S").time()
        return market_start <= current_time <= market_end # and now.weekday() < 5
        
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
        
        # Add clear fields button
        self.clear_button = ttk.Button(
            header_frame,
            text="Clear Fields",
            command=self.clear_fields
        )
        self.clear_button.pack(side=tk.LEFT, padx=10)
        
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
        pattern_frame = ttk.LabelFrame(main_container, text="Select Patterns to Scan",height=150)
        pattern_frame.pack(fill=tk.X, padx=10, pady=5)
        pattern_frame.pack_propagate(False)  # This prevents the frame from expanding
        
        # Create pattern selection dropdown and select all button
        pattern_dropdown_frame = ttk.Frame(pattern_frame)
        pattern_dropdown_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(pattern_dropdown_frame, text="Select Strategy:").pack(side=tk.LEFT, padx=5)
        self.strategy_var = tk.StringVar(value="All Patterns")
        strategy_dropdown = ttk.Combobox(
            pattern_dropdown_frame,
            textvariable=self.strategy_var,
            values=["All Patterns"] + self.available_patterns,
            width=20
        )
        strategy_dropdown.pack(side=tk.LEFT, padx=5)
        strategy_dropdown.bind("<<ComboboxSelected>>", self.update_strategy_selection)
        
        self.select_all_var = tk.BooleanVar(value=True)
        select_all_cb = ttk.Checkbutton(
            pattern_dropdown_frame,
            text="Select All",
            variable=self.select_all_var,
            command=self.toggle_all_patterns
        )
        select_all_cb.pack(side=tk.LEFT, padx=15)
        
        # Create scrollable frame for pattern checkboxes
        self.pattern_scroll_frame = ScrollableFrame(pattern_frame)
        self.pattern_scroll_frame.pack(fill=tk.X, padx=5, pady=5, expand=True)
        
        # Create pattern checkboxes
        self.pattern_vars = {}
        self.pattern_checkbuttons = {}
        self.create_pattern_checkboxes()
        
                # Create market status box
        market_status_frame = ttk.Frame(main_container)
        market_status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Market direction label and entry
        self.market_direction_var = tk.StringVar(value="Market Direction: Calculating...")
        self.market_direction_entry = ttk.Entry(
            market_status_frame, 
            textvariable=self.market_direction_var,
            state='readonly',
            width=80
        )
        self.market_direction_entry.pack(side=tk.LEFT, padx=5)
        
        # Start market direction updates
        self.update_market_direction()
        
        # Create frame for the results table
        table_frame = ttk.Frame(main_container)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create treeview for the results table with updated columns
        self.results_table = ttk.Treeview(
            table_frame,
            columns=("symbol", "ltp", "volume", "vol_ratio" , "pattern", "trend" , "timestamp"),
            show="headings"
        )
        self.results_table.heading("symbol", text="Symbol")
        self.results_table.heading("ltp", text="LTP")
        self.results_table.heading("volume", text="Volume")
        self.results_table.heading("vol_ratio", text="Vol Ratio")
        self.results_table.heading("pattern", text="Pattern")
        self.results_table.heading("trend", text="Trend")
        self.results_table.heading("timestamp", text="Detected At")
        
        # Configure column widths
        self.results_table.column("symbol", width=100)
        self.results_table.column("ltp", width=100)
        self.results_table.column("volume", width=100)
        self.results_table.column("vol_ratio", width=100)
        self.results_table.column("pattern", width=150)
        self.results_table.column("trend", width=100)
        self.results_table.column("timestamp", width=150)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.results_table.yview)
        self.results_table.configure(yscrollcommand=scrollbar.set)
        
        # Pack table and scrollbar
        self.results_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Start market status updates
        self.update_market_status()
        self.clear_fields()
        
    def update_market_direction(self):
        try:
            # Fetch Nifty data
            nifty_ltp = self.fetch_ltp("NIFTY", "26000", "NSE")
            if nifty_ltp:
                current_price = nifty_ltp["ltp"]
                
                # Store the previous price if not already stored
                if not hasattr(self, 'previous_nifty_price'):
                    self.previous_nifty_price = current_price
                    self.market_direction_var.set("Market Direction: Calculating...")
                else:
                    # Calculate direction
                    direction = "🟢 UP" if current_price > self.previous_nifty_price else "🔴 DOWN"
                    change = abs(current_price - self.previous_nifty_price)
                    change_percent = (change / self.previous_nifty_price) * 100
                    
                    self.market_direction_var.set(
                        f"Market Direction: {direction} | "
                        f"Current: {current_price:.2f} | "
                        f"Change: {change:.2f} ({change_percent:.2f}%)"
                    )
                    
                    # Update previous price
                    self.previous_nifty_price = current_price
                    
        except Exception as e:
            logger.error(f"Error updating market direction: {e}")
            self.market_direction_var.set("Market Direction: Error updating")
        
        # Update every 60 seconds if market is open
        if self.is_market_open():
            self.root.after(60000, self.update_market_direction)
        else:
            self.market_direction_var.set("Market Direction: Market Closed")
            self.root.after(300000, self.update_market_direction)  # Check every 5 minutes when closed
    
    def create_pattern_checkboxes(self):
        # Clear existing checkboxes
        for widget in self.pattern_scroll_frame.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Create pattern checkboxes
        self.pattern_vars = {}
        self.pattern_checkbuttons = {}
        
        for i, pattern in enumerate(self.available_patterns):
            var = tk.BooleanVar(value=self.select_all_var.get())
            self.pattern_vars[pattern] = var
            cb = ttk.Checkbutton(
                self.pattern_scroll_frame.scrollable_frame,
                text=pattern,
                variable=var
            )
            cb.grid(row=i//4, column=i%4, padx=5, pady=2, sticky="w")
            self.pattern_checkbuttons[pattern] = cb
    
    def update_strategy_selection(self, event):
        selected_strategy = self.strategy_var.get()
        
        if selected_strategy == "All Patterns":
            # Enable all checkboxes
            for pattern, cb in self.pattern_checkbuttons.items():
                cb.configure(state=tk.NORMAL)
        else:
            # Disable all checkboxes except the selected one
            for pattern, cb in self.pattern_checkbuttons.items():
                if pattern == selected_strategy:
                    cb.configure(state=tk.NORMAL)
                    self.pattern_vars[pattern].set(True)
                else:
                    cb.configure(state=tk.DISABLED)
                    self.pattern_vars[pattern].set(False)
    
    def toggle_all_patterns(self):
        if self.strategy_var.get() != "All Patterns":
            return
        
        select_all = self.select_all_var.get()
        for pattern, var in self.pattern_vars.items():
            var.set(select_all)
    
    def start_scanner(self):
        if not self.session_active:
            self.session_active = True
            # Create and start a new scanner thread
            self.scanner_thread = threading.Thread(
                target=self.scanner_thread_func,
                daemon=True
            )
            self.scanner_thread.start()
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            logger.info("Scanner started")
            # Immediate first scan
            self.run_manual_scan()
    
    def stop_scanner(self):
        if self.session_active:
            self.session_active = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            logger.info("Scanner stopped")
            
    def clear_fields(self):
        self.strategy_var.set("All Patterns")
        self.select_all_var.set(True)
        self.toggle_all_patterns()
        self.interval_var.set(str(self.scan_interval))
        self.timeframe_var.set("1min")
        #Clear the results table
        for item in self.results_table.get_children():
            self.results_table.delete(item)

        # Reset last scan label
        self.last_scan_label.config(text="Last Scan: Never")
        
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
                elif time_diff < 1 and self.request_count % 8 == 0:
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
            
            # Calculate from_date based on interval - only looking at minimal required data
            # We'll get just enough candles for pattern detection (most patterns need 2-3 candles)
            now = datetime.now()
            candles_needed = 5  # Minimum number of candles needed for most basic patterns
            
            # Calculate time delta based on interval
            if interval == "1min":
                from_date = (now - timedelta(minutes=candles_needed)).strftime("%Y-%m-%d %H:%M")
            elif interval == "3min":
                from_date = (now - timedelta(minutes=3 * candles_needed)).strftime("%Y-%m-%d %H:%M")
            elif interval == "5min":
                from_date = (now - timedelta(minutes=5 * candles_needed)).strftime("%Y-%m-%d %H:%M")
            elif interval == "15min":
                from_date = (now - timedelta(minutes=15 * candles_needed)).strftime("%Y-%m-%d %H:%M")
            elif interval == "30min":
                from_date = (now - timedelta(minutes=30 * candles_needed)).strftime("%Y-%m-%d %H:%M")
            else:  # 1hour
                from_date = (now - timedelta(hours=candles_needed)).strftime("%Y-%m-%d %H:%M")
                
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
                
                # Calculate volume ratio
                df['vol_ratio'] = df['volume'] / df['volume'].shift(1)
                df['vol_ratio'] = df['vol_ratio'].fillna(1)  # Fill first row with 1
                df['vol_ratio'] = df['vol_ratio'].round(2)  # Round to 2 decimal places
                
                # Calculate trend based on closing prices
                df['trend'] = 'Neutral'  # Default value
                df.loc[df['close'] > df['close'].shift(1), 'trend'] = 'Uptrend'
                df.loc[df['close'] < df['close'].shift(1), 'trend'] = 'Downtrend'
                
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
            if time_diff < 60 and self.request_count == 490:
                sleep_time = 60 - time_diff
                logger.warning(f"Approaching rate limit. Sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
                # Reset counter after sleeping
                self.request_count = 0
                self.last_request_time = time.time()
            
            # If we're making more than 10 requests per second
            elif time_diff < 1 and self.request_count % 8 == 0:
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
                volume = response["data"].get("volume", "N/A")
                
                return {
                    "ltp": ltp,
                    "volume": volume
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error fetching LTP for {symbol}: {e}")
            return None    
        
    def scan_for_patterns(self):
        # Use the lock to ensure we don't have overlapping scans
        if not self.scan_lock.acquire(blocking=False):
            logger.warning("Scan already in progress, skipping this request")
            return
        
        try:
            # Set the scan_in_progress flag
            self.scan_in_progress = True
            
            # Update UI to show scan is in progress
            self.scan_button.config(state=tk.DISABLED)
            
            if not self.smart_api:
                messagebox.showinfo("Session Error", "No active session. Please restart the application.")
                return
            
            # Get selected strategy
            selected_strategy = self.strategy_var.get()
            
            if selected_strategy == "All Patterns":
                # Get selected patterns
                selected_patterns = [pattern for pattern, var in self.pattern_vars.items() if var.get()]
                if not selected_patterns:
                    messagebox.showinfo("No Selection", "Please select at least one pattern to scan for.")
                    return
            else:
                # Use only the selected strategy
                selected_patterns = [selected_strategy]
            
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
                    
                    # Fetch minimal required candle data
                    df = self.fetch_candle_data(symbol, token, exchange, timeframe)
                    if df.empty:
                        logger.warning(f"Empty dataframe for {symbol}, skipping")
                        continue
                    
                    # Debug log
                    logger.info(f"Scanning {symbol} with {len(df)} candles")
                    
                    # Get the latest volume from candle data
                    latest_volume = int(df.iloc[-1]['volume']) if not df.empty else 0
                    
                    # Check each selected pattern
                    for pattern in selected_patterns:
                        pattern_func = self.strategy.patterns[pattern]
                        try:
                            # Check if pattern detected
                            if pattern_func(df):
                                logger.info(f"Pattern {pattern} detected for {symbol}")
                                
                                # Pattern detected, get current price and add to results
                                ltp_data = self.fetch_ltp(symbol, token, exchange)
                                if ltp_data:
                                    latest_trend = df['trend'].iloc[-1] if not df.empty else 'Unknown'
                                    latest_vol_ratio = df['vol_ratio'].iloc[-1] if not df.empty else 1.0
                                    # Always add the detected pattern to the table
                                    self.results_table.insert(
                                        "",
                                        "end",
                                        values=(
                                            symbol,
                                            ltp_data["ltp"],
                                            latest_volume,# Use volume from candle data
                                            latest_vol_ratio,
                                            pattern,
                                            latest_trend,
                                            datetime.now().strftime("%H:%M:%S")
                                        )
                                    )
                                    # Update UI immediately to show new results
                                    self.root.update_idletasks()
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
            # Log the summary instead of showing popup
            logger.info(f"Scan Complete: Found {patterns_found} pattern matches across {total_symbols} symbols.")
        
        finally:
            # Re-enable the scan button
            self.scan_button.config(state=tk.NORMAL)
            # Reset the scan in progress flag
            self.scan_in_progress = False
            # Release the lock
            self.scan_lock.release()
            
    def run_manual_scan(self):
        # Check if scan is already in progress
        if self.scan_in_progress:
            messagebox.showinfo("Scan in Progress", "A scan is already running. Please wait for it to complete.")
            return
        
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
            try:
                if self.is_market_open():
                    current_time = datetime.now()
                    
                    # Check if a scan is already in progress
                    if not self.scan_in_progress:
                        # Check if it's time for a scan
                        if (self.last_scan_time is None or
                            (current_time - self.last_scan_time).total_seconds() >= self.scan_interval * 60):
                            self.root.after(0, self.run_manual_scan)
                
                # Sleep for a minute before checking again
                time.sleep(60)
            except Exception as e:
                logger.error(f"Error in scanner thread: {e}")
                time.sleep(60)  # Keep running even if there's an error
    
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
