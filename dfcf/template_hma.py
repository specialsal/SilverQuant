# coding=utf-8
from __future__ import print_function, absolute_import
from gm.api import *

import sys
import pandas as pd
from typing import List, Dict, Optional

import numpy as np
import talib as ta

from tools.utils_cache import get_all_historical_codes
from tools.utils_dfcf import code_to_dfcf_symbol, dfcf_symbol_to_code


_BACKTEST_INTERVAL = '60s'
_BACKTEST_START_TIME = '2023-12-01 09:30:00'
_BACKTEST_END_TIME = '2023-12-05 15:00:00'

_cache_quotes = {}

positions = {}
held_days = {}


class p:
    # 下单持仓
    switch_begin = '09:45'  # 每天最早换仓时间
    hold_days = 3           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    order_premium = 0.08    # 保证成功下单成交的溢价
    upper_buy_count = 3     # 单次选股最多买入股票数量（若单次未买进当日不会再买这只
    # 止盈止损
    upper_income = 1.15     # 止盈率（ATR失效时使用）
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
    day_count = 69          # 70个足够算出周期为60的 HMA
    data_cols = ['close', 'high', 'low']    # 历史数据需要的列


def held_increase():
    for code in held_days:
        held_days[code] += 1


def order_buy(code: str, price: float, volume: int):
    print(' 买入', code, price, volume)
    order_volume(
        symbol=code_to_dfcf_symbol(code),
        volume=volume,
        side=OrderSide_Buy,
        order_type=OrderType_Limit,
        position_effect=PositionEffect_Open,
        price=price,
    )
    positions[code] = {'price': price, 'volume': volume}
    held_days[code] = 0


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


def decide_stock(quote: Dict, indicator: Dict) -> (bool, Dict):
    curr_close = quote['lastPrice']
    curr_open = quote['open']
    last_close = quote['lastClose']

    if not curr_close > p.min_price:
        return False, {}

    if not curr_open < curr_close < last_close * p.inc_limit:
        return False, {}

    sma = get_last_sma(np.append(indicator['PAST_69'], [curr_close]), p.S)
    if not (sma < last_close):
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

    return True, {}


def calculate_indicators(data: pd.DataFrame) -> Optional[Dict]:
    row_close = data['close']
    row_high = data['high']
    row_low = data['low']

    if not row_close.isna().any() and len(row_close) == p.day_count:
        close_3d = row_close.tail(p.atr_time_period).values
        high_3d = row_high.tail(p.atr_time_period).values
        low_3d = row_low.tail(p.atr_time_period).values

        return {
            'PAST_69': row_close.tail(p.day_count).values,
            'CLOSE_3D': close_3d,
            'HIGH_3D': high_3d,
            'LOW_3D': low_3d,
        }
    return None


def select_stocks(context, quotes: Dict) -> List[Dict[str, any]]:
    selections = []
    for code in quotes:
        data = get_history_data(context, code, p.day_count, ['close', 'high', 'low'])
        temp_indicator = calculate_indicators(data)

        passed, info = decide_stock(quotes[code], temp_indicator)
        if passed:
            selection = {'code': code, 'price': quotes[code]['lastPrice']}
            selection.update(info)
            selections.append(selection)
    return selections


def scan_buy(context, quotes, curr_date, curr_time):
    selections = select_stocks(context, quotes)
    print(selections)
    # for code in quotes:
    #     quote = quotes[code]
    #
    #     last_close = quote['lastClose']
    #     curr_open = quote['open']
    #     curr_price = quote['lastPrice']
    #     last_7d_close = get_history_data(context, code, 7, ['close']).head(1)['close'][0]
    #
    #     if (
    #         curr_price > 2.00
    #         and (curr_open < last_close * p.low_open)
    #         and (last_close * p.turn_red_lower < curr_price < last_close * p.turn_red_upper)
    #         and (curr_price < last_7d_close * 1.3)
    #         and len(positions.keys()) < 10
    #         and code not in positions
    #     ):
    #         print(curr_date, curr_time, end='')
    #         order_buy(code, curr_price, int(100 // curr_price * 100))


def order_sell(code, price, volume):
    print(' 卖出', code, price, volume)
    order_volume(
        symbol=code_to_dfcf_symbol(code),
        volume=volume,
        side=OrderSide_Sell,
        order_type=OrderType_Limit,
        position_effect=PositionEffect_Close,
        price=price,
    )


def scan_sell(context, quotes, curr_date, curr_time):
    pass
    # codes_sold = set()
    # for code in positions:
    #     if code in quotes and held_days[code] > 0:
    #         curr_price = quotes[code]['lastPrice']
    #         open_price = positions[code]['price']
    #         if curr_price > open_price * 1.09:
    #             print(curr_date, curr_time, end='')
    #             codes_sold.add(code)
    #             order_sell(code, curr_price, positions[code]['volume'])
    #         if curr_price < open_price * 1.05:
    #             print(curr_date, curr_time, end='')
    #             codes_sold.add(code)
    #             order_sell(code, curr_price, positions[code]['volume'])
    #
    # for code in codes_sold:
    #     del positions[code]
    #     del held_days[code]


