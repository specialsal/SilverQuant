import random

my_token = [
    '4ba66c603baf16303439a376d082ced5c7ae248c134e685975a697c2',
    '49c7753622785179b3b779883d4ce441d753cddd67e24e99731098e3',
]


def get_tushare_pro(account_number=1):
    import tushare as ts
    ts.set_token(my_token[account_number])
    return ts.pro_api()
