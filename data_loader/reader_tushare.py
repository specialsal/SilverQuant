from typing import List
from tools.tushare_token import get_tushare_pro


def get_ts_market(code: str, start_date: str, end_date: str, columns: list[str]):
    pro = get_tushare_pro()
    df = pro.daily(
        ts_code=code,
        start_date=start_date,
        end_date=end_date,
    )
    if len(df) > 0:
        return df.loc[df['ts_code'] == code][::-1][columns]
    return None


def get_ts_markets(codes: List[str], start_date: str, end_date: str, columns: list[str]):
    pro = get_tushare_pro()
    try_times = 0
    df = None
    while (df is None or len(df) <= 0) and try_times < 3:
        df = pro.daily(
            ts_code=','.join(codes),
            start_date=start_date,
            end_date=end_date,
        )

    return df[::-1][['ts_code'] + columns]


def test_get_ts_market():
    m = get_ts_market('000001.SZ', '20231028', '20231120', ['open', 'close'])
    print(m['close'].tail(3).values)


def test_get_ts_markets():
    m = get_ts_markets(['000001.SZ', '000002.SZ', '000004.SZ'], '20231028', '20231120', ['open', 'close'])
    print(m)


if __name__ == '__main__':
    # test_get_ts_market()
    test_get_ts_markets()
