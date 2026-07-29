import time
import requests
from appdownloadertools import ApkDownloaderTools

class Aptoide(object):

    def __init__(self) -> None:
        self.aptoide_web_api_base_url_get_versions = "https://ws75.aptoide.com/api/7/app/getVersions/"
        self.aptoide_web_api_base_url_get_meta = "https://ws2.aptoide.com/api/7/app/getMeta/"
        self.headers = ApkDownloaderTools().get_random_headers()

    def __app_id_finder(self, package_name: str, wanted_version: str, limit=15):
        version_url = f"{self.aptoide_web_api_base_url_get_versions}package_name={package_name}/limit={limit}"
        # 添加重试机制，最多重试3次
        for attempt in range(100):
            try:
                v_res = requests.get(url=version_url, headers=self.headers, timeout=30)
                if v_res.status_code != 200:
                    print(f"HTTP状态码错误: {v_res.status_code}，等待5分钟后重试...")
                    if attempt < 99:
                        time.sleep(300)
                        continue
                    else:
                        raise requests.exceptions.RequestException(f"HTTP状态码: {v_res.status_code}")
                print(v_res.json())
                json_data_list = v_res.json()["list"]
                if not json_data_list:
                    print(f"⚠️ 未找到应用 {package_name} 的版本信息，跳过下载")
                    return None  # 返回 None 表示未找到
                if wanted_version == "latest":
                    json_data = json_data_list[0]
                    app_id = json_data["id"]
                    return app_id
                else:
                    for json_data in json_data_list:
                        app_version = json_data["file"]["vername"]
                        if wanted_version == app_version:
                            app_id = json_data["id"]
                            return app_id
                        else:
                            continue
                    else:
                        print(
                            f"Not found\nIf you want deep search you need to decrease the \"limit\" (It is the limit of app versions' number.")
                        exit()
            except requests.exceptions.Timeout:
                print(f"请求超时: {version_url}，等待5分钟后重试...")
                if attempt < 100:  # 不是最后一次尝试
                    time.sleep(300)  # 等待5分钟
                else:
                    raise  # 最后一次尝试仍然失败，抛出异常
            except requests.exceptions.RequestException as e:
                print(f"请求失败: {e}")
                if attempt < 100:  # 不是最后一次尝试
                    time.sleep(300)  # 等待5分钟
                else:
                    raise  # 最后一次尝试仍然失败，抛出异常

    def __get_app_infos_by_app_id(self, app_id: str):
        app_info_url = f"{self.aptoide_web_api_base_url_get_meta}app_id={app_id}"
        # 添加重试机制，最多重试3次
        for attempt in range(100):
            try:
                i_res = requests.get(url=app_info_url, headers=self.headers, timeout=30)
                app_info_json = i_res.json()

                app_size = app_info_json["data"]["size"]
                app_version = app_info_json["data"]["file"]["vername"]
                app_download_url = app_info_json["data"]["file"]["path"]
                app_ext = app_download_url.split(".")[1]
                app_name = app_info_json["data"]["name"]
                app_fullname = f"{app_name} {app_version}.{app_ext}"

                return {
                    "app_size": app_size,
                    "app_version": app_version,
                    "app_download_url": app_download_url,
                    "app_ext": app_ext,
                    "app_name": app_name,
                    "app_fullname": app_fullname
                }
            except requests.exceptions.Timeout:
                print(f"请求超时: {app_info_url}，等待5分钟后重试...")
                if attempt < 99:  # 不是最后一次尝试
                    time.sleep(300)  # 等待5分钟
                else:
                    raise  # 最后一次尝试仍然失败，抛出异常
            except requests.exceptions.RequestException as e:
                print(f"请求失败: {e}")
                if attempt < 99:  # 不是最后一次尝试
                    time.sleep(300)  # 等待5分钟
                else:
                    raise  # 最后一次尝试仍然失败，抛出异常

    def download_by_package_name(self, package_name: str, file_name="default", version="latest", in_background=False,
                                 limit=15):
        app_id = self.__app_id_finder(
            package_name=package_name, wanted_version=version, limit=limit)
                # 检查是否找到应用
        if app_id is None:
            print(f"❌ 跳过应用: {package_name} (未找到版本信息)")
            return None  # 直接返回，跳过下载
        app_infos = self.__get_app_infos_by_app_id(app_id=app_id)
        d_url = app_infos["app_download_url"]
        app_size = app_infos["app_size"]
        app_ext = app_infos["app_ext"]
        app_version = app_infos["app_version"]
        if file_name == "default":
            file_name = app_infos["app_fullname"]
        else:
            file_name = f"{file_name} {app_version}.{app_ext}"
        if in_background:
            ApkDownloaderTools().download_in_t_background(url=d_url, file_name=file_name)
        else:
            ApkDownloaderTools().download_w_progress_bar(url=d_url, file_name=file_name, total_size=app_size)


