import time
import traceback
import pandas as pd
from typing import List, Dict

from xtquant import xtdata


def pre_download(start_date: str, end_date: str):
    def inner_download(codes, start_time: str, end_time: str):
        xtdata.download_history_data2(
            codes,
            period="1d",
            start_time=start_time,
            end_time=end_time,
        )

    df = pd.read_csv('_cache/_stock_list.csv')
    t = []
    i = 0
    for index, row in df.iterrows():
        t.append(row['ts_code'])
        if i == 100:
            inner_download(t, start_date, end_date)
            time.sleep(0.1)
            t = []
            i = 0
        else:
            i += 1
    inner_download(t, start_date, end_date)


def get_xtdata_market_dict(
    codes: List[str],
    start_date: str = '',
    end_date: str = '',
    columns: List[str] = None,
    period: str = '1d',  # 1m 5m 1d
) -> Dict[str, pd.DataFrame]:
    if columns is None:
        columns = ['open', 'close', 'high', 'low', 'volume']

    # 下载历史数据
    xtdata.download_history_data2(
        codes,
        period=period,
        start_time=start_date,
        end_time=end_date,
    )

    # 一次性取数据
    return xtdata.get_market_data(
        columns,
        codes,
        period=period,
        start_time=start_date,
        end_time=end_date,
    )


def get_xtdata_market_datas(
    codes: List[str],
    period: str = '1d',  # 1m 5m 1d
    start_date: str = '',
    end_date: str = '',
    columns: List[str] = None,
) -> (pd.DataFrame, bool):
    if columns is None:
        columns = ['open', 'close', 'high', 'low', 'volume']

    try:
        temp_dict = get_xtdata_market_dict(codes, start_date, end_date, columns, period)

        temp_list = []
        for code in codes:
            df = pd.concat([temp_dict[col].loc[code] for col in columns], axis=1)
            df.columns = columns
            for column in columns:
                df[column] = df[column].round(3)
            df = df.rename_axis('date')
            temp_list.append(df)
        ans = pd.concat(temp_list, axis=1, keys=codes)

        return ans, True
    except:
        traceback.print_exc()
        return None, False


def full_tick(codes: List[str]):
    # 取全推数据
    return xtdata.get_full_tick(codes)


def test_get_market():
    ts_code_1 = '000002.SZ'
    ts_code_2 = '600519.SH'

    data = get_xtdata_market_dict(
        [ts_code_1, ts_code_2],
        period='1d',
        start_date='20230701',
        end_date='20230731',
        columns=['close', 'high', 'low']
    )
    import talib as ta

    row_close = data['close'].loc[ts_code_1]
    row_high = data['high'].loc[ts_code_1]
    row_low = data['low'].loc[ts_code_1]

    period = 7
    low = row_low.tail(period + 1).values
    high = row_high.tail(period + 1).values
    close = row_close.tail(period + 1).values
    atr = ta.ATR(high, low, close, timeperiod=period)
    print(atr[-1])

    period = 3
    close = row_close.tail(period).values
    sma3 = ta.SMA(close, timeperiod=period)
    print(sma3[-1])

    # a, _ = get_xtdata_market_datas(
    #     [ts_code_1, ts_code_2],
    #     period='1d',
    #     start_date='20220703',
    #     end_date='20230710',
    # )
    # print(a[ts_code_1])


if __name__ == '__main__':
    from tools.utils_basic import pd_show_all
    pd_show_all()

    # pre_download()
    # print(full_tick(['000001.SZ', '000002.SZ']))
    test_get_market()
