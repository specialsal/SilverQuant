import json
import logging


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


def logging_init(path=None, level=logging.DEBUG):
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(message)s",
        filename=path
    )


if __name__ == '__main__':
    # logging_init()
    # logging.warning('123456')

    save_json('./data/test.json', {'a': 1 })
    a = load_json('./data/test.json')
    print(a)
