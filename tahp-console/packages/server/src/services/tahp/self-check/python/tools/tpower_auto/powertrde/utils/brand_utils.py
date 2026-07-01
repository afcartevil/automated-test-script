def get_brand_from_cs(cs_instance):
    """从cs实例中获取品牌"""
    app_keys = cs_instance.scheme_env.app_multi_package_keys
    brands = ["vivo", "huawei", "xiaomi", "oppo", "samsung"]

    for brand in brands:
        if brand.upper() in app_keys:
            return brand
    return None


def execute_brand_method(cs_instance, model_name, method_base_name, *args, **kwargs):
    """执行品牌特定方法"""
    brand = get_brand_from_cs(cs_instance)

    if brand:
        method_name = f"{model_name}_{brand}_{method_base_name}"
        if hasattr(cs_instance, method_name):
            return getattr(cs_instance, method_name)(*args, **kwargs)

    # 默认方法
    default_method_name = f"{model_name}_{method_base_name}"
    return getattr(cs_instance, default_method_name)(*args, **kwargs)