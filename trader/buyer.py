import datetime
import logging

from delegate.base_delegate import BaseDelegate

from tools.utils_basic import get_limit_up_price


class BaseBuyer:
    def __init__(self, account_id: str, strategy_name: str, delegate: BaseDelegate, parameters):
        self.account_id = account_id
        self.strategy_name = strategy_name
        self.delegate = delegate
        self.order_premium = parameters.order_premium

    def order_buy(
        self,
        code: str,
        price: float,
        last_close: float,
        volume: int,
        remark: str,
        market: bool = True,
        log: bool = True,
    ):

        if volume > 0:
            order_price = price + self.order_premium
            limit_price = get_limit_up_price(code, last_close)

            if market:
                buy_type = '市买'
                if order_price > limit_price:
                    # 如果涨停了只能挂限价单
                    self.delegate.order_limit_open(
                        code=code,
                        price=limit_price,
                        volume=volume,
                        remark=remark,
                        strategy_name=self.strategy_name)
                else:
                    self.delegate.order_market_open(
                        code=code,
                        price=min(order_price, limit_price),
                        volume=volume,
                        remark=remark,
                        strategy_name=self.strategy_name)
            else:
                buy_type = '限买'
                self.delegate.order_limit_open(
                    code=code,
                    price=min(order_price, limit_price),
                    volume=volume,
                    remark=remark,
                    strategy_name=self.strategy_name)

            if log:
                logging.warning(f'{buy_type}委托 {code} \t现价:{price:.3f} {volume}股')

            if self.delegate.callback is not None:
                self.delegate.callback.record_order(
                    order_time=datetime.datetime.now().timestamp(),
                    code=code,
                    price=price,
                    volume=volume,
                    side=f'{buy_type}委托',
                    remark=remark)
        else:
            print(f'{code} 挂单买量为0，不委托')
