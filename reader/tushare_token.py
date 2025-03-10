import random

my_token = [
    ['(your token)', '(your id)'],
]


ts_pro_api = None


def get_tushare_pro(account_number=None):
    global ts_pro_api
    if ts_pro_api is None:
        import tushare as ts
        if account_number is None:
            account_number = random.randint(0, len(my_token) - 1)
        # print("Account token from account number: " + str(account_number))
        ts.set_token(my_token[account_number][0])
        ts_pro_api = ts.pro_api()
    return ts_pro_api


if __name__ == '__main__':
    pro = get_tushare_pro()
    df = pro.daily(ts_code="000001.SZ", start_date='20230606', end_date='20230615')
    print(df)
