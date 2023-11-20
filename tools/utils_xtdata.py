import datetime

from xtquant import xtdata


# 最新只能支持到开盘当日
def check_today_is_open_day(curr_date: str) -> bool:
    time_tags = xtdata.get_trading_dates('SZ', curr_date, curr_date)
    # print([xtdata.timetag_to_datetime(time_tag, "%Y-%m-%d %H:%M:%S") for time_tag in time_tags])
    return len(time_tags) > 0


def get_prev_trading_date(now: datetime.datetime, count: int) -> str:
    assert count >= 0, 'count 不能 < 0'
    curr_date = now.strftime("%Y%m%d")
    prev_date = (now - datetime.timedelta(days=count * 2 + 10)).strftime("%Y%m%d")  # 设置大一些省的不够用

    count = count + 1  # 获取前count天的日期，为了不包含今天所以+1
    time_tags = xtdata.get_trading_dates('SZ', prev_date, curr_date, count)
    assert len(time_tags) == count, 'count 设置过大'

    return xtdata.timetag_to_datetime(time_tags[0], "%Y%m%d")


def test_check_today_is_open_day():
    # import timeit
    # curr_date = datetime.datetime.now().strftime("%Y%m%d")
    # number = 256
    # execution_time = timeit.repeat(lambda: check_today_is_open_day(curr_date), number=number, repeat=6)
    # print(execution_time)
    # average_time = sum(execution_time) / len(execution_time) / number
    # print(f"平均执行时间：{average_time} 秒")
    print(check_today_is_open_day('20231021'))


def test_get_prev_trading_date():
    print(get_prev_trading_date(datetime.datetime.now(), 0))


if __name__ == '__main__':
    # test_check_today_is_open_day()
    test_get_prev_trading_date()
