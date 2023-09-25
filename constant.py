
class DataSource:
    LOCAL = 0
    TUSHARE = 1
    AKSHARE = 2
    XTDATA = 3


class MarketColumns:
    DATE = 'date'
    OPEN = 'open'
    LOW = 'low'
    HIGH = 'high'
    CLOSE = 'close'
    VOLUME = 'volume'

    SMA5 = 'ma5'
    SMA10 = 'ma10'
    SMA20 = 'ma20'
    SMA30 = 'ma30'
    SMA60 = 'ma60'
    SMA120 = 'ma120'
    SMA250 = 'ma250'

    EMA10 = 'EMA_10'
    EMA14 = 'EMA_14'
    EMA55 = 'EMA_55'
    EMA300 = 'EMA_300'


if __name__ == '__main__':
    print(DataSource.AKSHARE)
