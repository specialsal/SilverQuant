"""
TODO:
"""
import time
import math
import logging
import datetime
import threading
import schedule
from typing import List, Dict

import numpy as np
import talib as ta
from xtquant import xtconstant, xtdata
from xtquant.xttype import XtPosition, XtTrade, XtOrderError, XtOrderResponse

import tick_accounts
from data_loader.reader_xtdata import get_xtdata_market_dict, pre_download_xtdata
from tools.utils_basic import logging_init
from tools.utils_cache import load_json, get_all_historical_codes, \
    check_today_is_open_day, load_pickle, save_pickle, all_held_inc, new_held, del_held
from tools.utils_ding import sample_send_msg
from tools.utils_xtdata import get_prev_trading_date
from tools.xt_delegate import XtDelegate, XtBaseCallback, get_holding_position_count, order_submit

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

cache_quotes: Dict[str, Dict] = {}          # 记录实时的价格信息
cache_select: Dict[str, List] = {}           # 记录选股历史，去重
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
    switch_begin = '09:45'  # 每天最早换仓时间
    hold_days = 3           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    order_premium = 0.05    # 保证成功下单成交的溢价
    upper_buy_count = 3     # 单次选股最多买入股票数量（若单次未买进当日不会再买这只
    # 止盈止损
    upper_income = 1.25     # 止盈率（ATR失效时使用）
    stop_income = 1.05      # 换仓阈值
    lower_income = 0.96     # 止损率（ATR失效时使用）
    atr_time_period = 3     # 计算atr的天数
    atr_upper_multi = 1.25  # 止盈atr的乘数
    atr_lower_multi = 0.85  # 止损atr的乘数
    sma_time_period = 3     # 卖点sma的天数
    # 策略参数
    L = 20                  # 选股HMA短周期
    M = 40                  # 选股HMA中周期
    N = 60                  # 选股HMA长周期
    S = 20                  # 选股SMA周期
    open_inc = 1.00         # 相对于开盘价涨幅阈值
    inc_limit = 0.05        # 相对于昨日收盘的涨幅限制
    # 历史指标
    day_count = 69          # 70个足够算出周期为60的 HMA
    data_cols = ['close', 'high', 'low']    # 历史数据需要的列


class MyCallback(XtBaseCallback):
    def on_stock_trade(self, trade: XtTrade):
        if trade.order_type == xtconstant.STOCK_BUY:
            log = f'买入成交 {trade.stock_code} {trade.traded_volume}股\t均价:{trade.traded_price:.3f}'
            logging.warning(log)
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - {log}', 0)
            new_held(lock_held_op_cache, PATH_HELD, [trade.stock_code])

        if trade.order_type == xtconstant.STOCK_SELL:
            log = f'卖出成交 {trade.stock_code} {trade.traded_volume}股\t均价:{trade.traded_price:.3f}'
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


# ======== 盘前 ========


def held_increase() -> None:
    all_held_inc(lock_held_op_cache, PATH_HELD)
    print(f'All held stock day +1!')


def calculate_indicators(market_dict: Dict, code: str) -> int:
    row_close = market_dict['close'].loc[code]
    row_high = market_dict['high'].loc[code]
    row_low = market_dict['low'].loc[code]

    if not row_close.isna().any() and len(row_close) == p.day_count:
        close_3d = row_close.tail(p.atr_time_period).values
        high_3d = row_high.tail(p.atr_time_period).values
        low_3d = row_low.tail(p.atr_time_period).values

        cache_indicators[code] = {
            'PAST_69': row_close.tail(p.day_count).values,
            'CLOSE_3D': close_3d,
            'HIGH_3D': high_3d,
            'LOW_3D': low_3d,
        }
        return 1
    return 0


