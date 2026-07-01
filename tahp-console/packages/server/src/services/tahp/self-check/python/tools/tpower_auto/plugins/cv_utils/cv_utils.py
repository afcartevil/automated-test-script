import os
import cv2
import numpy as np

from rapidocr import RapidOCR
from difflib import SequenceMatcher

from powertrde.utils.cv_extends.cv_defines import TemplateMatchResult, TemplateMatchError


def template_match_gray(template_input, target_input,
                        limit_area=None,
                        scale_range=(0.95, 1.05),
                        match_threshold=0.7,
                        raise_on_match_failed=False) -> TemplateMatchResult:
    """
    超精度灰度图像匹配算法，抗光照干扰
    修复点：
    - 处理浮点数转换问题
    - 优化预处理流程
    - 增强异常处理
    - 增加 target_pic_rotate 参数：读取 target 图后先按照该角度旋转后再进行识图算法计算
    :param template_input: 模板图片路径或者ndarray灰度图像数组信息
    :param target_input: 目标图片路径或者ndarray灰度图像数组信息
    :param limit_area: 限定识别区域
    :param scale_range: 缩放范围（浮点数）
    :param match_threshold: 匹配阈值
    :param raise_on_match_failed: 是否在匹配失败时抛出TemplateMatchError错误
    :param limit_area: 如果不为 None，则必须为 Tuple[float, float, float, float]，所有值在0到1之间，分别对应 target 图像中匹配区域的左、上、右、下的归一化坐标。仅在该区域内进行模板匹配。
    """
    # 自动判断输入类型：如果为字符串或 PathLike，则读取文件，否则假定为图像数据
    if isinstance(template_input, (str, os.PathLike)):
        template = cv2.imread(str(template_input), cv2.IMREAD_GRAYSCALE)
    else:
        template = template_input

    if isinstance(target_input, (str, os.PathLike)):
        target = cv2.imread(str(target_input), cv2.IMREAD_GRAYSCALE)
    else:
        target = target_input

    if template is None or target is None:
        raise ValueError("图像读取失败")

    # 如果设置了限定区域，则根据归一化坐标提取 target 中的局部区域
    if limit_area is not None:
        if (not isinstance(limit_area, tuple) or len(limit_area) != 4 or
                any(not (0 <= v <= 1) for v in limit_area)):
            raise ValueError("limit_area 必须为4个在0到1之间的浮点数组成的元组")
        h, w = target.shape
        left_norm, top_norm, right_norm, bottom_norm = limit_area
        x1 = int(left_norm * w)
        y1 = int(top_norm * h)
        x2 = int(right_norm * w)
        y2 = int(bottom_norm * h)
        # 防止出现无效区域
        if x1 >= x2 or y1 >= y2:
            raise ValueError("limit_area 指定的区域无效")
        target_region = target[y1:y2, x1:x2]
    else:
        target_region = target

    # 专业级预处理（优化细节、修复浮点转换问题）
    def expert_preprocess(img):
        blurred = cv2.GaussianBlur(img, (0, 0), 3.0)
        # sharpened = cv2.addWeighted(img, 1.5, blurred, -0.5, 0)
        log_trans = np.log1p(blurred.astype(np.float32))
        normalized = cv2.normalize(log_trans, None, 0, 255, cv2.NORM_MINMAX)
        return cv2.convertScaleAbs(normalized)

    template_pre = expert_preprocess(template)
    target_pre = expert_preprocess(target_region)

    best_score = 0
    best_loc = (0, 0)
    best_size = template_pre.shape[::-1]  # (width, height)

    scales = np.linspace(scale_range[0], scale_range[1], 5)
    for scale in scales:
        interp = cv2.INTER_LANCZOS4 if scale < 1 else cv2.INTER_CUBIC
        scaled_template = cv2.resize(template_pre, None, fx=scale, fy=scale,
                                     interpolation=interp)
        t_h, t_w = scaled_template.shape

        try:
            # 模板匹配仅在 target_pre 中执行
            res = cv2.matchTemplate(target_pre, scaled_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            dx, dy = (0, 0)
            if 0 < max_loc[0] < res.shape[1] - 1 and 0 < max_loc[1] < res.shape[0] - 1:
                neighbors = res[max_loc[1] - 1:max_loc[1] + 2, max_loc[0] - 1:max_loc[0] + 2]
                dy, dx = (np.array(np.unravel_index(np.argmax(neighbors), (3, 3))) - 1) * 0.5

            precise_x = max_loc[0] + dx
            precise_y = max_loc[1] + dy

            if scale == 1.0:
                try:
                    roi = target_pre[int(precise_y):int(precise_y) + t_h,
                          int(precise_x):int(precise_x) + t_w]
                    if roi.shape == scaled_template.shape:
                        phase_score = cv2.phaseCorrelate(scaled_template.astype(np.float32),
                                                         roi.astype(np.float32))[1]
                        combined_score = 0.7 * max_val + 0.3 * phase_score
                    else:
                        combined_score = max_val
                except Exception:
                    combined_score = max_val
            else:
                combined_score = max_val

            if combined_score > best_score:
                best_score = combined_score
                best_loc = (precise_x, precise_y)
                best_size = (t_w, t_h)
        except Exception as ee:
            if '_img.size().height <= _templ.size().height' not in str(ee):
                raise

    t_w, t_h = best_size
    x, y = best_loc
    # 保证边缘像素补偿：不要超出 target_pre 范围
    x = max(0, min(x, target_pre.shape[1] - t_w))
    y = max(0, min(y, target_pre.shape[0] - t_h))

    matched_region = target_pre[int(y):int(y) + t_h, int(x):int(x) + t_w]
    resized_template = cv2.resize(template_pre, (t_w, t_h),
                                  interpolation=cv2.INTER_CUBIC)
    final_score = cv2.matchTemplate(matched_region, resized_template,
                                    cv2.TM_CCOEFF_NORMED)[0][0]

    final_score = min(float(final_score) * 1.03, 1.0)  # 系统误差补偿
    match_success = bool(final_score >= match_threshold)

    # 计算最终匹配区域在 target 图像中的归一化坐标
    # 如果使用了 limit_area，则需要将匹配区域的坐标映射回原 target 图
    if limit_area is not None:
        h_full, w_full = target.shape
        left_norm, top_norm, _, _ = limit_area
        offset_x = left_norm * w_full
        offset_y = top_norm * h_full
    else:
        offset_x = 0
        offset_y = 0

    img_h, img_w = target.shape
    # x,y 基于 target_pre 区域，需要加上 offset_x, offset_y
    abs_x = x + offset_x
    abs_y = y + offset_y
    bounds = (
        float(abs_x / img_w),
        float(abs_y / img_h),
        float((abs_x + t_w) / img_w),
        float((abs_y + t_h) / img_h)
    )

    if bounds[0] < 0 or bounds[1] < 0 or bounds[2] < 0 or bounds[3] < 0:
        final_score = -1
        match_success = False

    result = TemplateMatchResult(target_score=match_threshold, score=final_score, bounds=bounds, result_code=0)

    if not match_success:
        result.result_code = 1
        if result.score < 0:
            result.result_code = 2
        if raise_on_match_failed:
            raise TemplateMatchError(
                f'template_match_gray failed, score {final_score}, but target score {match_threshold}',
                result)

    return result


def template_match_gray_ext(template_input, target_input,
                            limit_area=None,
                            scale_range=(0.95, 1.05),
                            match_threshold=0.7,
                            raise_on_match_failed=False) -> TemplateMatchResult:
    """
    扩展的超精度灰度图像匹配算法，支持模板输入为文件夹，并对 target_input 为文件路径的情况进行预加载优化。

    当 template_input 为文件夹路径时，方法会遍历文件夹中所有图像文件，
    逐一与 target_input 进行匹配，直至找到匹配度大于或等于 match_threshold 的结果；
    如果所有文件均未达到匹配阈值，则根据 raise_on_match_failed 的设置抛出 TemplateMatchError 异常，
    或返回最佳匹配结果。

    当 target_input 为文件路径时，会在循环外优先加载目标图像，从而避免重复读取文件，提高效率。

    如果 template_input 为单个图片路径或 ndarray 灰度图像数据，则直接调用 template_match_gray 进行处理。

    :param template_input: 模板图片路径、ndarray灰度图像数组，或包含图像文件的文件夹路径
    :param target_input: 目标图片路径或ndarray灰度图像数组信息
    :param limit_area: 限定识别区域，若不为 None，则必须为 Tuple[float, float, float, float]，所有值均在0到1之间
    :param scale_range: 缩放范围（浮点数）
    :param match_threshold: 匹配阈值
    :param raise_on_match_failed: 是否在匹配失败时抛出 TemplateMatchError 异常
    :return: TemplateMatchResult 对象
    """
    # 优化：如果 target_input 为文件路径，则提前加载目标图像
    if isinstance(target_input, (str, os.PathLike)) and os.path.isfile(target_input):
        loaded_target = cv2.imread(str(target_input), cv2.IMREAD_GRAYSCALE)
        if loaded_target is None:
            raise ValueError("target 图像读取失败")
    else:
        loaded_target = target_input

    # 如果模板输入为文件夹，则进行文件夹处理
    if isinstance(template_input, (str, os.PathLike)) and os.path.isdir(template_input):
        # 定义允许的图像文件扩展名
        allowed_ext = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}
        # 筛选出所有有效图像文件
        image_files = [
            os.path.join(template_input, f)
            for f in os.listdir(template_input)
            if os.path.isfile(os.path.join(template_input, f)) and os.path.splitext(f)[1].lower() in allowed_ext
        ]
        if not image_files:
            raise ValueError(f"文件夹 {template_input} 中没有有效的图像文件")

        best_result = None
        best_score = -1.0
        # 依次对每个图像文件进行匹配
        for img_path in image_files:
            try:
                result = template_match_gray(
                    img_path,
                    loaded_target,
                    limit_area=limit_area,
                    scale_range=scale_range,
                    match_threshold=match_threshold,
                    raise_on_match_failed=False  # 单个匹配不满足时不抛出异常
                )
                # 如果匹配分数达到或超过阈值，则直接返回匹配成功的结果
                if result.score >= match_threshold:
                    return result
                # 记录当前最佳匹配结果
                if result.score > best_score:
                    best_score = result.score
                    best_result = result
            except Exception:
                # 忽略该图像文件的异常，继续处理其它文件
                continue

        message = (f"在文件夹 {template_input} 中没有找到满足阈值 {match_threshold:.2f} 的匹配结果，"
                   f"最高分为 {best_score:.2f}")
        if raise_on_match_failed:
            raise TemplateMatchError(
                message,
                best_result if best_result is not None else TemplateMatchResult(
                    target_score=match_threshold, score=best_score, bounds=(0, 0, 0, 0), result_code=1
                )
            )
        else:
            return best_result if best_result is not None else TemplateMatchResult(
                target_score=match_threshold, score=best_score, bounds=(0, 0, 0, 0), result_code=1
            )
    else:
        # 非文件夹情况，直接调用原有的模板匹配方法，传入预加载的 target 图像
        return template_match_gray(
            template_input,
            loaded_target,
            limit_area=limit_area,
            scale_range=scale_range,
            match_threshold=match_threshold,
            raise_on_match_failed=raise_on_match_failed
        )


