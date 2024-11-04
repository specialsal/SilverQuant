
def get_stock_set():
    s = set()
    with open('./_doc/stock_list.csv', 'r', encoding='gbk', errors='ignore') as r:
        lines = r.readlines()
        for line in lines:
            s.add((line[:6]))
    return s


if __name__ == '__main__':
    ss = get_stock_set()
    print(ss)
    print(len(ss))
