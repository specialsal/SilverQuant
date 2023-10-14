import tushare as ts

my_token = [
    '4ba66c603baf16303439a376d082ced5c7ae248c134e685975a697c2'
]


def get_tushare_pro(token_number: int):
    ts.set_token(token_number)
    return ts.pro_api()
