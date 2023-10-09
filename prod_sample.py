import math
import logging
import datetime

from xtquant import xtdata, xtconstant
from _tools.utils_basic import logging_init, load_json, save_json, symbol_to_code
from _tools.xt_subscriber import sub_whole_quote
from _tools.xt_delegate import XtDelegate

strategy_name = "低开翻红策略"

path_his = './_cache/prod/history.json'  # 记录选股历史
path_pos = './_cache/prod/my_position.json'  # 记录持仓
path_dat = './_cache/prod/curr_date.json'  # 用来确认是不是新的一天出现

xt_delegate = XtDelegate()


class p:
    hold_days = 2           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    stop_income = 1.05      # 换仓阈值
    upper_income = 1.25     # 止盈率
    lower_income = 0.95     # 止损率
    low_open = 0.98         # 低开阈值
    turn_red = 1.02         # 翻红阈值


def callback_sub_whole(quotes: dict):
    now = datetime.datetime.now()
    curr_date = now.strftime("%Y%m%d")
    curr_time = now.strftime("%H:%M")

    print(".", end='')

    # for symbol in quotes:
    #     print(curr_date, curr_time, datetime.datetime.fromtimestamp(quotes[symbol]['time'] / 1000))
    #     break

    # 盘前
    if '09:15' <= curr_time <= '09:29':
        # TODO: 每天 09:15 执行一次就够喽，确认一定会执行哟
        if True:
            new_day = False
            read_date = load_json(path_dat)
            if 'date' not in read_date.keys() or curr_date != read_date['date']:
                save_json(path_dat, {'date': curr_date})
                new_day = True
                print('New day started!')

        # 新的一天决定是否要卖出持仓时间达标的股票
        if new_day:
            my_position = load_json(path_pos)

            sold_codes = []
            for code in my_position.keys():
                # 所有持仓天数计数+1
                my_position[code]['held'] += 1

                # if my_position[code]['held'] > p.hold_days:
                #     # 达到 hold_days
                #     quote = quotes[code]
                #     curr_price = quote['lastPrice']
                #     cost = my_position[code]['cost']
                #     if curr_price < cost * p.stop_income:
                #         # 不满足 5% 盈利的持仓平仓
                #         sell_volume = my_position[code]['volume']
                #
                #         logging.info(f"换仓 stock: {code} size:{sell_volume}")
                #         xt_delegate.order_submit(
                #             stock_code=code,
                #             order_type=xtconstant.STOCK_SELL,
                #             order_volume=sell_volume,
                #             price_type=xtconstant.LATEST_PRICE,
                #             price=-1,
                #             strategy_name=strategy_name,
                #             order_remark=f'持仓超过{p.hold_days}天卖出',
                #         )
                #         sold_codes.append(code)

            for sold_code in sold_codes:
                del my_position[sold_code]

            save_json(path_pos, my_position)

    # 早盘
    elif '09:30' <= curr_time <= '11:30':

        # 止盈止损卖出
        my_position = load_json(path_pos)
        sold_codes = []
        for code in my_position.keys():
            # TODO: 判断持仓超过一天
            quote = quotes[code]
            curr_price = quote['lastPrice']
            cost = my_position[code]['cost']
            sell_volume = my_position[code]['volume']

            if curr_price >= cost * p.upper_income:
                # 止盈卖出
                logging.info(f"止盈 stock: {code} size:{sell_volume} price:{curr_price}")
                xt_delegate.order_submit(
                    stock_code=code,
                    order_type=xtconstant.STOCK_SELL,
                    order_volume=sell_volume,
                    price_type=xtconstant.LATEST_PRICE,
                    price=-1,
                    strategy_name=strategy_name,
                    order_remark=f'止盈 {p.upper_income} 倍卖出',
                )
                sold_codes.append(code)
            elif curr_price <= cost * p.lower_income:
                # 止损卖出
                logging.info(f"止损 stock: {code} size:{sell_volume} price:{curr_price}")
                xt_delegate.order_submit(
                    stock_code=code,
                    order_type=xtconstant.STOCK_SELL,
                    order_volume=sell_volume,
                    price_type=xtconstant.LATEST_PRICE,
                    price=-1,
                    strategy_name='my_strategy',
                    order_remark=f'止损 {p.upper_income} 倍卖出',
                )
                sold_codes.append(code)

        for sold_code in sold_codes:
            del my_position[sold_code]

        if len(sold_codes) > 0:
            save_json(path_pos, my_position)

        # 选股
        selections = []
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

            if (curr_open < last_close * p.low_open) and (curr_price > last_close * p.turn_red):
                if code not in my_position.keys():
                    # 如果未持仓则记录
                    selections.append({'symbol': code, 'price': curr_price})

        # 记录选股历史
        if len(selections) > 0:
            history = load_json(path_his)

            if curr_date not in history.keys():
                history[curr_date] = []

            for selection in selections:
                if selection['symbol'] not in history[curr_date]:
                    history[curr_date].append(selection['symbol'])
                    logging.info(f"select stock: {selection['symbol']}  price: {selection['price']}")
            save_json(path_his, history)

        # 选出的股票按照现价从小到大排序
        selections = sorted(selections, key=lambda x: x["price"])

        # 如果仓不满，则补仓
        buy_count = max(0, p.max_count - len(my_position.keys()))
        buy_count = min(buy_count, len(selections))  # 确认筛选出来的数量
        # buy_count = min(buy_count, broker.get_cash())  # TODO: 确认钱够用，不借贷

        for i in range(buy_count):
            code = selections[i]['symbol']
            price = selections[i]['price']
            buy_volume = math.floor(p.amount_each / price / 100) * 100

            # 信号出现则以价格买入
            logging.info(f"买入 stock: {code} size:{buy_volume} price:{price}")
            xt_delegate.order_submit(
                stock_code=symbol_to_code(code),
                order_type=xtconstant.STOCK_BUY,
                order_volume=buy_volume,
                price_type=xtconstant.FIX_PRICE,
                price=price,
                strategy_name='strategy_name',
                order_remark=f'{code} 符合条件买入 {buy_volume}',
            )

            # 记录持仓变化
            my_position = load_json(path_pos)
            my_position[code] = {
                'held': 0,
                'cost': price,
                'volume': buy_volume,
            }
            save_json(path_pos, my_position)

    # # 午盘
    # elif '13:00' <= curr_time <= '14:56':
    #     pass

    # 盘后
    elif '14:57' <= curr_time <= '15:00':
        pass


if __name__ == '__main__':
    logging_init()
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
