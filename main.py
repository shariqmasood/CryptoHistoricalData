"""
Project: Binance Historical Data GUI App
Overview:
This application allows users to fetch historical OHLCV (Open, High, Low, Close, Volume) data for Binance trading pairs (USDT markets) over a specified time range and interval. Users can:
- Select a coin from a dropdown populated dynamically from Binance
- Choose start and end dates via calendar widgets
- Pick an interval (hourly, daily, weekly, monthly)
- Plot the closing price or save the data to CSV

Before running:
1. Create a `.env` file in the project root with your Binance credentials:
   ```
   BINANCE_API_KEY=your_binance_api_key
   BINANCE_API_SECRET=your_binance_api_secret
   ```
2. Place a background image named `background.png` in the same directory as this script.
3. Install dependencies from `requirements.txt`.

Key Features:
- Securely load API credentials from a `.env` file
- Handle Binance's 1000-candle limit through pagination
- Keep the UI responsive with background threading
- Interactive plotting with Matplotlib
- Easy CSV export via file dialog
- Enhanced UI with a background image and refined layout
- Detailed grid and tick formatting for quick insights
"""

import os
import threading
import pandas as pd
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
from tkcalendar import DateEntry

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import AutoMinorLocator

# ─── Setup ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = Client(API_KEY, API_SECRET)

# ─── Data Fetching ─────────────────────────────────────────────────────────────
def fetch_historical_data(symbol, interval, start_dt, end_dt):
    """
    Fetch OHLCV data for `symbol` between `start_dt` and `end_dt`, handling
    Binance's 1000-candle limit via pagination.
    """
    klines = []
    next_start = start_dt
    while next_start < end_dt:
        try:
            batch = client.get_historical_klines(
                symbol=symbol,
                interval=interval,
                start_str=next_start.strftime("%Y-%m-%d %H:%M:%S"),
                end_str=end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                limit=1000
            )
        except BinanceAPIException as e:
            raise RuntimeError(f"Binance API error: {e}")
        if not batch:
            break
        klines.extend(batch)
        last_ts = batch[-1][0]
        next_start = datetime.fromtimestamp(last_ts/1000) + timedelta(milliseconds=1)

    cols = ['timestamp','open','high','low','close','volume',
            'close_time','quote_asset_volume','trades',
            'taker_buy_base','taker_buy_quote','ignore']
    df = pd.DataFrame(klines, columns=cols)
    df.drop(columns=['close_time','ignore'], inplace=True)
    num_cols = ['open','high','low','close','volume','quote_asset_volume','trades']
    df[num_cols] = df[num_cols].apply(pd.to_numeric)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    return df

