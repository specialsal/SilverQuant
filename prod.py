"""
TODO:
"""
import math
import logging
import datetime
import threading
from typing import List, Dict

from xtquant import xtdata, xtconstant
from xtquant.xttype import XtPosition, XtTrade, XtOrderError, XtOrderResponse

from tools.utils_basic import logging_init, get_code_exchange
from tools.utils_cache import load_json, daily_once, all_held_inc, new_held, del_held, check_today_is_open_day
from tools.utils_ding import sample_send_msg
from tools.xt_subscriber import sub_whole_quote
from tools.xt_delegate import XtDelegate, XtBaseCallback, get_holding_position_count

# ======== 策略常量 ========

strategy_name = '低开翻红样板策略'

my_client_path = r'C:\国金QMT交易端模拟\userdata_mini'
my_account_id = '55009728'
# my_account_id = '55010470'

target_stock_prefix = [
    '000', '001', '002', '003',
    '300', '301',
    '600', '601', '603', '605',
]

path_held = './_cache/prod/held_days.json'  # 记录持仓日期
path_date = './_cache/prod/curr_date.json'  # 用来标记每天执行一次任务的缓存
path_logs = './_cache/prod/log.txt'         # 用来存储选股和委托操作

# ======== 全局变量 ========

my_quotes_update_lock = threading.Lock()    # 更新quotes缓存用的锁
my_held_cache_lock = threading.Lock()       # 操作held缓存用的锁
my_daily_inc_held_lock = threading.Lock()   # 记录每天一次所有held+1执行用的锁

quotes_cache: Dict[str, Dict] = {}  # 记录实时价格信息
select_cache: Dict[str, List] = {}  # 记录选股历史，目的是去重

time_cache = {
    'prev_datetime': '',    # 限制每秒执行一次的缓存
    'prev_minutes': '',     # 限制每分钟屏幕打印心跳的缓存
}


class p:
    hold_days = 1           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    stop_income = 1.05      # 换仓阈值
    upper_income = 1.168    # 止盈率
    upper_income_c = 1.368  # 止盈率:30开头创业板
    lower_income = 0.97     # 止损率
    low_open = 0.98         # 低开阈值
    turn_red_upper = 1.03   # 翻红阈值上限，防止买太高
    turn_red_lower = 1.02   # 翻红阈值下限
    order_premium = 0.05    # 保证成功下单成交的溢价
    stop_start = '09:40'    # 每天最早换仓时间


class MyCallback(XtBaseCallback):
    def on_stock_trade(self, trade: XtTrade):
        if trade.order_type == xtconstant.STOCK_BUY:
            log = f'买入成交 {trade.stock_code} {trade.traded_volume}股 均价:{round(trade.traded_price, 3)}'
            logging.warning(log)
            sample_send_msg(f'{my_account_id} - {strategy_name}\n{log}', 0)
            new_held(my_held_cache_lock, path_held, [trade.stock_code])

        if trade.order_type == xtconstant.STOCK_SELL:
            log = f'卖出成交 {trade.stock_code} {trade.traded_volume}股 均价:{round(trade.traded_price, 3)}'
            logging.warning(log)
            sample_send_msg(f'{my_account_id} - {strategy_name}\n{log}', 0)
            del_held(my_held_cache_lock, path_held, [trade.stock_code])

    # def on_stock_order(self, order: XtOrder):
    #     log = f'委托回调 id:{order.order_id} code:{order.stock_code} remark:{order.order_remark}',
    #     logging.warning(log)

    def on_order_stock_async_response(self, res: XtOrderResponse):
        log = f'异步委托回调 id:{res.order_id} sysid:{res.error_msg} remark:{res.order_remark}',
        logging.warning(log)

    def on_order_error(self, err: XtOrderError):
        log = f'委托报错 id:{err.order_id} error_id:{err.error_id} error_msg:{err.error_msg}'
        logging.warning(log)


def held_increase():
    print(f'All held stock day +1!')
    all_held_inc(my_held_cache_lock, path_held)


def order_submit(order_type: int, code: str, curr_price: float, order_volume: int, order_remark: str):
    price_type = xtconstant.LATEST_PRICE
    price = -1
    if get_code_exchange(code) == 'SZ':
        price_type = xtconstant.MARKET_SZ_CONVERT_5_CANCEL
        price = -1
    if get_code_exchange(code) == 'SH':
        price_type = xtconstant.MARKET_PEER_PRICE_FIRST
        if order_type == xtconstant.STOCK_SELL:
            price = curr_price - p.order_premium
        elif order_type == xtconstant.STOCK_BUY:
            price = curr_price + p.order_premium

    xt_delegate.order_submit(
        stock_code=code,
        order_type=order_type,
        order_volume=order_volume,
        price_type=price_type,
        price=price,
        strategy_name=strategy_name,
        order_remark=order_remark,
    )