def ocr_match(template_input: str, target_input,
              limit_area=None,
              match_lang: str = 'en',
              scale_factor: float = 4.0,
              match_threshold=0.7,
              case_sensitive: bool = True,
              raise_on_match_failed=False) -> TemplateMatchResult:
    """
    OCR 文字识别函数，支持图像裁剪区域限制。
    :param template_input: 模板字符串（对大小写敏感）
    :param target_input: 目标图片路径或者ndarray灰度图像数组信息
    :param limit_area: 限制识别区域，格式为 (left, top, right, bottom)，值为0-1的归一化坐标
    :param scale_factor: 放大倍数（默认 3 倍）
    :param match_lang: 识别语言（默认英语） 中文是“ch_mobile”
    :param match_threshold: 字符匹配阈值
    :param case_sensitive: 大小写敏感
    :param raise_on_match_failed: 是否在匹配失败时抛出TemplateMatchError错误
    """

    def ocr_preprocess(img, mode: str = "white"):
        """:
        图像预处理：光照均衡 + 二值化 + 去噪 + 锐化 + 动态阈值
        """
        if len(img.shape) == 2:  # 单通道灰度图像
            gray = img
        elif len(img.shape) == 3 and img.shape[2] == 3:  # BGR 图像
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif len(img.shape) == 3 and img.shape[2] == 4:  # 带透明通道的 BGRA 图像
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError(f"无效的图像通道数: {img.shape}")

        # 光照均衡（CLAHE）
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # 动态二值化（适应复杂背景）
        if mode == "white":
            binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, 11, 2)
        else:
            binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY_INV, 11, 2)

        # 去噪（中值滤波）
        denoised = cv2.medianBlur(binary, 3)

        # 闭运算连接笔画
        kernel = np.ones((3, 3), np.uint8)
        closed = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel)

        # 锐化增强边缘可能对 OCR 有副作用
        # closed_3ch = cv2.cvtColor(closed, cv2.COLOR_GRAY2BGR)
        # lap = cv2.Laplacian(closed_3ch, cv2.CV_16S, ksize=3)
        # lap = cv2.convertScaleAbs(lap)

        # 锐化处理方式可能对 OCR 有副作用
        # sharpened = cv2.addWeighted(closed_3ch, 1.0, lap, 0.5, 0)
        # 抗锯齿处理（平滑边缘）
        smoothed = cv2.GaussianBlur(closed, (3, 3), 0)
        return smoothed
        # return cv2.cvtColor(sharpened, cv2.COLOR_BGR2GRAY)

    # 图像读取
    if isinstance(target_input, (str, os.PathLike)):
        img = cv2.imread(str(target_input), cv2.IMREAD_GRAYSCALE)
    else:
        img = target_input

    if img is None:
        raise ValueError("图像读取失败")

    # 限定区域裁剪
    x1 = 0
    y1 = 0
    if limit_area is not None:
        if len(limit_area) != 4 or any(not (0 <= v <= 1) for v in limit_area):
            raise ValueError("limit_area 必须是包含4个[0,1]之间浮点数的元组")
        h, w = img.shape
        x1 = int(limit_area[0] * w)
        y1 = int(limit_area[1] * h)
        x2 = int(limit_area[2] * w)
        y2 = int(limit_area[3] * h)
        img_roi = img[y1:y2, x1:x2]
    else:
        img_roi = img

    # 图像放大
    roi_resized = cv2.resize(img_roi, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)

    # 预处理, 可能负优化
    processed = ocr_preprocess(roi_resized)
    engine = RapidOCR(params={"detector.lang_det": match_lang, "recognizer.lang_rec": match_lang})
    results = engine(processed)

    best_similarity = 0.0
    best_bounds = (0.0, 0.0, 0.0, 0.0)

    if results:
        for text, box, confidence in zip(results.txts, results.boxes, results.scores):
            # print(text)
            if confidence < 0.6 or len(text) < max(len(template_input) * 0.7, 0) or len(text) > len(template_input) * 2:
                continue

            if not case_sensitive:
                text = text.lower()
                template_input = template_input.lower()

            similarity = SequenceMatcher(None, template_input, text).ratio()
            if similarity >= match_threshold:
                h, w = img.shape[:2]

                # box 是四个点
                xs = [pt[0] for pt in box]
                ys = [pt[1] for pt in box]

                x1_px = min(xs) / scale_factor + (x1 if limit_area else 0)
                y1_px = min(ys) / scale_factor + (y1 if limit_area else 0)
                x2_px = max(xs) / scale_factor + (x1 if limit_area else 0)
                y2_px = max(ys) / scale_factor + (y1 if limit_area else 0)

                x1_norm = x1_px / w
                y1_norm = y1_px / h
                x2_norm = x2_px / w
                y2_norm = y2_px / h

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_bounds = tuple(map(float, (x1_norm, y1_norm, x2_norm, y2_norm)))
                    # print(best_bounds)
            else:
                best_similarity = max(best_similarity, similarity)

    result = TemplateMatchResult(
        target_score=match_threshold,
        score=best_similarity if best_similarity > 0 else 0.0,  # OCR 置信度转为 0-1 范围
        bounds=best_bounds if best_similarity > 0 else (0.0, 0.0, 0.0, 0.0),  # 坐标边界
        result_code=0  # 默认成功
    )

    # 检查匹配成功与否
    match_success = best_similarity >= match_threshold

    if not match_success:
        result.result_code = 1  # 设置为匹配失败
        if result.score <= 0:
            result.result_code = 2  # 如果置信度为 0 或更低，标记为更严重的错误
        if raise_on_match_failed:
            raise TemplateMatchError(
                f"OCR 匹配失败，score={best_similarity:.2f}, target_score={match_threshold:.2f}",
                result
            )
    return result


# 使用示例
if __name__ == "__main__":
    _match_result = ocr_match(template_input="Answer",
                              target_input='D:\\dz_auto_env\\.runtime\\log\\20250418_155305_dou3_X6855\\session_logs\\20250418_155308_main.png')

    if _match_result.success:
        print(f"匹配成功！置信度：{_match_result.score:.2%}")
        print(f"包围框：{_match_result.bounds}")
    else:
        print("未找到有效匹配")
        print(f"置信度：{_match_result.score:.2%}")
        print(f"包围框：{_match_result.bounds}")
