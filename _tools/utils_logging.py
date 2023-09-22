import logging


def logging_init(path=None, level=logging.DEBUG, file_line=True):
    file_line_fmt = ""
    if file_line:
        file_line_fmt = "%(filename)s[line:%(lineno)d] - %(levelname)s: "
    logging.basicConfig(
        level=level,
        format=file_line_fmt + "%(asctime)s|%(message)s",
        filename=path
    )


if __name__ == '__main__':
    logging_init()
    logging.warning('123456')
