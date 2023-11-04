"""
序号
代码
名称
最新价
涨跌幅
涨跌额
成交量
成交额
振幅
最高
最低
今开
昨收
量比
换手率
市盈率-动态
市净率
总市值
流通市值
涨速
5分钟涨跌
60日涨跌幅
年初至今涨跌幅
"""
import datetime
import pandas as pd
import akshare as ak

from tools.utils_basic import symbol_to_code


def samples():
    # # 查询单股信息
    # stock_individual_info_em_df = ak.stock_individual_info_em(symbol="000001")
    # print(stock_individual_info_em_df)

    # # 查询单股历史行情
    # df = ak.stock_zh_a_hist(symbol="000001", adjust="").iloc[:, :7]
    # print(df)

    # # 单次返回所有沪深京 A 股上市公司的实时行情数据，频繁调用会被封IP，慎用
    # stock_zh_a_spot_em_df = ak.stock_zh_a_spot_em()
    # print(stock_zh_a_spot_em_df)

    # # 上交所
    # stock_sh_a_spot_em_df = ak.stock_sh_a_spot_em()
    # print(stock_sh_a_spot_em_df)

    # # 深交所
    # stock_sz_a_spot_em_df = ak.stock_sz_a_spot_em()
    # print(stock_sz_a_spot_em_df)

    # # 北交所
    # stock_bj_a_spot_em_df = ak.stock_bj_a_spot_em()
    # print(stock_bj_a_spot_em_df)

    # # 新股
    # stock_new_a_spot_em_df = ak.stock_new_a_spot_em()
    # print(stock_new_a_spot_em_df)

    # # 创业板
    # stock_cy_a_spot_em_df = ak.stock_cy_a_spot_em()
    # print(stock_cy_a_spot_em_df)

    # # 科创板
    # stock_kc_a_spot_em_df = ak.stock_kc_a_spot_em()
    # print(stock_kc_a_spot_em_df)

    # # 同花顺概念列表
    # stock_board_concept_name_ths_df = ak.stock_board_concept_name_ths()
    # print(stock_board_concept_name_ths_df)

    # # 同花顺概念成份
    # stock_board_concept_cons_ths_df = ak.stock_board_concept_cons_ths(symbol="光刻机")
    # print(stock_board_concept_cons_ths_df)

    # # 东方财富 概念板块列表 单次返回当前时刻所有概念板块数据
    # stock_board_concept_name_em_df = ak.stock_board_concept_name_em()
    # print(stock_board_concept_name_em_df)

    # # 东方财富-沪深板块-概念板块-板块成份  单次返回当前时刻所有成份股
    # stock_board_concept_cons_em_df = ak.stock_board_concept_cons_em(symbol="光刻胶")
    # print(stock_board_concept_cons_em_df)

    # # 东方财富-指数-分时
    # stock_board_concept_hist_min_em_df = ak.stock_board_concept_hist_min_em(symbol="长寿药", max_param="1")
    # print(stock_board_concept_hist_min_em_df)

    a = ak.stock_zh_a_spot_em()
    print(a)


def get_new_stock_list_days(before_days: int) -> list:
    df = ak.stock_new_a_spot_em()
    filtered_df = df.loc[df['上市日期'] > (datetime.datetime.now() - datetime.timedelta(days=before_days)).date()]
    symbols = filtered_df['代码'].values
    return [symbol_to_code(symbol) for symbol in symbols]


def get_new_stock_list_date(before_date: str) -> list:
    df = ak.stock_new_a_spot_em()
    filtered_df = df.loc[df['上市日期'] > datetime.datetime.strptime(before_date, '%Y%m%d').date()]
    symbols = filtered_df['代码'].values
    return [symbol_to_code(symbol) for symbol in symbols]


def test_get_new_stock_list():
    c = get_new_stock_list_date('20230807')
    print(c)


if __name__ == '__main__':
    pd.set_option('display.width', 1000)
    pd.set_option('display.min_rows', 1000)
    pd.set_option('display.max_rows', 6000)
    pd.set_option('display.max_columns', 200)

    test_get_new_stock_list()
