import time
import math
import logging
import schedule

from credentials import *

from tools.utils_basic import logging_init, is_symbol
from tools.utils_cache import *
from tools.utils_ding import DingMessager

from delegate.xt_subscriber import XtSubscriber, update_position_held

from trader.buyer import BaseBuyer as Buyer
from trader.pools import StocksPoolWhiteIndexes as Pool
from trader.seller_groups import ShieldGroupSeller as Seller

# ======== 配置 ========

STRATEGY_NAME = '进攻监控'
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


class PoolConf:
    white_indexes = []
    black_queries = []


class BuyConf:
    time_ranges = [['09:31', '11:30'], ['13:00', '14:57']]
    interval = 1            # 扫描买入间隔，60的约数：1-6, 10, 12, 15, 20, 30
    order_premium = 0.00    # 保证市价单成交的溢价，单位（元）

    # 股票代码: [突破价, 溢价倍数, 是否向上突破, 买入量, 买入额]
    break_targets = {
        '000001.SZ': [20.00, 1.03, True, None, 10000.00],
    }


class SellConf:
    time_ranges = [['09:31', '11:30'], ['13:00', '14:57']]
    interval = 1                    # 扫描买入间隔，60的约数：1-6, 10, 12, 15, 20, 30
    order_premium = 0.03            # 保证市价单成交的溢价，单位（元）

    hard_time_range = ['09:31', '14:57']
    earn_limit = 9.999              # 硬性止盈率
    risk_limit = 1 - 0.03           # 硬性止损率
    risk_tight = 0.003              # 硬性止损率每日上移

    # 涨幅超过建仓价xA，并小于建仓价xB 时，回撤涨幅的C倍卖出
    # (A, B, C)
    return_time_range = ['09:31', '14:57']
    return_of_profit = [      # 至少保留收益范围
        (1.11, 9.99, 0.100),  # [9.900 % ~ 809.100 %)
        (1.08, 1.11, 0.300),  # [5.600 % ~ 7.700 %)
        (1.05, 1.08, 0.600),  # [2.000 % ~ 3.200 %)
        (1.03, 1.05, 0.800),  # [0.600 % ~ 1.000 %)
        (1.02, 1.03, 0.900),  # [0.200 % ~ 0.300 %)
    ]

    # 利润从最高点回撤卖出
    fall_time_range = ['09:31', '14:57']
    fall_from_top = [         # 至少保留收益范围
        (1.05, 9.99, 0.02),  # [2.900 % ~ 879.020 %)
        (1.02, 1.05, 0.05),  # [-3.100 % ~ -0.250 %)
    ]


# ======== 盘前 ========


def held_increase() -> None:
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    update_position_held(lock_of_disk_cache, my_delegate, PATH_HELD)
    if all_held_inc(lock_of_disk_cache, PATH_HELD):
        logging.warning('===== 所有持仓计数 +1 =====')
        print(f'All held stock day +1!')


def refresh_code_list():
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    my_pool.refresh()
    code_list = [code for code in BuyConf.break_targets.keys() if is_symbol(code)]
    my_suber.update_code_list(my_pool.get_code_list() + code_list)


# ======== 买点 ========


def select_stocks(quotes: Dict) -> List[Dict[str, any]]:
    selections = []
    for code in quotes:
        if code not in BuyConf.break_targets.keys():
            debug(code, f'不在监控名单')
            continue

        # e.g. [20.00, 1.03, True, None, 10000.00]
        target_price = BuyConf.break_targets[code][0]
        target_price_ratio = BuyConf.break_targets[code][1]
        target_is_up_cross = BuyConf.break_targets[code][2]
        target_volume = BuyConf.break_targets[code][3]
        target_amount = BuyConf.break_targets[code][4]

        quote = quotes[code]
        curr_price = quote['lastPrice']
        if target_is_up_cross:
            if curr_price > target_price:  # 上穿
                selection = {
                    'code': code,
                    'price': curr_price * target_price_ratio,
                    'volume': target_volume,
                    'amount': target_amount,
                    'lastClose': quote['lastClose'],
                }
                selections.append(selection)
        else:
            if curr_price < target_price:  # 下穿
                selection = {
                    'code': code,
                    'price': curr_price * target_price_ratio,
                    'volume': target_volume,
                    'amount': target_amount,
                    'lastClose': quote['lastClose'],
                }
                selections.append(selection)

    return selections


