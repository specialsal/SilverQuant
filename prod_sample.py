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
from _tools.utils_basic import logging_init, load_json, save_json
from _tools.utils_cache import check_today_is_open_day
from _tools.utils_ding import sample_send_msg
from _tools.xt_subscriber import sub_whole_quote
from _tools.xt_delegate import XtDelegate

strategy_name = '低开翻红策略'

path_hist = './_cache/prod/history.json'    # 记录选股历史
path_held = './_cache/prod/held_days.json'  # 记录持仓日期
path_date = './_cache/prod/curr_date.json'  # 用来确认是不是新的一天出现

xt_delegate = XtDelegate()

cache = {
    'prev_datetime': '',
    'prev_minutes': '',
}


class p:
    hold_days = 2           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    stop_income = 1.05      # 换仓阈值
    upper_income = 1.17     # 止盈率
    upper_income_30 = 1.37  # 止盈率:30开头创业板
    lower_income = 0.95     # 止损率
    low_open = 0.98         # 低开阈值
    turn_red_upper = 1.03   # 翻红阈值上限，防止买太高
    turn_red_lower = 1.02   # 翻红阈值下限


def before(now: datetime.datetime):
    # TODO: 每天 09:15 执行一次就够喽，确认一定会执行哟
    if True:
        new_day = False
        curr_date = now.strftime('%Y%m%d')
        read_date = load_json(path_date)

        if 'date' not in read_date.keys() or curr_date != read_date['date']:
            save_json(path_date, {'date': curr_date})
            new_day = True
            print(f'New day {curr_date} started!')

    if new_day:
        held_days = load_json(path_held)

        # 所有持仓天数计数+1
        for code in held_days.keys():
            held_days[code] += 1

        save_json(path_held, held_days)


def order_submit(
    order_type: int,
    order_code: str,
    order_volume: int,
    order_remark: str,
    order_log: str,
):
    logging.warning(order_log)
    sample_send_msg(order_log, 0)

    xt_delegate.order_submit_async(
        stock_code=order_code,
        order_type=order_type,
        order_volume=order_volume,
        price_type=xtconstant.MARKET_SZ_CONVERT_5_CANCEL,
        price=-1,
        strategy_name=strategy_name,
        order_remark=order_remark,
    )


def scan_sell(quotes: dict, positions: List[XtPosition]) -> None:
    # 卖出逻辑
    held_days = load_json(path_held)

    sold_codes = []
    for position in positions:
        code = position.stock_code
        if code in quotes.keys() and code in held_days.keys():
            # 如果有数据且有持仓时间记录
            quote = quotes[code]
            curr_price = quote['lastPrice']
            cost_price = position.open_price
            sell_volume = position.volume

            if held_days[code] > p.hold_days:  # 判断持仓超过限制
                if curr_price < cost_price * p.stop_income:  # 不满足 5% 盈利的持仓平仓
                    order_submit(xtconstant.STOCK_SELL, code, sell_volume,
                                 f'超{p.hold_days}天卖出',
                                 f'换仓卖 code: {code} size:{sell_volume}')
                    sold_codes.append(code)
            elif held_days[code] > 0:  # 判断持仓超过一天
                if curr_price <= cost_price * p.lower_income:  # 止损卖出
                    order_submit(xtconstant.STOCK_SELL, code, sell_volume,
                                 f'止损 {p.lower_income} 倍卖出',
                                 f'止损卖 code: {code} size:{sell_volume} price:{curr_price}')
                    sold_codes.append(code)
                elif curr_price >= cost_price * p.upper_income_30 and code[:2] == '30':  # 止盈卖出：创业板
                    order_submit(xtconstant.STOCK_SELL, code, sell_volume,
                                 f'止盈 {p.upper_income} 倍卖出',
                                 f'止盈卖 code: {code} size:{sell_volume} price:{curr_price}')
                    sold_codes.append(code)
                elif curr_price >= cost_price * p.upper_income:  # 止盈卖出：主板
                    order_submit(xtconstant.STOCK_SELL, code, sell_volume,
                                 f'止盈 {p.upper_income} 倍卖出',
                                 f'止盈卖 code: {code} size:{sell_volume} price:{curr_price}')
                    sold_codes.append(code)

    if len(sold_codes) > 0:
        for sold_code in sold_codes:
            del held_days[sold_code]
        save_json(path_held, held_days)


def scan_buy(quotes: dict, positions: List[XtPosition], now: datetime.datetime) -> None:
    selections = []
    position_codes = [position.stock_code for position in positions]

    # 扫描全市场选股
    for code in quotes:
        if code[:3] not in [
            '000', '001', '002', '003',
            '300', '301',
            '600', '601', '603', '605'
        ]:
            continue

        last_close = quotes[code]['lastClose']
        curr_open = quotes[code]['open']
        curr_price = quotes[code]['lastPrice']

        # 筛选符合买入条件的股票
        if ((curr_open < last_close * p.low_open)
                and (last_close * p.turn_red_upper > curr_price)
                and (last_close * p.turn_red_lower < curr_price)):
            if code not in position_codes:  # 如果目前没有持仓则记录
                selections.append({'code': code, 'price': curr_price})

    if len(selections) > 0:  # 选出一个以上的股票
        selections = sorted(selections, key=lambda x: x['price'])  # 选出的股票按照现价从小到大排序

        held_days = load_json(path_held)
        asset = xt_delegate.check_asset()

        buy_count = max(0, p.max_count - len(held_days.keys()))     # 确认剩余的仓位
        buy_count = min(buy_count, asset.cash / p.amount_each)      # 确认现金够用
        buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
        buy_count = min(buy_count, 1)                               # 限每次最多买入数量

        # 依次买入
        for i in range(buy_count):
            code = selections[i]['code']
            price = selections[i]['price']
            buy_volume = math.floor(p.amount_each / price / 100) * 100

            # 如果有可用的买点则买入
            order_submit(xtconstant.STOCK_BUY, code, buy_volume, f'买入{code}', f'买入{buy_volume}股{code}')

            # 记录持仓变化
            held_days = load_json(path_held)
            held_days[code] = 0
            save_json(path_held, held_days)

        # 记录选股历史
        history = load_json(path_hist)

        curr_date = now.strftime('%Y%m%d')
        if curr_date not in history.keys():
            history[curr_date] = []

        for selection in selections:
            if selection['code'] not in history[curr_date]:
                history[curr_date].append(selection['code'])
                logging.warning(f'记录选股历史 code: {selection["code"]} price: {selection["price"]}')
        save_json(path_hist, history)


def callback_sub_whole(quotes: dict) -> None:
    now = datetime.datetime.now()

    # 限制执行频率，每秒至多一次
    curr_datetime = now.strftime("%Y%m%d %H:%M:%S")
    if cache['prev_datetime'] != curr_datetime:
        cache['prev_datetime'] = curr_datetime
    else:
        return

    # 只有在交易日才执行
    if not check_today_is_open_day(now):
        return

    # 屏幕输出 HeartBeat 每分钟一个点
    curr_time = now.strftime('%H:%M')
    if cache['prev_minutes'] != curr_time:
        cache['prev_minutes'] = curr_time
        if curr_time[-1:] == '0':
            print('\n' + curr_time, end='')
        print('.', end='')

    # 盘前
    if '09:15' <= curr_time <= '09:29':
        before(now)

    # 早盘
    elif '09:30' <= curr_time <= '11:30':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, positions)
        scan_buy(quotes, positions, now)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, positions)

    # # 盘后
    # elif '14:57' <= curr_time <= '15:00':
    #     pass


if __name__ == '__main__':
    logging_init()
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
