# RF参数路径配置指南

## 路径格式说明

### Path_A_Priv（原分支私有仓路径）
- **格式**: `/path/to/workspace/codeA/private/`
- **示例**: `D:\project\mp_release_10.0\private\`
- **说明**: 代码A（原分支）的私有仓路径，包含未升级前项目的RF参数

### Path_B_Priv（目标分支私有仓路径）
- **格式**: `/path/to/workspace/codeB/private/`
- **示例**: `D:\project\main\private\`
- **说明**: 代码B（目标分支）的私有仓路径，新的RF参数将复制到这里

## 目录结构示例

### 原分支私有仓目录结构
```
codeA/private/
├── platform/
│   └── modem/
│       └── rf/
│           ├── rf_parameters.xml      # RF参数主文件
│           ├── config/
│           │   └── radio_config.dat   # 射频配置文件
│           └── calib/
│               └── calibration_data.bin  # 校准数据
└── ...
```

### 目标分支私有仓目录结构（执行后）
```
codeB/private/
├── platform/
│   └── modem/
│       └── rf/
│           ├── [新项目目录]/           # 新建的项目文件夹
│           │   ├── rf_parameters.xml
│           │   ├── config/
│           │   │   └── radio_config.dat
│           │   └── calib/
│           │       └── calibration_data.bin
│           └── ...
└── ...
```

## 路径验证规则
1. 路径必须存在且可访问
2. 路径不能为空字符串
3. 路径必须是绝对路径
4. 路径中不能包含特殊字符

## 常见问题
- **路径不存在**: 检查路径拼写是否正确
- **权限不足**: 确保有读取原分支私有仓和写入目标分支私有仓的权限
- **文件已存在**: 目标文件夹已存在时，会询问用户是否覆盖