def scan_sell(quotes: dict, positions: List[XtPosition], curr_time: str) -> None:
    # 卖出逻辑
    held_days = load_json(path_held)

    for position in positions:
        code = position.stock_code
        if (code in quotes) and (code in held_days):
            # 如果有数据且有持仓时间记录
            quote = quotes[code]
            curr_price = quote['lastPrice']
            cost_price = position.open_price
            sell_volume = position.volume

            if held_days[code] > p.hold_days and curr_time >= p.stop_start:
                # print(code, held_days[code], curr_price, cost_price, sell_volume)
                # 判断持仓超过限制时间
                if cost_price * p.lower_income < curr_price < cost_price * p.stop_income:
                    # 不满足盈利的持仓平仓
                    logging.warning(f'换仓委托 {code} {sell_volume}股 现价:{curr_price}')
                    order_submit(xtconstant.STOCK_SELL, code, curr_price, sell_volume, '换仓卖单')

            if held_days[code] > 0:
                # print(code, held_days[code], curr_price, cost_price, sell_volume)
                # 判断持仓超过一天
                if curr_price <= cost_price * p.lower_income:
                    # 止损卖出
                    logging.warning(f'止损委托 {code} {sell_volume}股 现价:{curr_price}')
                    order_submit(xtconstant.STOCK_SELL, code, curr_price, sell_volume, '止损卖单')
                elif curr_price >= cost_price * p.upper_income_c and code[:2] == '30':
                    # 止盈卖出：创业板
                    logging.warning(f'止盈委托 {code} {sell_volume}股 现价:{curr_price}')
                    order_submit(xtconstant.STOCK_SELL, code, curr_price, sell_volume, '止盈卖单')
                elif curr_price >= cost_price * p.upper_income:
                    # 止盈卖出：主板
                    logging.warning(f'止盈委托 {code} {sell_volume}股 现价:{curr_price}')
                    order_submit(xtconstant.STOCK_SELL, code, curr_price, sell_volume, '止盈卖单')


def scan_buy(quotes: dict, positions: List[XtPosition], curr_date: str) -> None:
    position_codes = [position.stock_code for position in positions]

    # 扫描全市场选股
    selections = []
    for code in quotes:
        if code[:3] not in target_stock_prefix:
            continue

        last_close = quotes[code]['lastClose']
        curr_open = quotes[code]['open']
        curr_price = quotes[code]['lastPrice']

        # 筛选符合买入条件的股票
        if ((curr_open < last_close * p.low_open)
                and (last_close * p.turn_red_upper > curr_price)
                and (last_close * p.turn_red_lower < curr_price)):
            if code not in position_codes:  # 如果目前没有持仓则记录
                selections.append({'code': code, 'price': round(curr_price, 3)})

    if len(selections) > 0:  # 选出一个以上的股票
        selections = sorted(selections, key=lambda x: x['price'])  # 选出的股票按照现价从小到大排序

        asset = xt_delegate.check_asset()

        buy_count = max(0, p.max_count - get_holding_position_count(positions))       # 确认剩余的仓位
        buy_count = min(buy_count, asset.cash / p.amount_each)      # 确认现金够用
        buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
        buy_count = min(buy_count, 1)                               # 限每次最多买入数量

        # 依次买入
        for i in range(buy_count):
            code = selections[i]['code']
            price = selections[i]['price']
            buy_volume = math.floor(p.amount_each / price / 100) * 100

            # 如果有可用的买点则买入
            if buy_volume > 0:
                order_submit(xtconstant.STOCK_BUY, code, price, buy_volume, '选股买单')
                logging.warning(f'买入委托 {code} {buy_volume}股 现价:{price}')

        # 记录选股历史
        if curr_date not in select_cache.keys():
            select_cache[curr_date] = []

        for selection in selections:
            if selection['code'] not in select_cache[curr_date]:
                select_cache[curr_date].append(selection['code'])
                logging.warning(f'记录选股历史 code: {selection["code"]} 现价: {selection["price"]}')


def execute_strategy(curr_date, curr_time, quotes):
    # 盘前
    if '09:15' <= curr_time <= '09:29':
        daily_once(
            my_daily_inc_held_lock, time_cache, path_date, '_daily_once_held_inc',
            curr_date, held_increase)

    # 早盘
    elif '09:30' <= curr_time <= '11:30':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, positions, curr_time)

        scan_buy(quotes, positions, curr_date)

    # 午盘
    elif '13:00' <= curr_time <= '14:56':
        positions = xt_delegate.check_positions()
        scan_sell(quotes, positions, curr_time)


def callback_sub_whole(quotes: dict) -> None:
    now = datetime.datetime.now()

    # 每分钟输出一行开头
    curr_time = now.strftime('%H:%M')
    if time_cache['prev_minutes'] != curr_time:
        time_cache['prev_minutes'] = curr_time
        print(f'\n[{curr_time}]', end='')

    # 每秒钟开始的时候输出一个点
    with my_quotes_update_lock:
        curr_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
        quotes_cache.update(quotes)
        if time_cache['prev_datetime'] != curr_datetime:
            time_cache['prev_datetime'] = curr_datetime
            curr_date = now.strftime('%Y-%m-%d')

            # 只有在交易日才执行策略
            if check_today_is_open_day(curr_date):
                print('.', end='')
                execute_strategy(curr_date, curr_time, quotes_cache)
                quotes_cache.clear()
            else:
                print('x', end='')


if __name__ == '__main__':
    logging_init(path=path_logs, level=logging.INFO)

    xt_delegate = XtDelegate(
        account_id=my_account_id,
        client_path=my_client_path,
        xt_callback=MyCallback(),
    )

    print('启动行情订阅...')
    check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d'))
    sub_whole_quote(callback_sub_whole)
    xtdata.run()  # 死循环 阻塞主线程退出
