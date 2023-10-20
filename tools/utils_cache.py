import json
import threading
from typing import List

HISTORICAL_SYMBOLS = '_cache/_historical_symbols.txt'


def load_json(path: str) -> dict:
    try:
        with open(path, 'r') as r:
            ans = r.read()
        return json.loads(ans)
    except:
        with open(path, 'w') as w:
            w.write('{}')
        return {}


def save_json(path: str, var: dict):
    with open(path, 'w') as w:
        w.write(json.dumps(var, indent=4))


def all_held_inc(lock: threading.Lock, path: str):
    with lock:
        held_days = load_json(path)

        # 所有持仓天数计数+1
        for code in held_days.keys():
            held_days[code] += 1

        save_json(path, held_days)


def new_held(lock: threading.Lock, path: str, codes: List[str]):
    with lock:
        held_days = load_json(path)
        for code in codes:
            held_days[code] = 0
        save_json(path, held_days)


def del_held(lock: threading.Lock, path: str, codes: List[str]):
    with lock:
        held_days = load_json(path)
        for code in codes:
            if code in held_days:
                del held_days[code]
        save_json(path, held_days)


def get_all_historical_symbols():
    with open(HISTORICAL_SYMBOLS, 'r') as r:
        symbols = r.read().split('\n')
    return symbols
