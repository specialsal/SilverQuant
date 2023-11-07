from tools.utils_cache import load_pickle

path = '_cache/prod_hma/info-2023-11-01.pkl'
test = load_pickle(path)

print(test)
