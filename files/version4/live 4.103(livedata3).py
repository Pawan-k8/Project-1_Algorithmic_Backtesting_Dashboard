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
        
        # Create header frame
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.market_status_label = ttk.Label(
            header_frame,
            text="Market Status: Checking...",
            font=("Helvetica", 10)
        )
        self.market_status_label.pack(side=tk.LEFT, padx=5)
        

        # Create button to load stocks
        self.load_stocks_button = ttk.Button(
            header_frame,
            text="Load All Stocks",
            command=self.load_all_stocks
        )
        self.load_stocks_button.pack(side=tk.LEFT, padx=10)
        
        logout_button = ttk.Button(
            header_frame,
            text="Logout",
            command=self.logout_session
        )
        logout_button.pack(side=tk.RIGHT, padx=5)
        

        # Create frame for the table
        table_frame = ttk.Frame(main_container)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Create treeview for the table
        self.stocks_table = ttk.Treeview(table_frame, columns=("symbol", "ltp","volume","prev_close", "timestamp"), show="headings")
        self.stocks_table.heading("symbol", text="Symbol")
        self.stocks_table.heading("ltp", text="LTP")
        self.stocks_table.heading("volume", text="Volume")
        #self.stocks_table.heading("his_vol", text="Historical Volume")
        self.stocks_table.heading("prev_close", text="Previous Close")
        self.stocks_table.heading("timestamp", text="Last Updated")
        
        self.stocks_table.column("symbol", width=150)
        self.stocks_table.column("ltp", width=100)
        self.stocks_table.column("volume", width=100)
        #self.stocks_table.column("his_vol", width=120)
        self.stocks_table.column("prev_close", width=100)
        self.stocks_table.column("timestamp", width=200)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.stocks_table.yview)
        self.stocks_table.configure(yscrollcommand=scrollbar.set)
        
        # Pack table and scrollbar
        self.stocks_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Start market status updates
        self.update_market_status()
        
        # Initialize the stocks data dictionary
        self.stocks_data = {}

    
    def load_all_stocks(self):
        try:
            # Load the symbols from the specified sheet
            df_symbols = pd.read_excel(wd.XLpath, sheet_name='Multiplier_5')
            
            if 'SymbolName' not in df_symbols.columns:
                messagebox.showerror("Error", "SymbolName column not found in the Excel sheet")
                return
            
            # Clear existing items in the table
            for item in self.stocks_table.get_children():
                self.stocks_table.delete(item)
            
            # Clear existing stocks data
            self.stocks_data = {}
            
            # Add each symbol to the table with initial "Loading..." values
            for index, row in df_symbols.iterrows():
                symbol = row['SymbolName']
                self.stocks_table.insert("", "end", values=(symbol, "Loading...", "Loading..."))
                
                # Store the token and exchange information
                if 'token' in row and 'Exchange' in row:
                    self.stocks_data[symbol] = {
                        'token': str(row['token']),
                        'exchange': row['Exchange'],
                        'ltp': "N/A",
                        'timestamp': "N/A"
                    }
                else:
                    messagebox.showwarning("Warning", f"Missing token or exchange information for {symbol}")
            
            # Start updating the LTP values
            self.start_ltp_updates()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load stocks: {str(e)}")
            logger.error(f"Error loading stocks: {e}")
    
    def start_ltp_updates(self):
        if not self.smart_api or not self.is_market_open():
            messagebox.showinfo("Info", "Cannot update LTP - market is closed or session is not active")
            return
        
        # Start a thread to update LTP values
        self.ltp_update_thread = threading.Thread(target=self.update_all_ltps, daemon=True)
        self.ltp_update_thread.start()
    
    def update_all_ltps(self):
        while self.session_active and self.is_market_open():
            # Get list of symbols to process this cycle
            symbols_to_process = list(self.stocks_data.keys())
            total_symbols = len(symbols_to_process)
            
            # Calculate delays to stay within rate limits
            # For 500/min limit, we'll aim for 450/min to be safe
            cycle_delay = 60 / 450 * total_symbols  # time in seconds for complete cycle
            request_delay = cycle_delay / total_symbols if total_symbols > 0 else 0.2
            
            logger.info(f"Starting update cycle for {total_symbols} symbols. Cycle delay: {cycle_delay:.2f}s, Request delay: {request_delay:.3f}s")
            
            cycle_start_time = time.time()
            requests_this_minute = 0
            
            for symbol in symbols_to_process:
                if not self.session_active or not self.is_market_open():
                    break
                    
                try:
                    data = self.stocks_data[symbol]
                    # Prepare the trading symbol
                    trading_symbol = f"{symbol}-EQ"
                    
                    # Check if we're approaching the rate limit
                    requests_this_minute += 1
                    if requests_this_minute >= 495:  # Buffer to avoid exceeding 500/min
                        time_elapsed = time.time() - cycle_start_time
                        if time_elapsed < 60:
                            sleep_time = 60 - time_elapsed
                            logger.warning(f"Approaching rate limit. Sleeping for {sleep_time:.2f}s")
                            time.sleep(sleep_time)
                        cycle_start_time = time.time()
                        requests_this_minute = 0
                    
                    # Make the LTP request
                    conn = http.client.HTTPSConnection("apiconnect.angelone.in")
                    payload = json.dumps({
                        "exchange": data['exchange'],
                        "tradingsymbol": trading_symbol,
                        "symboltoken": data['token']
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
                    print("API Response:", response["data"])  # Debugging print

                    # Update the data if successful
                    if response.get("data") and "ltp" in response["data"]:
                        ltp = response["data"]["ltp"]
                        volume = response["data"].get("volume", "N/A")  # Assuming API provides volume
                        prev_close = response["data"].get("close", "N/A") 
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        
                        # Update in our data dictionary
                        self.stocks_data[symbol]['ltp'] = ltp
                        self.stocks_data[symbol]['volume'] = volume
                        self.stocks_data[symbol]['prev_close'] = prev_close
                        self.stocks_data[symbol]['timestamp'] = timestamp
                        
                        # Update in the UI
                        self.update_table_row(symbol, ltp,volume, prev_close, timestamp)
                    elif response.get("message") and "rate limit" in response.get("message").lower():
                        logger.warning(f"Rate limit warning: {response.get('message')}")
                        time.sleep(1)  # Add extra delay when we get rate limit warnings
                
                except Exception as e:
                    logger.error(f"Error fetching LTP for {symbol}: {e}")
                
                # Controlled delay between requests
                time.sleep(request_delay)
            
            # Calculate how long the complete cycle took
            cycle_duration = time.time() - cycle_start_time
            
            
            
            # If we completed too quickly, add a delay before the next cycle
            if cycle_duration < cycle_delay:
                extra_delay = cycle_delay - cycle_duration
                logger.info(f"Completed cycle in {cycle_duration:.2f}s. Adding {extra_delay:.2f}s delay before next cycle.")
                time.sleep(extra_delay)
            else:
                logger.info(f"Completed cycle in {cycle_duration:.2f}s (longer than planned {cycle_delay:.2f}s)")    
    
    def update_table_row(self, symbol, ltp, volume, prev_close,timestamp):
        # This needs to run in the main thread
        self.root.after(0, self._update_table_row, symbol, ltp , volume, prev_close,timestamp)
        
    
    def _update_table_row(self, symbol, ltp, volume, prev_close, timestamp):
        for item in self.stocks_table.get_children():
            values = self.stocks_table.item(item, 'values')
            if values and values[0] == symbol:
                self.stocks_table.item(item, values=(symbol, ltp, volume ,prev_close ,timestamp))
                break

        
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
            self.update_market_status()
            
    def logout_session(self):
        self.session_active = False
        if self.smart_api:
            self.smart_api.terminateSession(self.username)
            self.smart_api = None
            logger.info("Logged out successfully!")

        self.root.destroy()
        
        
        if hasattr(self, "ltp_update_thread") and self.ltp_update_thread.is_alive():
            self.ltp_update_thread.join(timeout=2)  # Wait for the thread to stop
        
        messagebox.showinfo("Logout", "You have been logged out.")
        self.smart_api = None  # Clear API session
        
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    dashboard = MarketDashboard()
    dashboard.run()