import ccxt

def test_binance_symbols():
    exchange = ccxt.binanceusdm()
    exchange.load_markets()
    
    targets = ["1000000BOB", "ALCH", "1000PEPE"]
    
    print("Listing raw matching markets...")
    for sym in exchange.markets.keys():
        for t in targets:
            if t in sym:
                print(f"Found: {sym}")

if __name__ == '__main__':
    test_binance_symbols()
