import time
import datetime
from threading import Thread
from typing import List

from xtquant import xtconstant
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount, XtPosition, XtOrder, XtTrade, XtAsset, \
    XtOrderError, XtCancelError, XtOrderResponse, XtCancelOrderResponse, XtAccountStatus

from tools.utils_basic import get_code_exchange


default_client_path = r'C:\国金QMT交易端模拟\userdata_mini'
default_account_id = '55009728'


class XtDelegate:
    def __init__(self, account_id: str = None, client_path: str = None, xt_callback: object = None):
        self.xt_trader = None

        if client_path is None:
            client_path = default_client_path
        self.path = client_path

        if account_id is None:
            account_id = default_account_id
        self.account = StockAccount(account_id=account_id, account_type='STOCK')
        self.callback = xt_callback
        self.connect(self.callback)
        # 保证QMT持续连接
        Thread(target=self.keep_connected).start()

    def connect(self, callback: object) -> (XtQuantTrader, bool):
        print("连接中...")
        session_id = int(time.time())  # 生成session id 整数类型 同时运行的策略不能重复
        print("生成临时 session_id: ", session_id)
        self.xt_trader = XtQuantTrader(self.path, session_id)

        if callback is None:
            callback = XtDefaultCallback()

        callback.delegate = self
        self.xt_trader.register_callback(callback)

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
            _, success = self.connect(self.callback)
            if success:
                print('交易接口重连成功')
        # else:
        #     print('无需重连交易接口')
        #     pass

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
            self.xt_trader.order_stock(
                account=self.account,
                stock_code=stock_code,
                order_type=order_type,
                order_volume=order_volume,
                price_type=price_type,
                price=price,
                strategy_name=strategy_name,
                order_remark=order_remark,
            )
            return True
        else:
            return False

    def order_submit_async(
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
            self.xt_trader.order_stock_async(
                account=self.account,
                stock_code=stock_code,
                order_type=order_type,
                order_volume=order_volume,
                price_type=price_type,
                price=price,
                strategy_name=strategy_name,
                order_remark=order_remark,
            )
            return True
        else:
            return False

    def order_cancel(self, order_id) -> int:
        cancel_result = self.xt_trader.cancel_order_stock(self.account, order_id)
        return cancel_result

    def order_cancel_async(self, order_id) -> int:
        cancel_result = self.xt_trader.cancel_order_stock_async(self.account, order_id)
        return cancel_result

    def check_asset(self) -> XtAsset:
        return self.xt_trader.query_stock_asset(self.account)

    def check_order(self, order_id) -> XtOrder:
        return self.xt_trader.query_stock_order(self.account, order_id)

    def check_orders(self) -> List[XtOrder]:
        return self.xt_trader.query_stock_orders(self.account, False)

    def check_positions(self) -> List[XtPosition]:
        return self.xt_trader.query_stock_positions(self.account)


class XtBaseCallback(XtQuantTraderCallback):
    def __init__(self):
        self.delegate = None

    def on_disconnected(self):
        print(
            datetime.datetime.now(),
            '连接丢失，断线重连中...'
        )
        if self.delegate is not None:
            self.delegate.xt_trader = None


class XtDefaultCallback(XtBaseCallback):
    def on_stock_trade(self, trade: XtTrade):
        print(
            datetime.datetime.now(),
            f'成交回调 id:{trade.order_id} code:{trade.stock_code} remark:{trade.order_remark}',
        )

    def on_stock_order(self, order: XtOrder):
        print(
            datetime.datetime.now(),
            f'委托回调 id:{order.order_id} code:{order.stock_code} remark:{order.order_remark}',
        )

    def on_order_stock_async_response(self, res: XtOrderResponse):
        print(
            datetime.datetime.now(),
            f'异步委托回调 id:{res.order_id} sysid:{res.error_msg} remark:{res.order_remark}',
        )

    def on_order_error(self, order_error: XtOrderError):
        print(
            datetime.datetime.now(),
            f'委托报错回调 id:{order_error.order_id} error_id:{order_error.error_id} error_msg:{order_error.error_msg}',
        )

    def on_cancel_order_stock_async_response(self, res: XtCancelOrderResponse):
        print(
            datetime.datetime.now(),
            f'异步撤单回调 id:{res.order_id} sysid:{res.order_sysid} result:{res.cancel_result}',
        )

    def on_cancel_error(self, cancel_error: XtCancelError):
        print(
            datetime.datetime.now(),
            f'撤单报错回调 id:{cancel_error.order_id} error_id:{cancel_error.error_id} error_msg:{cancel_error.error_msg}',
        )

    # def on_account_status(self, status: XtAccountStatus):
    #     print(
    #         datetime.datetime.now(),
    #         f'账号查询回调: id:{status.account_id} type:{status.account_type} status:{status.status} ',
    #     )


def sell_all_positions(delegate: XtDelegate):
    positions = delegate.check_positions()
    for position in positions:
        if position.volume > 0:
            xt_delegate.order_submit_async(
                stock_code=position.stock_code,
                order_type=xtconstant.STOCK_SELL,
                order_volume=position.volume,
                price_type=xtconstant.LATEST_PRICE,
                price=-1,
                strategy_name='系统工具',
                order_remark='一键卖空',
            )


def order_submit(
    order_type: int,
    code: str,
    curr_price: float,
    order_volume: int,
    order_remark: str,
    order_premium: float = 0.0,
    strategy_name: str = '',
):
    price_type = xtconstant.LATEST_PRICE
    price = -1
    if get_code_exchange(code) == 'SZ':
        price_type = xtconstant.MARKET_SZ_CONVERT_5_CANCEL
        price = -1
    if get_code_exchange(code) == 'SH':
        price_type = xtconstant.MARKET_PEER_PRICE_FIRST
        if order_type == xtconstant.STOCK_SELL:
            price = curr_price - order_premium
        elif order_type == xtconstant.STOCK_BUY:
            price = curr_price + order_premium

    xt_delegate.order_submit(
        stock_code=code,
        order_type=order_type,
        order_volume=order_volume,
        price_type=price_type,
        price=price,
        strategy_name=strategy_name,
        order_remark=order_remark,
    )


def is_position_holding(position: XtPosition):
    return position.volume > 0


def get_holding_position_count(positions: List[XtPosition]):
    return sum(1 for position in positions if is_position_holding(position))


def get_profit(delegate: XtDelegate):
    positions = delegate.check_positions()
    profits = 0

    for position in positions:
        if is_position_holding(position):
            profit = (position.market_value - position.volume * position.open_price)
            print(position.stock_code, profit)
            profits += profit
    print(profits)


if __name__ == '__main__':
    xt_delegate = XtDelegate()
    try:
        time.sleep(0.5)

        # asset = xt_delegate.check_asset()
        # print('==== asset ====')
        # print("account_type: ", asset.account_type)
        # print("account_id: ", asset.account_id)
        # print("cash: ", asset.cash)
        # print("frozen_cash: ", asset.frozen_cash)
        # print("market_value: ", asset.market_value)
        # print("total_asset: ", asset.total_asset)

        # orders = xt_delegate.check_orders()
        # for order in orders:
        #     print('==== order ====')
        #     print("order_id: ", order.order_id)
        #     print("order_sysid: ", order.order_sysid)
        #     print("order_time: ", order.order_time)
        #     print("order_status: ", order.order_status)
        #     print("status_msg: ", order.status_msg)

        # positions = xt_delegate.check_positions()
        # for position in positions:
        #     print('==== position ====')
        #     print("stock_code: ", position.stock_code)
        #     print("volume: ", position.volume)
        #     print("can_use_volume: ", position.can_use_volume)
        #     print("open_price: ", position.open_price)
        #     print("market_value: ", position.market_value)

        # xt_delegate.order_submit_async(
        #     stock_code='600610.SH',
        #     order_type=xtconstant.STOCK_SELL,
        #     order_volume=500,
        #     price_type=xtconstant.MARKET_SH_CONVERT_5_CANCEL,
        #     price=1,
        #     strategy_name='策略名称',
        #     order_remark='下单测试',
        # )

        # sell_all_positions(xt_delegate)

        get_profit(xt_delegate)

        xt_delegate.xt_trader.run_forever()
    finally:
        print('Close delegate')
        xt_delegate.xt_trader.stop()
