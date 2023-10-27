import os
import json
import datetime
import threading
import pandas as pd
from typing import List, Dict, Callable

from tools.tushare_token import get_tushare_pro

open_day_cache = {}
OPEN_DAY_CACHE_PATH = '_cache/_open_day_list.csv'

HISTORICAL_SYMBOLS = '_cache/_historical_symbols.txt'


def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, 'r') as r:
            ans = r.read()
        return json.loads(ans)
    else:
        with open(path, 'w') as w:
            w.write('{}')
        return {}


def save_json(path: str, var: dict):
    with open(path, 'w') as w:
        w.write(json.dumps(var, indent=4))


def daily_once(
    lock: threading.Lock,
    memory_cache: Dict,
    file_cache_path: str,
    cache_key: str,
    curr_date: str,
    function: Callable,
    *args,
) -> None:
    with lock:
        if cache_key in memory_cache:
            # 有内存记录
            if memory_cache[cache_key] != curr_date:
                # 内存记录不是今天
                memory_cache[cache_key] = curr_date

                temp_cache = load_json(file_cache_path)
                temp_cache[cache_key] = curr_date
                save_json(file_cache_path, temp_cache)

                function(*args)
                return
        else:
            # 无内存记录，则寻找文件
            temp_cache = load_json(file_cache_path)
            if cache_key not in temp_cache or temp_cache[cache_key] != curr_date:
                # 无文件记录或者文件记录不是今天
                memory_cache[cache_key] = curr_date

                temp_cache[cache_key] = curr_date
                save_json(file_cache_path, temp_cache)
                function(*args)
                return


def all_held_inc(held_operation_lock: threading.Lock, path: str):
    with held_operation_lock:
        held_days = load_json(path)

        # 所有持仓天数计数+1
        for code in held_days.keys():
            held_days[code] += 1

        save_json(path, held_days)


def new_held(held_operation_lock: threading.Lock, path: str, codes: List[str]):
    with held_operation_lock:
        held_days = load_json(path)
        for code in codes:
            held_days[code] = 0
        save_json(path, held_days)


def del_held(held_operation_lock: threading.Lock, path: str, codes: List[str]):
    with held_operation_lock:
        held_days = load_json(path)
        for code in codes:
            if code in held_days:
                del held_days[code]
        save_json(path, held_days)


def get_all_historical_symbols():
    with open(HISTORICAL_SYMBOLS, 'r') as r:
        symbols = r.read().split('\n')
    return symbols


def check_today_is_open_day_by_df(df: pd.DataFrame, curr_date: str):
    today_int = int(curr_date)
    result = df[df['cal_date'] == today_int]
    return result['is_open'].values[0] == 1


def check_today_is_open_day(curr_date: str):
    today = datetime.datetime.strptime(curr_date, '%Y-%m-%d').strftime('%Y%m%d')
    # 内存缓存
    if today in open_day_cache.keys():
        return open_day_cache[today]

    # 文件缓存
    if os.path.exists(OPEN_DAY_CACHE_PATH):  # 文件缓存存在
        df = pd.read_csv(OPEN_DAY_CACHE_PATH)
        if int(today) <= df['cal_date'].max():  # 文件缓存未过期
            open_day_cache[today] = check_today_is_open_day_by_df(df, today)
            print(f'{today} is {open_day_cache[today]} open day in memory.')
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
    print(f'Cache open day list in {OPEN_DAY_CACHE_PATH}.')

    df = pd.read_csv(OPEN_DAY_CACHE_PATH)
    open_day_cache[today] = check_today_is_open_day_by_df(df, today)
    print(f'{today} is {open_day_cache[today]} open day in memory.')

    return open_day_cache[today]
