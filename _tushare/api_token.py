import tushare as ts


def get_tushare_pro():
    ts.set_token('4ba66c603baf16303439a376d082ced5c7ae248c134e685975a697c2')
    return ts.pro_api()
