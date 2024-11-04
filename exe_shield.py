import time
import logging
import schedule

from credentials import *

from tools.utils_basic import logging_init, is_stock
from tools.utils_cache import *
from tools.utils_ding import DingMessager

from delegate.xt_subscriber import XtSubscriber, update_position_held

from trader.buyer import BaseBuyer as Buyer
from trader.pools import StocksPoolWhiteIndexes as Pool
from trader.seller_groups import ShieldGroupSeller as Seller


# ======== 配置 ========

STRATEGY_NAME = '监控卖出'
DING_MESSAGER = DingMessager(DING_SECRET, DING_TOKENS)
IS_PROD = True
IS_DEBUG = True

PATH_BASE = CACHE_BASE_PATH

PATH_ASSETS = PATH_BASE + '/assets.csv'         # 记录历史净值
PATH_DEAL = PATH_BASE + '/deal_hist.csv'        # 记录历史成交
PATH_HELD = PATH_BASE + '/held_days.json'       # 记录持仓日期
PATH_MAXP = PATH_BASE + '/max_price.json'       # 记录历史最高
PATH_LOGS = PATH_BASE + '/logs.txt'             # 用来存储选股和委托操作

lock_of_disk_cache = threading.Lock()           # 操作磁盘文件缓存的锁

cache_selected: Dict[str, Set] = {}             # 记录选股历史，去重
cache_history: Dict[str, pd.DataFrame] = {}     # 记录历史日线行情的信息 { code: DataFrame }


def debug(*args):
    if IS_DEBUG:
        print(*args)


class PoolParameters:
    white_indexes = []

    black_queries = []

    # 忽略监控列表
    ignore_stocks = [
        '000001.SZ',  # 深交所股票尾部加.SZ
        '600000.SH',  # 上交所股票尾部加.SH
        '603117.SH',
    ]


class BuyParameters:
    time_ranges = []
    interval = 15           # 扫描买入间隔，60的约数：1-6, 10, 12, 15, 20, 30
    order_premium = 0.02    # 保证市价单成交的溢价，单位（元）

    slot_count = 10         # 持股数量上限
    slot_capacity = 10000   # 每个仓的资金上限
    once_buy_limit = 10     # 单次选股最多买入股票数量（若单次未买进当日不会再买这只

    inc_limit = 1.09        # 相对于昨日收盘的涨幅限制
    min_price = 3.00        # 限制最低可买入股票的现价


class SellParameters:
    time_ranges = [['09:31', '11:30'], ['13:00', '14:57']]
    interval = 1                    # 扫描买入间隔，60的约数：1-6, 10, 12, 15, 20, 30
    order_premium = 0.03            # 保证市价单成交的溢价，单位（元）

    earn_limit = 9.999              # 硬性止盈率
    risk_limit = 1 - 0.03           # 硬性止损率
    risk_tight = 0.003              # 硬性止损率每日上移

    # 涨幅超过建仓价xA，并小于建仓价xB 时，回撤涨幅的C倍卖出
    # (A, B, C)
    return_of_profit = [      # 至少保留收益范围
        (1.11, 9.99, 0.100),  # [9.900 % ~ 809.100 %)
        (1.08, 1.11, 0.300),  # [5.600 % ~ 7.700 %)
        (1.05, 1.08, 0.600),  # [2.000 % ~ 3.200 %)
        (1.03, 1.05, 0.800),  # [0.600 % ~ 1.000 %)
        (1.02, 1.03, 0.900),  # [0.200 % ~ 0.300 %)
    ]

    # 利润从最高点回撤卖出
    fall_from_top = [         # 至少保留收益范围
        (1.05, 9.99, 0.020),  # [2.900 % ~ 879.020 %)
        (1.02, 1.05, 0.050),  # [-3.100 % ~ -0.250 %)
    ]


# ======== 盘前 ========


def held_increase() -> None:
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    update_position_held(lock_of_disk_cache, xt_delegate, PATH_HELD)
    if all_held_inc(lock_of_disk_cache, PATH_HELD):
        logging.warning('===== 所有持仓计数 +1 =====')
        print(f'All held stock day +1!')


