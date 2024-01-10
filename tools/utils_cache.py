import os
import json
import pickle
import datetime
import threading
from typing import List, Dict, Callable, Optional

import numpy as np
import pandas as pd
import akshare as ak

from tools.tushare_token import get_tushare_pro
from tools.utils_basic import symbol_to_code, pd_show_all

open_day_cache = {}
OPEN_DAY_CACHE_PATH = '_cache/_open_day_list.csv'

STOCK_LIST_PATH = '_cache/_stock_list.csv'
STOCK_LIST_TXT_PATH = '_cache/_stock_list.txt'
HISTORICAL_OPEN_DAYS_PATH = '_cache/_historical_open_days.csv'
HISTORICAL_SYMBOLS = '_cache/_historical_symbols.txt'
BLACKLIST_SYMBOLS = '_data/_blacklist_symbols.txt'

INDEX_SH_ZS = '000001'
INDEX_SH_50 = '000016'
INDEX_SZ_CZ = '399001'
INDEX_SZ_100 = '399330'
INDEX_HS_300 = '000300'
INDEX_ZZ_500 = '000905'
INDEX_ZZ_800 = '000906'
INDEX_ZZ_1000 = '000852'
INDEX_ZZ_2000 = '932000'


def load_pickle(path: str) -> Optional[dict]:
    if os.path.exists(path):
        with open(path, 'rb') as f:
            loaded_object = pickle.load(f)
        return loaded_object
    else:
        return None


def save_pickle(path: str, obj: object) -> None:
    with open(path, 'wb') as f:
        pickle.dump(obj, f)


def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, 'r') as r:
            ans = r.read()
        return json.loads(ans)
    else:
        with open(path, 'w') as w:
            w.write('{}')
        return {}


def save_json(path: str, var: dict) -> None:
    with open(path, 'w') as w:
        w.write(json.dumps(var, indent=4))


def daily_once(
    lock: Optional[threading.Lock],   # None时不使用线程锁
    memory_cache: Dict,     # 不能为None
    file_cache_path: Optional[str],   # None时重启程序则失效
    cache_key: str,
    curr_date: str,
    function: Callable,
    *args,
) -> None:
    def _job():
        if cache_key in memory_cache:
            # 有内存记录
            if memory_cache[cache_key] != curr_date:
                # 内存记录不是今天
                memory_cache[cache_key] = curr_date
                if file_cache_path is not None:
                    file_cache = load_json(file_cache_path)
                    file_cache[cache_key] = curr_date
                    save_json(file_cache_path, file_cache)
                function(*args)
                return
        else:
            if file_cache_path is not None:
                # 无内存记录，有文件路径，则寻找文件
                file_cache = load_json(file_cache_path)
                if cache_key not in file_cache or file_cache[cache_key] != curr_date:
                    # 无文件记录或者文件记录不是今天
                    memory_cache[cache_key] = curr_date
                    file_cache[cache_key] = curr_date
                    save_json(file_cache_path, file_cache)
                    function(*args)
                    return
            else:
                # 无内存记录，无文件路径，则直接执行并记录
                memory_cache[cache_key] = curr_date
                function(*args)
                return

    if lock is None:
        _job()
    else:
        with lock:
            _job()


def all_held_inc(held_operation_lock: threading.Lock, path: str) -> None:
    with held_operation_lock:
        held_days = load_json(path)

        # 所有持仓天数计数+1
        for code in held_days.keys():
            held_days[code] += 1

        save_json(path, held_days)


def new_held(held_operation_lock: threading.Lock, path: str, codes: List[str]) -> None:
    with held_operation_lock:
        held_days = load_json(path)
        for code in codes:
            held_days[code] = 0
        save_json(path, held_days)


def del_held(held_operation_lock: threading.Lock, path: str, codes: List[str]) -> None:
    with held_operation_lock:
        held_days = load_json(path)
        for code in codes:
            if code in held_days:
                del held_days[code]
        save_json(path, held_days)


