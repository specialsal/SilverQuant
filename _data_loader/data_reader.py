import time
import pandas as pd


def get_daily_xtdata(
    ts_code: str,
    start_date: str,
    end_date: str,
    retry_max: int = 3,
) -> (pd.DataFrame, bool):
    from _data_loader.reader_xtdata import get_xtdata_market_datas
    df = None
    retry = 0
    succeed = False
    while (not succeed) and retry < retry_max and (df is None or df.size == 0):
        try:
            retry += 1

            temp_df, _ = get_xtdata_market_datas(
                [ts_code],
                period='1d',
                start_date=start_date,
                end_date=end_date,
            )
            df = temp_df[ts_code]
            df = df.reset_index()
            time.sleep(0.2)  # 不然会卡住
            succeed = True
        except:
            succeed = False

    if df is None or df.size == 0:
        return df, False

    return df, succeed
