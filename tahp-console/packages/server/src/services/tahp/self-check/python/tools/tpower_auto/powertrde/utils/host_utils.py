import getpass
import socket
from dataclasses import dataclass


@dataclass
class HostInfo:
    host_name: str = ''
    user_name: str = ''
    host_ip: str = ''

    def __str__(self):
        return f'[{self.host_name}][{self.user_name}][{self.host_ip}]'


def get_login_user_name():
    return getpass.getuser()


def get_host_name():
    return socket.gethostname()


def get_host_ip():
    return socket.gethostbyname(socket.gethostname())


def get_host_info():
    return HostInfo(get_host_name(), get_login_user_name(), get_host_ip())


def get_host_name_with_user_name():
    return f'[{get_host_name()}][{get_login_user_name()}]'


def get_host_name_with_user_name_with_ip():
    return f'[{get_host_name()}][{get_login_user_name()}][{get_host_ip()}]'
