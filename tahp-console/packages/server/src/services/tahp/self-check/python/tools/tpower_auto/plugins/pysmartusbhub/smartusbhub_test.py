from smartusbhub_utils import SmartUSBHub


def main():

    channel = 1
    from smartusbhub_utils import SmartUSBHub
    SmartUSBHub.scan_and_connect().set_channel_state(channel=channel, state=1)  # 开启USB
    SmartUSBHub.scan_and_connect().set_channel_state(channel=channel, state=0)  # 关闭USB


if __name__ == "__main__":
    main()