# ─── GUI Application ───────────────────────────────────────────────────────────
class HistoricalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Binance Historical Data Viewer")
        self.geometry("620x440")
        self.resizable(False, False)
        self._load_background()
        self._build_widgets()
        self._load_symbols()

    def _load_background(self):
        """Loads a background image behind all widgets."""
        try:
            img_path = os.path.join(BASE_DIR, 'background.png')
            bg = Image.open(img_path)
            bg = bg.resize((620, 440), Image.LANCZOS)
            self.bg_photo = ImageTk.PhotoImage(bg)
            bg_label = tk.Label(self, image=self.bg_photo)
            bg_label.place(x=0, y=0, relwidth=1, relheight=1)
            bg_label.lower()
        except Exception:
            pass

    def _build_widgets(self):
        """Creates and places all UI controls in a centered card frame."""
        style = ttk.Style()
        style.configure('Card.TFrame', background='white', relief='ridge', borderwidth=2)
        style.configure('TLabel', background='white', font=('Arial', 10))
        style.configure('TButton', font=('Arial', 10, 'bold'))
        style.configure('TCombobox', font=('Arial', 10))

        card = ttk.Frame(self, style='Card.TFrame', padding=20)
        card.place(relx=0.5, rely=0.5, anchor='center')

        ttk.Label(card, text="Historical Data Fetcher", font=('Arial',14,'bold')).grid(
            row=0, column=0, columnspan=2, pady=(0,10)
        )
        ttk.Label(card, text="Coin Symbol (USDT):").grid(row=1, column=0, sticky='e', pady=5)
        self.symbol_cb = ttk.Combobox(card, state="readonly", width=24)
        self.symbol_cb.grid(row=1, column=1, pady=5)
        ttk.Label(card, text="Interval:").grid(row=2, column=0, sticky='e', pady=5)
        self.interval_cb = ttk.Combobox(card, values=['1h','1d','1w','1M'], state="readonly", width=24)
        self.interval_cb.current(0)
        self.interval_cb.grid(row=2, column=1, pady=5)
        ttk.Label(card, text="Start Date:").grid(row=3, column=0, sticky='e', pady=5)
        self.start_cal = DateEntry(card, width=22)
        self.start_cal.grid(row=3, column=1, pady=5)
        ttk.Label(card, text="End Date:").grid(row=4, column=0, sticky='e', pady=5)
        self.end_cal = DateEntry(card, width=22)
        self.end_cal.grid(row=4, column=1, pady=5)

        btn_frame = ttk.Frame(card)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(15,0))
        ttk.Button(btn_frame, text="Plot", width=14, command=self._on_plot).grid(row=0, column=0, padx=10)
        ttk.Button(btn_frame, text="Save CSV", width=14, command=self._on_save).grid(row=0, column=1, padx=10)

    def _load_symbols(self):
        try:
            tickers = client.get_all_tickers()
            symbols = sorted([t['symbol'] for t in tickers if t['symbol'].endswith('USDT')])
            self.symbol_cb['values'] = symbols
            self.symbol_cb.set('BTCUSDT')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load symbols: {e}")

    def _gather_inputs(self):
        sym = self.symbol_cb.get()
        interval = self.interval_cb.get()
        start_dt = datetime.combine(self.start_cal.get_date(), datetime.min.time())
        end_dt = datetime.combine(self.end_cal.get_date(), datetime.min.time())
        if start_dt >= end_dt:
            raise ValueError("Start date must be before end date.")
        return sym, interval, start_dt, end_dt

    def _run_threaded(self, func):
        threading.Thread(target=func, daemon=True).start()

    def _on_plot(self):
        """Fetches data and displays a landscape plot with detailed ticks and grid."""
        def task():
            try:
                sym, inter, start_dt, end_dt = self._gather_inputs()
                df = fetch_historical_data(sym, inter, start_dt, end_dt)
                fig, ax = plt.subplots(figsize=(12,6))
                ax.plot(df.index, df['close'], label=f"{sym} Close Price", linewidth=1.5)
                ax.set_title(f"{sym} Close Price @ {inter}")
                ax.set_ylabel("Price (USDT)")

                # Major and minor ticks
                ax.xaxis.set_major_locator(mdates.MonthLocator())
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
                ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
                ax.yaxis.set_minor_locator(AutoMinorLocator())

                # Grid lines for major and minor ticks
                ax.grid(which='major', linestyle='-', linewidth=0.8, alpha=0.7)
                ax.grid(which='minor', linestyle='--', linewidth=0.5, alpha=0.4)

                plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
                ax.legend()
                plt.tight_layout()
                plt.show()
            except Exception as e:
                messagebox.showerror("Error", str(e))
        self._run_threaded(task)

    def _on_save(self):
        """Fetches data and saves to CSV file chosen by user."""
        def task():
            try:
                sym, inter, start_dt, end_dt = self._gather_inputs()
                df = fetch_historical_data(sym, inter, start_dt, end_dt)
                file = filedialog.asksaveasfilename(
                    initialfile=f"{sym}_{inter}.csv",
                    filetypes=[("CSV Files","*.csv")],
                    defaultextension=".csv"
                )
                if file:
                    df.to_csv(file)
                    messagebox.showinfo("Saved", f"Data exported to:{file}")
            except Exception as e:
                messagebox.showerror("Error", str(e))
        self._run_threaded(task)

if __name__ == "__main__":
    HistoricalApp().mainloop()
