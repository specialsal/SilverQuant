"""
TODO:
"""
import time
import math
import logging
import datetime
import threading
import schedule
from random import random
from typing import List, Dict, Set, Optional, Union

import numpy as np
import pandas as pd
import talib as ta
import pywencai
from xtquant import xtconstant, xtdata
from xtquant.xttype import XtPosition, XtTrade, XtOrderError, XtOrderResponse

import tick_accounts
from data_loader.reader_tushare import get_ts_markets
from tools.utils_basic import logging_init
from tools.utils_cache import load_json, get_all_historical_codes, get_blacklist_codes, \
    check_today_is_open_day, load_pickle, save_pickle, all_held_inc, new_held, del_held
from tools.utils_ding import sample_send_msg
from tools.utils_xtdata import get_prev_trading_date
from tools.xt_delegate import XtDelegate, XtBaseCallback, get_holding_position_count, order_submit

# ======== 配置 ========
STRATEGY_NAME = '问财策略'
QMT_ACCOUNT_ID = tick_accounts.DB_QMT_ACCOUNT_ID
QMT_CLIENT_PATH = tick_accounts.DB_QMT_CLIENT_PATH

PATH_BASE = tick_accounts.DB_CACHE_BASE_PATH
PATH_HELD = PATH_BASE + '/held_days.json'   # 记录持仓日期
PATH_DATE = PATH_BASE + '/curr_date.json'   # 用来标记每天一次的缓存
PATH_LOGS = PATH_BASE + '/logs.txt'         # 用来存储选股和委托操作
PATH_INFO = PATH_BASE + '/info-{}.pkl'      # 用来缓存当天的指标信息

lock_quotes_update = threading.Lock()       # 聚合实时打点缓存的锁
lock_held_op_cache = threading.Lock()       # 操作持仓数据缓存的锁

cache_blacklist: Set[str] = set()           # 记录黑名单中的股票
cache_quotes: Dict[str, Dict] = {}          # 记录实时的价格信息
cache_select: Dict[str, Set] = {}           # 记录选股历史，去重
cache_indicators: Dict[str, Dict] = {}      # 记录技术指标相关值 { code: { indicator_name: ...} }
cache_limits: Dict[str, str] = {    # 限制执行次数的缓存集合
    'prev_seconds': '',             # 限制每秒一次跑策略扫描的缓存
    'prev_minutes': '',             # 限制每分钟屏幕心跳换行的缓存
}

# ======== 策略 ========
target_stock_prefixes = {  # set
    '000', '001', '002', '003',
    # '300', '301',  # 创业板
    '600', '601', '603', '605',
    # '688', '689',  # 科创板
}

# query = '上一周增持；非ST；主板；昨日流通市值从小到大排序'
query = '向上突破20日均线，主板，涨幅大于4%，非ST，量比大于1.47，委比大于0'


class p:
    # 下单持仓
    switch_begin = '09:45'  # 每天最早换仓时间
    hold_days = 3           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    order_premium = 0.08    # 保证成功下单成交的溢价
    upper_buy_count = 3     # 单次选股最多买入股票数量（若单次未买进当日不会再买这只
    # 止盈止损
    upper_income = 1.45     # 止盈率（ATR失效时使用）
    lower_income = 0.97     # 止损率（ATR失效时使用）
    sw_upper_multi = 0.02   # 换仓上限乘数
    sw_lower_multi = 0.005  # 换仓下限乘数
    atr_time_period = 3     # 计算atr的天数
    atr_upper_multi = 1.25  # 止盈atr的乘数
    atr_lower_multi = 0.85  # 止损atr的乘数
    sma_time_period = 3     # 卖点sma的天数
    # 策略参数
    L = 20                  # 选股HMA短周期
    M = 40                  # 选股HMA中周期
    N = 60                  # 选股HMA长周期
    S = 5                   # 选股SMA周期
    inc_limit = 1.02        # 相对于昨日收盘的涨幅限制
    min_price = 2.00        # 限制最低可买入股票的现价
    # 历史指标
    day_count = 5           # 3天atr和sma，5天够用
    data_cols = ['close', 'high', 'low']    # 历史数据需要的列


