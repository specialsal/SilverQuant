"""
TODO:
"""
import logging
import datetime
import threading

import numpy as np
import talib as ta
from typing import List, Dict

from xtquant import xtdata
from data_loader.reader_xtdata import get_xtdata_market_dict
from tools.utils_basic import logging_init, symbol_to_code
from tools.utils_cache import get_all_historical_symbols, daily_once, check_today_is_open_day, load_pickle, save_pickle
from tools.utils_xtdata import get_prev_trading_date
from tools.xt_subscriber import sub_whole_quote
# from tools.xt_delegate import XtDelegate

# ======== 策略常量 ========

STRATEGY_NAME = '银狐二号'

QMT_CLIENT_PATH = r'C:\国金QMT交易端模拟\userdata_mini'
QMT_ACCOUNT_ID = '55009728'
# QMT_ACCOUNT_ID = '55010470'

TARGET_STOCK_PREFIX = [
    '000', '001', '002', '003',
    # '300', '301',
    '600', '601', '603', '605',
]

PATH_HELD = './_cache/prod_hma/held_days.json'  # 记录持仓日期
PATH_DATE = './_cache/prod_hma/curr_date.json'  # 用来标记每天执行一次任务的缓存
PATH_LOGS = './_cache/prod_hma/log.txt'         # 用来存储选股和委托操作
PATH_INFO = './_cache/prod_hma/info-{}.pkl'     # 用来缓存当天计算的历史指标之类的信息

# ======== 全局变量 ========

lock_quotes_update = threading.Lock()    # 更新quotes缓存用的锁
lock_daily_prepare = threading.Lock()    # 每天更新历史数据用的锁

cache_quotes: Dict[str, Dict] = {}                  # 记录实时价格信息
cache_select: Dict[str, List] = {}                  # 记录选股历史，目的是为了去重
cache_indicators: Dict[str, Dict[str, any]] = {}    # 记录历史技术指标信息
cache_limits: Dict[str, str] = {
    'prev_datetime': '',    # 限制每秒执行一次的缓存
    'prev_minutes': '',     # 限制每分钟屏幕打印心跳的缓存
}


class p:
    S = 20
    M = 40
    N = 60
    open_inc = 0.02         # 相对于开盘价涨幅阈值
    day_count = 69          # 70个足够算出周期为60的 HMA
    data_cols = ['close']   # 历史数据需要的列


def prepare_indicator_source(cache_path: str) -> None:
    temp_indicators = load_pickle(cache_path)
    if temp_indicators is not None:
        cache_indicators.update(temp_indicators)
    else:
        history_symbols = get_all_historical_symbols()
        history_codes = [
            symbol_to_code(symbol)
            for symbol in history_symbols
            if symbol[:3] in TARGET_STOCK_PREFIX
        ]

        now = datetime.datetime.now()

        start = get_prev_trading_date(now, p.day_count)
        end = get_prev_trading_date(now, 1)
        print(f'Fetching qmt history data from {start} to {end}')

        t0 = datetime.datetime.now()
        group_size = 500
        count = 0

        # 获取需要的历史数据
        for i in range(0, len(history_codes), group_size):
            sub_codes = [sub_code for sub_code in history_codes[i:i + group_size]]
            print(f'Preparing {sub_codes}')
            data = get_xtdata_market_dict(
                codes=sub_codes,
                start_date=start,
                end_date=end,
                columns=p.data_cols,
            )

            for code in sub_codes:
                row = data['close'].loc[code]
                if not row.isna().any() and len(row) == p.day_count:
                    count += 1
                    cache_indicators[code] = {
                        'past_69': row.tail(p.day_count).values,
                    }

        t1 = datetime.datetime.now()
        print(f'Preparing time cost: {t1 - t0}')
        print(f'{count} stocks prepared.')
        save_pickle(cache_path, cache_indicators)


