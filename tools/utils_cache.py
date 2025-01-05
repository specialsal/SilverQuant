import os
import csv
import json
import pickle
import threading
import datetime
from typing import List, Dict, Set, Optional

import pandas as pd
import akshare as ak

from tools.utils_basic import symbol_to_code

trade_day_cache = {}
trade_max_year_key = 'max_year'
TRADE_DAY_CACHE_PATH = '_cache/_open_day_list_sina.csv'


# 指数常量
class IndexSymbol:
    INDEX_SH_ZS = '000001'
    INDEX_SH_50 = '000016'
    INDEX_SZ_CZ = '399001'
    INDEX_SZ_50 = '399850'
    INDEX_SZ_100 = '399330'
    INDEX_HS_300 = '000300'
    INDEX_ZZ_100 = '000903'
    INDEX_ZZ_500 = '000905'
    INDEX_ZZ_800 = '000906'
    INDEX_ZZ_1000 = '000852'
    INDEX_ZZ_2000 = '932000'
    INDEX_ZZ_ALL = '000985'
    INDEX_CY_ZS = '399006'
    INDEX_KC_50 = '000688'
    INDEX_ZX_100 = '399005'


# 查询股票名称
class StockNames:
    _instance = None
    _data = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(StockNames, cls).__new__(cls)
            cls._data = None  # Initialize data as None initially
        return cls._instance

    def __init__(self):
        if self._data == None:
            self.load_codes_and_names()

    def load_codes_and_names(self):
        print('Loading codes and names...', end='')
        self._data = get_stock_codes_and_names()
        print('Complete!')

    def get_name(self, code) -> str:
        if self._data == None:
            self.load_codes_and_names()

        if code in self._data:
            return self._data[code]
        return '[Unknown]'


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


def del_key(lock: threading.Lock, path: str, key: str) -> None:
    with lock:
        temp_json = load_json(path)
        if key in temp_json:
            del temp_json[key]
        save_json(path, temp_json)


def del_keys(lock: threading.Lock, path: str, keys: List[str]) -> None:
    with lock:
        temp_json = load_json(path)
        for key in keys:
            if key in temp_json:
                del temp_json[key]
        save_json(path, temp_json)


# 所有缓存持仓天数+1
def all_held_inc(held_operation_lock: threading.Lock, path: str) -> bool:
    with held_operation_lock:
        held_days = load_json(path)

        today = datetime.datetime.now().strftime('%Y-%m-%d')
        inc_date_key = '_inc_date'

        try:
            if (inc_date_key not in held_days) or (held_days[inc_date_key] != today):
                held_days[inc_date_key] = today
                for code in held_days.keys():
                    if code != inc_date_key:
                        held_days[code] += 1

                save_json(path, held_days)
                return True
            else:
                return False
        except:
            return False


# 增加新的持仓记录
def new_held(held_operation_lock: threading.Lock, path: str, codes: List[str]) -> None:
    with held_operation_lock:
        held_days = load_json(path)
        for code in codes:
            held_days[code] = 0
        save_json(path, held_days)


# 更新持仓股买入次日开始最高价格
def update_max_prices(
    lock: threading.Lock,
    quotes: dict,
    positions: list,
    path_max_prices: str,
    path_held_days: str,
    ignore_open_day: bool = True,
):
    held_days = load_json(path_held_days)

    with lock:
        max_prices = load_json(path_max_prices)

    # 更新历史最高
    updated = False
    for position in positions:
        code = position.stock_code
        if code in held_days:  # 只更新持仓超过一天的
            if ignore_open_day:  # 忽略开仓日的最高价
                held_day = held_days[code]
                if held_day <= 0:
                    continue
            if code in quotes:
                quote = quotes[code]
                high_price = quote['high']

                if code in max_prices:
                    if max_prices[code] < high_price:
                        max_prices[code] = round(high_price, 3)
                        updated = True
                else:
                    max_prices[code] = round(high_price, 3)
                    updated = True

    if updated:
        with lock:
            save_json(path_max_prices, max_prices)

    return max_prices, held_days


# 记录成交单
def record_deal(
    lock: threading.Lock,
    path: str,
    timestamp: str,
    code: str,
    name: str,
    order_type: str,
    remark: str,
    price: float,
    volume: int,
):
    with lock:
        if not os.path.exists(path):
            with open(path, 'w') as w:
                w.write(','.join(['日期', '时间', '代码', '名称', '类型', '注释', '成交价', '成交量']))
                w.write('\n')

        with open(path, 'a+', newline='') as w:
            wf = csv.writer(w)
            dt = datetime.datetime.fromtimestamp(int(timestamp))

            wf.writerow([
                dt.date(), dt.time(),
                code, name, order_type, remark, price, volume
            ])


# 获取磁盘缓存的交易日列表
def get_disk_trade_day_list_and_update_max_year() -> list:
    # 读磁盘，这里可以有内存缓存的速度优化
    df = pd.read_csv(TRADE_DAY_CACHE_PATH)
    trade_dates = pd.to_datetime(df['trade_date']).dt.strftime('%Y-%m-%d').values
    trade_day_cache[trade_max_year_key] = trade_dates[-1][:4]
    return trade_dates


