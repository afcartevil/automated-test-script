# -- coding: utf-8 --

import zipfile


# 解压theme.apk并获取wallpaper.png
def get_themewallpaper(apk_path, temp_dir):
    zip_file = zipfile.ZipFile(apk_path)
    zip_list = zip_file.namelist()
    theme_wallpaper_name = ""

    for f in zip_list:
        if "/wallpaper.png" in f:
            theme_wallpaper_name = temp_dir + f
            zip_file.extract(f, temp_dir)
            break

    zip_file.close()
    return theme_wallpaper_name
