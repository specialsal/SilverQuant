import threading
import datetime
import logging

from xtquant import xtconstant
from xtquant.xttrader import XtQuantTraderCallback
from xtquant.xttype import XtOrder, XtTrade, XtOrderError, XtCancelError, XtOrderResponse, XtCancelOrderResponse

from tools.utils_cache import record_deal, new_held, del_key, get_stock_codes_and_names
from tools.utils_ding import DingMessager


class XtBaseCallback(XtQuantTraderCallback):
    def __init__(self):
        self.delegate = None

    def on_disconnected(self):
        # deprecated
        print(datetime.datetime.now(), '连接丢失，断线重连中...')
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


class XtCustomCallback(XtBaseCallback):
    def __init__(
        self,
        account_id: str,
        strategy_name: str,
        ding_messager: DingMessager,
        lock_of_disk_cache: threading.Lock,
        path_deal: str,
        path_held: str,
        path_maxp: str,
    ):
        super().__init__()
        self.account_id = '**' + str(account_id)[-4:]
        self.strategy_name = strategy_name
        self.ding_messager = ding_messager
        self.lock_of_disk_cache = lock_of_disk_cache
        self.path_deal = path_deal
        self.path_held = path_held
        self.path_maxp = path_maxp

        self.code_name = get_stock_codes_and_names()

    def record_order(self, order_time: str, code: str, price: float, volume: int, side: str, remark: str):
        if code not in self.code_name:
            print(f'找不到{code}对应的名字无法记录!')

        record_deal(
            lock=self.lock_of_disk_cache,
            path=self.path_deal,
            timestamp=order_time,
            code=code,
            name=self.code_name[code],
            order_type=side,
            remark=remark,
            price=round(price, 2),
            volume=volume,
        )

    def on_stock_trade(self, trade: XtTrade):
        stock_code = trade.stock_code
        traded_volume = trade.traded_volume
        traded_price = trade.traded_price
        # traded_time = trade.traded_time
        order_remark = trade.order_remark

        if trade.order_type == xtconstant.STOCK_SELL:
            del_key(self.lock_of_disk_cache, self.path_held, stock_code)
            del_key(self.lock_of_disk_cache, self.path_maxp, stock_code)

            # self.record_order(
            #     order_datetime=traded_time,
            #     code=stock_code,
            #     price=traded_price,
            #     volume=traded_volume,
            #     side='卖出成交',
            #     remark=order_remark,
            # )

            name = self.code_name[stock_code] if stock_code in self.code_name else '(Unknown)'
            self.ding_messager.send_text(
                f'[{self.account_id}]{self.strategy_name} {order_remark}\n'
                f'{datetime.datetime.now().strftime("%H:%M:%S")} 卖出成交 {stock_code}\n'
                f'{name} {traded_volume}股 {traded_price:.2f}元',
                '[SELL]')
            return

        if trade.order_type == xtconstant.STOCK_BUY:
            new_held(self.lock_of_disk_cache, self.path_held, [stock_code])

            # self.record_order(
            #     order_datetime=traded_time,
            #     code=stock_code,
            #     price=traded_price,
            #     volume=traded_volume,
            #     side='买入成交',
            #     remark=order_remark,
            # )

            name = self.code_name[stock_code] if stock_code in self.code_name else '(Unknown)'
            self.ding_messager.send_text(
                f'[{self.account_id}]{self.strategy_name} {order_remark}\n'
                f'{datetime.datetime.now().strftime("%H:%M:%S")} 买入成交 {stock_code}\n'
                f'{name} {traded_volume}股 {traded_price:.2f}元',
                '[BUY]')
            return


    def on_order_stock_async_response(self, res: XtOrderResponse):
        log = f'异步委托回调 id:{res.order_id} sysid:{res.error_msg} remark:{res.order_remark}',
        logging.warning(log)

    def on_order_error(self, err: XtOrderError):
        log = f'委托报错 id:{err.order_id} error_id:{err.error_id} error_msg:{err.error_msg}'
        logging.warning(log)
