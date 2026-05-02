import pandas as pd
import socket
import platform
import threading
from datetime import datetime
import http.client
import json
import tkinter as tk
from tkinter import ttk, messagebox
from SmartApi import SmartConnect
import pyotp
import time
from logzero import logger
import credentials as wd

# Constants
SAFE_PERCENT = 0.04
TAX_RATE = 0.008
PROFIT_PERCENT = 0.13
LOSS_PERCENT = 0.045

# Global variables
authToken = None
XT = 0
tradingsymbol = None
symbol_token = None
ltp_value = 0
PRICE_MULTIPLIER = 0
products_buyable = 0

# Load Excel data
XLpath = wd.XLpath
df = pd.read_excel(XLpath, sheet_name='NSE Token & Multiplier')

# Setup API credentials
api_key = wd.api_key
username = wd.username
pwd = wd.pwd
smartApi = SmartConnect(api_key=wd.api_key)

def initialize_session():
    global authToken
    try:
        token = wd.Token
        totp = pyotp.TOTP(token).now()
        
        data = smartApi.generateSession(username, pwd, totp)
        if not data.get('status'):
            raise Exception(f"Login failed: {data.get('message','unknown error')}")
        
        authToken = data['data']['jwtToken']
        refreshToken = data['data']['refreshToken']
        feedToken = smartApi.getfeedToken()
        smartApi.getProfile(refreshToken)
        smartApi.generateToken(refreshToken)
        return True
    except Exception as e:
        logger.error(f"Session initialization failed: {e}")
        return False

# Network information
local_ip = socket.gethostbyname(socket.gethostname())
public_ip = socket.gethostbyname(socket.getfqdn())
mac_address = ":".join(["{:02x}".format((platform.uname().node.encode())[i]) for i in range(6)])

class TradingDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Trading Dashboard")
        self.root.geometry("800x900")
        
        # Create main frames
        self.create_search_frame()
        self.create_ltp_frame()
        self.create_calculator_frame()
        self.create_results_frame()
        self.create_trading_frame()
        self.net_amount = 0
        
        # Initialize session
        if not initialize_session():
            messagebox.showerror("Error", "Failed to initialize trading session")
    
    def create_search_frame(self):
        frame = ttk.LabelFrame(self.root, text="Symbol Search")
        frame.pack(fill="x", padx=10, pady=5)
        
        self.symbol_entry = ttk.Entry(frame, font=("Helvetica", 12))
        self.symbol_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        
        search_btn = ttk.Button(frame, text="Search", command=self.search_symbol)
        search_btn.pack(side="left", padx=5, pady=5)
        
        self.symbol_result = ttk.Label(frame, text="")
        self.symbol_result.pack(side="left", padx=5)
    
    def create_ltp_frame(self):
        frame = ttk.LabelFrame(self.root, text="Market Data")
        frame.pack(fill="x", padx=10, pady=5)
        
        self.ltp_label = ttk.Label(frame, text="LTP: Loading...", font=("Helvetica", 14))
        self.ltp_label.pack(pady=5)
        
        self.multiplier_label = ttk.Label(frame, text="Multiplier: -", font=("Helvetica", 12))
        self.multiplier_label.pack(pady=5)
    
    def create_calculator_frame(self):
        frame = ttk.LabelFrame(self.root, text="Trading Calculator")
        frame.pack(fill="x", padx=10, pady=5)
        
        fetch_rms_btn = ttk.Button(frame, text="Fetch RMS Data", command=self.fetch_rms_data)
        fetch_rms_btn.pack(pady=5)
        
        ttk.Label(frame, text="Total Amount (XT):").pack(pady=5)
        self.xt_entry = ttk.Entry(frame, width=20)
        self.xt_entry.pack(pady=5)
        
        calc_btn = ttk.Button(frame, text="Calculate", command=self.calculate)
        calc_btn.pack(pady=5)
    
    def create_results_frame(self):
        frame = ttk.LabelFrame(self.root, text="Calculation Results")
        frame.pack(fill="both", padx=10, pady=5, expand=True)
        
        # Create Treeview
        self.tree = ttk.Treeview(frame, columns=("Description", "Value"), show="headings")
        self.tree.heading("Description", text="Description")
        self.tree.heading("Value", text="Value")
        self.tree.pack(pady=5, fill="both", expand=True)
    
    def create_trading_frame(self):
        frame = ttk.LabelFrame(self.root, text="Trading Panel")
        frame.pack(fill="x", padx=10, pady=5)
        
        # Add trading controls here
        self.quantity_label = ttk.Label(frame, text="Quantity: 0")
        self.quantity_label.pack(pady=5)
        
        logout_btn = ttk.Button(frame, text="Logout", command=self.logout)
        logout_btn.pack(pady=5)
    
    def search_symbol(self):
        global tradingsymbol, symbol_token, PRICE_MULTIPLIER
        
        symbol = self.symbol_entry.get().strip().upper()
        if not symbol:
            messagebox.showerror("Error", "Please enter a symbol")
            return
        
        tradingsymbol = f"{symbol}-EQ"
        result = df[df['SymbolName'].str.upper() == symbol.upper()]
        
        if not result.empty:
            symbol_token = str(result['token'].values[0])
            PRICE_MULTIPLIER = result['Multiplier'].values[0]
            exchange = result['Exchange'].values[0]
            
            self.symbol_result.config(text=f"Token: {symbol_token}")
            self.multiplier_label.config(text=f"Multiplier: {PRICE_MULTIPLIER}")
            self.start_ltp_updates()
        else:
            messagebox.showinfo("No Result", f"No data found for symbol: {symbol}")
    
    def fetch_ltp(self):
        global ltp_value
        try:
            conn = http.client.HTTPSConnection("apiconnect.angelone.in")
            payload = json.dumps({
                "exchange": "NSE",
                "tradingsymbol": tradingsymbol,
                "symboltoken": symbol_token
            })
            headers = {
                'Authorization': f'{authToken}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': local_ip,
                'X-ClientPublicIP': public_ip,
                'X-MACAddress': mac_address,
                'X-PrivateKey': api_key
            }
            conn.request("POST", "/order-service/rest/secure/angelbroking/order/v1/getLtpData", payload, headers)
            res = conn.getresponse()
            data = json.loads(res.read().decode("utf-8"))
            
            ltp_value = data.get("data", {}).get("ltp", 0)
            return ltp_value
        except Exception as e:
            logger.error(f"Error fetching LTP: {e}")
            return None
    
    def update_ltp_display(self):
        ltp = self.fetch_ltp()
        if ltp:
            self.ltp_label.config(text=f"LTP: {ltp} | Time: {datetime.now().strftime('%H:%M:%S')}")
        self.root.after(1000, self.update_ltp_display)
    
    def start_ltp_updates(self):
        self.update_ltp_display()
        
    def get_rms_data(self):
        try:
            conn = http.client.HTTPSConnection("apiconnect.angelone.in")
            payload = ''
            headers = {
                'Authorization': f'{authToken}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-UserType': 'USER',
                'X-SourceID': 'WEB',
                'X-ClientLocalIP': local_ip,
                'X-ClientPublicIP': public_ip,
                'X-MACAddress': mac_address,
                'X-PrivateKey': api_key
            }
            conn.request("GET", "/rest/secure/angelbroking/user/v1/getRMS", payload, headers)
            res = conn.getresponse()
            data = res.read().decode("utf-8")
            return data
        except Exception as e:
            logger.error(f"Error fetching RMS data: {e}")
            raise e

    def fetch_rms_data(self):
        try:
            # Fetch RMS data
            rms_data = self.get_rms_data()
            rms_data_parsed = json.loads(rms_data)  # Parse JSON response
    
    
            if rms_data_parsed.get("status") and "data" in rms_data_parsed:
                rms_data = rms_data_parsed["data"]
     # Extract the Net Value (assuming it exists in the data)
                net_amount = rms_data.get("Net", 0)
                
                if net_amount is None:
                    raise ValueError("Net amount is missing in RMS data")
                    
                try:
                    self.net_amount = float(net_amount)
                    if self.net_amount > 0:
                        #raise ValueError("Net amount must be greater than zero")
                        self.calculate()
                    else:
                        raise ValueError ("Net amount must be greater than zero")
                except Exception as e:
                    raise ValueError(f"Invalid net amount format: {net_amount}")
            else:
                raise ValueError ("RMS data is not valid or incomplete")
        except:
            raise ValueError("Invalid RMS data")
            
    def clear_xt_field(self):
        """Clear the Total Amount (XT) field."""
        self.xt_entry.delete(0, tk.END)
    
    
    def calculate(self):
        try:
            global XT, ltp_value, products_buyable
            XT = float(self.net_amount)
            
            if XT <= 0 or ltp_value <= 0:
                raise ValueError("Invalid input values")
            
            # Calculations
            Xs = XT * SAFE_PERCENT
            remaining_amount = XT - Xs
            
            Xt = remaining_amount * TAX_RATE
            Xa = remaining_amount - Xt
            
            profit = Xa * PROFIT_PERCENT
            loss = Xa * LOSS_PERCENT
            
            N_price = ltp_value / PRICE_MULTIPLIER
            products_buyable = int(Xa / N_price)
            
            # Update quantity display
            self.quantity_label.config(text=f"Quantity: {products_buyable}")
            
            # Calculate trading values
            product_profit_at_buy = N_price * (1 + PROFIT_PERCENT)
            product_profit_at_sell = N_price * (1 - PROFIT_PERCENT)
            product_loss_at_buy = N_price * (1 - LOSS_PERCENT)
            product_loss_at_sell = N_price * (1 + LOSS_PERCENT)
            value_profit = product_profit_at_buy - N_price
            value_loss = product_loss_at_buy - N_price
            
            # Update results table
            self.update_results({
                "Amount Before Tax (Xts)": f"{remaining_amount:.2f}",
                "Remaining Amount (Xa)": f"{Xa:.2f}",
                f"Profit ({PROFIT_PERCENT*100}% of Xa)": f"{profit:.2f}",
                f"Loss ({LOSS_PERCENT*100}% of Xa)": f"{loss:.2f}",
                "Price per Product": f"{N_price:.2f}",
                "Products Buyable": f"{products_buyable}",
                "Product Buy Profit": f"{product_profit_at_buy:.2f}",
                "Product Sell Profit": f"{product_profit_at_sell:.2f}",
                "Product Buy Loss": f"{product_loss_at_buy:.2f}",
                "Product Sell Loss": f"{product_loss_at_sell:.2f}",
                "Value Profit": f"{value_profit:.2f}",
                "Value Loss": f"{value_loss:.2f}"
            })
        
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid positive numbers")
            self.clear_fields()
    
    def update_results(self, results):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for description, value in results.items():
            self.tree.insert("", "end", values=(description, value))
    
    def clear_fields(self):
        self.xt_entry.delete(0, tk.END)
        for row in self.tree.get_children():
            self.tree.delete(row)
    
    def logout(self):
        try:
            smartApi.terminateSession(username)
            logger.info("Logout Successful")
            self.root.destroy()
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            messagebox.showerror("Error", f"Logout failed: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = TradingDashboard(root)
    root.mainloop()