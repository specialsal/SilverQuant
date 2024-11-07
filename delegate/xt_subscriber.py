import json
import datetime
import schedule
import threading
import math
import os
import pandas as pd

from random import random
from typing import Dict, Callable

from xtquant import xtdata

from delegate.xt_delegate import XtDelegate
from reader.reader_market import get_ak_market
from tools.utils_cache import check_today_is_open_day, get_total_asset_increase, load_pickle, save_pickle,\
    load_json, save_json
from tools.utils_ding import DingMessager


class XtSubscriber:
    def __init__(
        self,
        account_id: str,
        strategy_name: str,
        delegate: XtDelegate,
        path_deal: str,
        path_assets: str,
        execute_strategy: Callable,     # 策略回调函数
        execute_interval: int = 1,      # 策略执行间隔，单位（秒）
        ding_messager: DingMessager = None,
        open_tick: bool = False,
        open_today_deal_report: bool = False,
        open_today_hold_report: bool = False,
    ):
        self.account_id = '**' + str(account_id)[-4:]
        self.strategy_name = strategy_name
        self.delegate = delegate

        self.path_deal = path_deal
        self.path_assets = path_assets

        self.execute_strategy = execute_strategy
        self.execute_interval = execute_interval
        self.ding_messager = ding_messager

        self.lock_quotes_update = threading.Lock()  # 聚合实时打点缓存的锁

        self.cache_quotes: Dict[str, Dict] = {}     # 记录实时的价格信息
        self.cache_limits: Dict[str, str] = {       # 限制执行次数的缓存集合
            'prev_seconds': '',                     # 限制每秒一次跑策略扫描的缓存
            'prev_minutes': '',                     # 限制每分钟屏幕心跳换行的缓存
        }
        self.cache_history: Dict[str, pd.DataFrame] = {}     # 记录历史日线行情的信息 { code: DataFrame }

        self.open_tick = open_tick
        self.quick_ticks: bool = False              # 是否开启quick tick模式
        self.today_ticks: Dict[str, list] = {}      # 记录tick的历史信息
        # [ 成交时间, 成交价格, 累计成交量 ]

        self.open_today_deal_report = open_today_deal_report
        self.open_today_hold_report = open_today_hold_report

        self.code_list = ['SH', 'SZ']

    # ================
    # 策略触发主函数
    # ================
    def callback_sub_whole(self, quotes: Dict) -> None:
        now = datetime.datetime.now()

        curr_date = now.strftime('%Y-%m-%d')
        curr_time = now.strftime('%H:%M')

        # 每分钟输出一行开头
        if self.cache_limits['prev_minutes'] != curr_time:
            self.cache_limits['prev_minutes'] = curr_time
            print(f'\n[{curr_time}]', end='')

        curr_seconds = now.strftime('%S')
        with self.lock_quotes_update:
            self.cache_quotes.update(quotes)  # 合并最新数据

        if self.open_tick and (not self.quick_ticks):
            self.record_tick_to_memory(quotes)  # 更全

        # 执行策略
        if self.cache_limits['prev_seconds'] != curr_seconds:
            self.cache_limits['prev_seconds'] = curr_seconds

            if int(curr_seconds) % self.execute_interval == 0:
                print('.' if len(self.cache_quotes) > 0 else 'x', end='')  # 每秒钟开始的时候输出一个点

                if self.execute_strategy(
                    curr_date,
                    curr_time,
                    curr_seconds,
                    self.cache_quotes,
                ):
                    with self.lock_quotes_update:
                        if self.quick_ticks:
                            self.record_tick_to_memory(self.cache_quotes)  # 更快
                        self.cache_quotes.clear()  # execute_strategy() return True means need clear

    # ================
    # 订阅tick相关
    # ================
    def subscribe_tick(self, notice=True):
        if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
            return

        if self.ding_messager is not None:
            self.ding_messager.send_text(f'[{self.account_id}]{self.strategy_name}:{"启动" if notice else "恢复"}')
        self.cache_limits['sub_seq'] = xtdata.subscribe_whole_quote(self.code_list, callback=self.callback_sub_whole)
        xtdata.enable_hello = False
        print('[启动行情订阅]', end='')

    def unsubscribe_tick(self, notice=True):
        if not check_today_is_open_day(datetime.datetime.now().strftime('%Y-%m-%d')):
            return

        if 'sub_seq' in self.cache_limits:
            if self.ding_messager is not None:
                self.ding_messager.send_text(f'[{self.account_id}]{self.strategy_name}:{"关闭" if notice else "暂停"}')
            xtdata.unsubscribe_quote(self.cache_limits['sub_seq'])
            print('\n[关闭行情订阅]')

    def update_code_list(self, code_list: list[str]):
        # 防止没数据不打点
        code_list += ['000001.SH']
        self.code_list = code_list

    # ================
    # 盘中实时的tick历史
    # ================
    def record_tick_to_memory(self, quotes):
        # 记录 tick 历史
        for code in quotes:
            if code not in self.today_ticks:
                self.today_ticks[code] = []

            tick_time = datetime.datetime.fromtimestamp(quotes[code]['time'] / 1000).strftime('%H:%M:%S')
            self.today_ticks[code].append([
                tick_time,                              # 成交时间，格式：%H:%M:%S
                round(quotes[code]['lastPrice'], 2),    # 成交价格
                quotes[code]['volume'],                 # 累计成交量（手）
            ])

    def clean_ticks_history(self):
        self.today_ticks.clear()

    def save_tick_history(self):
        json_file = './_cache/debug/tick_history.json'
        with open(json_file, 'w') as file:
            json.dump(self.today_ticks, file, indent=4)
        print(f"字典已成功存储为 {json_file} 文件")

    # ================
    # 盘前下载数据缓存
    # ================
    def download_from_akshare(self, target_codes: list, start: str, end: str, adjust: str, columns: list[str]):
        print(f'Prepared time range: {start} - {end}')
        t0 = datetime.datetime.now()

        group_size = 200
        for i in range(0, len(target_codes), group_size):
            sub_codes = [sub_code for sub_code in target_codes[i:i + group_size]]

            for code in sub_codes:
                df = get_ak_market(code, start, end, columns=columns, adjust=adjust)

                if df is not None:
                    self.cache_history[code] = df

            print(i, sub_codes)  # 已更新数量

        t1 = datetime.datetime.now()
        print(f'Prepared TIME COST: {t1 - t0}')

    def download_cache_history(
        self,
        cache_path: str,
        code_list: list[str],
        start: str,
        end: str,
        adjust: str,
        columns: list[str],
    ):
        temp_indicators = load_pickle(cache_path)
        if temp_indicators is not None and len(temp_indicators) > 0:
            # 如果有缓存就读缓存
            self.cache_history.clear()
            self.cache_history.update(temp_indicators)
            print(f'{len(self.cache_history)} histories loaded from {cache_path}')
        else:
            # 如果没缓存就刷新白名单
            self.cache_history.clear()
            self.download_from_akshare(code_list, start, end, adjust, columns)
            save_pickle(cache_path, self.cache_history)
            print(f'{len(self.cache_history)} of {len(code_list)} histories saved to {cache_path}')

    # ================
    # 盘后报告总结
    # ================
    def check_asset(self):
        curr_date = datetime.datetime.now().strftime('%Y-%m-%d')
        if not check_today_is_open_day(curr_date):
            return

        asset = self.delegate.check_asset()
        change = ''
        increase = get_total_asset_increase(self.path_assets, curr_date, asset.total_asset)
        if increase is not None:
            change = f'\n当日变动: {"+" if increase > 0 else ""}{round(increase, 2)}元'
        self.ding_messager.send_text(f'[{self.account_id}]{self.strategy_name} 盘后清点'
                                     f'\n资产总计: {asset.total_asset}元{change}')

    def today_deal_report(self):
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        if not check_today_is_open_day(today):
            return

        if not os.path.exists(self.path_deal):
            return

        if self.open_today_deal_report:
            df = pd.read_csv(self.path_deal, encoding='gbk')
            if '日期' in df.columns:
                df = df[df['日期'] == today]

            if len(df) > 0:
                title = f'{self.strategy_name} {today} 记录 {len(df)} 条'
                txt = title
                for index, row in df.iterrows():
                    txt += '\n\n> '
                    txt += ' '.join(map(str, row.tolist()))

                self.ding_messager.send_markdown(title, txt)

    def today_hold_report(self):
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        if not check_today_is_open_day(today):
            return

        if self.open_today_hold_report:
            positions = self.delegate.check_positions()
            txt = ''
            i = 0
            for position in positions:
                if position.volume > 0:
                    i += 1
                    txt += '\n\n>'
                    txt += f'{i}[{position.stock_code}]{position.volume}'

            title = f'{self.strategy_name} {today} 持仓 {i} 支'
            txt = title + txt

            self.ding_messager.send_markdown(title, txt)

    # ================
    # 定时器
    # ================
    def start_scheduler(self):
        random_time = f'08:{str(math.floor(random() * 60)).zfill(2)}'
        schedule.every().day.at(random_time).do(random_check_open_day)

        if self.open_tick:
            schedule.every().day.at('09:10').do(self.clean_ticks_history)
            schedule.every().day.at('15:30').do(self.save_tick_history)

        schedule.every().day.at('09:15').do(self.subscribe_tick)
        schedule.every().day.at('11:30').do(self.unsubscribe_tick, False)

        schedule.every().day.at('13:00').do(self.subscribe_tick, False)
        schedule.every().day.at('15:00').do(self.unsubscribe_tick)

        schedule.every().day.at('15:31').do(self.today_deal_report)
        schedule.every().day.at('15:32').do(self.today_hold_report)
        schedule.every().day.at('15:33').do(self.check_asset)


# ================
# 检查是否交易日
# ================
def random_check_open_day():
    now = datetime.datetime.now()
    curr_date = now.strftime('%Y-%m-%d')
    curr_time = now.strftime('%H:%M')
    print(f'[{curr_time}]', end='')
    check_today_is_open_day(curr_date)


# ================
# 持仓自动发现
# ================
def update_position_held(lock: threading.Lock, delegate: XtDelegate, path: str):
    with lock:
        positions = delegate.check_positions()

        held_days = load_json(path)

        # 添加未被缓存记录的持仓
        for position in positions:
            if position.can_use_volume > 0 and \
                    position.stock_code not in held_days.keys():
                held_days[position.stock_code] = 0

        # 删除已清仓的held_days记录
        position_codes = [position.stock_code for position in positions]
        holding_codes = list(held_days.keys())
        for code in holding_codes:
            if code[0] == '_':
                continue

            if code not in position_codes:
                del held_days[code]

        save_json(path, held_days)


# ================================
# 订阅单个股票历史N个分钟级K线
# ================================
def sub_quote(
    callback: Callable,
    code: str,
    count: int = -1,
    period: str = '1m',
):
    xtdata.subscribe_quote(code, period=period, count=count, callback=callback)