def get_last_hma(data: np.array, n: int):
    wma1 = ta.WMA(data, timeperiod=n // 2)
    wma2 = ta.WMA(data, timeperiod=n)
    sqrt_n = int(np.sqrt(n))

    diff = 2 * wma1 - wma2
    hma = ta.WMA(diff, timeperiod=sqrt_n)

    return hma[-1:][0]


def stock_selection(quote: dict, indicator: dict) -> (bool, dict):
    p_close = quote['lastPrice']
    p_open = quote['open']

    if not p_close > p_open:
        return False, {}

    if not p_close > p_open * p.open_inc:
        return False, {}

    ma_60 = get_last_hma(np.append(indicator['past_69'], [p_close]), 60)
    if not (p_open < ma_60 < p_close):
        return False, {}

    ma_40 = get_last_hma(np.append(indicator['past_69'], [p_close]), 40)
    if not (p_open < ma_40 < p_close):
        return False, {}

    ma_20 = get_last_hma(np.append(indicator['past_69'], [p_close]), 20)
    if not (p_open < ma_20 < p_close):
        return False, {}

    return True, {'hma20': ma_20, 'hma40': ma_40, 'hma60': ma_60}


def scan_buy(quotes: dict, curr_date: str):
    selections = []
    for code in quotes:
        if code[:3] not in TARGET_STOCK_PREFIX:
            continue

        if code not in cache_indicators:
            continue

        passed, info = stock_selection(quotes[code], cache_indicators[code])
        if passed:
            selection = {'code': code, 'price': quotes[code]["lastPrice"]}
            selection.update(info)
            selections.append(selection)

    if len(selections) > 0:  # 选出一个以上的股票
        # 记录选股历史
        if curr_date not in cache_select.keys():
            cache_select[curr_date] = []

        for selection in selections:
            if selection['code'] not in cache_select[curr_date]:
                cache_select[curr_date].append(selection['code'])
                logging.warning('选股 {}\t现价: {}\tHMA 20: {}\tHMA 40: {}\tHMA 60: {}'.format(
                    selection['code'],
                    round(selection['price'], 2),
                    round(selection['hma20'], 2),
                    round(selection['hma40'], 2),
                    round(selection['hma60'], 2),
                ))


def execute_strategy(curr_date, curr_time, quotes):
    # 预备
    if '09:10' <= curr_time <= '09:14':
        daily_once(
            lock_daily_prepare, cache_limits, PATH_DATE, '_daily_once_prepare_ind',
            curr_date, prepare_indicator_source, PATH_INFO.format(today))

    # 早盘
    elif '09:30' <= curr_time <= '11:30':
        scan_buy(quotes, curr_date)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        scan_buy(quotes, curr_date)


def callback_sub_whole(quotes: dict) -> None:
    now = datetime.datetime.now()

    # # 测试用，实盘的时候记得删掉
    # curr_date = now.strftime('%Y-%m-%d')
    # scan_buy(quotes, curr_date)

    # 每分钟输出一行开头
    curr_time = now.strftime('%H:%M')
    if cache_limits['prev_minutes'] != curr_time:
        cache_limits['prev_minutes'] = curr_time
        print(f'\n[{curr_time}]', end='')

    # 每秒钟开始的时候输出一个点
    with lock_quotes_update:
        curr_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
        cache_quotes.update(quotes)
        if cache_limits['prev_datetime'] != curr_datetime:
            cache_limits['prev_datetime'] = curr_datetime
            curr_date = now.strftime('%Y-%m-%d')

            # 只有在交易日才执行策略
            if check_today_is_open_day(curr_date):
                print('.', end='')
                execute_strategy(curr_date, curr_time, cache_quotes)
                cache_quotes.clear()
            else:
                print('x', end='')


if __name__ == '__main__':
    logging_init(path=PATH_LOGS, level=logging.INFO)

    # xt_delegate = XtDelegate(
    #     account_id=my_account_id,
    #     client_path=my_client_path,
    #     xt_callback=None,
    # )

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    daily_once(
        lock_daily_prepare, cache_limits, None, '_daily_once_prepare_ind',
        today, prepare_indicator_source, PATH_INFO.format(today))

    print('启动行情订阅...')
    check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d'))
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
