import datetime
import requests
import pandas as pd
from typing import Optional

import akshare as ak
import pywencai
from tools.utils_basic import is_symbol, is_stock, code_to_symbol


def get_wencai_codes(queries: list[str]) -> list[str]:
    result = set()
    for query in queries:
        df = pywencai.get(query=query, perpage=100, loop=True)
        if df is not None and type(df) != dict and df.shape[0] > 0:
            result.update(df['股票代码'].values)
    return list(result)


def pull_stock_codes(prefix: str, host: str, auth: str) -> (Optional[list[str]], str):
    key = f'{prefix}_{datetime.datetime.now().date().strftime("%Y%m%d")}'
    response = requests.get(f'{host}/get_set/{key}?auth={auth}')
    if response.status_code == 200:
        return response.json(), ''
    elif response.status_code == 404:
        return None, response.json()['error']
    else:
        return None, 'Unknown Error'


def append_ak_daily_dict(source_df: pd.DataFrame, quote: dict, curr_date: str) -> pd.DataFrame:
    df = source_df._append({
        'datetime': curr_date,
        'open': quote['open'],
        'high': quote['high'],
        'low': quote['low'],
        'close': quote['lastPrice'],
        'volume': quote['volume'],
        'amount': quote['amount'],
    }, ignore_index=True)
    return df


def append_ak_daily_row(source_df: pd.DataFrame, row: dict) -> pd.DataFrame:
    df = source_df._append(row, ignore_index=True)
    return df


# https://akshare.akfamily.xyz/data/stock/stock.html#id21
def get_ak_daily_history(
    code: str,
    start_date: str,  # format: 20240101
    end_date: str,
    columns: list[str] = None,
    adjust='',
):
    if not is_stock(code):
        return None

    try:
        df = ak.stock_zh_a_hist(
            symbol=code_to_symbol(code),
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            period='daily',
        )
        df = df.rename(columns={
            '日期': 'datetime',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
            '成交额': 'amount',
        })
    except:
        df = []

    if len(df) > 0:
        df['datetime'] = pd.to_datetime(df['datetime']).dt.strftime('%Y%m%d')
        if columns is not None:
            return df[columns]
        return df
    return None

