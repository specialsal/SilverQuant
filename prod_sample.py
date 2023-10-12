"""
TODO:
* held文件更新，只在成交回调里完成
"""

import math
import logging
import datetime
from typing import List

from xtquant.xttype import XtPosition
from xtquant import xtdata, xtconstant
from _tools.utils_basic import logging_init, load_json, save_json, symbol_to_code
from _tools.xt_subscriber import sub_whole_quote
from _tools.xt_delegate import XtDelegate

strategy_name = '低开翻红策略'

path_hist = './_cache/prod/history.json'    # 记录选股历史
path_hold = './_cache/prod/held_days.json'  # 记录持仓日期
path_date = './_cache/prod/curr_date.json'  # 用来确认是不是新的一天出现

xt_delegate = XtDelegate()

minute_flag = []


class p:
    hold_days = 2           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    stop_income = 1.05      # 换仓阈值
    upper_income = 1.18     # 止盈率
    upper_income_30 = 1.38  # 止盈率:30开头创业板
    lower_income = 0.95     # 止损率
    low_open = 0.98         # 低开阈值
    turn_red_upper = 1.03   # 翻红阈值上限，防止买太高
    turn_red_lower = 1.02   # 翻红阈值下限


def scan_sell(quotes: dict, positions: List[XtPosition]):
    # 卖出逻辑
    held_days = load_json(path_hold)

    sold_codes = []
    for position in positions:
        code = position.stock_code
        if code in quotes.keys() and code in held_days.keys():
            # 如果有数据且有持仓时间记录
            quote = quotes[code]
            curr_price = quote['lastPrice']
            cost_price = position.open_price
            volume = position.volume

            if held_days[code] > p.hold_days:  # 判断持仓超过限制
                if curr_price < cost_price * p.stop_income:
                    # 不满足 5% 盈利的持仓平仓
                    logging.warning(f'换仓卖 code: {code} size:{volume}')
                    xt_delegate.order_submit_async(
                        stock_code=code,
                        order_type=xtconstant.STOCK_SELL,
                        order_volume=volume,
                        price_type=xtconstant.LATEST_PRICE,
                        price=-1,
                        strategy_name=strategy_name,
                        order_remark=f'超{p.hold_days}天卖出',
                    )
                    sold_codes.append(code)
            elif held_days[code] > 0:  # 判断持仓超过一天
                if curr_price <= cost_price * p.lower_income:
                    # 止损卖出
                    logging.warning(f'止损卖 code: {code} size:{volume} price:{curr_price}')
                    xt_delegate.order_submit_async(
                        stock_code=code,
                        order_type=xtconstant.STOCK_SELL,
                        order_volume=volume,
                        price_type=xtconstant.LATEST_PRICE,
                        price=-1,
                        strategy_name='my_strategy',
                        order_remark=f'止损 {p.lower_income} 倍卖出',
                    )
                    sold_codes.append(code)
                elif curr_price >= cost_price * p.upper_income_30 and code[:2] == '30':
                    # 止盈卖出：创业板
                    logging.warning(f'止盈卖 code: {code} size:{volume} price:{curr_price}')
                    xt_delegate.order_submit_async(
                        stock_code=code,
                        order_type=xtconstant.STOCK_SELL,
                        order_volume=volume,
                        price_type=xtconstant.LATEST_PRICE,
                        price=-1,
                        strategy_name=strategy_name,
                        order_remark=f'止盈 {p.upper_income} 倍卖出',
                    )
                    sold_codes.append(code)
                elif curr_price >= cost_price * p.upper_income:
                    # 止盈卖出：主板
                    logging.warning(f'止盈卖 code: {code} size:{volume} price:{curr_price}')
                    xt_delegate.order_submit_async(
                        stock_code=code,
                        order_type=xtconstant.STOCK_SELL,
                        order_volume=volume,
                        price_type=xtconstant.LATEST_PRICE,
                        price=-1,
                        strategy_name=strategy_name,
                        order_remark=f'止盈 {p.upper_income} 倍卖出',
                    )
                    sold_codes.append(code)

    if len(sold_codes) > 0:
        for sold_code in sold_codes:
            del held_days[sold_code]
        save_json(path_hold, held_days)


