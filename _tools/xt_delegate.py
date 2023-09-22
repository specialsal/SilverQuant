import time
import datetime
from threading import Thread

from xtquant import xtconstant
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount, \
    XtOrder, XtTrade, \
    XtOrderError, XtCancelError,\
    XtOrderResponse, XtCancelOrderResponse, \
    XtAccountStatus


class XtDelegate:
    def __init__(self, account: StockAccount = None):
        self.path = r'C:\国金QMT交易端模拟\userdata_mini'

        if account is None:
            account = StockAccount('55009728', 'STOCK')
        self.account = account

        self.xt_trader = None

        self.connect()
        Thread(target=self.keep_connected).start()

    def connect(self) -> (XtQuantTrader, bool):
        print("Connecting...")
        session_id = int(time.time())  # 生成session id 整数类型 同时运行的策略不能重复
        print("Generate session_id: ", session_id)
        self.xt_trader = XtQuantTrader(self.path, session_id)

        xt_callback = XtCallback(self)
        self.xt_trader.register_callback(xt_callback)

        self.xt_trader.start()  # 启动交易线程

        connect_result = self.xt_trader.connect()  # 建立交易连接，返回0表示连接成功
        print('建立交易连接，返回 0 表示连接成功，返回值：', connect_result)
        if connect_result != 0:
            self.xt_trader = None
            return None, False

        subscribe_result = self.xt_trader.subscribe(self.account)  # 对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功
        print('订阅主推回调，返回 0 表示订阅成功，返回值：', subscribe_result)
        if subscribe_result != 0:
            self.xt_trader = None
            return None, False

        return self.xt_trader, True

    def reconnect(self) -> None:
        if self.xt_trader is None:
            print('开始重连交易接口')
            _, success = self.connect()
            if success:
                print('交易接口重连成功')
        else:
            # print('无需重连交易接口')
            pass

    def keep_connected(self) -> None:
        while True:
            time.sleep(3)
            self.reconnect()

    def order_submit(
        self,
        stock_code: str,
        order_type: int,
        order_volume: int,
        price_type: int,
        price: float,
        strategy_name: str,
        order_remark: str,
    ) -> bool:
        if self.xt_trader is not None:

            async_seq = self.xt_trader.order_stock_async(
                account=self.account,
                stock_code=stock_code,
                order_type=order_type,
                order_volume=order_volume,
                price_type=price_type,
                price=price,
                strategy_name=strategy_name,
                order_remark=order_remark,
            )
            print("async_seq: " + str(async_seq))
            return True
        else:
            return False

    def order_cancel(self, order_id):
        print('Cancel:', order_id)
        cancel_result = self.xt_trader.cancel_order_stock_async(self.account, order_id)
        print(cancel_result)
        return cancel_result

    def check_asset(self):
        asset = self.xt_trader.query_stock_asset(self.account)
        print('==== asset ====')
        print("account_type: ", asset.account_type)
        print("account_id: ", asset.account_id)
        print("cash: ", asset.cash)
        print("frozen_cash: ", asset.frozen_cash)
        print("market_value: ", asset.market_value)
        print("total_asset: ", asset.total_asset)
        return asset

    def check_order(self):
        orders = self.xt_trader.query_stock_orders(self.account, False)
        for order in orders:
            print('==== order ====')
            print("order_id: ", order.order_id)
            print("order_sysid: ", order.order_sysid)
            print("order_time: ", order.order_time)
            print("order_status: ", order.order_status)
            print("status_msg: ", order.status_msg)
        return orders

    def check_position(self):
        positions = self.xt_trader.query_credit_detail(self.account)
        for position in positions:
            print('==== position ====')
            print("stock_code: ", position.stock_code)
            print("volume: ", position.volume)
            print("can_use_volume: ", position.can_use_volume)
            print("open_price: ", position.open_price)
            print("market_value: ", position.market_value)
        return positions


class XtCallback(XtQuantTraderCallback):
    def __init__(
        self,
        delegate: XtDelegate,
    ):
        self.delegate = delegate
        # self.future_normal = asyncio.Future()
        # self.future_error = asyncio.Future()

    def on_disconnected(self):
        print(
            datetime.datetime.now(),
            "qmt connection lost, reconnecting..."
        )
        self.delegate.xt_trader = None

    def on_stock_order(self, order: XtOrder):
        # self.future_normal.set_result(order.order_remark)
        print(
            datetime.datetime.now(),
            '委托回调',
        )
        print(order.order_remark)
        print(order.order_status)
        print(order.order_id)
        self.delegate.order_cancel(order.order_id)

    def on_stock_trade(self, trade: XtTrade):
        print(
            datetime.datetime.now(),
            '成交回调',
        )
        print(trade.order_id)
        print(trade.order_sysid)
        print(trade.order_remark)

    def on_order_stock_async_response(self, response: XtOrderResponse):
        print(
            datetime.datetime.now(),
            "异步委托回调",
        )
        print(response.order_remark)

    def on_cancel_order_stock_async_response(self, response: XtCancelOrderResponse):
        print(
            datetime.datetime.now(),
            "异步撤单回调",
        )
        print(response)

    def on_order_error(self, order_error: XtOrderError):
        print(
            datetime.datetime.now(),
            "委托报错回调",
        )
        print(order_error.error_msg)
        print(order_error.order_remark)

    def on_cancel_error(self, cancel_error: XtCancelError):
        print(
            datetime.datetime.now(),
            "撤单报错回调"
        )
        print(cancel_error.error_msg)
        print(cancel_error.error_id)
        print(cancel_error.order_id)

    def on_account_status(self, status: XtAccountStatus):
        print(
            datetime.datetime.now(),
            "账号查询回调",
        )
        print(status.account_type)
        print(status.account_id)
        print(status.status)


def test_delegate(delegate: XtDelegate):
    while True:
        time.sleep(5)


if __name__ == '__main__':
    xt_delegate = XtDelegate()
    try:
        # delegate.check_asset()
        # orders = delegate.check_order()
        # delegate.check_position()

        time.sleep(1)
        xt_delegate.order_submit(
            '000001.SZ',
            xtconstant.STOCK_BUY,
            100,
            xtconstant.LATEST_PRICE,
            -1,
            'strategy_name',
            '000001.SZ action',
        )

        xt_delegate.xt_trader.run_forever()
    finally:
        print('close delegate')
        xt_delegate.xt_trader.stop()
