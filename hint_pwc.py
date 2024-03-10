import logging
import schedule
import datetime
import pywencai

from tools.utils_ding import sample_send_msg


query = '向上突破20日均线，主板，涨幅大于4%，非ST，量比大于1.47，委比大于0'
cache = set()


def run():
    df = pywencai.get(query=query)
    df = df[['股票代码', '股票简称', '最新价']]
    df = df[~df['股票代码'].isin(cache)]
    cache.update(list(df['股票代码']))
    if df.shape[0] > 0:
        return df
    return None


def job():
    now = datetime.datetime.now()
    now_day = now.strftime("%Y-%m-%d")
    now_min = now.strftime("%H:%M")
    logging.basicConfig(filename=f'_data/{now_day}-{query}.log')

    if ("09:30" <= now_min < "11:30") or ("13:00" <= now_min < "14:57"):
        print(f'[{now_min}]', end='')
        result = run()
        if result is not None:
            sample_send_msg(f'{now_min}\n{result}', 0, 'Message send successful!')
            print(result)
            logging.warning(f'{now_min}\n{result}', )
        else:
            print(None)
    elif now_min == '09:15':
        cache.clear()


def start_schedule():
    schedule.every(1).minutes.do(job)
    while True:
        schedule.run_pending()


def test():
    from tools.utils_basic import pd_show_all
    pd_show_all()
    print(run())


if __name__ == '__main__':
    # test()
    start_schedule()
