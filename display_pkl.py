from tools.utils_cache import load_pickle

path = '_cache/prod_debug/test.pkl'
test = load_pickle(path)

print(test)
