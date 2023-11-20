import random

my_token = [
    '4ba66c603baf16303439a376d082ced5c7ae248c134e685975a697c2'
]


def get_tushare_pro(account_number=0):
    import tushare as ts
    ts.set_token(my_token[account_number])
    return ts.pro_api()

