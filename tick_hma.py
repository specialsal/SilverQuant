"""
TODO:
"""
import time
import math
import logging
import datetime
import threading
from typing import List, Dict

import numpy as np
import talib as ta
from xtquant import xtconstant
from xtquant.xttype import XtPosition, XtTrade, XtOrderError, XtOrderResponse

import tick_accounts
from data_loader.reader_xtdata import get_xtdata_market_dict
from tools.utils_basic import logging_init, symbol_to_code
from tools.utils_cache import load_json, get_all_historical_symbols, daily_once, \
    check_today_is_open_day, load_pickle, save_pickle, all_held_inc, new_held, del_held
from tools.utils_ding import sample_send_msg
from tools.utils_xtdata import get_prev_trading_date
from tools.xt_subscriber import sub_whole_quote
from tools.xt_delegate import XtDelegate, XtBaseCallback, get_holding_position_count, order_submit, xt_stop_exit

# ======== 配置 ========
STRATEGY_NAME = '银狐二号'
QMT_ACCOUNT_ID = tick_accounts.YH_QMT_ACCOUNT_ID
QMT_CLIENT_PATH = tick_accounts.YH_QMT_CLIENT_PATH

PATH_BASE = tick_accounts.YH_CACHE_BASE_PATH
PATH_HELD = PATH_BASE + '/held_days.json'   # 记录持仓日期
PATH_DATE = PATH_BASE + '/curr_date.json'   # 用来标记每天一次的缓存
PATH_LOGS = PATH_BASE + '/logs.txt'         # 用来存储选股和委托操作
PATH_INFO = PATH_BASE + '/info-{}.pkl'      # 用来缓存当天的指标信息

lock_quotes_update = threading.Lock()       # 聚合实时打点缓存的锁
lock_held_op_cache = threading.Lock()       # 操作持仓数据缓存的锁
lock_daily_cronjob = threading.Lock()       # 标记每天一次执行的锁

cache_quotes: Dict[str, Dict] = {}          # 记录实时的价格信息
cache_select: Dict[str, set] = {}           # 记录选股历史，去重
cache_indicators: Dict[str, Dict] = {}      # 记录技术指标相关值 { code: { indicator_name: ...} }
cache_limits: Dict[str, str] = {    # 限制执行次数的缓存集合
    'prev_datetime': '',            # 限制每秒一次跑策略扫描的缓存
    'prev_minutes': '',             # 限制每分钟屏幕心跳换行的缓存
}

# ======== 策略 ========
target_stock_prefixes = {  # set
    '000', '001', '002', '003',
    # '300', '301',  # 创业板
    '600', '601', '603', '605',
    # '688', '689',  # 科创板
}


class p:
    # 下单持仓
    switch_begin = '10:30'  # 每天最早换仓时间
    hold_days = 1           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    order_premium = 0.05    # 保证成功下单成交的溢价
    upper_buy_count = 3     # 单次选股最多买入股票数量（若单次未买进当日不会再买这只
    # 止盈止损
    upper_income_c = 1.09   # 止盈率:30开头创业板
    upper_income = 1.09     # 止盈率
    stop_income = 1.05      # 换仓阈值
    lower_income = 0.97     # 止损率
    # 策略参数
    S = 20
    M = 40
    N = 60
    open_inc = 1.00         # 相对于开盘价涨幅阈值
    inc_limit = 0.05        # 相对于昨日收盘的涨幅限制
    day_count = 69          # 70个足够算出周期为60的 HMA
    data_cols = ['close']   # 历史数据需要的列


class MyCallback(XtBaseCallback):
    def on_stock_trade(self, trade: XtTrade):
        if trade.order_type == xtconstant.STOCK_BUY:
            log = f'买入成交 {trade.stock_code} {trade.traded_volume}股 均价:{trade.traded_price:.3f}'
            logging.warning(log)
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - {log}', 0)
            new_held(lock_held_op_cache, PATH_HELD, [trade.stock_code])

        if trade.order_type == xtconstant.STOCK_SELL:
            log = f'卖出成交 {trade.stock_code} {trade.traded_volume}股 均价:{trade.traded_price:.3f}'
            logging.warning(log)
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - {log}', 0)
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


def held_increase():
    all_held_inc(lock_held_op_cache, PATH_HELD)
    print(f'All held stock day +1!')


