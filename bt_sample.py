import math
import datetime
import backtrader as bt
import pandas as pd
from typing import List

from constant import *
from _tools.utils_bt import bt_feed_pandas_datas
from _tools.utils_basic import pd_show_all, logger_init


pd_show_all()
logger = logger_init('./_data/bt_sample_log.txt')


class MyStrategy(bt.Strategy):
    params = dict(
        max_count=10,
        amount_each=10000,
        hold_days=2,
        take_profit=1.05,
        stop_loss=0.97
    )

    def __init__(self):
        self.my_position = {}

    def next(self):
        logger.error(f'===== {self.datas[0].datetime.datetime(0)} =====')

        sold_names = []
        for name in self.my_position.keys():
            # 所有持仓天数计数+1
            self.my_position[name]['held'] += 1

            data = self.getdatabyname(name)
            held = self.my_position[name]['held']  # 已持有天数
            cost = self.my_position[name]['cost']
            volume = self.my_position[name]['volume']

            sold = False
            for i in range(1, self.p.hold_days + 1):
                # 未达到止盈止损线则继续持有
                if held == i and cost * self.p.stop_loss < data.high[0] < cost * self.p.take_profit:
                    pass

                # 止盈价卖出
                elif held == i and data.high[0] >= cost * self.p.take_profit:
                    self.sell(data, size=volume, price=cost * self.p.take_profit, info=[name, 'Take Profit'])
                    sold = True

                # 止损价卖出
                elif held == i and data.low[0] <= cost * self.p.stop_loss:
                    self.sell(data, size=volume, price=cost * self.p.stop_loss, info=[name, 'Stop Loss'])
                    sold = True

            # 卖出持有 max_hold_day 天的
            if held == self.p.hold_days and not sold:
                self.sell(data, size=volume, price=data.close[0], info=[name, 'Hold Max'])
                sold = True

            if sold:
                sold_names.append(name)

        for sold_name in sold_names:
            del self.my_position[sold_name]

        # 选股
        selections = []
        for i in range(len(self.datas)):
            open = self.datas[i].open[0]
            last_price = self.datas[i].close[0]
            last_close = self.datas[i].close[-1]

            if (open < last_close * 0.98) and (last_price > last_close * 1.02):
                selections.append([i, self.datas[i]._name, last_price])

        # 按照现价从小到大排序
        selections = sorted(selections, key=lambda x: x[2])

        # 如果仓不满，则补仓
        buy_count = max(0, self.p.max_count - len(self.my_position.keys()))
        buy_count = min(buy_count, len(selections))
        if buy_count > 0:
            for i in range(buy_count):
                name = selections[i][1]
                price = selections[i][2]
                buy_volume = math.floor(self.p.amount_each / price / 100) * 100

                # 信号出现则以收盘价买入
                cash = self.broker.get_cash()
                if cash >= buy_volume * price:  # 确认钱够用，不借贷
                    self.buy(self.getdatabyname(name), size=buy_volume, price=price, info=name)
                    self.my_position[name] = {
                        'held': 0,
                        'cost': price,
                        'volume': buy_volume,
                    }

    def log(self, msg, dt=None):
        dt = dt or self.datas[0].datetime.date(0)
        logger.info(f'{dt.isoformat()}, {msg}')

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'Buy: Price %.2f\tVolume %.0f\tAmount %.2f\tCom %.2f {order.info}' %
                         (order.executed.price,
                          order.executed.size,
                          order.executed.value,
                          order.executed.comm))
            elif order.issell():
                self.log(f'Sell: Price %.2f\tVolume %.0f\tAmount %.2f\tCom %.2f {order.info}' %
                         (order.executed.price,
                          order.executed.size,
                          order.executed.value,
                          order.executed.comm))

        # elif order.status in [order.Canceled, order.Margin, order.Rejected]:
        #     self.log('Order Failed')
        #
        # elif order.status in [order.Submitted, order.Accepted, order.Partial]:
        #     self.log('Order Status: %s' % order.Status[order.status])


def checker(df: pd.DataFrame):
    return True


def run_backtest(
    symbols: List[str],
    start_date: datetime.datetime,
    end_date: datetime.datetime,
):
    cerebro = bt.Cerebro()

    start_cash = 100000
    cerebro.broker.setcash(start_cash)
    cerebro.broker.setcommission(commission=0.0001)

    t1 = datetime.datetime.now()
    all_suc = bt_feed_pandas_datas(
        cerebro,
        symbols,
        start_date,
        end_date,
        check=checker,
        data_source=DataSource.XTDATA,
    )
    cerebro.addstrategy(MyStrategy)
    print(f'All succeed: {all_suc}')

    t2 = datetime.datetime.now()
    cerebro.run()  # 运行回测系统

    t3 = datetime.datetime.now()
    end_value = cerebro.broker.getvalue()  # 获取回测结束后的总资金
    end_cash = cerebro.broker.getcash()  # 获取回测结束后的总资金
    pnl = end_value - start_cash  # 盈亏统计

    print(f"Start asset: {start_cash}")
    print(f"End asset: {round(end_value, 2)}")
    print(f"Net Benefit: {round(pnl, 2)}")
    print(f"End asset: {round(end_cash, 2)}")

    print(f"feed datas use: {t2 - t1}")
    print(f"simulation use: {t3 - t2}")

    figure = cerebro.plot(style='candlebars')[0][0]
    figure.savefig('./_data/bt_sample_log.png')


if __name__ == '__main__':
    # symbol_list = [
    #     '000001',
    #     '000002',
    #     '000003',
    #     '000004',
    # ]

    from _tools.utils_cache import get_all_historical_symbols
    symbol_list = []
    for symbol in get_all_historical_symbols():
        if symbol[:3] in [
            '000', '001',
            # '002', '003'
            # '300', '301',
            '600', '601', '603', '605'
        ]:
            symbol_list.append(symbol)

    run_backtest(
        symbol_list,
        start_date=datetime.datetime(2020, 7, 1),
        end_date=datetime.datetime(2023, 7, 1),
    )
