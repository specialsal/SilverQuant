"""
TODO:
"""
import time
import math
import logging
import datetime
import threading
import schedule
from random import random
from typing import List, Dict, Set, Optional, Union

import akshare as ak
import numpy as np
import pandas as pd
import pywencai

from xtquant import xtconstant, xtdata
from xtquant.xttype import XtPosition, XtTrade, XtOrderError, XtOrderResponse

import tick_accounts
from data_loader.reader_tushare import get_ts_markets
from tools.utils_basic import logging_init
from tools.utils_cache import load_json, save_json, get_all_historical_codes, \
    get_blacklist_codes, get_whitelist_codes, \
    check_today_is_open_day, load_pickle, save_pickle, \
    all_held_inc, new_held, del_key
from tools.utils_ding import sample_send_msg
from tools.utils_xtdata import get_prev_trading_date
from delegate.xt_delegate import XtDelegate, XtBaseCallback, get_holding_position_count, order_submit
from trader.seller import Seller

# ======== 配置 ========
STRATEGY_NAME = '问财策略'
QMT_ACCOUNT_ID = tick_accounts.DB_QMT_ACCOUNT_ID
QMT_CLIENT_PATH = tick_accounts.DB_QMT_CLIENT_PATH

PATH_BASE = tick_accounts.DB_CACHE_BASE_PATH

PATH_MAXP = PATH_BASE + '/max_price.json'   # 记录历史最高
PATH_HELD = PATH_BASE + '/held_days.json'   # 记录持仓日期
PATH_DATE = PATH_BASE + '/curr_date.json'   # 用来标记每天一次的缓存
PATH_LOGS = PATH_BASE + '/logs.txt'         # 用来存储选股和委托操作
PATH_INFO = PATH_BASE + '/info-{}.pkl'      # 用来缓存当天的指标信息

lock_wencai_select = threading.Lock()       # 问财选股内容缓存德索
lock_quotes_update = threading.Lock()       # 聚合实时打点缓存的锁
lock_of_disk_cache = threading.Lock()       # 操作持仓数据缓存的锁

cache_blacklist: Set[str] = set()           # 记录黑名单中的股票
cache_whitelist: Set[str] = set()           # 记录白名单中的股票

# cache_wencai: Dict[str, float] = {}         # 记录问财的选股信息
cache_quotes: Dict[str, Dict] = {}          # 记录实时的价格信息
cache_select: Dict[str, Set] = {}           # 记录选股历史，去重
cache_indicators: Dict[str, Dict] = {}      # 记录技术指标相关值 { code: { indicator_name: ...} }
cache_limits: Dict[str, str] = {    # 限制执行次数的缓存集合
    'prev_seconds': '',             # 限制每秒一次跑策略扫描的缓存
    'prev_minutes': '',             # 限制每分钟屏幕心跳换行的缓存
}


# ======== 策略 ========
target_stock_prefixes = {  # set
    '000', '001', '002', '003',
    '300', '301',  # 创业板
    '600', '601', '603', '605',
    # '688', '689',  # 科创板
}

query = '，'.join([
    # '涨幅小于5%',
    '主板',
    '非ST',
    # '非银行',
    # '非证券',
    # '非交通',
    # '非地产',
    # '非基建',
    '向上突破60日均线',
    # '向上突破30日均线',
    # 'mtm金叉',
    # 'skdj金叉',
    # '放量',
    '大单净量大于0.1',
    '量比大于1.99',
    '委比大于0.02',
    '昨日流通市值从小到大排序',
])
print(query)