if __name__ == '__main__':
    app_info = {
        # "Google Chrome: Fast & Secure": "com.android.chrome",
        # "YouTube": "com.google.android.youtube",
        # "WhatsApp Messenger": "com.whatsapp",
        # "Facebook": "com.facebook.katana",
        # "Messenger": "com.facebook.orca",
        # "Maps": "com.google.android.apps.maps",
        # "TikTok": "com.zhiliaoapp.musically",
        # "Facebook Lite": "com.facebook.lite",
        # "YouTube Music": "com.google.android.apps.youtube.music",
        # "Instagram": "com.instagram.android",
        # "CapCut - Video Editor": "com.lemon.lvoverseas",
        # "TikTok Lite - Save Data & Fast": "com.zhiliaoapp.musically.go",
        # "TikTok1": "com.ss.android.ugc.trill",
        # "Snapchat": "com.snapchat.android",
        # "Telegram": "org.telegram.messenger",
        # "WhatsApp Business": "com.whatsapp.w4b",
        # "SHAREit: Transfer, Share Files": "com.lenovo.anyshare.gps",
        # "Xender - Share Music Transfer": "cn.xender",
        # "Truecaller": "com.truecaller",
        # "FreeFire": "com.dts.freefireth",
        # "Mobile Legends: Bang Bang": "com.mobile.legends",
        # "VidMate": "com.video.fun.app",
        # "Snaptube": "com.snaptube.premium",
        # "Shopee": "com.shopee.id",
        # "Spotify: Music and Podcasts": "com.spotify.music",
        # "imo-International Calls & Chat": "com.imo.android.imoim",
        # "Pinterest": "com.pinterest",
        # "Opera Mini: Fast Web Browser": "com.opera.mini.native",
        # "Temu: Shop Like a Billionaire": "com.einnovation.temu",
        # "Threads": "com.instagram.barcelona",
        # "Lazada Birthday Blowout": "com.lazada.android",
        # "MX Player": "com.mxtech.videoplayer.ad",
        # "ChatGPT": "com.openai.chatgpt",
        # "X": "com.twitter.android",
        # "Roblox": "com.roblox.client",
        # "Lark Player:Music Player & MP3": "com.dywx.larkplayer",
        # "Instagram Lite": "com.instagram.lite",
        # "Subway Rusher": "com.runninggame.street.runner",
        # "DANA Indonesia Digital Wallet": "id.dana",
        # "Zalo": "com.zing.zalo",
        # "Fun Cat Go": "com.joylife.talkingkitty.runner",
        # "Piano Fire: Edm Music & Piano": "beatmaker.edm.musicgames.PianoGames",
        # "Block Blast!": "com.block.juggle",
        # "Snake Lite® - Worm Snake Game": "com.snake.io.slither.worms",
        # "Zapya - File Transfer, Share": "com.dewmobile.kuaiya.play",
        # "Subway Surfers": "com.kiloo.subwaysurf",
        # "PLAYit-All in One Video Player": "com.tencent.ig",
        # "Google Translate": "com.google.android.apps.translate",
        # "PUBG MOBILE": "com.tencent.ig",
        # "Netflix": "com.netflix.mediaclient",
        # "Call of Duty®: Mobile - Garena": "com.garena.game.codm",
        # "eFootball": "jp.konami.pesam",
        # "M-PESA": "com.safaricom.mpesa.lifestyle",
        # "Kilimall - Affordable Shopping": "net.kilimall.shop",
        # "MySafaricom": "com.safaricom.mysafaricom",
        # "SOYO: Meet & Chat Party": "com.haflla.soulu",
        # "Equity Mobile": "ke.co.equitygroup.equitymobile",
        # "Zenka Loan App Kenya": "com.zenkafinance.microloans",
        # "KCB": "com.kcbbankgroup.android",
        # "Vskit - Short Series": "com.yomobigroup.short",
        # "Good News Bible-Holy Bible NIV": "com.hailey.goodnews.holybible",
        # "Word Legend Puzzle Addictive": "com.lydia.wordsgame.word.talent",
        # "Branch - Digital Bank & Loans": "com.branch_international.branch.branch_demo_android",
        # "Odi bets Betting app": "com.odibet.app",
        # "Temple Run": "com.imangi.templerun",
        # "Jiji Kenya: Buy & Sell Online": "com.olx.ssa.ke",
        # "ZK Pesa- Instant Loan Solution": "ke.zk.pesa.loanapp",
        # "MyTelkomsel - Buy Package": "com.telkomsel.telkomselcm",
        # "myIM3: Data Plan & Buy Package": "com.pure.indosat.care",
        # "GoPay: Transfer Pulsa Bills": "com.gojek.gopay",
        # "AXISnet Cek & Beli Kuota Data": "com.axis.net",
        # "Getcontact": "app.source.getcontact",
        # "BCA mobile": "com.bca",
        # "myXL - XL, PRIORITAS & HOME": "com.apps.MyXL",
        # "Mobile JKN": "app.bpjs.mobile",
        # "ShopeePay – QRIS & Kirim Uang": "com.shopeepay.id",
        # "bima+ -Buy Pulsa Package- Tri": "com.linkit.bimatri",
        # "Livin' by Mandiri": "id.bmri.livin",
        # "OVO": "ovo.id",
        # "SeaBank": "id.co.bankbkemobile.digitalbank",
        # "Turbo VPN - Secure VPN Proxy": "free.vpn.unblock.proxy.turbovpn",
        # "maxim — order a taxi & food": "com.taxsee.taxsee",
        # "OPay": "team.opay.pay",
        # "PalmPay - 0 Transfer Fee": "com.transsnet.palmpay",
        # "FirstMobile": "com.firstbank.firstmobile",
        # "SportyBet - Sports Betting App": "com.sportybet.android.gp",
        # "UBA Mobile Banking": "com.uba.vericash",
        "GENIEX - Connection Made Easy": "com.transtech.geniex",
        "SOYO: Meet & Chat Party": "com.haflla.soulu",
        "OKash: Safe and reliable loan": "com.loan.cash.credit.okash.nigeria",
        "GTWorld": "com.gtbank.gtworldv1",
        "FairMoney: Loans & Banking": "ng.com.fairmoney.fairmoney",
        "myMTN NG": "ng.mtn.nextgen",
        "Zangi Private Messenger": "com.beint.zangi",
        "OPay Business": "team.opay.pay.merchant.service",
        "Smartcash PSB": "com.africa.smartcash",
        "PhonePe UPI, Payment, Recharge": "com.phonepe.app",
        "Meesho: Online Shopping App": "com.meesho.supply",
        "Flipkart Online Shopping App": "com.flipkart.android",
        "JioHotstar": "in.startv.hotstar",
        "MyJio: For Everything Jio": "com.jio.myjio",
        "Where is my Train": "com.whereismytrain.android",
        "Airtel Thanks: Recharge & Bank": "com.myairtelapp",
        "Paytm: Secure UPI Payments": "net.one97.paytm",
        "mAst: Music Status Video Maker": "com.mast.status.video.edit",
        "ShareChat Trends Videos & Live": "in.mohalla.sharechat",
        "Amazon India Shop, Pay, miniTV": "in.amazon.mShop.android.shopping",
        "JioSaavn - Music & Podcasts": "com.jio.media.jiobeats",
        "Shopsy Shopping App - Flipkart": "com.flipkart.shopsy",
        "Moj: Short Videos & Reels": "in.mohalla.video",
        "JioCinema-Shows, Movies & More": "com.jio.media.ondemand",
        "My Zong": "com.zong.customercare",
        "SIMOSA - Jazz World": "com.jazz.jazzworld",
        "My Telenor": "com.telenor.pakistan.mytelenor",
        "UPTCL– App Up Your Life!": "com.ufoneselfcare",
        "Easy Urdu Keyboard اردو Editor": "com.pakdata.easyurdu",
        "App Lock Lite": "applock.security.vault.lockapps.fingerprint.password.locker.hide",
        "OLX Pakistan - Online Shopping": "com.olx.pk",
        "HBL Mobile": "com.hbl.android.hblmobilebanking",
        "Meezan Bank Classic": "invo8.meezan.mb",
        "Edge VPN - Fast Secure VPN": "com.hbl.android.hblmobilebanking",
        "Status Saver": "com.statussaver.statusdownloader.lite",
        "UBL Digital - Safe Banking": "app.com.brd",
        "Offline Music Mp3 Player- Muso": "com.muso.musicplayer",
        "Ludo STAR": "com.superking.ludo.star",
        "Farming Tractor Village Games": "com.hq.farming.tractor.simulation.game",
        "VK: music, video, messenger": "ru.sberbankmobile",
    }
    Downloader = Aptoide()
    for app in app_info.items():
        #每隔一分钟请求一次
        Downloader.download_by_package_name(package_name=app[1], file_name=app[0], version="latest",
                                            in_background=False, limit=30)
        time.sleep(10)