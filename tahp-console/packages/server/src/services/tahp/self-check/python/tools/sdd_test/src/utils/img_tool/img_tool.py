# -- coding: utf-8 --
import numpy
from PIL import Image
from PIL import ImageChops


# 转换为RGB
def convert_img2RGB(path):
    img = Image.open(path)
    img = Image.fromarray(numpy.uint8(img))
    t = img.convert("RGB")

    return Image.fromarray(numpy.uint8(t))


# # 图片比较
def compare_images(path1, path2):
    image1 = convert_img2RGB(path1)
    image2 = convert_img2RGB(path2)

    try:
        diff = ImageChops.difference(image1, image2)
        if diff.getbbox() is None:
            return True
        else:
            return False
    except ValueError as e:
        print("compare_images: except ValueError!")
        return False
