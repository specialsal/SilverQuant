import json
import logging
import pandas as pd


def pd_show_all() -> None:
    pd.set_option('display.width', 1000)
    pd.set_option('display.min_rows', 1000)
    pd.set_option('display.max_rows', 5000)
    pd.set_option('display.max_columns', 20)
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
    if symbol[:2] == '00':
        return symbol + '.SZ'
    elif symbol[:2] == '30':
        return symbol + '.SZ'
    elif symbol[:2] == '60':
        return symbol + '.SH'
    elif symbol[:2] == '68':
        return symbol + '.SH'
    else:
        return ''


def code_to_symbol(code: str) -> str:
    return code.split('.')[0]


def load_json(path: str) -> dict:
    try:
        with open(path, 'r') as r:
            ans = r.read()

        return json.loads(ans)
    except:
        return {}


def save_json(path: str, var: dict):
    with open(path, 'w') as w:
        w.write(json.dumps(var))


if __name__ == '__main__':
    # logging_init()
    # logging.warning('123456')

    save_json('./data/test.json', {'a': 1})
    a = load_json('./data/test.json')
    print(a)
