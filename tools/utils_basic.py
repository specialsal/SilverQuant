import logging
import pandas as pd


def pd_show_all() -> None:
    pd.set_option('display.width', None)
    pd.set_option('display.min_rows', 1000)
    pd.set_option('display.max_rows', 5000)
    pd.set_option('display.max_columns', 200)
    pd.set_option('display.unicode.ambiguous_as_wide', True)
    pd.set_option('display.unicode.east_asian_width', True)
    pd.set_option('display.float_format', lambda x: f'{x:.3f}')


def logging_init(path=None, level=logging.DEBUG, file_line=False):
    file_line_fmt = ""
    if file_line:
        file_line_fmt = "%(filename)s[line:%(lineno)d] - %(levelname)s: "
    logging.basicConfig(
        level=level,
        format=file_line_fmt + "%(asctime)s|%(message)s",
        filename=path
    )


def logger_init(path=None) -> logging.Logger:
    logger = logging.getLogger('a')
    logger.setLevel(logging.DEBUG)

    # 移除已存在的处理器
    for handler in logger.handlers:
        logger.removeHandler(handler)

    if path is None:
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
    else:
        handler = logging.FileHandler(path)
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


def symbol_to_code(symbol: str) -> str:
    if symbol[:2] in ['00', '30']:
        return f'{symbol}.SZ'
    elif symbol[:2] in ['60', '68']:
        return f'{symbol}.SH'
    else:
        return f'{symbol}.BJ'


def code_to_symbol(code: str) -> str:
    arr = code.split('.')
    assert len(arr) == 2, 'code不符合格式'
    return arr[0]


def get_symbol_exchange(symbol: str) -> str:
    if symbol[:2] in ['00', '30']:
        return 'SZ'
    elif symbol[:2] in ['60', '68']:
        return 'SH'
    else:
        return 'BJ'


def get_code_exchange(code: str) -> str:
    arr = code.split('.')
    assert len(arr) == 2, 'code不符合格式'
    return arr[1][:2]


def map_num_to_chr(num):
    quotient = num // 100
    if quotient < 10:
        return chr(quotient + 48)  # 将数字转换为对应的 ASCII 字符
    elif quotient < 36:
        return chr(quotient - 10 + 97)  # 将数字转换为小写字母
    elif quotient < 62:
        return chr(quotient - 36 + 65)  # 将数字转换为大写字母
    else:
        return '.'


if __name__ == '__main__':
    # logging_init()
    # logging.warning('123456')
    print(map_num_to_chr(6300))