def scan_buy(quotes: Dict, curr_date: str, positions: List) -> None:
    selections = select_stocks(quotes)

    # 选出一个以上的股票
    if len(selections) > 0:
        position_codes = [position.stock_code for position in positions]

        for i in range(len(selections)):  # 依次买入
            selection = selections[i]

            code = selection['code']
            price = selection['price']
            last_close = selection['lastClose']

            if selection['volume'] is None:
                buy_volume = math.floor(selection['volume'] / price / 100) * 100
            else:
                buy_volume = selection['volume']

            if buy_volume <= 0:
                debug(f'{code} 不够一手')
            elif code in position_codes:
                debug(f'{code} 正在持仓')
            elif curr_date in cache_selected and code in cache_selected[curr_date]:
                debug(f'{code} 今日已选')
            else:
                my_buyer.order_buy(code=code, price=price, last_close=last_close,
                                   volume=buy_volume, remark='买入委托')

    # 记录选股历史
    if curr_date not in cache_selected:
        cache_selected[curr_date] = set()

    for selection in selections:
        if selection['code'] not in cache_selected[curr_date]:
            cache_selected[curr_date].add(selection['code'])
            logging.warning(f"记录选股 {selection['code']}\t现价: {selection['price']:.2f}")


# ======== 框架 ========


def execute_strategy(curr_date: str, curr_time: str, curr_seconds: str, curr_quotes: Dict) -> bool:
    positions = my_delegate.check_positions()

    for time_range in BuyConf.time_ranges:
        if time_range[0] <= curr_time <= time_range[1]:
            if int(curr_seconds) % BuyConf.interval == 0:
                scan_buy(curr_quotes, curr_date, positions)
                return True

    return False


if __name__ == '__main__':
    logging_init(path=PATH_LOGS, level=logging.INFO)
    print(f'正在启动 {STRATEGY_NAME}{"" if IS_PROD else "(模拟)"}...')
    if IS_PROD:
        from delegate.xt_callback import XtCustomCallback
        from delegate.xt_delegate import XtDelegate

        my_callback = XtCustomCallback(
            account_id=QMT_ACCOUNT_ID,
            strategy_name=STRATEGY_NAME,
            ding_messager=DING_MESSAGER,
            lock_of_disk_cache=lock_of_disk_cache,
            path_deal=PATH_DEAL,
            path_held=PATH_HELD,
            path_maxp=PATH_MAXP,
        )
        my_delegate = XtDelegate(
            account_id=QMT_ACCOUNT_ID,
            client_path=QMT_CLIENT_PATH,
            callback=my_callback,
        )
    else:
        from delegate.gm_callback import GmCallback
        from delegate.gm_delegate import GmDelegate

        my_callback = GmCallback(
            account_id=QMT_ACCOUNT_ID,
            strategy_name=STRATEGY_NAME,
            ding_messager=DING_MESSAGER,
            lock_of_disk_cache=lock_of_disk_cache,
            path_deal=PATH_DEAL,
            path_held=PATH_HELD,
            path_maxp=PATH_MAXP,
        )
        my_delegate = GmDelegate(
            account_id=QMT_ACCOUNT_ID,
            callback=my_callback,
            ding_messager=DING_MESSAGER,
        )

    my_pool = Pool(
        account_id=QMT_ACCOUNT_ID,
        strategy_name=STRATEGY_NAME,
        parameters=PoolConf,
        ding_messager=DING_MESSAGER,
    )
    my_buyer = Buyer(
        account_id=QMT_ACCOUNT_ID,
        strategy_name=STRATEGY_NAME,
        delegate=my_delegate,
        parameters=BuyConf,
    )
    my_seller = Seller(
        strategy_name=STRATEGY_NAME,
        delegate=my_delegate,
        parameters=SellConf,
    )
    my_suber = XtSubscriber(
        account_id=QMT_ACCOUNT_ID,
        strategy_name=STRATEGY_NAME,
        delegate=my_delegate,
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

    if '09:10' < temp_time < '15:30' and check_today_is_open_day(temp_date):
        held_increase()
        refresh_code_list()

        if '09:30' <= temp_time <= '11:30' or '13:00' <= temp_time <= '14:57':
            my_suber.subscribe_tick()  # 重启时如果在交易时间则订阅Tick

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    finally:
        schedule.clear()
        my_delegate.shutdown()
