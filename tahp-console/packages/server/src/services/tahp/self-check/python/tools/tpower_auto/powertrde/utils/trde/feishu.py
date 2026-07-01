import json
import time

import requests

from powertrde.utils.trde.trde_utils import pc_name, pc_ip


# 飞书后台配置： https://open.feishu.cn/app
def _read_tanant_token():
    url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
    headers = {
        'Content-Type': 'application/json; charset=utf-8'
    }
    data = json.dumps(
        {'app_id': 'cli_a3519d386ebc500c', 'app_secret': 'lC3rVHuto3ZFxE5N0No6pgQMZDQdQh72'}
    )
    response = requests.request('POST', url, headers=headers, data=data)
    res = json.loads(response.text)
    return res['tenant_access_token']


def _list_groups(tenant_access_token):
    url = "https://open.feishu.cn/open-apis/im/v1/chats?page_size=100"
    payload = ''

    headers = {
        'Authorization': f'Bearer {tenant_access_token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    res = json.loads(response.text)
    chat_list = [(i['name'], i['chat_id']) for i in res['data']['items']]
    for c in chat_list:
        print(c)


# https://open.feishu.cn/document/common-capabilities/message-card/message-cards-content/card-structure/card-content
def _send_msg(chat_id, tenant_access_token, content: str, case_name, device_info):
    case = f'{case_name}' if case_name else ''
    dev = f'{device_info}' if device_info else ''
    t = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
    pc = f'{pc_name()} {pc_ip()}'
    s = f'<font color=gray>{case} {dev}\n{t} {pc}\n</font>{content}'

    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    params = {"receive_id_type": "chat_id"}
    msgContent = {
        "elements": [{"tag": "markdown", "content": s, }, ]
    }
    req = {
        "receive_id": chat_id,  # chat id
        "msg_type": "interactive",
        "content": json.dumps(msgContent)
    }
    payload = json.dumps(req)
    headers = {
        'Authorization': f'Bearer {tenant_access_token}',
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, params=params, headers=headers, data=payload)
    # print(response.headers['X-Tt-Logid'])  # for debug or oncall
    # print(response.content)  # Print Response


def list_groups():
    t = _read_tanant_token()
    _list_groups(t)


# test chat id: 'oc_2e3193ea929c32dbf1f580bb8c0adadd'
def send_msg(chat_id: str, msg: str, case_name: str = '', device_info=''):
    t = _read_tanant_token()
    _send_msg(chat_id, t, msg, case_name, device_info)


def _to_md_str(_d, _lev):
    if _lev > 3:
        return '\n' + ' ' * _lev + f'{_d}'

    _s = ''
    if isinstance(_d, dict):
        for _k, _v in _d.items():
            _s += '\n' + ' ' * _lev + f'**{_k}:**{_to_md_str(_v, _lev + 1)}'
    elif isinstance(_d, list):
        for _i, _di in enumerate(_d):
            _s += f'{_to_md_str(_di, _lev + 1)}'
    else:
        _s = '\n' + ' ' * _lev + f'{_d}'
    _s = _s.replace('::', ':')
    return _s


def data_to_md_str(data):
    s = _to_md_str(data, 0)
    return s


def _test():
    list_groups()

    # data = {'电池总电量太小了': ' 实际总容量为4686.0， < 5833', '放电速度异常': [[{'放电时1格电池容量太小为-25.92mah<32.8mah,开始结束:': [
    #     '2023-10-07 23:37:39-1696693059-98', '2023-10-07 23:44:54-1696693494-98']}], [{
    #     '放电时1格电池容量太小为-27.6mah<32.8mah,开始结束:': [
    #         '2023-10-07 23:44:55-1696693495-97',
    #         '2023-10-07 23:51:59-1696693919-97']}],
    #     [{'放电时1格电池容量太小为-26.5mah<32.8mah,开始结束:': [
    #         '2023-10-07 23:59:22-1696694362-94',
    #         '2023-10-08 00:00:40-1696694440-94']}], [{
    #         '放电时1格电池容量太小为-31.22mah<32.8mah,开始结束:': [
    #             '2023-10-08 00:00:42-1696694442-93',
    #             '2023-10-08 00:02:15-1696694535-93']}]]}
    #
    # cht = 'oc_2e3193ea929c32dbf1f580bb8c0adadd'
    # s = data_to_md_str(data)
    # send_msg(cht, s, 'AgeingStress')


if __name__ == '__main__':
    _test()