class p:
    # 下单持仓
    switch_begin = '09:45'  # 每天最早换仓时间
    hold_days = 3           # 持仓天数
    max_count = 10          # 持股数量上限
    amount_each = 10000     # 每个仓的资金上限
    order_premium = 0.08    # 保证成功下单成交的溢价
    upper_buy_count = 3     # 单次选股最多买入股票数量（若单次未买进当日不会再买这只
    # 卖点：绝对止盈止损
    clean_max_rise = 0.008  # 换仓上限乘数
    max_income = 1.45       # 止盈率（ATR失效时使用）
    min_income = 0.958      # 止损率（ATR失效时使用）
    min_rise = 0.002        # 换仓下限乘数
    # 卖点：动态止盈止损
    atr_threshold = 1.05    # 高低涨幅确定atr止盈的分界
    atr_time_period = 3     # 计算atr的天数
    atr_max_h_ratio = 1.36  # 高位止盈atr的乘数
    atr_max_l_ratio = 1.03  # 低位止盈atr的乘数
    atr_max_drop = 0.01     # 止盈atr的每日递减
    atr_min_ratio = 0.85    # 止损atr的乘数
    sma_time_period = 3     # 卖点sma的天数，用来计算atr的中间变量
    # 卖点：回落止盈
    fall_h_trigger = 1.06   # 回落止盈的涨幅触发阈值
    fall_h_limit = 0.051    # 回落止盈的倍数
    fall_l_trigger = 1.03   # 回落止盈的涨幅触发阈值
    fall_l_limit = 0.021    # 回落止盈的倍数
    # 买点：策略参数
    buy_interval = 15       # 问财买点的时间间隔（秒）
    clean_interval = 30     # 清除缓存的时间间隔（秒）
    inc_limit = 1.03        # 相对于昨日收盘的涨幅限制
    min_price = 2.00        # 限制最低可买入股票的现价
    market_value_min = 15 * 10000 * 10000   # 市值下限
    market_value_max = 600 * 10000 * 10000  # 市值上限
    # 历史指标
    day_count = 5           # 3天atr和sma，5天够用
    data_cols = ['close', 'high', 'low']    # 历史数据需要的列


class MyCallback(XtBaseCallback):
    def on_stock_trade(self, trade: XtTrade):
        log = f'{trade.stock_code} v:{trade.traded_volume} p:{trade.traded_price:.2f}'

        if trade.order_type == xtconstant.STOCK_BUY:
            logging.warning(f'buy\t{log}')
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - 买成 {log}', 0, '[BUY]')
            new_held(lock_of_disk_cache, PATH_HELD, [trade.stock_code])

        if trade.order_type == xtconstant.STOCK_SELL:
            logging.warning(f'sell\t{log}')
            sample_send_msg(f'[{QMT_ACCOUNT_ID}]{STRATEGY_NAME} - 卖成 {log}', 0, '[SELL]')
            del_key(lock_of_disk_cache, PATH_HELD, trade.stock_code)
            del_key(lock_of_disk_cache, PATH_MAXP, trade.stock_code)

    def on_order_stock_async_response(self, res: XtOrderResponse):
        log = f'异步委托回调 id:{res.order_id} sysid:{res.error_msg} remark:{res.order_remark}',
        logging.warning(log)

    def on_order_error(self, err: XtOrderError):
        log = f'委托报错 id:{err.order_id} error_id:{err.error_id} error_msg:{err.error_msg}'
        logging.warning(log)


# ======== 盘前 ========


def held_increase() -> None:
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    all_held_inc(lock_of_disk_cache, PATH_HELD)
    print(f'All held stock day +1!')


def refresh_code_list():
    cache_blacklist.clear()
    black_codes = get_blacklist_codes(target_stock_prefixes)
    cache_blacklist.update(black_codes)
    print(f'Black list refreshed {len(cache_blacklist)} codes.')

    # 中证1000（399852）在5日线之上的时候才开仓
    end_dt = datetime.datetime.now()
    start_dt = end_dt - datetime.timedelta(days=15)
    index_zh_a_hist_df = ak.index_zh_a_hist(
        symbol="399852",
        period="daily",
        start_date=start_dt.strftime('%Y%m%d'),
        end_date=end_dt.strftime('%Y%m%d'),
    )
    values = index_zh_a_hist_df.tail(5)['收盘'].values

    cache_whitelist.clear()
    if values[-1] > np.average(values):
        white_codes = get_whitelist_codes(target_stock_prefixes, p.market_value_min, p.market_value_max)
        cache_whitelist.update(white_codes)
        print(f'White list refreshed {len(cache_whitelist)} codes.')
    else:
        print(f'White list cleared because 399852 is lower than MA.')


