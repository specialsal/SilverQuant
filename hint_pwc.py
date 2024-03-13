import logging
import schedule
import datetime
import pywencai

from tools.utils_ding import sample_send_msg

interval = 5
query = '向上突破20日均线，主板，涨幅大于4%，非ST，量比大于1.47，委比大于0.01'
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
    now_min = now.strftime("%H:%M")
    now_sec = now.strftime("%S")
    logging.basicConfig(filename=f'_data/{now_day}-{query}.log')

    if ("09:30" <= now_min < "11:30") or ("13:00" <= now_min < "14:57"):
        result = run()
        if result is not None and result.shape[0] > 0:
            print(f'\n[{now_min}:{now_sec}]', end='')
            sample_send_msg(f'\n{now_min}:{now_sec}\n{result}', 0, 'Message send successful!')
            print('\n', result)
            logging.warning(f'{now_min}:{now_sec}\n{result}', )
        else:
            if int(now_sec) % 60 < interval:
                print(f'\n{now_min}', end='')
            print('.', end='')
    elif now_min == '09:15':
        cache.clear()


def start_schedule():
    schedule.every(interval).seconds.do(job)
    while True:
        schedule.run_pending()


def test():
    from tools.utils_basic import pd_show_all
    pd_show_all()
    print(run(debug=True))


if __name__ == '__main__':
    # test()
    start_schedule()
