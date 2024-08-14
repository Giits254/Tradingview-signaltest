import websocket
import csv
import json
from datetime import datetime
import threading
import time
from tradingview_ta import TA_Handler, Interval

# Define input variables
PROFIT_PERCENTAGE = 0.5  # Adjust as needed
LOSS_PERCENTAGE = 0.2  # Adjust as needed
LEVERAGE = 40
MARGIN = 10   # Adjust as needed

symbols_to_track = {
    'BTCUSDT': 1, 'ETHUSDT': 2, 'SOLUSDT': 3, 'ADAUSDT': 4, 'DOTUSDT': 3, 'XRPUSDT': 4, 'DOGEUSDT': 5, 'LINKUSDT': 3,
    'LTCUSDT': 2, 'TRBUSDT': 2, 'EOSUSDT': 4, 'THETAUSDT': 4, 'VETUSDT': 5, 'XLMUSDT': 5, 'MATICUSDT': 4, 'ALGOUSDT': 4
}
symbol_to_letter = {symbol: chr(ord('A') + i) for i, symbol in enumerate(symbols_to_track)}

symbol_to_amount_precision = {
    'BTCUSDT': 3, 'ETHUSDT': 2, 'SOLUSDT': 1, 'ADAUSDT': 0, 'DOTUSDT': 1, 'XRPUSDT': 0, 'DOGEUSDT': 0, 'LINKUSDT': 1,
    'LTCUSDT': 1, 'TRBUSDT': 2, 'EOSUSDT': 1, 'THETAUSDT': 1, 'VETUSDT': 0, 'XLMUSDT': 0, 'MATICUSDT': 0, 'ALGOUSDT': 1
}


def calculate_tp_sl(recommendation_price, recommendation_type, symbol):
    if recommendation_type == 'STRONG_BUY':
        take_profit = recommendation_price + (PROFIT_PERCENTAGE / LEVERAGE) * recommendation_price
        stop_loss = recommendation_price - (LOSS_PERCENTAGE / LEVERAGE) * recommendation_price
    elif recommendation_type == 'STRONG_SELL':
        take_profit = recommendation_price - (PROFIT_PERCENTAGE / LEVERAGE) * recommendation_price
        stop_loss = recommendation_price + (LOSS_PERCENTAGE / LEVERAGE) * recommendation_price
    else:
        # Default values if recommendation is not 'STRONG_BUY' or 'STRONG_SELL'
        take_profit = stop_loss = None

    # Apply precision to tp and sl prices
    if take_profit is not None and stop_loss is not None:
        precision = symbols_to_track.get(symbol, 0)
        take_profit = round(take_profit, precision)
        stop_loss = round(stop_loss, precision)

    return take_profit, stop_loss

def on_open(ws):
    sub_msg = {"method": "SUBSCRIBE", "params": [f"{symbol.lower()}@ticker" for symbol in symbols_to_track], "id": 1}
    ws.send(json.dumps(sub_msg))
    print("Opened connection")

def on_message(ws, message):
    global current_prices, open_orders
    data = json.loads(message)
    if 's' in data and 'c' in data and 'E' in data:
        symbol = data['s']
        if symbol.upper() in symbols_to_track:
            current_prices[symbol.upper()] = float(data['c'])
            handle_orders(symbol.upper())

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Closed with status code {close_status_code}. Reconnecting...")
    ws.run_forever()



# Define Balance Variable
balance = 0.0

