import logging
import time

import datetime
import pywencai

from tools.utils_ding import sample_send_msg


interval = 12
query = '，'.join([
    # '涨幅小于5%',
    '主板和创业板',
    '非ST',
    '非银行',
    # '非证券',
    # '非交通',
    # '非地产',
    # '非基建',
    '向上突破20日均线',
    # '向上突破30日均线',
    # 'mtm金叉',
    # 'skdj金叉',
    '放量',
    'dde大单净量大于0.1',
    '量比大于1.99',
    '委比大于0.02',
    '30亿<市值<600亿',
    '昨日流通市值从小到大排序',
])
cache = set()


def run(debug=False):
    df = pywencai.get(query=query)
    if debug:
        print(df)

    if df is not None:
        if type(df) == dict:
            print(df)
            return None
        elif df.shape[0] > 0:
            df = df[['股票代码', '股票简称', '最新价']]
            df = df[~df['股票代码'].isin(cache)]
            cache.update(list(df['股票代码']))
            return df
    return None


def job():
    now = datetime.datetime.now()
    now_day = now.strftime("%Y-%m-%d")
    logging.basicConfig(filename=f'_data/{now_day}.txt')

    now_min = now.strftime("%H:%M")
    now_sec = now.strftime("%S")

    if ("09:30" <= now_min < "11:30") or ("13:00" <= now_min < "14:57"):
        result = run()
        if result is not None and result.shape[0] > 0:
            for index, row in result.iterrows():
                logging.warning(f"{now_day} {now_min}:{now_sec} {row['股票代码']} {row['股票简称']} {row['最新价']}", )

            result_str = result.to_string(header=False, index=False)

            print(f'\n[{now_min}:{now_sec}] ', result_str, end='')
            sample_send_msg(f'{now_day} {now_min}:{now_sec}\n{result_str}', 1, '',)
        else:
            if int(now_min[-2:]) % 5 == 0 and int(now_sec) < interval * 2 - 5:
                print(f'\n{now_day} {now_min}', end='')
            print('.', end='')
    elif now_min == '09:15':
        logging.warning(query)
        cache.clear()


def start_schedule():
    print('Start watching...')
    print(query)
    while True:
        job()
        time.sleep(interval)


def test():
    from tools.utils_basic import pd_show_all
    pd_show_all()
    df = run(debug=True)
    print('=========')
    if df is not None:
        for index, row in df.iterrows():
            print('Row index:', index)
            print('股票代码:', row['股票代码'])
            print('股票简称:', row['股票简称'])
            print('最新价:', row['最新价'])


if __name__ == '__main__':
    # test()
    start_schedule()