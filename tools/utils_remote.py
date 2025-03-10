import datetime
import requests
import pandas as pd
from typing import Optional

import akshare as ak
import pywencai

from reader.tushare_agent import get_tushare_pro
from tools.utils_basic import is_stock, code_to_symbol


DATA_SOURCE_AKSHARE = 0
DATA_SOURCE_TUSHARE = 1


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


def get_daily_history(
    code: str,
    start_date: str,  # format: 20240101
    end_date: str,
    columns: list[str] = None,
    adjust='',
    data_source=DATA_SOURCE_AKSHARE,
) -> Optional[pd.DataFrame]:
    if data_source == DATA_SOURCE_TUSHARE:
        return get_ts_daily_history(code, start_date, end_date, columns, adjust)
    return get_ak_daily_history(code, start_date, end_date, columns, adjust)


# https://akshare.akfamily.xyz/data/stock/stock.html#id21
def get_ak_daily_history(
    code: str,
    start_date: str,  # format: 20240101
    end_date: str,
    columns: list[str] = None,
    adjust='',
) -> Optional[pd.DataFrame]:
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


def ts_to_standard(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={
        'vol': 'volume',
        'trade_date': 'datetime',
    })
    df['volume'] = df['volume'].astype(int)
    df['amount'] *= 1000
    df = df[::-1]
    df.reset_index(drop=True, inplace=True)
    return df


# 使用 tushare 数据源记得 pip install tushare
# 同时配置 tushare 的 token，在官网注册获取
# https://tushare.pro/document/2?doc_id=27
def get_ts_daily_history(
    code: str,
    start_date: str,  # format: 20240101
    end_date: str,
    columns: list[str] = None,
    adjust='',
) -> Optional[pd.DataFrame]:
    if not is_stock(code):
        return None

    pro = get_tushare_pro()
    df = pro.daily(
        ts_code=code,
        start_date=start_date,
        end_date=end_date,
    )
    df = ts_to_standard(df)
    if len(df) > 0:
        if columns is not None:
            return df[columns]
        return df
    return None


# 复合版:通过 ts_code 列区分不同的票
# https://tushare.pro/document/2?doc_id=27
def get_ts_daily_histories(
    codes: list[str],
    start_date: str,
    end_date: str,
    columns: list[str] = None,
) -> Optional[pd.DataFrame]:
    pro = get_tushare_pro()
    try_times = 0
    df = None
    while (df is None or len(df) <= 0) and try_times < 3:
        df = pro.daily(
            ts_code=','.join(codes),
            start_date=start_date,
            end_date=end_date,
        )

    df = ts_to_standard(df)
    if len(df) > 0:
        if columns is not None:
            return df[['ts_code'] + columns]
        return df
    return None
