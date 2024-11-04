"""
https://www.iwencai.com/
"""
import pywencai

query_1 = '，'.join([
    '向上突破10日均线',
    '量比大于1.8',
    '大单净量大于0.0',
    '主板',
    '非ST',
    '50亿<市值<1000亿',
    '委比大于0.02',
    '利润增长大于50%',
])

query_2 = '，'.join([
    # 'MACD<0',
    '10个交易日内MACD绿柱昨日最长',
    'MACD今日上升',
    '流通市值小于100亿',
    '最近一个月内有一次涨幅大于9.9%',
    '非北交所',
    '非科创板',
    '非ST',
    '上市时间大于100天',
])

select_query = query_2
print(select_query, '\n')


def get_wencai_codes_prices(query, debugging=False) -> dict[str, str]:
    df = pywencai.get(query=query)

    if df is not None and type(df) != dict and df.shape[0] > 0:
        # target_col = f'收盘价:不复权[{datetime.datetime.now().strftime("%Y%m%d")}]'
        target_col = '最新价'

        df['最新价'] = df[target_col].astype(float)
        if debugging:
            now = datetime.datetime.now()
            # now_day = now.strftime("%Y-%m-%d")
            # now_min = now.strftime("%H:%M")
            print(f'Wencai: {now.strftime("%H:%M:%S")}\n', df[['股票代码', '股票简称', '最新价']])
        return df.set_index('股票代码')['最新价'].to_dict()
    return {}


if __name__ == '__main__':
    import datetime
    from tools.utils_basic import pd_show_all
    pd_show_all()

    # a = select(select_query, debugging=True)
    a = get_wencai_codes_prices([select_query])
    print(a)
