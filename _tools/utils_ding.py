import time
import hmac
import hashlib
import base64
import json
import urllib.parse
import urllib.request
import requests
from typing import Optional

auth_list = [
    {
        "secret": 'SECc09d8ebd218867a739d0298a6135d0750bfd7666055974dfe5262305690e8e2d',
        "url": 'https://oapi.dingtalk.com/robot/send?access_token='
               '75bda2341662de9f35698557faedd00e46ab78da1569e2d7127e700eae18b721',
    },
]


class DingDingWebHook(object):

    def __init__(self, secret=None, url=None):
        """
        :param secret: 安全设置的加签秘钥
        :param url: 机器人没有加签的WebHook_url
        """
        if secret is not None:
            secret = secret
        else:
            secret = 'SECa0ab7f3ba9742c0*********'  # 加签秘钥

        if url is not None:
            url = url
        else:
            url = "https://oapi.dingtalk.com/robot/send?access_token=1554a3dd1e748*********"  # 无加密的url

        timestamp = round(time.time() * 1000)  # 时间戳
        secret_enc = secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))  # 最终签名

        self.webhook_url = url + '&timestamp={}&sign={}'.format(timestamp, sign)  # 最终url，url+时间戳+签名

    def send_message(self, data):
        """
        发送消息至机器人对应的群
        :param data: 发送的内容
        :return:
        """
        header = {
            "Content-Type": "application/json",
            "Charset": "UTF-8"
        }
        send_data = json.dumps(data)  # 将字典类型数据转化为json格式
        send_data = send_data.encode("utf-8")  # 编码为UTF-8格式

        # request = urllib.request.Request(url=self.webhook_url, data=send_data, headers=header)  # 发送请求
        # opener = urllib.request.urlopen(request)  # 将请求发回的数据构建成为文件格式
        # print(opener.read())  # 打印返回的结果

        print(self.webhook_url)
        print(send_data)
        response = requests.post(url=self.webhook_url, data=send_data, headers=header)
        print(response.text)


def sample_send_msg(message, auth_number=0):
    dingding = DingDingWebHook(
        secret=auth_list[auth_number]["secret"],
        url=auth_list[auth_number]["url"]
    )
    dingding.send_message({
        "msgtype": "text",
        "text": {
            "content": message
        },
        "at": {
            "isAtAll": False
        }
    })


def notify_report(
    report: str,
    cache_path: Optional[str],
    channel: int,
) -> None:
    # Cache Message
    if cache_path is not None:
        with open(cache_path, "w") as w:
            w.write(report)

    # Send Message
    sample_send_msg(report, channel)


if __name__ == '__main__':
    # my_data = {
    #     "msgtype": "markdown",
    #     "markdown": {
    #         "title": "测试markdown样式",
    #         "text": "# 一级标题 \n## 二级标题 \n> 引用文本  \n**加粗**  \n*斜体*  \n[百度链接](https://www.baidu.com) "
    #             "\n![草莓](https://dss0.bdstatic.com/70cFuHSh_Q1YnxGkpoWK1HF6hhy/it/u=1906469856,4113625838&fm=26&gp=0.jpg)"
    #             "\n- 无序列表 \n1.有序列表  \n@某手机号主 @18688889999"},
    #     "at": {
    #         "atMobiles": [""],
    #         "isAtAll": False}  # 是否@所有人
    # }

    sample_send_msg("""测试""", 3)