def calculate_indicators(market_dict: Dict, code: str) -> int:
    row_close = market_dict['close'].loc[code]
    if not row_close.isna().any() and len(row_close) == p.day_count:
        cache_indicators[code] = {
            'past_69': row_close.tail(p.day_count).values,
        }
        return 1
    return 0


def prepare_indicators(cache_path: str) -> None:
    temp_indicators = load_pickle(cache_path)
    if temp_indicators is not None:
        cache_indicators.update(temp_indicators)
        print(f'Prepared indicators from {cache_path}')
    else:
        history_symbols = get_all_historical_symbols()
        history_codes = [
            symbol_to_code(symbol)
            for symbol in history_symbols
            if symbol[:3] in target_stock_prefixes
        ]

        now = datetime.datetime.now()

        start = get_prev_trading_date(now, p.day_count)
        end = get_prev_trading_date(now, 1)
        print(f'Fetching qmt history data from {start} to {end}')

        t0 = datetime.datetime.now()
        group_size = 500
        count = 0
        for i in range(0, len(history_codes), group_size):
            sub_codes = [sub_code for sub_code in history_codes[i:i + group_size]]
            print(f'Preparing {sub_codes}')
            market_dict = get_xtdata_market_dict(
                codes=sub_codes,
                start_date=start,
                end_date=end,
                columns=p.data_cols)
            time.sleep(0.5)

            for code in sub_codes:
                count += calculate_indicators(market_dict, code)

        t1 = datetime.datetime.now()
        save_pickle(cache_path, cache_indicators)
        print(f'Preparing TIME COST: {t1 - t0}')
        print(f'{count} stocks prepared.')


