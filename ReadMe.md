# Project-1 Algorithmic Backtesting Dashboard 
## Hybrid processing - Live data + Historic data

### Duration: feb 2024 - sep 2024 
**Git upload : 2 may 2026**

## Summary:

An analytical framework developed to evaluate trading strategy performance against live data and historical stock data. 

It allows users to simulate and visualize the profitability of different trading strategies, 

providing a clear perspective on alpha generation.

## Basic workflow 
        Symbol Loop (scan_for_patterns)
        ├── fetch_candle_data (historical: last 5 candles → df)
        │   ├── Add vol_ratio/trend columns
        │   └── For each selected pattern:
        │       └── if pattern_func(df):  # Historical analysis
        │           ├── fetch_ltp (live: current price/volume)
        │           ├── Table: (symbol, ltp_live, volume_hist, vol_ratio_hist, pattern, trend_hist, timestamp)
        │           └── Alert: ltp_live + volume_hist + trend_hist + vol_ratio_hist
        └── Rate limited sleeps between calls

## Tools 
Python, SQL, VS code, Excel, Json

## Libraries used 
Pandas, Matplotlib, tKinter, SmartApi, pyotp, asyncio, Telegram

## API connection
AngelOne API

## Market 
NSE

## Steps 
### 1 - Data accumulation, Simulation & Loading
Uses Pandas and NumPy to create or load time-series datasets, 

preparing them for quantitative analysis.
        
### 2 - Strategy Implementation
Incorporates modular logic for Moving Average Crossover (10/50-day) 

and Buy & Hold strategies, calculating P&L based on simulated execution.
        
### 3 - Visual Backtesting Engine
Embeds Matplotlib figures directly into Tkinter to plot price trends, 

MA overlays, and specific buy/sell signal markers.
        
### 4 - Interactive GUI Control
Features an OptionMenu that allows the user to switch between strategies instantly, 

triggering real-time updates of the canvas and P&L display.

exports live alerts to dedicated telegram channel.

## Architecture

        ##code structure
        StockScanner Script
        ├── ScrollableFrame (ttk.Frame subclass)
        │   ├── __init__
        │   │   ├── canvas = tk.Canvas(self)
        │   │   ├── scrollbar = ttk.Scrollbar (vertical)
        │   │   ├── scrollable_frame = ttk.Frame(canvas)
        │   │   ├── <Configure> binding → scrollregion update
        │   │   ├── canvas_frame = canvas.create_window()
        │   │   ├── MouseWheel bindings (_bind/_unbind/_on_mouse_scroll)
        │   │   └── _on_canvas_configure (resize handler)
        │   └── Methods: _on_canvas_configure, _bind_mouse_scroll, etc.
        └── StockScanner Class
            ├── __init__
            │   ├── API creds (wd.api_key, username, pwd, Token)
            │   ├── Flags: session_active, scan_in_progress, scan_lock
            │   ├── strategy = TradeStrategy(max_price=Y)
            │   ├── df_symbols = pd.read_excel('Multiplier_X')
            │   ├── root = tk.Tk(1200x800)
            │   └── Calls: setup_ui(), generate_session(), setup_telegram()
            ├── Telegram Methods
            │   ├── setup_telegram() → Bot token/chat_id, test alert
            │   ├── send_telegram_alert (async)
            │   ├── send_notification
            │   └── send_pattern_alert (threaded)
            ├── UI Setup (setup_ui)
            │   ├── Header: status labels, buttons (Start/Stop/Clear/Scan), combos (interval/timeframe)
            │   ├── Pattern Frame: strategy combo, Select All CB, ScrollableFrame + checkboxes
            │   ├── Market Direction: readonly Entry (updates via timer)
            │   └── Results Table: Treeview (7 cols), scrollbar, <ButtonRelease-1> → handle_table_click
            ├── Table Handlers
            │   ├── handle_table_click → copy_to_clipboard (#1 col) or show_graph (#5 col)
            │   ├── copy_to_clipboard + show_tooltip (1s popup)
            │   └── show_graph → Toplevel + candlestick matplotlib (60min data)
            ├── Data Fetchers
            │   ├── fetch_historical_data (60min 1min candles)
            │   ├── fetch_candle_data (minimal 5 candles, vol_ratio/trend calc, rate limit)
            │   └── fetch_ltp (POST /getLtpData, full headers, rate limit)
            ├── Market Monitors
            │   ├── is_market_open (09:00-15:30)
            │   ├── update_market_status (60s timer)
            │   └── update_market_direction (Nifty LTP tracking, 60s/5min timer)
            ├── Pattern UI
            │   ├── create_pattern_checkboxes (grid 4/col in ScrollableFrame)
            │   ├── update_strategy_selection (enable/disable CBs)
            │   └── toggle_all_patterns
            ├── Scanner Controls
            │   ├── start_scanner → daemon thread (scanner_thread_func)
            │   ├── stop_scanner
            │   ├── run_manual_scan → thread (scan_for_patterns)
            │   ├── scanner_thread_func (60s loop, interval check)
            │   └── clear_fields (reset UI + table)
            ├── Core Scanner
            │   └── scan_for_patterns (lock protected)
            │       ├── Get selected_patterns
            │       ├── Clear table
            │       ├── Loop df_symbols → fetch data → test patterns
            │       ├── On match: table.insert + send_pattern_alert
            │       └── Summary alert
            ├── Session
            │   ├── generate_session (TOTP + SmartConnect)
            │   └── logout_session (terminate + destroy)
            └── run → protocol("WM_DELETE_WINDOW") + mainloop()

## Results: 

The scanner successfully detected chart patterns across NSE stocks during live market hours, 

demonstrating real-time performance with Telegram alerts, tracking and visualizations.

  1- Exceptional scan efficiency : obtained immediate scanned symbols within given price range with pattern observed
  
  2- Instant market direction detection : stock price up / down data availabilty within seconds
  
  3- Interactive table and visualization : Double-click symbol → clipboard; pattern → candlestick graph (Matlibplot, 60min chart)
  
  4- Pattern selection : with option to select all or a particular pattern.
  
  5- 99% of uptime with TOTP login success, fallback empty DataFrames on API fail
  
  6- Thread safety: scan_lock blocked concurrent scans.
  
  7- Market status: Auto-updates green/red (09:00-15:30 IST)
  
  8- delivered 100% effeicient data alerts to telegram channel.

## Conclusion:

The StockScanner application successfully delivers a robust, real-time pattern recognition system for NSE equities. 

Integrating live Angel One API data with sophisticated UI/UX features tailored for active traders.

To analyse processed data at your fingertips 
