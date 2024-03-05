import schedule
import datetime
import pywencai

from tools.utils_ding import sample_send_msg


query = '向上突破2日均线，主板，涨幅大于4%，非ST'
cache = set()


def run():
    df = pywencai.get(query=query)
    df = df[['股票代码', '股票简称', '最新价']]
    df = df[~df['股票代码'].isin(cache)]
    cache.update(list(df['股票代码']))
    return str(df)


def job():
    now = datetime.datetime.now().strftime("%H:%M")
    if ("09:30" <= now <= "11:30") or ("13:00" <= now <= "14:57"):
        result = run()
        sample_send_msg(f'{now}\n{result}', 0, now)
    elif now == '15:00':
        cache.clear()


def start_schedule():
    schedule.every(1).minutes.do(job)
    while True:
        schedule.run_pending()


def test():
    print(run())
    print('====')
    print(run())


if __name__ == '__main__':
    # test()
    start_schedule()