def check_today_is_open_day_by_df(df: pd.DataFrame, today: str) -> bool:
    today_int = int(today)
    result = df[df['cal_date'] == today_int]
    return result['is_open'].values[0] == 1


def check_today_is_open_day(curr_date: str) -> bool:
    today = datetime.datetime.strptime(curr_date, '%Y-%m-%d').strftime('%Y%m%d')
    # 内存缓存
    if today in open_day_cache.keys():
        return open_day_cache[today]

    # 文件缓存
    if os.path.exists(OPEN_DAY_CACHE_PATH):  # 文件缓存存在
        df = pd.read_csv(OPEN_DAY_CACHE_PATH)
        if int(today) <= df['cal_date'].max():  # 文件缓存未过期
            open_day_cache[today] = check_today_is_open_day_by_df(df, today)
            print(f'[{curr_date} is {open_day_cache[today]} open day in memory]')
            return open_day_cache[today]

    # 网络缓存
    next_year_date = str(int(curr_date[:4]) + 1) + curr_date[4:]

    pro = get_tushare_pro(0)
    df = pro.trade_cal(
        exchange='',
        start_date=curr_date,
        end_date=next_year_date,
    )
    df.to_csv(OPEN_DAY_CACHE_PATH)
    print(f'Cache open day list {curr_date} - {next_year_date} in {OPEN_DAY_CACHE_PATH}.')

    df = pd.read_csv(OPEN_DAY_CACHE_PATH)
    open_day_cache[today] = check_today_is_open_day_by_df(df, today)
    print(f'[{curr_date} is {open_day_cache[today]} open day in memory]')

    return open_day_cache[today]


def today_is_open_day():
    today = int(datetime.datetime.now().strftime("%Y%m%d"))
    return is_open_day(today)


def get_open_day_list():
    df = pd.read_csv(OPEN_DAY_CACHE_PATH)
    ans = []
    for index, row in df.iterrows():
        if row['is_open'] == 1:
            ans.append(row['cal_date'])
    return ans


def get_open_day_prev(target_day: int, delta_days: int):
    arr = get_open_day_list()
    index = arr.index(target_day) + delta_days
    assert index < len(arr), '交易日历史不足，需要更久前数据'
    return arr[index]


def is_open_day(today: int):
    return today in get_open_day_list()


def get_stock_info(ts_code):
    df = pd.read_csv(STOCK_LIST_PATH)
    df = df[df["ts_code"] == ts_code]
    return df.iloc[0].to_dict()


def update_open_day_list(start_date, end_date):
    pro = get_tushare_pro(0)
    df = pro.trade_cal(exchange='', start_date=start_date, end_date=end_date)
    df.to_csv(OPEN_DAY_CACHE_PATH)


def update_current_open_day_list():
    curr_year = datetime.datetime.now().year
    next_year = curr_year + 1
    update_open_day_list(str(curr_year) + '0101', str(next_year) + '1231')


def update_stock_list():
    pro = get_tushare_pro(0)
    df = pro.stock_basic(exchange='', list_status='L', fields='ts_code, symbol, name, area, industry, list_date')
    df.to_csv(STOCK_LIST_PATH, index=True)

    with open(STOCK_LIST_TXT_PATH, 'w') as w:
        print(df.columns.values)
        s = ''
        for value in df.columns.values:
            s += str(value)
            s += '\t'
        w.write(s + '\n')
        for index, row in df.iterrows():
            s = ''
            for key in row.index.values:
                s += str(row[key])
                s += '\t'
            print(s)
            w.write(s + '\n')

    print(df)


def refresh_historical_stock_list():
    with open(HISTORICAL_SYMBOLS, 'r') as r:
        symbols = r.read().split('\n')

    stock_zh_a_spot_em_df = ak.stock_zh_a_spot_em()

    for symbol in stock_zh_a_spot_em_df['代码'].values:
        if symbol not in symbols:
            print(symbol)
            symbols.append(symbol)

    symbols = sorted(symbols)

    with open(HISTORICAL_SYMBOLS, 'w') as w:
        w.write('\n'.join(symbols))


