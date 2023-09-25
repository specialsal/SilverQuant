import traceback
import pandas as pd
import backtrader as bt
from datetime import datetime
from typing import List, Callable

from constant import *
from _data_loader.reader_xtdata import get_xtdata_market_datas
from _tools.utils_basic import symbol_to_code, code_to_symbol


def bt_feed_pandas_xtdata(
    cerebro: bt.Cerebro,
    codes: List[str],
    start_date: datetime,
    end_date: datetime,
    check: Callable = None,
) -> bool:
    print(f'fetching codes {codes} ...')
    dfs, succeed = get_xtdata_market_datas(
        codes,
        period="1d",
        start_date=start_date.strftime('%Y%m%d'),
        end_date=end_date.strftime('%Y%m%d'),
    )
    if not succeed:
        print(f'fetch codes {codes} failed!')
        return False

    all_succeed = True
    for code in codes:
        symbol = code_to_symbol(code)
        try:
            df = dfs[code]
            df = df.reset_index()
            df.index = pd.to_datetime(df['date'], format='%Y%m%d')

            if (check is not None) and (not check(df)):
                print(f'check codes {symbol} failed!')
                return False

            data = bt.feeds.PandasData(
                name=symbol,
                dataname=df,
                fromdate=start_date,
                todate=end_date,
                plot=False,
            )
            cerebro.adddata(data)
            print(f'feeds symbol {symbol} succeed!')
            all_succeed = all_succeed and True
        except:
            traceback.print_exc()
            print(f'feeds symbol {symbol} failed!')
            all_succeed = all_succeed and False
    return all_succeed


def bt_feed_pandas_datas(
    cerebro: bt.Cerebro,
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    check: Callable = None,
    data_source: int = DataSource.XTDATA,
) -> bool:
    all_succeed = True
    if data_source == DataSource.XTDATA:
        codes = []
        i = 0
        for symbol in symbols:
            codes.append(symbol_to_code(symbol))
            if i == 100:
                bt_feed_pandas_xtdata(cerebro, codes, start_date, end_date, check)
                codes = []
                i = 0
            else:
                i += 1
        bt_feed_pandas_xtdata(cerebro, codes, start_date, end_date, check)
    return all_succeed


def bt_data_to_pandas(
    bt_data: bt.feeds.pandafeed.PandasData,
    length: int,
    columns: List[str] = None,
) -> pd.DataFrame:
    """
    如果长度超出，则返回 df.empty == True 的DataFrame
    """
    get = lambda temp_data: temp_data.get(ago=0, size=length)

    if columns is None:
        columns = ['open', 'high', 'low', 'close', 'volume']

    fields = {}
    for column in columns:
        fields[column] = get(getattr(bt_data, column))

    time = [bt_data.num2date(x) for x in get(bt_data.datetime)]
    df = pd.DataFrame(data=fields, index=time)
    df.index.name = 'date'

    return df


if __name__ == '__main__':
    data, _ = get_xtdata_market_datas(['000001.SZ', '000002.SZ'], '1d', start_date='20220101', end_date='20220701')
    print(data)
    print(data['000001.SZ'])