# 获取前n个交易日，返回格式 %Y%m%d
def get_prev_trading_date(now: datetime.datetime, count: int) -> str:
    trading_day_list = get_disk_trade_day_list_and_update_max_year()
    trading_index = list(trading_day_list).index(now.strftime('%Y-%m-%d'))
    return trading_day_list[trading_index - count].replace('-', '')


def check_today_is_open_day_sina(curr_date: str) -> bool:
    curr_year = curr_date[:4]

    # 内存缓存
    if curr_date in trade_day_cache:
        if curr_year <= trade_day_cache[trade_max_year_key]:
            return trade_day_cache[curr_date]

    # 文件缓存
    if os.path.exists(TRADE_DAY_CACHE_PATH):  # 文件缓存存在
        trade_day_list = get_disk_trade_day_list_and_update_max_year()
        if curr_year <= trade_day_cache[trade_max_year_key]:  # 未过期
            ans = curr_date in trade_day_list
            trade_day_cache[curr_date] = ans
            print(f'[{curr_date} is {ans} trade day in memory]')
            return ans

    # 网络缓存
    df = ak.tool_trade_date_hist_sina()
    df.to_csv(TRADE_DAY_CACHE_PATH)
    print(f'Cache trade day list {curr_year} - {int(curr_year) + 1} in {TRADE_DAY_CACHE_PATH}.')

    trade_day_list = get_disk_trade_day_list_and_update_max_year()
    if curr_year <= trade_day_cache[trade_max_year_key]:  # 未过期
        ans = curr_date in trade_day_list
        trade_day_cache[curr_date] = ans
        print(f'[{curr_date} is {ans} trade day in memory]')
        return ans

    # 实在拿不到数据默认为True
    print(f'[DO NOT KNOW {curr_date}, default to True trade day]')
    return True


def check_today_is_open_day(curr_date: str) -> bool:
    """
    curr_date example: '2024-12-31'
    """
    return check_today_is_open_day_sina(curr_date)


def get_symbols_from_file(path: str) -> list:
    with open(path, 'r') as r:
        symbols = r.read().split('\n')
    return symbols


# 获取手工黑名单的code列表
def get_blacklist_codes(target_stock_prefixes: set = None) -> list:
    history_symbols = get_symbols_from_file('_data/_blacklist_symbols.txt')
    if target_stock_prefixes is None:
        return [symbol_to_code(symbol) for symbol in history_symbols]
    return [symbol_to_code(symbol) for symbol in history_symbols if symbol[:3] in target_stock_prefixes]


# 获取市值符合范围的code列表
def get_market_value_limited_codes(code_prefixes: Set[str], min_value: int, max_value: int) -> list[str]:
    # samples()
    df = ak.stock_zh_a_spot_em()
    df = df.sort_values('代码')
    df = df[['代码', '名称', '总市值', '流通市值']]
    df = df[(min_value < df['总市值']) & (df['总市值'] < max_value)]
    df = df[df['代码'].str.startswith(tuple(code_prefixes))]
    return [symbol_to_code(symbol) for symbol in list(df['代码'].values)]


def get_index_symbols(index_symbol: str) -> list[str]:
    df = ak.index_stock_cons_csindex(symbol=index_symbol)
    return [str(code).zfill(6) for code in df['成分券代码'].values]


def get_index_codes(index_symbol: str) -> list:
    df = ak.index_stock_cons(symbol=index_symbol)
    return [symbol_to_code(str(code).zfill(6)) for code in df['品种代码'].values]


def get_prefixes_stock_codes(prefixes: set[str]) -> List[str]:
    """
    prefixes: 六位数的两位数前缀
    """
    df = ak.stock_zh_a_spot_em()
    return [
        symbol_to_code(symbol)
        for symbol in df['代码'].values
        if symbol[:2] in prefixes
    ]


def get_stock_codes_and_names() -> Dict[str, str]:
    ans = {}

    with open('./_data/mktdt00.txt', 'r', errors='replace') as r:
        lines = r.readlines()
        for line in lines:
            arr = line.split('|')
            if len(arr) > 2 and len(arr[1]) == 6:
                ans[arr[1] + '.SH'] = arr[2]

    with open('./_data/sjshq.txt', 'r', encoding='utf-8', errors='replace') as r:
        lines = r.readlines()
        for line in lines:
            arr = json.loads(line)
            ans[arr['code']] = arr['name']

    df = ak.stock_zh_a_spot_em()
    df['代码'] = df['代码'].apply(lambda x:symbol_to_code(x))
    ans.update(dict(zip(df['代码'], df['名称'])))
    return ans


# 获取流通市值，单位（元）
def get_stock_codes_and_circulation_mv() -> Dict[str, int]:
    df = ak.stock_zh_a_spot_em()
    df['代码'] = df['代码'].apply(lambda x:symbol_to_code(x))
    df = df[['代码', '流通市值']].dropna()
    return dict(zip(df['代码'], df['流通市值']))


def get_total_asset_increase(path_assets, curr_date, curr_asset) -> Optional[float]:
    if os.path.exists(path_assets):
        df = pd.read_csv(path_assets)
        prev_asset = df.tail(1)['asset'].values[0]
        df.loc[len(df)] = [curr_date, curr_asset]
        df.to_csv(path_assets, index=False)
        return curr_asset - prev_asset
    else:
        df = pd.DataFrame({'date': [curr_date], 'asset': [curr_asset]})
        df.to_csv(path_assets, index=False)
        return None