class MyCallback(XtBaseCallback):
    def on_stock_trade(self, trade: XtTrade):
        if trade.order_type == xtconstant.STOCK_BUY:
            log = f'买入成交 {trade.stock_code} 量{trade.traded_volume}\t价{trade.traded_price:.2f}'
            logging.warning(log)
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - {log}', 0, '+')
            new_held(lock_held_op_cache, PATH_HELD, [trade.stock_code])

        if trade.order_type == xtconstant.STOCK_SELL:
            log = f'卖出成交 {trade.stock_code} 量{trade.traded_volume}\t价{trade.traded_price:.2f}'
            logging.warning(log)
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - {log}', 0, '-')
            del_held(lock_held_op_cache, PATH_HELD, [trade.stock_code])

    # def on_stock_order(self, order: XtOrder):
    #     log = f'委托回调 id:{order.order_id} code:{order.stock_code} remark:{order.order_remark}',
    #     logging.warning(log)

    def on_order_stock_async_response(self, res: XtOrderResponse):
        log = f'异步委托回调 id:{res.order_id} sysid:{res.error_msg} remark:{res.order_remark}',
        logging.warning(log)

    def on_order_error(self, err: XtOrderError):
        log = f'委托报错 id:{err.order_id} error_id:{err.error_id} error_msg:{err.error_msg}'
        logging.warning(log)


# ======== 盘前 ========


def held_increase() -> None:
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    all_held_inc(lock_held_op_cache, PATH_HELD)
    print(f'All held stock day +1!')


def refresh_blacklist():
    cache_blacklist.clear()
    black_codes = get_blacklist_codes(target_stock_prefixes)
    cache_blacklist.update(black_codes)
    print(f'Blacklist refreshed: {black_codes}')


def calculate_indicators(data: Union[Dict, pd.DataFrame]) -> Optional[Dict]:
    row_close = data['close']
    row_high = data['high']
    row_low = data['low']

    close_3d = row_close.tail(p.atr_time_period).values
    high_3d = row_high.tail(p.atr_time_period).values
    low_3d = row_low.tail(p.atr_time_period).values

    return {
        'CLOSE_3D': close_3d,
        'HIGH_3D': high_3d,
        'LOW_3D': low_3d,
    }


