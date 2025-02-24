import json
import datetime
import pandas as pd
from toolbox.draw_two_lines import draw_two

stock_code = '301396.SZ'
root = './_cache/debug'
today = datetime.datetime.now().date().strftime("%Y%m%d")

source_path = f'{root}/tick_history.json'
target_path = f'{root}/tick_{today}_{stock_code.split(".")[0]}.csv'
visualization_path = f'{root}/tick_{today}_{stock_code.split(".")[0]}.html'

headers = ['timestamp', 'price', 'volume', 'askPrice', 'askVol', 'bidPrice', 'bidVol']


def locate_and_save():
    with open(source_path, 'r') as file:
        ticks = json.load(file)[stock_code]

    with open(target_path, 'w') as w:
        w.write(',  \t'.join(headers))
        w.write('\n')
        for tick in ticks:
            w.write(',   \t'.join([str(i) for i in tick]))
            w.write('\n')


def visualization():
    # with open(source_path, 'r') as file:
    #     data = json.load(file)[stock_code]
    #
    # x_data = [str(row[0]) for row in data]
    # y1_data = [row[1] for row in data]
    # y2_data = [row[6] for row in data]

    df = pd.read_csv(target_path)
    df.columns = headers
    x_data = list(df['timestamp'].astype(str).values)
    y1_data = list(df['price'].astype(float).values)
    y2_data = list(df['bidVol'].astype(float).values)

    print(x_data)
    print(y1_data)
    print(y2_data)

    data = [x_data, y1_data, y2_data]
    draw_two(data, visualization_path, stock_code)


if __name__ == '__main__':
    # locate_and_save()
    visualization()
