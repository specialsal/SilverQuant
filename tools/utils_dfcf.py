'''
dfcf_symbol <-> symbol <-> code
'''
from tools.utils_basic import symbol_to_code, code_to_symbol


def symbol_to_dfcf_symbol(symbol: str) -> str:
    if symbol[:2] in ['00', '30']:
        return f'SZSE.{symbol}'
    elif symbol[:2] in ['60', '68']:
        return f'SHSE.{symbol}'
    else:
        return symbol + f'BJSE.{symbol}'


def dfcf_symbol_to_symbol(dfcf_symbol: str) -> str:
    arr = dfcf_symbol.split('.')
    assert len(arr) == 2, 'code不符合格式'
    return arr[-1]


def code_to_dfcf_symbol(code):
    return symbol_to_dfcf_symbol(code_to_symbol(code))


def dfcf_symbol_to_code(dfcf_symbol):
    return symbol_to_code(dfcf_symbol_to_symbol(dfcf_symbol))
