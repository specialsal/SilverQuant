import logging
from typing import List, Dict

import numpy as np
import talib as ta
from xtquant import xtconstant
from xtquant.xttype import XtPosition

from delegate.xt_delegate import order_submit


def get_sma(row_close, period) -> float:
    sma = ta.SMA(row_close, timeperiod=period)
    return sma[-1]


def get_atr(row_close, row_high, row_low, period) -> float:
    atr = ta.ATR(row_high, row_low, row_close, timeperiod=period)
    return atr[-1]


class Seller:
    def __init__(self, xt_delegate, param, strategy_name):
        self.xt_delegate = xt_delegate
        self.param = param
        self.strategy_name = strategy_name

    def order_sell(self, code, price, volume, remark, log=True) -> None:
        if log:
            logging.warning(f'{remark} {code} {volume}股\t现价:{price:.3f}')
        order_submit(
            self.xt_delegate,
            xtconstant.STOCK_SELL,
            code,
            price,
            volume,
            remark,
            self.param.order_premium,
            self.strategy_name
        )

    def execute_sell(
        self,
        curr_time: str,
        positions: List[XtPosition],
        quotes: Dict[str, Dict],
        held_days: Dict[str, int],
        max_prices: Dict[str, float],
        cache_indicators: Dict[str, Dict],
    ) -> None:
        p = self.param
        for position in positions:
            code = position.stock_code
            cost_price = position.open_price
            sell_volume = position.volume

            # 如果有数据且有持仓时间记录
            if (code in quotes) and (code in held_days):
                held_day = held_days[code]

                quote = quotes[code]
                curr_price = quote['lastPrice']

                # 换仓卖天
                if held_day > 0:
                    switch_lower = cost_price * (p.min_income + held_day * p.min_rise)
                    switch_upper = cost_price * (1 + held_day * p.switch_max_rise)

                    # 未满足盈利目标的仓位 & 大于当日最早换仓时间
                    if held_day > p.hold_days and curr_time >= p.switch_begin:
                        if switch_lower < curr_price < switch_upper:
                            self.order_sell(code, curr_price, sell_volume, '��������')
                            continue

                # 回落止盈
                if held_day > 0:
                    if code in max_prices:
                        max_price = max_prices[code]

                        # 历史最高大于触发阈值，且当前价格在最高点回落超过阈值
                        if max_price > cost_price * p.fall_trigger and curr_price < max_price * (1 - p.fall_limit):
                            self.order_sell(code, curr_price, sell_volume, '����ֹӯ')
                            continue

                # ATR止盈止损
                if held_day > 0:
                    if code in cache_indicators:
                        quote = quotes[code]
                        close = np.append(cache_indicators[code]['CLOSE_3D'], quote['lastPrice'])
                        high = np.append(cache_indicators[code]['HIGH_3D'], quote['high'])
                        low = np.append(cache_indicators[code]['LOW_3D'], quote['low'])

                        sma = get_sma(close, p.sma_time_period)
                        atr = get_atr(close, high, low, p.atr_time_period)

                        # ATR 止损委托
                        atr_lower = sma - atr * p.atr_min_ratio
                        if curr_price <= atr_lower:
                            # ATR 止损卖出
                            logging.warning(f'ATRֹ��ί�� {code} {sell_volume}��\t�ּ�:{curr_price:.3f}\t'
                                            f'ATRֹ����:{atr_lower}')
                            self.order_sell(code, curr_price, sell_volume, 'ATRֹ��ί��', log=False)
                            continue

                        # 分段ATR 止盈委托
                        if curr_price >= cost_price * p.atr_threshold:
                            atr_upper = sma + atr * (p.atr_max_h_ratio - held_day * p.atr_max_drop)
                            if curr_price >= atr_upper:
                                # 高位 ATR止盈卖出
                                logging.warning(f'HATRֹӯί�� {code} {sell_volume}��\t�ּ�:{curr_price:.3f}\t'
                                                f'HATRֹӯ��:{atr_upper}')
                                self.order_sell(code, curr_price, sell_volume, 'HATRֹӯί��', log=False)
                                continue
                        else:
                            atr_upper = sma + atr * (p.atr_max_l_ratio - held_day * p.atr_max_drop)
                            if curr_price >= atr_upper:
                                # 低位 ATR止盈卖出
                                logging.warning(f'LATRֹӯί�� {code} {sell_volume}��\t�ּ�:{curr_price:.3f}\t'
                                                f'LATRֹӯ��:{atr_upper}')
                                self.order_sell(code, curr_price, sell_volume, 'LATRֹӯί��', log=False)
                                continue

                # 绝对止盈止损卖出
                if held_day > 0:
                    switch_lower = cost_price * (p.min_income + held_day * p.min_rise)
                    if curr_price <= switch_lower:
                        self.order_sell(code, curr_price, sell_volume, 'ABSֹ��ί��')
                        continue
                    elif curr_price >= cost_price * p.max_income:
                        self.order_sell(code, curr_price, sell_volume, 'ABSֹӯί��')
                        continue
