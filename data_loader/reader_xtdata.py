import time
import traceback
import pandas as pd
from typing import List, Dict

from xtquant import xtdata


def pre_download_xtdata(codes: list[str], start_date: str, end_date: str, period: str = '1d'):
    def inner_callback(data: dict):
        """
        Example data: {'finished': 1237, 'total': 5300, 'stockcode': '', 'message': '603173.SH'}
        """
        if data['finished'] == data['total']:
            print(f'Download {data["total"]} completed!')
        else:
            # print(data)
            if data['finished'] % 100 == 0:
                print('.', end='')

    time.sleep(1)
    group_size = 500
    for i in range(0, len(codes), group_size):
        sub_codes = [sub_code for sub_code in codes[i:i + group_size]]
        print(f'Downloading: {sub_codes}')
        xtdata.download_history_data2(
            sub_codes,
            period=period,
            start_time=start_date,
            end_time=end_date,
            callback=inner_callback,
        )
        time.sleep(0.2)
    print(f'Download ALL completed!')


def get_xtdata_market_dict(
    codes: List[str],
    start_date: str = '',
    end_date: str = '',
    columns: List[str] = None,
    period: str = '1d',  # 1m 5m 1d
) -> Dict[str, pd.DataFrame]:
    if columns is None:
        columns = ['open', 'close', 'high', 'low', 'volume']

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


def test_pre_download():
    from tools.utils_basic import symbol_to_code
    from tools.utils_cache import get_all_historical_codes

    history_codes = get_all_historical_codes({'000', '001', '002', '003'})
    pre_download_xtdata(
        history_codes,
        start_date='20230801',
        end_date='20230804',
    )

    dict = get_xtdata_market_dict(
        history_codes,
        period='1d',
        start_date='20230801',
        end_date='20230804',
        columns=['close', 'high', 'low']
    )
    print(dict)


if __name__ == '__main__':
    from tools.utils_basic import pd_show_all
    pd_show_all()

    # pre_download()
    # print(full_tick(['000001.SZ', '000002.SZ']))
    # test_get_market()
    test_pre_download()
