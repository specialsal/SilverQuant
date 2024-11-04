from typing import List, Optional

import pandas as pd
import akshare as ak

from tools.utils_basic import code_to_symbol, is_stock
from reader.tushare_token import get_tushare_pro


# https://tushare.pro/document/2?doc_id=27
def get_ts_market(
    code: str,
    start_date: str,
    end_date: str,
    columns: List[str] = None,
) -> Optional[pd.DataFrame]:
    pro = get_tushare_pro()
    df = pro.daily(
        ts_code=code,
        start_date=start_date,
        end_date=end_date,
    )
    df = df.rename(columns={
        'vol': 'volume',
        'trade_date': 'datetime',
    })
    df['amount'] *= 1000
    if len(df) > 0:
        if columns is not None:
            return df[::-1][['ts_code'] + columns]
        return df[::-1]
    return None


# https://tushare.pro/document/2?doc_id=27
def get_ts_markets(
    codes: List[str],
    start_date: str,
    end_date: str,
    columns: List[str] = None,
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
        df = df.rename(columns={
            'vol': 'volume',
            'trade_date': 'datetime',
        })
        df['amount'] *= 1000
    if len(df) > 0:
        if columns is not None:
            return df[::-1][['ts_code'] + columns]
        return df[::-1]
    return None


# https://akshare.akfamily.xyz/data/stock/stock.html#id21
def get_ak_market(
    code: str,
    start_date: str,
    end_date: str,
    columns: List[str] = None,
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
