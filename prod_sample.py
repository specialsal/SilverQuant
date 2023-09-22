import math
import json
import logging
import datetime

from xtquant import xtdata
from _tools.utils_logging import logging_init, load_json, save_json
from _tools.xt_subscriber import sub_whole_quote
# from _tools.xt_delegate import XtDelegate


history_finding = {}  # 选股历史
position = {}  # 持仓

hold_days = 2  # 持仓天数
max_count = 10 # 持股数量上限
amount_each = 10000

path_his = './data/history.json'
path_pos = './data/position.json'
path_dat = './data/curr_date.json'


def callback_sub_whole(datas: dict):
    now = datetime.datetime.now()
    curr_date = now.strftime("%Y%m%d")
    curr_time = now.strftime("%H:%M")

    read_date = load_json(path_dat)['date']
    new_day = False
    if curr_date != read_date:
        save_json(path_dat, { 'date': curr_date })
        new_day = True

    # 盘前
    if '09:15' <= curr_time <= '09:29':
        # 新的一天第一次决定是否要卖出
        if new_day:
            position = load_json(path_pos)
            for symbol in position.keys():
                position[symbol]['hold'] += 1
                if position[symbol]['hold'] == hold_days:
                    print(f"SELL {symbol} {position[symbol]['volume']}")
                    del position[symbol]
            save_json(path_pos, position)

    # 盘中
    if '09:30' <= curr_time <= '14:56':
        position = load_json(path_pos)

        # 选股并记录历史
        selections = []
        for symbol in datas:
            if symbol[:3] not in ['000', '001', '002', '300', '301', '600', '601', '603', '605']:
                continue

            last_open = datas[symbol]['open']
            last_close = datas[symbol]['lastClose']
            last_price = datas[symbol]['lastPrice']

            if (last_open < last_close * 0.98) and (last_price > last_close * 1.02):
                if symbol not in position.keys():
                    selections.append([symbol, last_price])
                    logging.info(f"stock: {symbol} open: {last_open} last_close: {last_close} last_price: {last_price}")

        # 记录选股历史
        if len(selections) > 0:
            history = load_json(path_his)
            if curr_date not in history.keys():
                history[curr_date] = []
            for selection in selections:
                history[curr_date].append(selection[0])
            save_json(path_his, history)

        # 按照现价从小到大排序
        selections = sorted(selections, key=lambda x: x[1])

        # 如果仓不满，则补仓
        buy_count = max(0, max_count - len(position.keys()))
        if buy_count > 0:
            for i in range(buy_count):
                stock = selections[i][0]
                price = selections[i][1]
                buy_volume = math.floor(amount_each / price / 100) * 100

                print(f"BUY {stock} of {buy_volume} volume in price {price}.")
                position[stock] = {
                    'hold': 0,
                    'volume': buy_volume
                }
                save_json(path_pos, position)

    # 盘后
    if '14:57' <= curr_time <= '15:00':
        pass


if __name__ == '__main__':
    logging_init()
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