def calculate_indicators(data: Union[Dict, pd.DataFrame]) -> Optional[Dict]:
    row_close = data['close']
    row_high = data['high']
    row_low = data['low']

    close_3d = row_close.tail(p.atr_time_period).values
    high_3d = row_high.tail(p.atr_time_period).values
    low_3d = row_low.tail(p.atr_time_period).values

    return {
        'CLOSE_3D': close_3d,
        'HIGH_3D': high_3d,
        'LOW_3D': low_3d,
    }


def prepare_by_tushare(history_codes: List, start: str, end: str) -> int:
    print(f'Prepared time range: {start} - {end}')
    t0 = datetime.datetime.now()

    cache_indicators.clear()
    count = 0

    group_size = min(6000 // p.day_count, 300)  # ts接口最大行数限制8000，保险起见设成6000
    for i in range(0, len(history_codes), group_size):
        sub_codes = [sub_code for sub_code in history_codes[i:i + group_size]]
        temp_data = get_ts_markets(sub_codes, start, end, p.data_cols)
        print(sub_codes)

        for code in sub_codes:
            temp_df = temp_data[temp_data['ts_code'] == code]
            if not temp_df.isnull().values.any() and len(temp_df) == p.day_count:
                cache_indicators[code] = calculate_indicators(temp_df)
                count += 1

    t1 = datetime.datetime.now()
    print(f'Prepared TIME COST: {t1 - t0}')
    return count


def prepare_indicators() -> None:
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return

    now = datetime.datetime.now()
    curr_date = now.strftime('%Y-%m-%d')
    cache_path = PATH_INFO.format(curr_date)
    day_count = p.day_count

    temp_indicators = load_pickle(cache_path)
    if temp_indicators is not None and len(temp_indicators) > 0:
        cache_indicators.update(temp_indicators)
        print(f'Prepared indicators from {cache_path}')
    else:
        history_codes = get_all_historical_codes(target_stock_prefixes)

        start = get_prev_trading_date(now, day_count)
        end = get_prev_trading_date(now, 1)

        count = prepare_by_tushare(history_codes, start, end)
        save_pickle(cache_path, cache_indicators)
        print(f'{count} stock indicators saved to {cache_path}')


# ======== 买点 ========


def wencai_select() -> dict:
    now = datetime.datetime.now()
    now_day = now.strftime("%Y-%m-%d")
    now_min = now.strftime("%H:%M")
    if check_today_is_open_day(now_day):
        if ("09:31" <= now_min < "11:30") or ("13:00" <= now_min < "14:57"):
            print('!', end='')
            df = pywencai.get(query=query)

            if df is not None and type(df) != dict and df.shape[0] > 0:
                with lock_wencai_select:
                    df['最新价'] = df['最新价'].astype(float)
                    print(f'Wencai: {now.strftime("%H:%M:%S")}\n', df[['股票代码', '股票简称', '最新价']])
                    return df.set_index('股票代码')['最新价'].to_dict()
    return {}


def check_stock(code: str, quote: Dict) -> (bool, Dict):
    curr_close = quote['lastPrice']
    curr_open = quote['open']
    last_close = quote['lastClose']

    if code in cache_blacklist:
        return False, {'reason': f'在黑名单'}

    if code not in cache_whitelist:
        return False, {'reason': f'不在白名单'}

    if not curr_close > p.min_price:
        return False, {'reason': f'价格小于{p.min_price}'}

    if not curr_open < curr_close < last_close * p.inc_limit:
        return False, {'reason': f'涨幅不符合区间 {curr_open} < {curr_close} < {last_close * p.inc_limit}'}

    return True, {}


def select_stocks(quotes: Dict) -> List[Dict[str, any]]:
    codes_wencai = wencai_select()

    selections = []
    for code in codes_wencai:
        if code not in quotes:
            print(f'{code} 没有quote数据')
        elif code not in cache_indicators:
            print(f'{code} 没有indicator数据')
        else:
            passed, info = check_stock(code, quotes[code])
            if not passed:
                print(f'{code} {info}')
            else:
                selection = {'code': code, 'price': quotes[code]['lastPrice']}
                selection.update(info)
                selections.append(selection)
    return selections


def scan_buy(quotes: Dict, curr_date: str, positions: List[XtPosition]) -> None:
    selections = select_stocks(quotes)

    # 选出一个以上的股票
    if len(selections) > 0:
        print('Selected: ', selections)
        # selections = sorted(selections, key=lambda x: x['price'])  # 选出的股票按照现价从小到大排序

        position_codes = [position.stock_code for position in positions]
        position_count = get_holding_position_count(positions)
        available_cash = xt_delegate.check_asset().cash

        buy_count = max(0, p.max_count - position_count)            # 确认剩余的仓位
        buy_count = min(buy_count, available_cash // p.amount_each)     # 确认现金够用
        buy_count = min(buy_count, len(selections))                 # 确认选出的股票够用
        buy_count = min(buy_count, p.upper_buy_count)               # 限制一秒内下单数量
        buy_count = int(buy_count)

        for i in range(len(selections)):  # 依次买入
            # logging.info(f'买数相关：持仓{position_count} 现金{available_cash} 已选{len(selections)}')
            if buy_count > 0:
                code = selections[i]['code']
                price = selections[i]['price']
                buy_volume = math.floor(p.amount_each / price / 100) * 100

                if buy_volume <= 0:
                    print(f'{code} 价格过高')
                elif code in position_codes:
                    print(f'{code} 正在持仓')
                elif curr_date in cache_select and code in cache_select[curr_date]:
                    print(f'{code} 今日已选')
                else:
                    buy_count = buy_count - 1
                    # 如果今天未被选股过 and 目前没有持仓则记录（意味着不会加仓
                    order_submit(xt_delegate, xtconstant.STOCK_BUY, code, price, buy_volume,
                                 '选股买单', p.order_premium, STRATEGY_NAME)
                    logging.warning(f'买入委托 {code} {buy_volume}股\t现价:{price:.3f}')
            else:
                break

    # 记录选股历史
    if curr_date not in cache_select:
        cache_select[curr_date] = set()

    for selection in selections:
        if selection['code'] not in cache_select[curr_date]:
            cache_select[curr_date].add(selection['code'])
            logging.warning(
                f"记录选股 {selection['code']}"
                f"\t现价: {selection['price']:.2f}")


def async_scan_buy(quotes: Dict, curr_date: str, positions: List[XtPosition]):
    threading.Thread(target=scan_buy, args=(quotes, curr_date, positions)).start()  # 异步买点


# ======== 卖点 ========


def scan_sell(quotes: Dict, curr_time: str, positions: List[XtPosition]) -> None:
    held_days = load_json(PATH_HELD)

    with lock_of_disk_cache:
        max_prices = load_json(PATH_MAXP)

        # 更新历史最高
        for position in positions:
            code = position.stock_code
            if code in held_days:
                held_day = held_days[code]
                if held_day == 0:
                    continue
                if code in quotes:
                    quote = quotes[code]
                    curr_price = quote['lastPrice']
                    max_prices[code] = round(
                        max(max_prices[code], curr_price) if code in max_prices else curr_price,
                        3,
                    )
        save_json(PATH_MAXP, max_prices)

    my_seller.execute_sell(curr_time, positions, quotes, held_days, max_prices, cache_indicators)


# ======== 框架 ========


def execute_strategy(
    curr_date: str,
    curr_time: str,
    curr_seconds: str,
    curr_quotes: Dict,
):
    positions = xt_delegate.check_positions()

    if '09:31' <= curr_time <= '11:30' or '13:00' <= curr_time <= '14:56':
        scan_sell(curr_quotes, curr_time, positions)

    if '09:40' <= curr_time <= '11:30' or '13:00' <= curr_time <= '14:56':
        if int(curr_seconds) % p.buy_interval == 0:
            async_scan_buy(curr_quotes, curr_date, positions)


def callback_sub_whole(quotes: Dict) -> None:
    now = datetime.datetime.now()

    curr_date = now.strftime('%Y-%m-%d')
    curr_time = now.strftime('%H:%M')

    # 每分钟输出一行开头
    if cache_limits['prev_minutes'] != curr_time:
        cache_limits['prev_minutes'] = curr_time
        print(f'\n[{curr_time}]', end='')

    # 每秒钟开始的时候输出一个点
    with lock_quotes_update:
        curr_seconds = now.strftime('%S')
        cache_quotes.update(quotes)
        if cache_limits['prev_seconds'] != curr_seconds:
            cache_limits['prev_seconds'] = curr_seconds

            # 只有在交易日才执行策略
            if check_today_is_open_day(curr_date):
                print('.' if len(cache_quotes) > 0 else 'x', end='')
                execute_strategy(curr_date, curr_time, curr_seconds, cache_quotes)

                if int(curr_seconds) % p.clean_interval == 0:
                    cache_quotes.clear()  # 防止过时的价格导致挂延时单
            else:
                print('_', end='')


def subscribe_tick(notice=True):
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return
    if notice:
        sample_send_msg(f'[{QMT_ACCOUNT_ID}] {STRATEGY_NAME} 策略启动', 0, '')
    print('[启动行情订阅]', end='')
    cache_limits['sub_seq'] = xtdata.subscribe_whole_quote(["SH", "SZ"], callback=callback_sub_whole)


def unsubscribe_tick(notice=True):
    if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
        return
    if notice:
        sample_send_msg(f'[{QMT_ACCOUNT_ID}] {STRATEGY_NAME} 策略关闭', 0, '')
    if 'sub_seq' in cache_limits:
        xtdata.unsubscribe_quote(cache_limits['sub_seq'])
        print('\n[关闭行情订阅]')


def random_check_open_day():
    now = datetime.datetime.now()
    curr_date = now.strftime('%Y-%m-%d')
    curr_time = now.strftime('%H:%M')
    logging.warning(f'================')
    print(f'[{curr_time}]', end='')
    check_today_is_open_day(curr_date)


if __name__ == '__main__':
    logging_init(path=PATH_LOGS, level=logging.INFO)
    xt_delegate = XtDelegate(
        account_id=QMT_ACCOUNT_ID,
        client_path=QMT_CLIENT_PATH,
        xt_callback=MyCallback())

    my_seller = Seller(xt_delegate, p, STRATEGY_NAME)

    # 重启时防止没有数据在这先加载历史数据
    temp_now = datetime.datetime.now()
    temp_date = temp_now.strftime('%Y-%m-%d')
    temp_time = temp_now.strftime('%H:%M')

    if '09:15' < temp_time and check_today_is_open_day(temp_date):
        refresh_code_list()
        prepare_indicators()
        # 重启如果在交易时间则订阅Tick

        if '09:30' <= temp_time <= '11:30' or '13:00' <= temp_time <= '14:56':
            subscribe_tick()

    # 定时任务启动
    random_time = f'08:{str(math.floor(random() * 60)).zfill(2)}'
    schedule.every().day.at(random_time).do(random_check_open_day)
    schedule.every().day.at('09:10').do(held_increase)
    schedule.every().day.at('09:11').do(refresh_code_list)
    schedule.every().day.at('09:15').do(prepare_indicators)

    schedule.every().day.at('09:30').do(subscribe_tick)
    schedule.every().day.at('11:30').do(unsubscribe_tick, False)

    schedule.every().day.at('13:00').do(subscribe_tick, False)
    schedule.every().day.at('15:00').do(unsubscribe_tick)

    while True:
        schedule.run_pending()
        time.sleep(1)
