import os
import json
import threading
from typing import List, Dict, Callable

HISTORICAL_SYMBOLS = '_cache/_historical_symbols.txt'


def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, 'r') as r:
            ans = r.read()
        return json.loads(ans)
    else:
        with open(path, 'w') as w:
            w.write('{}')
        return {}


def save_json(path: str, var: dict):
    with open(path, 'w') as w:
        w.write(json.dumps(var, indent=4))


def daily_once(
    lock: threading.Lock,
    memory_cache: Dict,
    file_cache_path: str,
    cache_key: str,
    curr_date: str,
    function: Callable,
    *args,
) -> None:
    with lock:
        if cache_key in memory_cache:
            # 有内存记录
            if memory_cache[cache_key] != curr_date:
                # 内存记录不是今天
                memory_cache[cache_key] = curr_date

                temp_cache = load_json(file_cache_path)
                temp_cache[cache_key] = curr_date
                save_json(file_cache_path, temp_cache)

                function(*args)
                return
        else:
            # 无内存记录，则寻找文件
            temp_cache = load_json(file_cache_path)
            if cache_key not in temp_cache or temp_cache[cache_key] != curr_date:
                # 无文件记录或者文件记录不是今天
                memory_cache[cache_key] = curr_date

                temp_cache[cache_key] = curr_date
                save_json(file_cache_path, temp_cache)
                function(*args)
                return


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