def get_blacklist_symbols() -> list:
    with open(BLACKLIST_SYMBOLS, 'r') as r:
        symbols = r.read().split('\n')
    return symbols


def get_blacklist_codes(target_stock_prefixes: set = None) -> list:
    history_symbols = get_blacklist_symbols()
    if target_stock_prefixes is None:
        return [symbol_to_code(symbol) for symbol in history_symbols]
    return [symbol_to_code(symbol) for symbol in history_symbols if symbol[:3] in target_stock_prefixes]


def get_market_value_top_codes(market_value_top: int):
    # samples()
    df = ak.stock_zh_a_spot_em()
    df = df.sort_values('代码')
    df = df[['代码', '名称', '总市值', '流通市值']]
    df = df[df['总市值'] < market_value_top]
    df = df[df['代码'].str.startswith(('00', '60'))]
    return [symbol_to_code(symbol) for symbol in list(df['代码'].values)]


def get_all_historical_symbols() -> list:
    with open(HISTORICAL_SYMBOLS, 'r') as r:
        symbols = r.read().split('\n')
    return symbols


def get_all_historical_codes(target_stock_prefixes: set = None) -> list:
    history_symbols = get_all_historical_symbols()
    if target_stock_prefixes is None:
        return [symbol_to_code(symbol) for symbol in history_symbols]
    return [symbol_to_code(symbol) for symbol in history_symbols if symbol[:3] in target_stock_prefixes]


def update_historical_open_days():
    pro = get_tushare_pro(0)
    df = pro.trade_cal(exchange='', start_date=19950101, end_date=20230101)
    df.to_csv(HISTORICAL_OPEN_DAYS_PATH)


def get_historical_open_days(start_date: str = None, end_date: str = None):
    df = pd.read_csv(HISTORICAL_OPEN_DAYS_PATH)
    df = df[df['is_open'] == 1]
    df['date'] = df['cal_date'].astype(str)
    if start_date is not None:
        df = df[df['date'] >= start_date]
    if end_date is not None:
        df = df[df['date'] <= end_date]

    df = df.reset_index()
    return df


def get_index_element(index_symbol: str) -> pd.DataFrame:

    return ak.index_stock_cons_csindex(symbol=index_symbol)


def get_index_symbols(index_symbol: str):
    df = ak.index_stock_cons(symbol=index_symbol)
    return [str(code).zfill(6) for code in df['品种代码'].values]


def get_index_codes(index_symbol: str):
    df = ak.index_stock_cons(symbol=index_symbol)
    return [symbol_to_code(str(code).zfill(6)) for code in df['品种代码'].values]


def test_cache_held():
    lock = threading.Lock()
    path = '_cache/prod_debug/held_days.json'
    new_held(lock, path, ['000001.SZ'])
    all_held_inc(lock, path)


def test_check_today_is_open_day():
    test = check_today_is_open_day('2023-10-23')
    print(test)


def test_cache_pickle():
    my_object = {'name': 'Alice', 'age': np.array([1, 2, 3, 4])}
    save_pickle('_cache/prod_debug/test.pkl', my_object)

    test = load_pickle('_cache/prod_debug/test.pkl')
    print(type(test))
    print(test['age'])


if __name__ == '__main__':
    pd_show_all()

    # update_open_day_list(
    #     '20220101',
    #     '20231231',
    # )
    # update_stock_list()
    # update_current_open_day_list()

    # update_historical_open_days()
    # refresh_historical_stock_list()

    # print(get_historical_open_days(end_date='20000101'))
    # test_cache_held()
    # test_check_today_is_open_day()
    # test_cache_pickle()

    # print(get_index_element(INDEX_SH_50))
    # print(get_blacklist_codes({'000', '001', '002', '003'}))

    print(get_market_value_top_codes(3000000000))
    print(get_blacklist_codes())
