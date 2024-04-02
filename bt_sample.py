import math
import logging
import datetime
from types import SimpleNamespace

from xtquant import xtdata
from tools.utils_basic import logging_init, load_json, save_json
from delegate.xt_subscriber import sub_whole_quote
# from tools.xt_delegate import XtDelegate


history_finding = {}  # 选股历史

p = SimpleNamespace(
    max_count=10,  # 持股数量上限
    hold_days=2,   # 持仓天数
    amount_each=10000,  # 每个仓的价位
    upper_income=1.05,  # 止盈率
    lower_income=0.97,  # 止损率
)

path_his = './_cache/history.json'  # 记录选股历史
path_pos = './_cache/my_position.json'  # 记录持仓
path_dat = './_cache/curr_date.json'  # 用来确认是不是新的一天出现


def callback_sub_whole(quotes: dict):
    now = datetime.datetime.now()
    curr_date = now.strftime("%Y%m%d")
    curr_time = now.strftime("%H:%M")

    for symbol in quotes:
        print(curr_date, curr_time, datetime.datetime.fromtimestamp(quotes[symbol]['time'] / 1000))
        break

    if True:  # TODO: 每天 09:15 执行一次就够喽，确认一定会执行哟
        read_date = load_json(path_dat)['date']
        new_day = False
        if curr_date != read_date:
            save_json(path_dat, {'date': curr_date})
            new_day = True
            print('New day started!')

    # 盘前
    if '09:15' <= curr_time <= '09:29':
        # 新的一天决定是否要卖出持仓时间达标的股票
        if new_day:
            my_position = load_json(path_pos)

            sold_symbols = []
            for symbol in my_position.keys():
                # 所有持仓天数计数+1
                my_position[symbol]['held'] += 1
                # TODO: 达到 hold_days 的持仓卖掉

            for sold_symbol in sold_symbols:
                del my_position[sold_symbol]

            save_json(path_pos, my_position)

    # 盘中
    if '09:30' <= curr_time <= '14:56':
        my_position = load_json(path_pos)

        # TODO: 确认止盈卖还是止损卖

        # 选股
        selections = []
        for symbol in quotes:
            if symbol[:3] not in [
                '000', '001',
                '002', '003',
                '300', '301',
                '600', '601', '603', '605'
            ]:
                continue

            quote = quotes[symbol]

            last_close = quote['lastClose']
            curr_open = quote['open']
            curr_price = quote['lastPrice']

            if (curr_open < last_close * 0.98) and (curr_price > last_close * 1.02):
                if symbol not in my_position.keys():
                    selections.append({'symbol': symbol, 'price': curr_price})

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
            symbol = selections[i]['symbol']
            price = selections[i]['price']
            buy_volume = math.floor(p.amount_each / price / 100) * 100

            # TODO: 信号出现则以价格买入

            logging.info(f"buy stock: {symbol} size:{buy_volume} price:{price}")
            my_position[symbol] = {
                'held': 0,
                'cost': price,
                'volume': buy_volume,
            }
            save_json(path_pos, my_position)

    # 盘后
    if '14:57' <= curr_time <= '15:00':
        pass


if __name__ == '__main__':
    logging_init()
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
