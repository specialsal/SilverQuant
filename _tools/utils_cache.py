import os
import datetime
import pandas as pd

from _tushare.api_token import get_tushare_pro

OPEN_DAY_CACHE_PATH = '_cache/_open_day_list.csv'
open_day_cache = {}


def check_today_is_open_day_by_df(df, today):
    df = df[df['is_open'] == 1]
    is_today_open_day = today in df['cal_date'].values
    open_day_cache[today] = is_today_open_day
    return is_today_open_day


def check_today_is_open_day(now: datetime.datetime):
    today = int(now.strftime("%Y%m%d"))

    # 内存缓存
    if today in open_day_cache.keys():
        return open_day_cache[today]

    # 文件缓存
    if os.path.exists(OPEN_DAY_CACHE_PATH):  # 文件缓存存在
        df = pd.read_csv(OPEN_DAY_CACHE_PATH)
        if today <= df['cal_date'].max():  # 文件缓存未过期
            return check_today_is_open_day_by_df(df, today)

    # 网络缓存
    curr_year = datetime.datetime.now().year
    next_year = curr_year + 1

    pro = get_tushare_pro(0)
    df = pro.trade_cal(exchange='', start_date=str(curr_year) + '0101', end_date=str(next_year) + '1231')
    df.to_csv(OPEN_DAY_CACHE_PATH)

    return check_today_is_open_day_by_df(df, today)


def get_all_historical_symbols():
    with open('_cache/_historical_symbols.txt', 'r') as r:
        symbols = r.read().split('\n')
    return symbols