def prepare_indicators() -> None:
    now = datetime.datetime.now()
    curr_date = now.strftime('%Y-%m-%d')
    cache_path = PATH_INFO.format(curr_date)
    count = p.day_count

    temp_indicators = load_pickle(cache_path)
    if temp_indicators is not None:
        cache_indicators.update(temp_indicators)
        print(f'Prepared indicators from {cache_path}')
    else:
        history_codes = get_all_historical_codes(target_stock_prefixes)

        start = get_prev_trading_date(now, count)
        end = get_prev_trading_date(now, 1)

        print(f'Download time range: {start} - {end}')
        t0 = datetime.datetime.now()
        pre_download_xtdata(
            history_codes,
            start_date=start,
            end_date=end,
        )
        t1 = datetime.datetime.now()
        print(f'Download TIME COST: {t1 - t0}')

        time.sleep(0.5)
        market_dict = get_xtdata_market_dict(
            codes=history_codes,
            start_date=start,
            end_date=end,
            columns=p.data_cols)

        count = 0
        for code in history_codes:
            count += calculate_indicators(market_dict, code)

        save_pickle(cache_path, cache_indicators)
        print(f'{count} stocks prepared.')


# ======== 买点 ========


def get_last_hma(data: np.array, n: int) -> float:
    wma1 = ta.WMA(data, timeperiod=n // 2)
    wma2 = ta.WMA(data, timeperiod=n)
    sqrt_n = int(np.sqrt(n))

    diff = 2 * wma1 - wma2
    hma = ta.WMA(diff, timeperiod=sqrt_n)

    return hma[-1:][0]


def get_last_sma(data: np.array, n: int) -> float:
    sma = ta.SMA(data, timeperiod=n)
    return sma[-1:][0]


def decide_stock(quote: dict, indicator: dict) -> (bool, dict):
    curr_close = quote['lastPrice']
    curr_open = quote['open']
    last_close = quote['lastClose']

    if not curr_close > curr_open * p.open_inc:
        return False, {}

    sma20 = get_last_sma(np.append(indicator['PAST_69'], [curr_close]), p.S)
    if not (sma20 < last_close):
        return False, {}

    hma60 = get_last_hma(np.append(indicator['PAST_69'], [curr_close]), p.N)
    if not (curr_open < hma60 < curr_close):
        return False, {}

    hma40 = get_last_hma(np.append(indicator['PAST_69'], [curr_close]), p.M)
    if not (curr_open < hma40 < curr_close):
        return False, {}

    hma20 = get_last_hma(np.append(indicator['PAST_69'], [curr_close]), p.L)
    if not (curr_open < hma20 < curr_close):
        return False, {}

    return True, {'hma20': hma20, 'hma40': hma40, 'hma60': hma60, 'sma20': sma20}


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


def scan_buy(quotes: dict, curr_date: str, positions: List[XtPosition]) -> None:
    selections = select_stocks(quotes)

    # 记录选股历史
    if curr_date not in cache_select:
        cache_select[curr_date] = []

    for selection in selections:
        if selection['code'] not in cache_select[curr_date]:
            cache_select[curr_date].append(selection['code'])
            logging.warning(
                f"记录选股 {selection['code']}"
                f"\t现价: {selection['price']:.2f}"
                f"\tHMA_20: {selection['hma20']:.2f}"
                f"\tHMA_40: {selection['hma40']:.2f}"
                f"\tHMA_60: {selection['hma60']:.2f}"
                f"\tSMA_20: {selection['sma20']:.2f}")

    # 选出一个以上的股票
    if len(selections) > 0:
        selections = sorted(selections, key=lambda x: x['price'])  # 选出的股票按照现价从小到大排序

        position_codes = [position.stock_code for position in positions]
        position_count = get_holding_position_count(positions)
        asset = xt_delegate.check_asset()

        buy_count = max(0, p.max_count - position_count)            # 确认剩余的仓位
        buy_count = min(buy_count, asset.cash // p.amount_each)     # 确认现金够用
        buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
        buy_count = min(buy_count, p.upper_buy_count)               # 限制一秒内下单数量
        buy_count = int(buy_count)
        print(f'买数相关 现有仓位{position_count} 现金{asset.cash} 本次选数{len(selections)} 仓数{p.upper_buy_count}')

        for i in range(buy_count):  # 依次买入
            code = selections[i]['code']
            price = selections[i]['price']
            buy_volume = math.floor(p.amount_each / price / 100) * 100

            if buy_volume <= 0:
                print('可买数量不足一手')
            elif code in position_codes:
                print('目前已经正在持仓')
            elif curr_date in cache_select and code in cache_select[curr_date]:
                print('今日已经选过该股')
            else:
                # 如果今天未被选股过 and 目前没有持仓则记录（意味着不会加仓
                order_submit(xt_delegate, xtconstant.STOCK_BUY, code, price, buy_volume,
                             '选股买单', p.order_premium, STRATEGY_NAME)
                logging.warning(f'买入委托 {code} {buy_volume}股\t现价:{price:.3f}')


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

            # 换仓：未满足盈利目标的仓位
            if held_days[code] > p.hold_days and curr_time >= p.switch_begin:
                if cost_price * p.lower_income < curr_price < cost_price * p.stop_income:
                    order_sell(code, curr_price, sell_volume, '换仓卖单')

            # 判断持仓超过一天
            if held_days[code] > 0:
                if (code in quotes) and (code in cache_indicators):
                    if curr_price <= cost_price * p.lower_income:
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
                                            f'ATR止损线:{cache_indicators[code]["ATR_LOWER"]}')
                            order_sell(code, curr_price, sell_volume, 'ATR止损委托', log=False)
                        elif curr_price >= atr_upper:
                            # ATR止盈卖出
                            logging.warning(f'ATR止盈委托 {code} {sell_volume}股\t现价:{curr_price:.3f}\t'
                                            f'ATR止盈线:{cache_indicators[code]["ATR_UPPER"]}')
                            order_sell(code, curr_price, sell_volume, 'ATR止盈委托', log=False)
                else:
                    if curr_price <= cost_price * p.lower_income:
                        # 默认止损卖出
                        order_sell(code, curr_price, sell_volume, 'DEF止损委托')
                    elif curr_price >= cost_price * p.upper_income:
                        # 默认止盈卖出
                        order_sell(code, curr_price, sell_volume, 'DEF止盈委托')


# ======== 框架 ========


def execute_strategy(curr_date: str, curr_time: str, quotes: dict):
    # 早盘
    if '09:30' <= curr_time <= '11:30':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, curr_time, positions)
        scan_buy(quotes, curr_date, positions)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, curr_time, positions)
        scan_buy(quotes, curr_date, positions)


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


def subscribe_tick():
    if check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        print('启动行情订阅...')
        cache_limits['sub_seq'] = xtdata.subscribe_whole_quote(["SH", "SZ"], callback=callback_sub_whole)


def unsubscribe_tick():
    if check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')) and 'sub_seq' in cache_limits:
        print('关闭行情订阅...')
        xtdata.unsubscribe_quote(cache_limits['sub_seq'])


if __name__ == '__main__':
    logging_init(path=PATH_LOGS, level=logging.INFO)
    xt_delegate = XtDelegate(
        account_id=QMT_ACCOUNT_ID,
        client_path=QMT_CLIENT_PATH,
        xt_callback=MyCallback())

    # 重启时防止没有数据在这先下载历史数据
    temp_date = datetime.datetime.now().strftime('%Y-%m-%d')
    if check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        prepare_indicators()

    # 定时任务启动
    schedule.every().day.at('09:10').do(held_increase)
    schedule.every().day.at('09:15').do(prepare_indicators)
    schedule.every().day.at('09:25').do(subscribe_tick)
    schedule.every().day.at('15:10').do(unsubscribe_tick)

    while True:
        schedule.run_pending()
        time.sleep(1)
