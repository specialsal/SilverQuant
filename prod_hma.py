"""
TODO:
"""
import math
import logging
import datetime
import threading
from typing import List, Dict

import numpy as np
import talib as ta
from xtquant import xtdata, xtconstant
from xtquant.xttype import XtPosition, XtTrade, XtOrderError, XtOrderResponse

from data_loader.reader_xtdata import get_xtdata_market_dict
from tools.utils_basic import logging_init, symbol_to_code
from tools.utils_cache import get_all_historical_symbols, daily_once, check_today_is_open_day, \
    load_pickle, save_pickle, load_json, all_held_inc, new_held, del_held
from tools.utils_ding import sample_send_msg
from tools.utils_xtdata import get_prev_trading_date
from tools.xt_subscriber import sub_whole_quote
from tools.xt_delegate import XtDelegate, XtBaseCallback, get_holding_position_count, order_submit

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
PATH_LOGS = './_cache/prod_hma/logs.txt'        # 用来存储选股和委托操作
PATH_INFO = './_cache/prod_hma/info-{}.pkl'     # 用来缓存当天计算的历史指标之类的信息

# ======== 全局变量 ========

lock_quotes_update = threading.Lock()  # 更新quotes缓存用的锁
lock_daily_prepare = threading.Lock()  # 每天更新历史数据用的锁
lock_held_op_cache = threading.Lock()  # 操作held缓存用的锁
lock_held_days_inc = threading.Lock()  # 记录每天一次所有held+1执行用的锁

cache_quotes: Dict[str, Dict] = {}                  # 记录实时价格信息
cache_select: Dict[str, List] = {}                  # 记录选股历史，目的是为了去重
cache_indicators: Dict[str, Dict[str, any]] = {}    # 记录历史技术指标信息
cache_limits: Dict[str, str] = {
    'prev_datetime': '',    # 限制每秒执行一次的缓存
    'prev_minutes': '',     # 限制每分钟屏幕打印心跳的缓存
}


class p:
    # 下单持仓
    switch_begin = '09:31'  # 每天最早换仓时间
    hold_days = 1           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    order_premium = 0.05    # 保证成功下单成交的溢价
    # 止盈止损
    upper_income_c = 1.28   # 止盈率:30开头创业板
    upper_income = 1.168    # 止盈率
    stop_income = 1.05      # 换仓阈值
    lower_income = 0.94     # 止损率
    # 策略参数
    S = 20
    M = 40
    N = 60
    open_inc = 0.02         # 相对于开盘价涨幅阈值
    day_count = 69          # 70个足够算出周期为60的 HMA
    data_cols = ['close']   # 历史数据需要的列


class MyCallback(XtBaseCallback):
    def on_stock_trade(self, trade: XtTrade):
        if trade.order_type == xtconstant.STOCK_BUY:
            log = f'买入成交 {trade.stock_code} {trade.traded_volume}股 均价:{round(trade.traded_price, 3)}'
            logging.warning(log)
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - {log}', 0)
            new_held(lock_held_op_cache, PATH_HELD, [trade.stock_code])

        if trade.order_type == xtconstant.STOCK_SELL:
            log = f'卖出成交 {trade.stock_code} {trade.traded_volume}股 均价:{round(trade.traded_price, 3)}'
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
    print(f'All held stock day +1!')
    all_held_inc(lock_held_op_cache, PATH_HELD)


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


def scan_buy(quotes: dict, curr_date: str, positions: List[XtPosition]):
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
        selections = sorted(selections, key=lambda x: x['price'])  # 选出的股票按照现价从小到大排序

        asset = xt_delegate.check_asset()

        buy_count = max(0, p.max_count - get_holding_position_count(positions))  # 确认剩余的仓位
        buy_count = min(buy_count, asset.cash // p.amount_each)     # 确认现金够用
        buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
        buy_count = min(buy_count, 3)                               # 限每次最多买入数量
        buy_count = int(buy_count)

        # 依次买入
        for i in range(buy_count):
            code = selections[i]['code']
            price = selections[i]['price']
            buy_volume = math.floor(p.amount_each / price / 100) * 100

            # 如果有可用的买点，且无之前的委托则买入
            if buy_volume > 0:
                if (curr_date not in cache_select or code not in cache_select[curr_date]) \
                        and (code not in [position.stock_code for position in positions]):  # 如果目前没有持仓则记录
                    order_submit(xt_delegate, xtconstant.STOCK_BUY, code, price, buy_volume,
                                 '选股买单', p.order_premium, STRATEGY_NAME)
                    logging.warning(f'买入委托 {code} {buy_volume}股\t现价:{round(price, 3)}')

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


def scan_sell(quotes: dict, curr_time: str, positions: List[XtPosition]) -> None:
    # 卖出逻辑
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
                    logging.warning(f'换仓委托 {code} {sell_volume}股\t现价:{round(curr_price, 3)}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '换仓卖单', p.order_premium, STRATEGY_NAME)

            if held_days[code] > 0:
                # 判断持仓超过一天
                if curr_price <= cost_price * p.lower_income:
                    # 止损卖出
                    logging.warning(f'止损委托 {code} {sell_volume}股\t现价:{round(curr_price, 3)}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '止损卖单', p.order_premium, STRATEGY_NAME)
                elif curr_price >= cost_price * p.upper_income_c and code[:2] == '30':
                    # 止盈卖出：创业板
                    logging.warning(f'止盈委托 {code} {sell_volume}股\t现价:{round(curr_price, 3)}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '止盈卖单', p.order_premium, STRATEGY_NAME)
                elif curr_price >= cost_price * p.upper_income:
                    # 止盈卖出：主板
                    logging.warning(f'止盈委托 {code} {sell_volume}股\t现价:{round(curr_price, 3)}')
                    order_submit(xt_delegate, xtconstant.STOCK_SELL, code, curr_price, sell_volume,
                                 '止盈卖单', p.order_premium, STRATEGY_NAME)


def execute_strategy(curr_date, curr_time, quotes):
    # 预备
    if '09:10' <= curr_time <= '09:14':
        daily_once(
            lock_daily_prepare, cache_limits, PATH_DATE, '_daily_once_prepare_ind',
            curr_date, prepare_indicator_source, PATH_INFO.format(curr_date))

    # 盘前
    if '09:15' <= curr_time <= '09:29':
        daily_once(
            lock_held_days_inc, cache_limits, PATH_DATE, '_daily_once_held_inc',
            curr_date, held_increase)

    # 早盘
    elif '09:30' <= curr_time <= '11:30':
        positions = xt_delegate.check_positions()
        scan_buy(quotes, curr_date, positions)
        scan_sell(quotes, curr_time, positions)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        positions = xt_delegate.check_positions()
        scan_buy(quotes, curr_date, positions)
        scan_sell(quotes, curr_time, positions)


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
        lock_daily_prepare, cache_limits, None, '_daily_once_prepare_ind',
        today, prepare_indicator_source, PATH_INFO.format(today))

    print('启动行情订阅...')
    check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d'))
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