def print_order_closed(order_number, symbol, status, balance_change):
    global balance
    white_color_code = "\033[97m"
    reset_color_code = "\033[0m"
    balance += balance_change
    print(f'\r Order {order_number} for {white_color_code}{symbol}{reset_color_code} closed - {status} bal: {balance:.4f}')
    with open('xem.csv', 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([order_number, symbol, status,balance])

# Update handle_orders function
def handle_orders(symbol):
    global current_prices, open_orders, order_counter, balance

    num_open_orders = sum(1 for order in open_orders.values() if order is not None)

    if symbol in open_orders and open_orders[symbol] is not None:
        # Check if the order is closed
        order_info = open_orders[symbol]
        recommendation_type, recommendation_price, take_profit, stop_loss, order_number = order_info
        current_price = current_prices.get(symbol, None)

        if current_price is not None:
            if recommendation_type == 'STRONG_BUY' and current_price >= take_profit:
                balance_change = PROFIT_PERCENTAGE * MARGIN - 0.0005 * (recommendation_price * (LEVERAGE * MARGIN / recommendation_price) * 2)
                print_order_closed(order_number, symbol, 'Profit', balance_change)
                open_orders[symbol] = None
            elif recommendation_type == 'STRONG_BUY' and current_price <= stop_loss:
                balance_change = -1 * (LOSS_PERCENTAGE * MARGIN + 0.0005 * (recommendation_price * (LEVERAGE * MARGIN / recommendation_price) * 2))
                print_order_closed(order_number, symbol, 'Loss', balance_change)
                open_orders[symbol] = None
            elif recommendation_type == 'STRONG_SELL' and current_price <= take_profit:
                balance_change = PROFIT_PERCENTAGE * MARGIN - 0.0005 * (recommendation_price * (LEVERAGE * MARGIN / recommendation_price) * 2)
                print_order_closed(order_number, symbol, 'Profit', balance_change)
                open_orders[symbol] = None
            elif recommendation_type == 'STRONG_SELL' and current_price >= stop_loss:
                balance_change = -1 * (LOSS_PERCENTAGE * MARGIN + 0.0005 * (recommendation_price * (LEVERAGE * MARGIN / recommendation_price) * 2))
                print_order_closed(order_number, symbol, 'Loss', balance_change)
                open_orders[symbol] = None
    # Rest of the code remains the same

    elif order_counter < 100 and num_open_orders < 15:  # Only fetch new recommendations if order_counter is less than 100
        # No open order for this symbol, check for new signals
        try:
            output = TA_Handler(symbol=symbol + '.P',
                                screener='Crypto',
                                exchange='Bybit',
                                interval=Interval.INTERVAL_30_MINUTES)
            summary = output.get_analysis().summary
        except Exception as e:

            #print(f"Failed to fetch trading signals for {symbol}: {e}")
            return


        if summary['RECOMMENDATION'] in ['STRONG_BUY', 'STRONG_SELL']:
            recommendation_type = 'STRONG_SELL' if summary['RECOMMENDATION'] == 'STRONG_SELL' else 'STRONG_BUY'
            recommendation_price = current_prices[symbol]
            take_profit, stop_loss = calculate_tp_sl(recommendation_price, recommendation_type, symbol)

            if take_profit is not None and stop_loss is not None:
                order_counter += 1  # Increment order counter
                amount = LEVERAGE * MARGIN / recommendation_price  # Calculate the amount

                # Apply precision to amount
                amount_precision = symbol_to_amount_precision.get(symbol, 0)
                amount = round(amount, amount_precision)

                open_orders[symbol] = (recommendation_type, recommendation_price, take_profit, stop_loss, order_counter)

                print(
                    '\r ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') +
                    f' | Symbol: {white_color_code}{symbol}{reset_color_code} | Rec at Price: {recommendation_price}' +
                    f' | signal: {summary["RECOMMENDATION"]} | {"Short" if recommendation_type == "STRONG_SELL" else "Long"} Order {order_counter} Opened - TP: {take_profit}, SL: {stop_loss}, Amt: {amount}')
# Move these outside of the functions
white_color_code = "\033[97m"
reset_color_code = "\033[0m"

url = "wss://fstream.binance.com/ws"
ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
ws_thread = threading.Thread(target=ws.run_forever)
ws_thread.start()

current_prices = {}
open_orders = {}  # Dictionary to track open orders for each symbol
order_counter = 0  # Initialize order counter

while True:
    time.sleep(200)
