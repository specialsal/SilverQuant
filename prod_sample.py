import logging
import datetime

from xtquant import xtdata
from _tools.utils_logging import logging_init
from _tools.xt_subscriber import sub_whole_quote
# from _tools.xt_delegate import XtDelegate


position = {}


def callback_sub_whole(datas: dict):
    for stock in datas:
        # print(stock, datas[stock])
        # （开盘价 - 前收盘价) / 前收盘价 < -2 %  ；（现价 - 前收盘价) / 前收盘价 > 2 % 则买入
        if stock[:3] in ['000', '001', '002', '300', '301', '600', '601', '603', '605']:
            last_open = datas[stock]['open']
            last_close = datas[stock]['lastClose']
            last_price = datas[stock]['lastPrice']

            if (last_open < last_close * 0.98) and (last_price > last_close * 1.02):
                today = datetime.datetime.now().strftime("%Y%m%d")

                if today not in position.keys():
                    position[today] = []

                if stock not in position[today]:
                    position[today].append(stock)
                    logging.info(f"stock:{stock} open:{last_open} last_close:{last_close} last_price:{last_price}")
                    # 执行买入逻辑 买入datas[stock]['ask'][0]


if __name__ == '__main__':
    logging_init()
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
