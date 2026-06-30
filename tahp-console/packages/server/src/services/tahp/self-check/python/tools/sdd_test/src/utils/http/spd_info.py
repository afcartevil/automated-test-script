from src.utils.http.http_client import get, post
from src.utils.http.uac_login import UacLogin
import json
import os
import logging
from functools import wraps

logger = logging.getLogger(__name__)

TOKEN_TEMP_FILE = "temp_token.tmp"

class SpdInfo:
    """SPD 信息客户端，从 SPD 服务器获取信息。"""
    P_Auth = None
    P_Rtoken = None

    ProjectInfoList_URL = "https://api-tones.transsion.com/tones-spd/spd-projectInfo/getProjectInfoList"
    ProductSpecificationList_URL = "https://api-tones.transsion.com/tones-spd/productSpecificationList/queryProductSpecificationList"
    ProjectInfoDetail_URL = "https://api-tones.transsion.com/tones-spd/spd-projectInfo/getProjectInfoDetail"
    FeatureConfigList_URL = "https://api-tones.transsion.com/tones-spd/productSpecificationList/queryFeatureConfigList"
    GoogleProgramList_URL = "https://api-tones.transsion.com/tones-spd/productSpecificationList/queryGoogleProgramList"
    ProductConfigList_URL = "https://api-tones.transsion.com/tones-spd/productSpecificationList/queryProductConfigList" # 产品配置清单

    def _get_cache_token(self) -> dict[str, str]:
        """
        获取缓存的token，如果缓存不存在则从配置文件中读取。
        """
        # 如果文件不存在时
        if not os.path.exists(TOKEN_TEMP_FILE):
            self._flash_token() 
            return None
        # 从缓存文件中读取token
        logger.info(f"从缓存文件中读取token")
        with open(TOKEN_TEMP_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        self.P_Auth = config["P-Auth"]
        self.P_Rtoken = config["P-Rtoken"]

    def _flash_token(self):
        uac_login = UacLogin()
        res = uac_login.login()
        if res is None:
            raise Exception("登录到用户中心失败,请检查用户名和密码")
        self.P_Auth = res["P-Auth"]
        self.P_Rtoken = res["P-Rtoken"]
        logger.info(f"刷新token成功")

    def __init__(self):
        self._get_cache_token()

    @staticmethod
    def _retry_on_token_expired(method: callable):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            try:
                return method(self, *args, **kwargs)
            except Exception:
                logger.info("请求失败，尝试刷新 token 后重试...")
                self._flash_token()
                return method(self, *args, **kwargs)
        return wrapper

    @_retry_on_token_expired
    def get_project_info_list(self, debug=False) -> dict[str, str]:
        """
        获取项目信息列表。
        参数:
            无查询参数
            debug (bool): 是否打印请求/响应细节。
        返回值:
            dict[str, str]: 项目名称到项目信息的映射。
        """
        headers = {
            "P-Auth": self.P_Auth,
            "P-Rtoken": self.P_Rtoken,
        }
        body = {}
        res = post(
            url = self.ProjectInfoList_URL, 
            headers = headers, 
            body_json = body,
            debug = debug)
        if "success" in res.body["msg"]:
            logger.info(f"获取项目信息列表成功")
            project_info_list = res.body["data"]
            return {item["name"]: item for item in project_info_list}
        else:
            logger.error(f"获取项目信息列表失败: {res.body['msg']}")
            return None
    
    def get_product_id(self,projectName: str,debug=False) -> str:
        """
        根据项目名称获取产品ID。
        参数:
            projectName (str): 项目名称。
            debug (bool): 是否打印请求/响应细节。
        返回值:
            str: 产品ID。
        """
        project_info_list = self.get_project_info_list(debug)
        if project_info_list is None:
            print("获取项目信息列表失败")
            return None
        for item in project_info_list.keys():
            if projectName in item:
                # 返回了第一个匹配的项目ID ，可能不是唯一的 TODO: 处理多个匹配的情况
                return project_info_list[item]["bid"]
        return None

    @_retry_on_token_expired
    def get_product_specification(self, projectBid: str, tos_version: str,  debug=False) -> dict[str, str]:
        """
        根据项目ID和TOS版本号获取产品规格ID。
        参数:
            projectBid (str): 项目ID。
            tos_version (str): TOS 版本号。
            debug (bool): 是否打印请求/响应细节。
        返回值:
            str: 产品规格ID。
        """
        headers = {
            "P-Auth": self.P_Auth,
            "P-Rtoken": self.P_Rtoken,
        }
        body = {"projectBid": projectBid}
        res = post(
            url = self.ProductSpecificationList_URL, 
            headers = headers, 
            body_json = body,
            debug = debug)

        if "success" in res.body["msg"]:
            product_specification_list = res.body["data"]
            for item in product_specification_list:
                if item["tosVersion"] == tos_version:
                    return item["bid"]
            return None

        else:
            logger.error(f"获取产品规格列表失败: {res.body['msg']}")
            return None
    
    @_retry_on_token_expired
    def get_project_info_detail(self, bid: str, debug=False) -> dict[str, str]:
        """
        根据项目ID获取项目详细信息。
        参数:
            bid (str): 项目ID。
            debug (bool): 是否打印请求/响应细节。
        返回值:
            dict[str, str]: 项目详细信息。
        """
        headers = {
            "P-Auth": self.P_Auth,
            "P-Rtoken": self.P_Rtoken,
        }
        body = {"bid": bid}
        res = post(
            url = self.ProjectInfoDetail_URL, 
            headers = headers, 
            body_json = body,
            debug = debug)
        if "success" in res.body["msg"]:
            project_info_detail = res.body["data"]
            keep_keys = [
                "name", "bid", "projectName", "brand", "androidVersion",
                "go", "osVersion", "systemType", "chipPlatform","chip","series","androidGo"
            ]
            return {k: project_info_detail[k] for k in keep_keys if k in project_info_detail}
        else:
            print(f"获取项目详细信息失败: {res.body['msg']}")
            return None

    @_retry_on_token_expired
    def get_feature_config_list(self, bid: str,current = 1, size = 99999, myRelated = False, debug=False) -> dict[str, str]:
        """
        根据项目ID获取功能配置列表。
        参数:
            bid (str): 项目ID。
            current (int): 当前页码。
            size (int): 每页数量。
            myRelated (bool): 是否只返回与当前用户相关的功能配置。
            debug (bool): 是否打印请求/响应细节。
        返回值:
            dict[str, str]: 功能配置列表。
        """
        headers = {
            "P-Auth": self.P_Auth,
            "P-Rtoken": self.P_Rtoken,
        }
        body = {
            "bid": bid,
            "current": current, 
            "size": size, 
            "myRelated": myRelated}

        res = post(
            url = self.FeatureConfigList_URL, 
            headers = headers, 
            body_json = body,
            debug = debug)

        if "success" in res.body["msg"]:
            feature_config_list = res.body["data"]["records"]
            keep_keys = [
                "lv4Code", "lv4Name", "description", "versionNumber", "marketInfoList",
            ]
            logger.info(f"获取功能配置列表成功")
            return { item["lv4Code"]: {k: item[k] for k in keep_keys if k in item} for item in feature_config_list }
        else:
            logger.error(f"获取功能配置列表失败: {res.body['msg']}")
            return None
    
    @_retry_on_token_expired
    def get_google_feature_list(self, bid: str, debug=False):
        """
        根据项目ID获取google功能配置列表。
        参数:
            bid (str): 特性列表ID。
            debug (bool): 是否打印请求/响应细节。
        返回值:
            dict[str, str]: google功能配置列表。
        """
        headers = {
            "P-Auth": self.P_Auth,
            "P-Rtoken": self.P_Rtoken,
        }
        body = {
            "bid": bid
            }
        res = post(
            url = self.GoogleProgramList_URL, 
            headers = headers, 
            body_json = body,
            debug = debug)
        if "success" in res.body["msg"]:
            google_feature_list = res.body["data"]
            keep_keys = [
                "googleConfigCode", "strategy", "detail", "configStatus", "marketInfoList",
            ]
            logger.info(f"获取google功能配置列表成功")
            return { item["googleConfigCode"] :{k: item[k] for k in keep_keys if k in item} for item in google_feature_list}
        else:
            logger.error(f"获取google功能配置列表失败: {res.body['msg']}")
            return None
    
    # 拼接 两个配置列表
    def merge_feature_config_list(self, feature_config_list: dict[str, str], google_feature_list: dict[str, str]) -> dict[str, str]:
        """
        拼接功能配置列表和google功能配置列表。
        参数:
            feature_config_list (dict[str, str]): 功能配置列表。
            google_feature_list (dict[str, str]): google功能配置列表。
        返回值:
            dict[str, str]: 拼接后的功能配置列表。
        """
        return {**feature_config_list, **google_feature_list}
    
    def feature_with_market(self, feature_config_list: dict[str, str]) -> dict[str, str]:
        """
        从功能配置列表中提取包含市场信息的功能配置。
        参数:
            feature_config_list (dict[str, str]): 功能配置列表。
        返回值:
            dict[str, str]: 包含市场信息的功能配置列表。
        """
        res = {}

        for key, valueDict in feature_config_list.items():
            if "marketInfoList" not in valueDict:
                continue
            market_support = {}
            for item in valueDict["marketInfoList"]:
                if item["market"] == None or item["value"] == None:
                    continue
                market_support[item["market"]] = "0" if "不参加" in item["value"] or "不支持" in item["value"] else "1"
            res[key] = market_support
        return res
    
    def one_step_feature_list(self, product_name: str, osVersion: str, debug=False) -> dict[str, str]:
        """
        一步获取功能配置列表和google功能配置列表。
        参数:
            product_name (str): 项目名称。
            osVersion (str): 操作系统版本。
            debug (bool): 是否打印请求/响应细节。
        返回值:
            dict[str, str]: 拼接后的功能配置列表。
        """
        product_id = self.get_product_id(product_name,debug=debug)
        # detail = self.get_project_info_detail(product_id,debug=debug)
        product_configId = self.get_product_specification(product_id, osVersion,debug=debug)
        common_feature = self.get_feature_config_list(product_configId, debug=debug)
        google_feature = self.get_google_feature_list(product_configId, debug=debug)
        config_dict = self.merge_feature_config_list(common_feature, google_feature)
        feature_with_market = self.feature_with_market(config_dict)
        logger.info(f"获取功能配置列表成功")
        return feature_with_market