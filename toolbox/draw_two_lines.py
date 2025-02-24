from pyecharts import options as opts
from pyecharts.charts import Grid, Line


def draw_two(
    data: list,
    path: str,
    title: str = '',
    names: list = None,
    color: list = None,
    maxmin_A: list = None,
    maxmin_B: list = None,
    init_range: list = None,
):
    if names is None:
        names = ['A', 'B']

    if color is None:
        color = ['#d14a61', '#5793f3']

    x_data = data[0]
    y0_data = data[1]
    y1_data = data[2]

    max_A = max(y0_data) if maxmin_A is None else maxmin_A[0]
    min_A = min(y0_data) if maxmin_A is None else maxmin_A[1]

    max_B = max(y1_data) if maxmin_B is None else maxmin_B[0]
    min_B = min(y1_data) if maxmin_B is None else maxmin_B[1]

    display_start = 0 if maxmin_B is None else init_range[0]
    display_end = 100 if maxmin_B is None else init_range[1]

    bar = (
        Line()
        .add_xaxis(xaxis_data=x_data)
        .add_yaxis(
            series_name=names[0],
            y_axis=y0_data,
            color=color[0],
            label_opts=opts.LabelOpts(is_show=False),
        )
        .extend_axis(
            yaxis=opts.AxisOpts(
                name=names[1],
                type_="value",
                max_=max_B,
                min_=min_B,
                # interval=5,
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color=color[1])
                ),
                axislabel_opts=opts.LabelOpts(formatter="{value}"),
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            tooltip_opts=opts.TooltipOpts(
                is_show=True, trigger="axis", axis_pointer_type="cross"
            ),
            xaxis_opts=opts.AxisOpts(
                type_="category",
                axispointer_opts=opts.AxisPointerOpts(is_show=True, type_="shadow"),
            ),
            yaxis_opts=opts.AxisOpts(
                name=names[0],
                type_="value",
                max_=max_A,
                min_=min_A,
                # interval=50,
                axisline_opts=opts.AxisLineOpts(
                    linestyle_opts=opts.LineStyleOpts(color=color[0])
                ),
                axislabel_opts=opts.LabelOpts(formatter="{value}"),
                axistick_opts=opts.AxisTickOpts(is_show=True),
                splitline_opts=opts.SplitLineOpts(is_show=True),
            ),
            datazoom_opts=[
                opts.DataZoomOpts(
                    is_show=True,
                    # type_='inside',
                    range_start=display_start,
                    range_end=display_end,
                )
            ],
        )
    )

    line = (
        Line()
        .add_xaxis(xaxis_data=x_data)
        .add_yaxis(
            series_name=names[1],
            yaxis_index=1,
            y_axis=y1_data,
            color=color[1],
            label_opts=opts.LabelOpts(is_show=False),
        )
    )

    bar.overlap(line)
    grid = Grid(
        init_opts=opts.InitOpts(
            width='100%',
            page_title=title,
        )
    )
    grid.add(
        bar,
        opts.GridOpts(
            is_show=False,
            pos_left='10%',
            pos_right='10%'
        ),
        is_control_axis_index=True,
    )
    grid.render(path)


def closest_round_number(num):
    # 从最大两位数开始找到最大的整十数
    for factor in [100000, 10000, 1000, 100, 10]:
        closest_num = round((num) / factor + 0.1) * factor
        if closest_num > num:
            return closest_num
    return None


def test_closest():
    numbers = [48, 472, 6645, 24383]  # 28对应30，24383对应25000

    for num in numbers:
        result = closest_round_number(num)
        print(f'For {num}, the closest round number is: {result}')


if __name__ == '__main__':
    test_data = [
        ['{}月'.format(i) for i in range(1, 13)],
        [2.0, 4.9, 7.0, 23.2, 25.6, 76.7, 135.6, 162.2, 32.6, 20.0, 6.4, 3.3],
        [2.0, 2.2, 3.3, 4.5, 6.3, 10.2, 20.3, 23.4, 23.0, 16.5, 12.0, 6.2],
    ]
    test_path = './_cache/debug/test.html'
    draw_two(test_data, test_path, 'test_title')