def get_last_hma(data: np.array, n: int):
    wma1 = ta.WMA(data, timeperiod=n // 2)
    wma2 = ta.WMA(data, timeperiod=n)
    sqrt_n = int(np.sqrt(n))

    diff = 2 * wma1 - wma2
    hma = ta.WMA(diff, timeperiod=sqrt_n)

    return hma[-1:][0]


def decide_stock(quote: dict, indicator: dict) -> (bool, dict):
    p_close = quote['lastPrice']
    p_open = quote['open']

    if not p_close > p_open:
        return False, {}

    if not p_close > p_open * p.open_inc:
        return False, {}

    ma_60 = get_last_hma(np.append(indicator['past_69'], [p_close]), p.N)
    if not (p_open < ma_60 < p_close):
        return False, {}

    ma_40 = get_last_hma(np.append(indicator['past_69'], [p_close]), p.M)
    if not (p_open < ma_40 < p_close):
        return False, {}

    ma_20 = get_last_hma(np.append(indicator['past_69'], [p_close]), p.S)
    if not (p_open < ma_20 < p_close):
        return False, {}

    return True, {'hma20': ma_20, 'hma40': ma_40, 'hma60': ma_60}


def select_stocks(quotes: dict) -> list[dict[str, any]]:
    selections = []
    for code in quotes:
        if code[:3] not in target_stock_prefixes:
            continue

        if code not in cache_indicators:
            continue

        passed, info = decide_stock(quotes[code], cache_indicators[code])
        if passed:
            selection = {'code': code, 'price': quotes[code]["lastPrice"]}
            selection.update(info)
            selections.append(selection)
    return selections


def scan_buy(selections: list, curr_date: str, positions: List[XtPosition]) -> None:
    if len(selections) > 0:  # 选出一个以上的股票
        selections = sorted(selections, key=lambda x: x['price'])  # 选出的股票按照现价从小到大排序

        position_codes = [position.stock_code for position in positions]
        position_count = get_holding_position_count(positions)
        asset = xt_delegate.check_asset()

        buy_count = max(0, p.max_count - position_count)            # 确认剩余的仓位
        buy_count = min(buy_count, asset.cash // p.amount_each)     # 确认现金够用
        buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
        buy_count = min(buy_count, p.upper_buy_count)               # 限制一秒内下单数量
        buy_count = int(buy_count)

        for i in range(buy_count):  # 依次买入
            code = selections[i]['code']
            price = selections[i]['price']
            buy_volume = math.floor(p.amount_each / price / 100) * 100

            if (
                (buy_volume > 0)
                and (code not in position_codes)
                and (curr_date not in cache_select or code not in cache_select[curr_date])
            ):
                # 如果今天未被选股过 and 目前没有持仓则记录（意味着不会加仓
                order_submit(xt_delegate, xtconstant.STOCK_BUY, code, price, buy_volume,
                             '选股买单', p.order_premium, STRATEGY_NAME)
                logging.warning(f'买入委托 {code} {buy_volume}股\t现价:{price:.3f}')

        # 记录选股历史
        if curr_date not in cache_select:
            cache_select[curr_date] = set()

        for selection in selections:
            if selection['code'] not in cache_select[curr_date]:
                cache_select[curr_date].add(selection['code'])
                logging.warning('选股 {}\t现价: {}\tHMA 20: {}\tHMA 40: {}\tHMA 60: {}'.format(
                    selection['code'],
                    round(selection['price'], 2),
                    round(selection['hma20'], 2),
                    round(selection['hma40'], 2),
                    round(selection['hma60'], 2),
                ))


def scan_sell(quotes: dict, curr_time: str, positions: List[XtPosition]) -> None:
    held_days = load_json(PATH_HELD)

    for position in positions:
        code = position.stock_code
        if (code in quotes) and (code in held_days):
            # 如果有数据且有持仓时间记录
            quote = quotes[code]
            curr_price = quote['lastPrice']
            cost_price = position.open_price
            sell_volume = position.volume

            if held_days[code] > p.hold_days and curr_time >= p.switch_begin:
                # 判断持仓超过限制时间
                if cost_price * p.lower_income < curr_price < cost_price * p.stop_income:
                    # 不满足盈利的持仓平仓
                    logging.warning(f'换仓委托 {code} {sell_volume}股\t现价:{PATH_BASE + curr_price:.3f}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '换仓卖单', p.order_premium, STRATEGY_NAME)

            if held_days[code] > 0:
                # 判断持仓超过一天
                if curr_price <= cost_price * p.lower_income:
                    # 止损卖出
                    logging.warning(f'止损委托 {code} {sell_volume}股\t现价:{PATH_BASE + curr_price:.3f}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '止损卖单', p.order_premium, STRATEGY_NAME)
                elif curr_price >= cost_price * p.upper_income_c and code[:2] == '30':
                    # 止盈卖出：创业板
                    logging.warning(f'止盈委托 {code} {sell_volume}股\t现价:{PATH_BASE + curr_price:.3f}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '止盈卖单', p.order_premium, STRATEGY_NAME)
                elif curr_price >= cost_price * p.upper_income:
                    # 止盈卖出：主板
                    logging.warning(f'止盈委托 {code} {sell_volume}股\t现价:{PATH_BASE + curr_price:.3f}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '止盈卖单', p.order_premium, STRATEGY_NAME)


def execute_strategy(curr_date: str, curr_time: str, quotes: dict):
    # 盘前
    if '09:15' <= curr_time <= '09:29':
        daily_once(
            lock_daily_cronjob, cache_limits, PATH_DATE, '_daily_once_held_inc',
            curr_date, held_increase)

        daily_once(
            lock_daily_cronjob, cache_limits, PATH_DATE, '_daily_once_prepare_ind',
            curr_date, prepare_indicators, PATH_INFO.format(curr_date))

    # 早盘
    elif '09:30' <= curr_time <= '11:30':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, curr_time, positions)

        selections = select_stocks(quotes)
        scan_buy(selections, curr_date, positions)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, curr_time, positions)

        selections = select_stocks(quotes)
        scan_buy(selections, curr_date, positions)


def callback_sub_whole(quotes: dict) -> None:
    now = datetime.datetime.now()

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

    xt_delegate = XtDelegate(
        account_id=QMT_ACCOUNT_ID,
        client_path=QMT_CLIENT_PATH,
        xt_callback=MyCallback(),
    )

    # 重启时防止没有数据在这先读取历史数据
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    daily_once(
        lock_daily_cronjob, cache_limits, None, '_daily_once_prepare_ind',
        today, prepare_indicators, PATH_INFO.format(today))

    print('启动行情订阅...')
    check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d'))
    sub_whole_quote(callback_sub_whole)
    xt_stop_exit()  # 死循环 阻塞主线程退出
