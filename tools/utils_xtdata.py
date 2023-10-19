import datetime

from xtquant import xtdata

open_day_cache = {}


# 最新只能支持到开盘当日
def check_today_is_open_day(now: datetime.datetime):
    cache_key_today = now.strftime("%Y%m%d")

    # 内存缓存
    if cache_key_today in open_day_cache.keys():
        return open_day_cache[cache_key_today]

    # 软件缓存
    start_date = (now - datetime.timedelta(days=10)).strftime("%Y%m%d")
    end_date = (now + datetime.timedelta(days=20)).strftime("%Y%m%d")
    time_tags = xtdata.get_trading_dates('SZ', start_date, end_date, 60)

    is_today_open_day = xtdata.datetime_to_timetag(cache_key_today + '000000') in time_tags
    if  9 < now.hour < 18:
        print(f'{cache_key_today} is {is_today_open_day} open day')
        open_day_cache[cache_key_today] = is_today_open_day
    return is_today_open_day


def test_check_today_is_open_day():
    print(check_today_is_open_day(datetime.datetime.now() - datetime.timedelta(days=5)))


if __name__ == '__main__':
    test_check_today_is_open_day()
