import os
import io
import base64
import pandas as pd
from datetime import datetime, timedelta
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import AutoMinorLocator

# ─── Setup ─────────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY    = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
client     = Client(API_KEY, API_SECRET)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-this!')

# ─── Data Fetching ─────────────────────────────────────────────────────────────
def fetch_historical_data(symbol: str, interval: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
 """
 Fetch OHLCV data for `symbol` between `start_dt` and `end_dt`, handling
 Binance's 1000-candle limit via pagination.

 Returns:
     pd.DataFrame: Indexed by timestamp with columns open, high, low, close, volume.
 """
 klines = []
 next_start = start_dt

 while next_start < end_dt:
     try:
         batch = client.get_historical_klines(
             symbol=symbol,
             interval=interval,
             start_str=next_start.strftime('%Y-%m-%d %H:%M:%S'),
             end_str=end_dt.strftime('%Y-%m-%d %H:%M:%S'),
             limit=1000
         )
     except BinanceAPIException as e:
         raise RuntimeError(f"Binance API error: {e}")
     if not batch:
         break
     klines.extend(batch)
     last_ts = batch[-1][0]
     next_start = datetime.fromtimestamp(last_ts / 1000) + timedelta(milliseconds=1)

 # Define full schema and select only OHLCV
 all_cols = [
     'timestamp', 'open', 'high', 'low', 'close', 'volume',
     'close_time', 'quote_asset_volume', 'trades',
     'taker_buy_base', 'taker_buy_quote', 'ignore'
 ]
 df = pd.DataFrame(klines, columns=all_cols)
 df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
 df[['open', 'high', 'low', 'close', 'volume']] = df[
     ['open', 'high', 'low', 'close', 'volume']
 ].apply(pd.to_numeric)
 df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
 df.set_index('timestamp', inplace=True)
 return df

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def index():
 symbols   = sorted([t['symbol'] for t in client.get_all_tickers() if t['symbol'].endswith('USDT')])
 intervals = ['1h', '1d', '1w', '1M']
 img_data  = None
 csv_name  = None

 if request.method == 'POST':
     symbol   = request.form.get('symbol')
     interval = request.form.get('interval')
     start    = request.form.get('start')
     end      = request.form.get('end')

     try:
         start_dt = datetime.fromisoformat(start)
         end_dt   = datetime.fromisoformat(end)
         if start_dt >= end_dt:
             flash('Start date must be before end date.', 'danger')
             return redirect(url_for('index'))

         df = fetch_historical_data(symbol, interval, start_dt, end_dt)

         # Plot to in-memory PNG
         fig, ax = plt.subplots(figsize=(10, 5))
         ax.plot(df.index, df['close'], linewidth=1.5)
         ax.set_title(f'{symbol} Close Price ({interval})')
         ax.set_xlabel('Date')
         ax.set_ylabel('Price (USDT)')
         ax.xaxis.set_major_locator(mdates.MonthLocator())
         ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
         ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
         ax.yaxis.set_minor_locator(AutoMinorLocator())
         ax.grid(which='major', linestyle='-', alpha=0.7)
         ax.grid(which='minor', linestyle='--', alpha=0.4)
         plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
         plt.tight_layout()

         buf = io.BytesIO()
         fig.savefig(buf, format='png')
         buf.seek(0)
         img_data = base64.b64encode(buf.getvalue()).decode()
         plt.close(fig)

         # Save CSV for download
         csv_name = f"{symbol}_{interval}.csv"
         df.to_csv(csv_name)

     except Exception as e:
         flash(str(e), 'danger')

 return render_template(
     'index.html',
     symbols=symbols,
     intervals=intervals,
     img_data=img_data,
     csv_name=csv_name
 )

@app.route('/download/<csv_name>')
def download(csv_name):
 if os.path.exists(csv_name):
     return send_file(csv_name, as_attachment=True)
 flash('CSV not found.', 'warning')
 return redirect(url_for('index'))

if __name__ == '__main__':
 app.run(debug=True)
