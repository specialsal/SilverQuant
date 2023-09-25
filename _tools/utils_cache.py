def get_all_historical_symbols():
    with open('_cache/_historical_symbols.txt', 'r') as r:
        symbols = r.read().split('\n')
    return symbols
