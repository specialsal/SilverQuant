"""
{
    'time': 1692862230130,
    'lastPrice': 1277.511,
    'open': 1266.749,
    'high': 1284.353,
    'low': 1264.445,
    'lastClose': 1260.0969,
    'amount': 48467528500.0,
    'volume': 20545623,
    'pvolume': 2054562284,
    'stockStatus': 0,
    'openInt': 13,
    'transactionNum': 0,
    'lastSettlementPrice': 0.0,
    'settlementPrice': 0.0,
    'pe': 0.0,
    'askPrice': [0.0, 0.0, 0.0, 0.0, 0.0],
    'bidPrice': [0.0, 0.0, 0.0, 0.0, 0.0],
    'askVol': [0, 0, 0, 0, 0],
    'bidVol': [0, 0, 0, 0, 0],
    'volRatio': 0.0,
    'speed1Min': 0.0,
    'speed5Min': 0.0
}
"""
from typing import Callable
from xtquant import xtdata


def sub_quote(
    callback: Callable,
    code: str,
    count: int = -1,
    period: str = '1m',
):
    xtdata.subscribe_quote(
        code,
        period=period,
        count=count,
        callback=callback,
    )


def sub_whole_quote(
    callback: Callable,
    exchanges=None,
):
    if exchanges is None:
        exchanges = ["SH", "SZ"]
    xtdata.subscribe_whole_quote(exchanges, callback=callback)


if __name__ == '__main__':
    from _tools.utils_basic import pd_show_all
    pd_show_all()

    # 订阅单只股票的最新K线行情
    def callback_sub(data):
        # 第一个数据是缓存需要弃掉
        print('Callback triggered: ', data)

    sub_quote(callback_sub, '000001.SZ')

    # # 订阅全市场行情推送
    # def callback_sub_whole(datas: dict):
    #     for stock in datas:
    #         print(stock, datas[stock])
    # sub_whole_quote(callback_sub_whole)

    xtdata.run()  # 死循环 阻塞主线程退出