def prepare_by_tushare(history_codes: List, start: str, end: str) -> int:
    print(f'Prepared time range: {start} - {end}')
    t0 = datetime.datetime.now()

    cache_indicators.clear()
    count = 0

    group_size = min(6000 // p.day_count, 300)  # ts接口最大行数限制8000，保险起见设成6000
    for i in range(0, len(history_codes), group_size):
        sub_codes = [sub_code for sub_code in history_codes[i:i + group_size]]
        temp_data = get_ts_markets(sub_codes, start, end, p.data_cols)
        print(sub_codes)

        for code in sub_codes:
            temp_df = temp_data[temp_data['ts_code'] == code]
            if not temp_df.isnull().values.any() and len(temp_df) == p.day_count:
                cache_indicators[code] = calculate_indicators(temp_df)
                count += 1

    t1 = datetime.datetime.now()
    print(f'Prepared TIME COST: {t1 - t0}')
    return count


def prepare_indicators() -> None:
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    now = datetime.datetime.now()
    curr_date = now.strftime('%Y-%m-%d')
    cache_path = PATH_INFO.format(curr_date)
    day_count = p.day_count

    temp_indicators = load_pickle(cache_path)
    if temp_indicators is not None and len(temp_indicators) > 0:
        cache_indicators.update(temp_indicators)
        print(f'Prepared indicators from {cache_path}')
    else:
        history_codes = get_all_historical_codes(target_stock_prefixes)

        start = get_prev_trading_date(now, day_count)
        end = get_prev_trading_date(now, 1)

        count = prepare_by_tushare(history_codes, start, end)
        save_pickle(cache_path, cache_indicators)
        print(f'{count} stock indicators saved to {cache_path}')


# ======== 买点 ========


def decide_stock(quote: Dict, indicator: Dict) -> (bool, Dict):
    return True, {}


def select_stocks(quotes: Dict) -> List[Dict[str, any]]:

    selections = []

    df = pywencai.get(query=query)
    wencai_selected = []
    if df.shape[0] > 0:
        wencai_selected = df['股票代码'].to_list()
        print(wencai_selected)

    for code in quotes:
        if code[:3] not in target_stock_prefixes:
            continue

        if code not in cache_indicators:
            continue

        if code not in cache_blacklist and code in wencai_selected:    # 如果不在黑名单
            passed, info = decide_stock(quotes[code], cache_indicators[code])
            if passed:
                selection = {'code': code, 'price': quotes[code]['lastPrice']}
                selection.update(info)
                selections.append(selection)
    return selections


def scan_buy(quotes: Dict, curr_date: str, positions: List[XtPosition]) -> None:
    selections = select_stocks(quotes)
    print(selections)

    # 选出一个以上的股票
    if len(selections) > 0:
        # selections = sorted(selections, key=lambda x: x['price'])  # 选出的股票按照现价从小到大排序

        position_codes = [position.stock_code for position in positions]
        position_count = get_holding_position_count(positions)
        available_cash = xt_delegate.check_asset().cash

        buy_count = max(0, p.max_count - position_count)            # 确认剩余的仓位
        buy_count = min(buy_count, available_cash // p.amount_each)     # 确认现金够用
        buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
        buy_count = min(buy_count, p.upper_buy_count)               # 限制一秒内下单数量
        buy_count = int(buy_count)

        for i in range(len(selections)):  # 依次买入
            logging.debug(f'买数相关：持仓{position_count} 现金{available_cash} 已选{len(selections)}')
            if buy_count > 0:
                code = selections[i]['code']
                price = selections[i]['price']
                buy_volume = math.floor(p.amount_each / price / 100) * 100

                if buy_volume <= 0:
                    logging.debug(f'{code} 价格过高')
                elif code in position_codes:
                    logging.debug(f'{code} 正在持仓')
                elif curr_date in cache_select and code in cache_select[curr_date]:
                    logging.debug(f'{code} 今日已选')
                else:
                    buy_count = buy_count - 1
                    # 如果今天未被选股过 and 目前没有持仓则记录（意味着不会加仓
                    order_submit(xt_delegate, xtconstant.STOCK_BUY, code, price, buy_volume,
                                 '选股买单', p.order_premium, STRATEGY_NAME)
                    logging.warning(f'买入委托 {code} {buy_volume}股\t现价:{price:.3f}')
            else:
                break

    # 记录选股历史
    if curr_date not in cache_select:
        cache_select[curr_date] = set()

    for selection in selections:
        if selection['code'] not in cache_select[curr_date]:
            cache_select[curr_date].add(selection['code'])
            logging.warning(
                f"记录选股 {selection['code']}"
                f"\t现价: {selection['price']:.2f}")


# ======== 卖点 ========


def get_sma(row_close, period) -> float:
    sma = ta.SMA(row_close, timeperiod=period)
    return sma[-1]


def get_atr(row_close, row_high, row_low, period) -> float:
    atr = ta.ATR(row_high, row_low, row_close, timeperiod=period)
    return atr[-1]


def order_sell(code, price, volume, remark, log=True):
    if log:
        logging.warning(f'{remark} {code} {volume}股\t现价:{price:.3f}')
    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, price, volume, remark, p.order_premium, STRATEGY_NAME)


def scan_sell(quotes: Dict, curr_time: str, positions: List[XtPosition]) -> None:
    held_days = load_json(PATH_HELD)

    for position in positions:
        code = position.stock_code
        if (code in quotes) and (code in held_days):
            # 如果有数据且有持仓时间记录
            quote = quotes[code]
            curr_price = quote['lastPrice']
            cost_price = position.open_price
            sell_volume = position.volume

            # 换仓：未满足盈利目标的仓位
            held_day = held_days[code]
            switch_upper = cost_price * (1 + held_day * p.sw_upper_multi)
            switch_lower = cost_price * (p.lower_income + held_day * p.sw_lower_multi)

            if held_day > p.hold_days and curr_time >= p.switch_begin:
                if switch_lower < curr_price < switch_upper:
                    order_sell(code, curr_price, sell_volume, '换仓卖单')

            # 判断持仓超过一天
            if held_day > 0:
                if (code in quotes) and (code in cache_indicators):
                    if curr_price <= switch_lower:
                        # 绝对止损卖出
                        order_sell(code, curr_price, sell_volume, 'ABS止损委托')
                    elif curr_price >= cost_price * p.upper_income:
                        # 绝对止盈卖出
                        order_sell(code, curr_price, sell_volume, 'ABS止盈委托')
                    else:
                        quote = quotes[code]
                        close = np.append(cache_indicators[code]['CLOSE_3D'], quote['lastPrice'])
                        high = np.append(cache_indicators[code]['HIGH_3D'], quote['high'])
                        low = np.append(cache_indicators[code]['LOW_3D'], quote['low'])

                        sma = get_sma(close, p.sma_time_period)
                        atr = get_atr(close, high, low, p.atr_time_period)

                        atr_upper = sma + atr * p.atr_upper_multi
                        atr_lower = sma - atr * p.atr_lower_multi

                        if curr_price <= atr_lower:
                            # ATR止损卖出
                            logging.warning(f'ATR止损委托 {code} {sell_volume}股\t现价:{curr_price:.3f}\t'
                                            f'ATR止损线:{atr_lower}')
                            order_sell(code, curr_price, sell_volume, 'ATR止损委托', log=False)
                        elif curr_price >= atr_upper:
                            # ATR止盈卖出
                            logging.warning(f'ATR止盈委托 {code} {sell_volume}股\t现价:{curr_price:.3f}\t'
                                            f'ATR止盈线:{atr_upper}')
                            order_sell(code, curr_price, sell_volume, 'ATR止盈委托', log=False)
                else:
                    if curr_price <= switch_lower:
                        # 默认绝对止损卖出
                        order_sell(code, curr_price, sell_volume, 'DEF止损委托')
                    elif curr_price >= cost_price * p.upper_income:
                        # 默认绝对止盈卖出
                        order_sell(code, curr_price, sell_volume, 'DEF止盈委托')


# ======== 框架 ========


def execute_sell_strategy(curr_date: str, curr_time: str, quotes: Dict):
    # 早盘
    if '09:31' <= curr_time <= '11:30':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, curr_time, positions)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, curr_time, positions)