def callback_sub_whole(quotes: dict):
    now = datetime.datetime.now()
    curr_date = now.strftime('%Y%m%d')
    curr_time = now.strftime('%H:%M')

    if curr_date + curr_time not in minute_flag:
        if curr_time[-1:] == '0':
            print('\n' + curr_time, end='')

        minute_flag.append(curr_date + curr_time)
        print('.', end='')

    # for symbol in quotes:
    #     print(curr_date, curr_time, datetime.datetime.fromtimestamp(quotes[symbol]['time'] / 1000))
    #     break

    # 盘前
    if '09:15' <= curr_time <= '09:29':
        # TODO: 每天 09:15 执行一次就够喽，确认一定会执行哟
        if True:
            new_day = False
            read_date = load_json(path_date)
            if 'date' not in read_date.keys() or curr_date != read_date['date']:
                save_json(path_date, {'date': curr_date})
                new_day = True
                print('New day started!')

        if new_day:
            my_position = load_json(path_hold)

            # 所有持仓天数计数+1
            for code in my_position.keys():
                my_position[code]['held'] += 1

            save_json(path_hold, my_position)

    # 早盘
    elif '09:30' <= curr_time <= '11:30':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, positions)

        # 选股
        selections = []
        position_codes = [position.stock_code for position in positions]

        for code in quotes:
            if code[:3] not in [
                '000', '001',
                '002', '003',
                '300', '301',
                '600', '601', '603', '605'
            ]:
                continue

            quote = quotes[code]

            last_close = quote['lastClose']
            curr_open = quote['open']
            curr_price = quote['lastPrice']

            if (
                (curr_open < last_close * p.low_open)
                and (last_close * p.turn_red_lower < curr_price < last_close * p.turn_red_upper)
            ):
                if code not in position_codes:
                    # 如果未持仓则记录
                    selections.append({'symbol': code, 'price': curr_price})

        if len(selections) > 0:
            # 选出的股票按照现价从小到大排序
            selections = sorted(selections, key=lambda x: x['price'])

            # 如果仓不满，则补仓
            held_days = load_json(path_hold)

            # 确认买入的仓位数
            asset = xt_delegate.check_asset()

            buy_count = max(0, p.max_count - len(held_days.keys()))     # 确认剩余的仓位
            buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
            buy_count = min(buy_count, asset.cash / p.amount_each)      # 确认现金够用

            # 依次买入
            for i in range(buy_count):
                code = selections[i]['symbol']
                price = selections[i]['price']
                buy_volume = math.floor(p.amount_each / price / 100) * 100

                # 如果有可用的买点则买入，记录的成本可能有滑点
                xt_delegate.order_submit_async(
                    stock_code=symbol_to_code(code),
                    order_type=xtconstant.STOCK_BUY,
                    order_volume=buy_volume,
                    price_type=xtconstant.LATEST_PRICE,
                    price=-1,
                    strategy_name=strategy_name,
                    order_remark=f'买入{buy_volume}股{code}',
                )

                # 记录持仓变化
                held_days = load_json(path_hold)
                held_days[code] = 0
                save_json(path_hold, held_days)

            # 记录选股历史
            history = load_json(path_hist)

            if curr_date not in history.keys():
                history[curr_date] = []

            for selection in selections:
                if selection['symbol'] not in history[curr_date]:
                    history[curr_date].append(selection['symbol'])
                    logging.warning(f'选股 symbol: {selection["symbol"]}  price: {selection["price"]}')
            save_json(path_hist, history)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, positions)

    # 盘后
    elif '14:57' <= curr_time <= '15:00':
        pass


if __name__ == '__main__':
    logging_init()
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