def refresh_code_list():
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    my_pool.refresh()
    positions = xt_delegate.check_positions()
    hold_list = [
        position.stock_code
        for position in positions
        if is_stock(position.stock_code) and position.stock_code not in PoolParameters.ignore_stocks
    ]
    my_suber.update_code_list(my_pool.get_code_list() + hold_list)


# ======== 卖点 ========


def scan_sell(quotes: Dict, curr_date: str, curr_time: str, positions: List) -> None:
    max_prices, held_days = update_max_prices(lock_of_disk_cache, quotes, positions, PATH_MAXP, PATH_HELD)
    my_seller.execute_sell(quotes, curr_date, curr_time, positions, held_days, max_prices, cache_history)


# ======== 框架 ========


def execute_strategy(curr_date: str, curr_time: str, curr_seconds: str, curr_quotes: Dict) -> bool:
    positions = xt_delegate.check_positions()

    for time_range in SellParameters.time_ranges:
        if time_range[0] <= curr_time <= time_range[1]:
            if int(curr_seconds) % SellParameters.interval == 0:
                scan_sell(curr_quotes, curr_date, curr_time, positions)

    return False


if __name__ == '__main__':
    logging_init(path=PATH_LOGS, level=logging.INFO)

    if IS_PROD:
        from delegate.xt_callback import XtCustomCallback
        from delegate.xt_delegate import XtDelegate

        xt_callback = XtCustomCallback(
            account_id=QMT_ACCOUNT_ID,
            strategy_name=STRATEGY_NAME,
            ding_messager=DING_MESSAGER,
            lock_of_disk_cache=lock_of_disk_cache,
            path_deal=PATH_DEAL,
            path_held=PATH_HELD,
            path_maxp=PATH_MAXP,
        )
        xt_delegate = XtDelegate(
            account_id=QMT_ACCOUNT_ID,
            client_path=QMT_CLIENT_PATH,
            callback=xt_callback,
        )
    else:
        from delegate.gm_callback import GmCallback
        from delegate.gm_delegate import GmDelegate

        xt_callback = GmCallback(
            account_id=QMT_ACCOUNT_ID,
            strategy_name=STRATEGY_NAME,
            ding_messager=DING_MESSAGER,
            lock_of_disk_cache=lock_of_disk_cache,
            path_deal=PATH_DEAL,
            path_held=PATH_HELD,
            path_maxp=PATH_MAXP,
        )
        xt_delegate = GmDelegate(
            account_id=QMT_ACCOUNT_ID,
            callback=xt_callback,
            ding_messager=DING_MESSAGER,
        )

    my_pool = Pool(
        account_id=QMT_ACCOUNT_ID,
        strategy_name=STRATEGY_NAME,
        parameters=PoolParameters,
        ding_messager=DING_MESSAGER,
    )
    my_buyer = Buyer(
        account_id=QMT_ACCOUNT_ID,
        strategy_name=STRATEGY_NAME,
        delegate=xt_delegate,
        parameters=BuyParameters,
    )
    my_seller = Seller(
        strategy_name=STRATEGY_NAME,
        delegate=xt_delegate,
        parameters=SellParameters,
    )
    my_suber = XtSubscriber(
        account_id=QMT_ACCOUNT_ID,
        strategy_name=STRATEGY_NAME,
        delegate=xt_delegate,
        path_deal=PATH_DEAL,
        path_assets=PATH_ASSETS,
        execute_strategy=execute_strategy,
        ding_messager=DING_MESSAGER,
    )
    my_suber.start_scheduler()

    temp_now = datetime.datetime.now()
    temp_date = temp_now.strftime('%Y-%m-%d')
    temp_time = temp_now.strftime('%H:%M')

    # 定时任务启动
    schedule.every().day.at('09:00').do(held_increase)
    schedule.every().day.at('09:05').do(refresh_code_list)

    if '09:05' < temp_time < '15:30' and check_today_is_open_day(temp_date):
        held_increase()
        refresh_code_list()

        if '09:15' <= temp_time <= '11:30' or '13:00' <= temp_time <= '14:57':
            my_suber.subscribe_tick()  # 重启时如果在交易时间则订阅Tick

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    finally:
        schedule.clear()
        xt_delegate.shutdown()