def execute_buy_strategy(curr_date: str, curr_time: str, quotes: Dict):
    positions = xt_delegate.check_positions()
    scan_buy(quotes, curr_date, positions)


def callback_sub_whole(quotes: Dict) -> None:
    now = datetime.datetime.now()

    # 每分钟输出一行开头
    curr_date = now.strftime('%Y-%m-%d')
    curr_time = now.strftime('%H:%M')
    if cache_limits['prev_minutes'] != curr_time:
        cache_limits['prev_minutes'] = curr_time
        print(f'\n[{curr_time}]', end='')
        if check_today_is_open_day(curr_date):
            execute_buy_strategy(curr_date, curr_time, cache_quotes)

    # 每秒钟开始的时候输出一个点
    with lock_quotes_update:
        curr_seconds = now.strftime('%H:%M:%S')
        cache_quotes.update(quotes)
        if cache_limits['prev_seconds'] != curr_seconds:
            cache_limits['prev_seconds'] = curr_seconds

            # 只有在交易日才执行策略
            if check_today_is_open_day(curr_date):
                print('.' if len(cache_quotes) > 0 else 'x', end='')
                execute_sell_strategy(curr_date, curr_time, cache_quotes)
                cache_quotes.clear()
            else:
                print('_', end='')


def subscribe_tick():
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    print('[启动行情订阅]', end='')
    cache_limits['sub_seq'] = xtdata.subscribe_whole_quote(["SH", "SZ"], callback=callback_sub_whole)


def unsubscribe_tick():
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    if 'sub_seq' in cache_limits:
        xtdata.unsubscribe_quote(cache_limits['sub_seq'])
        print('\n[关闭行情订阅]')


def random_check_open_day():
    now = datetime.datetime.now()
    curr_date = now.strftime('%Y-%m-%d')
    curr_time = now.strftime('%H:%M')
    logging.warning(f'================')
    print(f'[{curr_time}]', end='')
    check_today_is_open_day(curr_date)


if __name__ == '__main__':
    logging_init(path=PATH_LOGS, level=logging.INFO)
    xt_delegate = XtDelegate(
        account_id=QMT_ACCOUNT_ID,
        client_path=QMT_CLIENT_PATH,
        xt_callback=MyCallback())

    # 重启时防止没有数据在这先加载历史数据
    temp_now = datetime.datetime.now()
    temp_date = temp_now.strftime('%Y-%m-%d')
    temp_time = temp_now.strftime('%H:%M')

    if '09:15' < temp_time and check_today_is_open_day(temp_date):
        prepare_indicators()
        # 重启如果在交易时间则订阅Tick
        if '09:30' <= temp_time <= '14:57':
            subscribe_tick()

    # 定时任务启动
    random_time = f'08:{str(math.floor(random() * 60)).zfill(2)}'
    schedule.every().day.at(random_time).do(random_check_open_day)
    schedule.every().day.at('09:10').do(held_increase)
    schedule.every().day.at('09:11').do(refresh_blacklist)
    schedule.every().day.at('09:15').do(prepare_indicators)
    schedule.every().day.at('09:25').do(subscribe_tick)
    schedule.every().day.at('15:00').do(unsubscribe_tick)

    while True:
        schedule.run_pending()
        time.sleep(1)
