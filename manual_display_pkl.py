from tools.utils_cache import load_pickle

path = '_cache/prod_dk/info-2023-11-09.pkl'
test = load_pickle(path)
for code in test:
    print(code, test[code])