def execute_strategy(context, curr_date: str, curr_time: str, prev_time: str, quotes: dict):
    # 盘前
    if prev_time == '09:30':
        print(f'{curr_date} ==========')
        held_increase()

    print(curr_date, curr_time, len(quotes))
    # 早盘
    if '09:31' <= curr_time <= '11:30':
        scan_sell(context, quotes, curr_date, curr_time)
        scan_buy(context, quotes, curr_date, curr_time)
    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        scan_sell(context, quotes, curr_date, curr_time)


# ==== 框架部分 ====


def init(context):
    context.backtest_interval = _BACKTEST_INTERVAL
    context.period = p.day_count
    # context.symbol = [
    #     'SZSE.002678',
    #     # 'SZSE.000001',
    # ]
    context.symbol = [
        code_to_dfcf_symbol(code)
        for code in get_all_historical_codes({'002'})
    ]

    # 订阅行情
    subscribe(symbols=context.symbol, frequency=_BACKTEST_INTERVAL, wait_group=True)
    subscribe(symbols=context.symbol, frequency='1d', count=context.period)


def get_history_data(context, code: str, days: int, fields: list[str], frequency='1d') -> pd.DataFrame:
    return context.data(
        symbol=code_to_dfcf_symbol(code),
        frequency=frequency,
        count=days,
        fields=','.join(fields),
    )


def on_bar(context, bars):
    if bars[0]['frequency'] != context.backtest_interval:
        return

    now = bars[0]['eob']
    curr_date = now.strftime('%Y-%m-%d')
    curr_time = now.strftime('%H:%M')
    prev_time = bars[0]['bob'].strftime('%H:%M')
    # print(curr_date, curr_time, bars)

    # 如果全天无量则说明停牌：删除股票
    if curr_time == '15:00':
        suspensions = set()
        for code in _cache_quotes:
            if _cache_quotes[code]['lastPrice'] == 0:
                suspensions.add(code)
                print(f'当日停牌 {curr_date} {code} {_cache_quotes[code]}')

        for code in suspensions:
            del _cache_quotes[code]

    # 报价单改成统一的格式
    for bar in bars:
        code = dfcf_symbol_to_code(bar['symbol'])
        bar['close'] = round(bar['close'], 3)
        bar['open'] = round(bar['open'], 3)
        bar['high'] = round(bar['high'], 3)
        bar['low'] = round(bar['low'], 3)

        if code not in _cache_quotes:
            _cache_quotes[code] = {'lastClose': None}
            _cache_quotes[code]['lastPrice'] = bar['close']
            _cache_quotes[code]['open'] = bar['open']
            _cache_quotes[code]['high'] = bar['high']
            _cache_quotes[code]['low'] = bar['low']
            _cache_quotes[code]['volume'] = bar['volume']
            _cache_quotes[code]['amount'] = bar['amount']

        if prev_time > '09:30' and curr_time < '15:00':
            _cache_quotes[code]['lastPrice'] = bar['close']
            try:
                if _cache_quotes[code]['open'] == 0:
                    _cache_quotes[code]['open'] = bar['open']
            except:
                print(_cache_quotes)
            _cache_quotes[code]['high'] = max(_cache_quotes[code]['high'], bar['high'])
            _cache_quotes[code]['low'] = min(_cache_quotes[code]['low'], bar['low'])
            _cache_quotes[code]['volume'] = _cache_quotes[code]['volume'] + bar['volume']
            _cache_quotes[code]['amount'] = _cache_quotes[code]['amount'] + bar['amount']

        # 如果停牌或者开盘成交量为0则标记为0
        elif curr_time == '15:00':
            _cache_quotes[code].clear()
            _cache_quotes[code]['lastClose'] = bar['close']
            _cache_quotes[code]['lastPrice'] = 0
            _cache_quotes[code]['open'] = 0
            _cache_quotes[code]['high'] = 0
            _cache_quotes[code]['low'] = 0
            _cache_quotes[code]['volume'] = 0
            _cache_quotes[code]['amount'] = 0

    # 执行预定策略
    if '09:30' < curr_time <= '14:57':
        legal_quotes = {
            k: v
            for k, v in _cache_quotes.items()
            if v['lastClose'] is not None and v['lastPrice'] != 0
        }
        if len(legal_quotes) > 0:
            execute_strategy(context, curr_date, curr_time, prev_time, legal_quotes)


if __name__ == '__main__':
    '''
        strategy_id策略ID,由系统生成
        filename文件名,请与本文件名保持一致
        mode实时模式:MODE_LIVE回测模式:MODE_BACKTEST
        token绑定计算机的ID,可在系统设置-密钥管理中生成
        backtest_start_time回测开始时间
        backtest_end_time回测结束时间
        backtest_adjust股票复权方式不复权:ADJUST_NONE前复权:ADJUST_PREV后复权:ADJUST_POST
        backtest_initial_cash回测初始资金
        backtest_commission_ratio回测佣金比例
        backtest_slippage_ratio回测滑点比例
    '''
    run(
        strategy_id='7fb51459-7b32-11ee-8dbe-182649765b57',
        filename=sys.argv[0].split('/')[-1],
        mode=MODE_BACKTEST,
        token='970a008e02b631efd0d7fa53caeed0ee700e2342',
        backtest_start_time=_BACKTEST_START_TIME,
        backtest_end_time=_BACKTEST_END_TIME,
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=1000,
        backtest_commission_ratio=0.0001,
        backtest_slippage_ratio=0.0001,
    )
