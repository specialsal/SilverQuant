from data_loader.reader_xtdata import get_xtdata_market_datas
from tools.utils_basic import pd_show_all

codes = [
    '000001.SZ',
    '600519.SH',
]

dfs, succeed = get_xtdata_market_datas(
    codes,
    period="1d",
    start_date='20230701',
    end_date='20230731',
    columns=['open'],
)

pd_show_all()
print(dfs)
