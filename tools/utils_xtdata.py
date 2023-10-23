import datetime

from xtquant import xtdata

open_day_cache = {}


# 最新只能支持到开盘当日
def check_today_is_open_day(now: datetime.datetime) -> bool:
    cache_key_today = now.strftime("%Y%m%d")

    # 内存缓存
    if cache_key_today in open_day_cache.keys():
        return open_day_cache[cache_key_today]

    # 软件缓存
    start_date = (now - datetime.timedelta(days=10)).strftime("%Y%m%d")
    end_date = (now + datetime.timedelta(days=20)).strftime("%Y%m%d")
    time_tags = xtdata.get_trading_dates('SZ', start_date, end_date, 60)

    is_today_open_day = xtdata.datetime_to_timetag(cache_key_today + '000000') in time_tags
    if 8 < now.hour < 18:
        print(f'{now.strftime("%H:%M:%S")} {cache_key_today} is {is_today_open_day} open day')
        open_day_cache[cache_key_today] = is_today_open_day
    return is_today_open_day


def get_prev_trading_date(now: datetime.datetime, count: int) -> str:
    assert count > 0
    curr_date = now.strftime("%Y%m%d")
    prev_date = (now - datetime.timedelta(days=count * 2 + 10)).strftime("%Y%m%d")

    time_tags = xtdata.get_trading_dates('SZ', prev_date, curr_date, count)
    assert len(time_tags) == count, 'count 设置过大'

    return xtdata.timetag_to_datetime(time_tags[0], "%Y%m%d")


def test_check_today_is_open_day():
    print(check_today_is_open_day(datetime.datetime.now() - datetime.timedelta(days=5)))


def test_get_prev_trading_date():
    print(get_prev_trading_date(datetime.datetime.now(), 5))


if __name__ == '__main__':
    # test_check_today_is_open_day()
    test_get_prev_trading_date()
