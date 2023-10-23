"""
S = 20
M = 40
N = 60
CLOSE > OPEN
(CLOSE - OPEN) > 0.0618 * CLOSE
CLOSE > MA(CLOSE, N)
OPEN < MA(CLOSE, N)
CLOSE > MA(CLOSE, M)
OPEN < MA(CLOSE, M)
CLOSE > MA(CLOSE, S)
"""

import logging
import datetime
import threading
from typing import List, Dict

from xtquant import xtdata
from data_loader.reader_xtdata import get_xtdata_market_dict
from tools.utils_basic import logging_init, symbol_to_code
from tools.utils_cache import get_all_historical_symbols, daily_once
from tools.utils_xtdata import get_prev_trading_date, check_today_is_open_day
from tools.xt_subscriber import sub_whole_quote
# from tools.xt_delegate import XtDelegate

strategy_name = '均线策略'

my_client_path = r'C:\国金QMT交易端模拟\userdata_mini'
my_account_id = '55009728'

# 创建互斥锁
my_daily_prepare_lock = threading.Lock()

path_held = './_cache/prod_ma/held_days.json'  # 记录持仓日期
path_date = './_cache/prod_ma/curr_date.json'  # 用来标记每天执行一次任务的缓存
path_logs = './_cache/prod_ma/log.txt'         # 用来存储选股和委托操作

indicators_cache: Dict[str, Dict[str, float]] = {}

history_cache: Dict[str, List] = {}  # 记录选股历史，目的是为了去重

time_cache = {
    'prev_datetime': '',  # 限制每秒执行一次的缓存
    'prev_minutes': '',  # 限制每分钟屏幕打印心跳的缓存
}

target_stock_prefix = [
    '000', '001', '002', '003',
    '300', '301',
    '600', '601', '603', '605',
]


class p:
    S = 20
    M = 40
    N = 60
    open_inc = 0.0618


def prepare_indicator_source() -> dict:
    history_symbols = get_all_historical_symbols()
    history_codes = [
        symbol_to_code(symbol)
        for symbol in history_symbols
        if symbol[:3] in target_stock_prefix
    ]

    now = datetime.datetime.now()
    start = get_prev_trading_date(now, 59)
    end = get_prev_trading_date(now, 1)

    t0 = datetime.datetime.now()
    group_size = 500
    count = 0

    for i in range(0, len(history_codes), group_size):
        sub_codes = [sub_code for sub_code in history_codes[i:i + group_size]]
        print(f'Preparing {sub_codes}')
        data = get_xtdata_market_dict(
            codes=sub_codes,
            start_date=start,
            end_date=end,
            columns=['close'],
        )

        for code in sub_codes:
            row = data['close'].loc[code]
            if not row.isna().any() and len(row) == 59:
                count += 1
                indicators_cache[code] = {
                    'ma19': row.tail(19).mean(),
                    'ma39': row.tail(39).mean(),
                    'ma59': row.tail(59).mean(),
                }

    t1 = datetime.datetime.now()
    print(f'Preparing time cost: {t1 - t0}')
    print(f'{count} stocks prepared.')

    return indicators_cache


def stock_selection(quote: dict, indicator: dict) -> bool:
    p_close = quote['lastPrice']
    p_open = quote['open']

    if not p_close > p_open:
        return False

    if not p_close > p_open * p.open_inc:
        return False

    ma_60 = (indicator['ma59'] * 59.0 + p_close) / 60.0
    if not (p_open < ma_60 < p_close):
        return False

    ma_40 = (indicator['ma39'] * 39.0 + p_close) / 40.0
    if not (p_open < ma_40 < p_close):
        return False

    ma_20 = (indicator['ma19'] * 19.0 + p_close) / 20.0
    if not (ma_20 < p_close):
        return False

    return True


def scan_buy(quotes: dict, curr_date: str):
    selections = []
    for code in quotes:
        if code[:3] not in target_stock_prefix:
            continue

        if code not in indicators_cache:
            continue

        if stock_selection(quotes[code], indicators_cache[code]):
            selections.append({'code': code, 'price': quotes[code]["lastPrice"]})

    if len(selections) > 0:  # 选出一个以上的股票
        # 记录选股历史
        if curr_date not in history_cache.keys():
            history_cache[curr_date] = []

        for selection in selections:
            if selection['code'] not in history_cache[curr_date]:
                history_cache[curr_date].append(selection['code'])
                logging.warning(f'选股 {selection["code"]} 现价: {round(selection["price"], 3)}')


def callback_sub_whole(quotes: dict) -> None:
    now = datetime.datetime.now()

    # 限制执行频率，每秒至多一次
    curr_datetime = now.strftime("%Y%m%d %H:%M:%S")
    if time_cache['prev_datetime'] != curr_datetime:
        time_cache['prev_datetime'] = curr_datetime
    else:
        return

    # 屏幕输出 HeartBeat 每分钟一个点
    curr_time = now.strftime('%H:%M')
    if time_cache['prev_minutes'] != curr_time:
        time_cache['prev_minutes'] = curr_time
        if curr_time[-1:] == '0':
            print('\n' + curr_time, end='')
        print('.', end='')

    curr_date = now.strftime('%Y%m%d')

    # 只有在交易日才执行
    if not check_today_is_open_day(now):
        return

    # 预备
    if '09:10' <= curr_time <= '09:14':
        daily_once(
            my_daily_prepare_lock, time_cache, path_date, '_daily_once_prepare_ind',
            curr_date, prepare_indicator_source)

    # 早盘
    elif '09:30' <= curr_time <= '11:30':
        scan_buy(quotes, curr_date)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        scan_buy(quotes, curr_date)


if __name__ == '__main__':
    logging_init(path=path_logs, level=logging.INFO)

    # xt_delegate = XtDelegate(
    #     account_id=my_account_id,
    #     client_path=my_client_path,
    #     xt_callback=None,
    # )

    today = datetime.datetime.now().strftime('%Y%m%d')
    daily_once(
        my_daily_prepare_lock, time_cache, path_date, '_daily_once_prepare_ind',
        today, prepare_indicator_source)

    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
