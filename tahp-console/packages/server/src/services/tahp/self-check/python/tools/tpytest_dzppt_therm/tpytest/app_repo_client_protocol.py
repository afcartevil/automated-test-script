from typing import List, Tuple, Optional, Union, Dict, Any, Protocol


class AppRepoClientProtocol(Protocol):
    def fetch_global_index(self, force: bool = False) -> Dict[str, Any]:
        """
        Fetch global index, using local cache with TTL and provider as fallback.
        If force=True -> always fetch remote and refresh local cached copy.
        Returns the parsed index dict.
        """
        ...

    def list_remote_apps(self) -> List[Dict[str, Any]]:
        ...

    def get_latest_version_from_index(self, package_name: str) -> Optional[Dict[str, Any]]:
        ...

    def get_remote_meta(self, package_name: str, version_code: Union[int, str], force: bool = False) -> Optional[Dict[str, Any]]:
        ...

    def get_cached_meta(self, package_name: str, version_code: Union[int, str]) -> Optional[Dict[str, Any]]:
        ...

    def update_cache_for_package(self,
                                 package_name: str,
                                 version_code: Optional[Union[int, str]] = None,
                                 force_download: bool = False,
                                 extract_xapk: bool = False):
        """
        Ensure meta + artifact cached for package/version.
        Uses locks to prevent concurrent downloads and cache corruption.
        """
        ...

    def submit_missing_request(self, package_name: str, version_code: Union[int, str], notes: str = ""):
        """
        Submit a missing artifact request to repo requests dir; idempotent.
        If a request file for same package/version exists, skip.
        """
        ...

    def prefetch_caches_parallel(self,
                                 pkg_ver_list: List[Tuple[str, Union[int, str]]],
                                 max_workers: Optional[int] = None,
                                 force_download: bool = False,
                                 extract_xapk: bool = False) -> Dict[Tuple[str, Union[int, str]], Dict[str, Any]]:
        """
        Prefetch a list of (package, version) pairs into cache in parallel.
        Returns mapping (package, version) -> result dict:
            { "success": bool, "download_result": DownloadResult or None, "error": str or None }

        - Uses self._download_semaphore to limit concurrent provider download operations.
        - Each task will call update_cache_for_package internally (so artifact-level locks are respected).
        - This method is reusable (you can call it outside install_batch_parallel).
        """
        ...

    def install_batch_parallel(self,
                               device_id: str,
                               install_specs: List[Union[str, Dict[str, Any]]],
                               compare_mode_default: str = "existence",
                               max_workers: int = 8,
                               per_install_timeout: int = 3600,
                               install_options: Tuple[str, ...] = ('-r', '-g', '-t'),
                               precheck: bool = True,
                               allow_remote_fetch: bool = True,
                               force: bool = False,
                               downgrade: bool = False,
                               retries: int = 2) -> Dict[str, Dict[str, Any]]:
        """
        并行批量安装多个 app 到同一台设备的方案（ThreadPoolExecutor）。
        - install_specs: list of package_name (str) or dicts with keys matching install_cached_to_device params
          e.g. "com.example.app"  or {"package_name": "com.example.app", "version_code": 123, "device_abis": [.]}
        - 返回: dict mapping task_key -> result_dict (result format same as install_cached_to_device)
        - precheck=True: 在提交实际安装前并发地做 compare-only 检查以过滤掉可跳过项，避免下载。
        - 每个任务会使用 per_install_timeout 作为其超时时间（install_cached_to_device 的 timeout_seconds）
        Note: 本方法不会自动对设备加锁（除非 caller 的 spec 指定 device_lock=True）。
        """
        ...

    def install_cached_to_device(self,
                                 device_id: str,
                                 package_name: str,
                                 version_code: Optional[Union[int, str]] = None,
                                 device_abis: Optional[List[str]] = None,
                                 compare_mode: str = "existence",
                                 install_options: Tuple[str, ...] = ('-r', '-g', '-t'),
                                 allow_remote_fetch: bool = True,
                                 force: bool = False,
                                 downgrade: bool = False,
                                 retries: int = 2,
                                 device_lock: bool = False,
                                 timeout_seconds: int = 3600) -> Dict[str, Any]:
        """
        安装仓库中的 app 到指定 Android 设备

        简要
        ----
        将仓库（通过 provider）中的某个 package/version 的 artifact（apk 或 xapk）安装到指定设备。
        该函数会负责：
          * 从 remote 拉取或使用本地缓存的 global_index/meta/artifact（可控是否允许远端拉取）；
          * 根据 device_abis 与 meta 选择最合适的二进制（apk 或 xapk）；
          * 在需要时把 artifact 下载并缓存（`update_cache_for_package`，受 artifact 锁保护）；
          * 根据 `compare_mode` 决定是否跳过安装（默认宽松：只要设备存在该包就跳过）；
          * 使用 provider.local_adb_install(...) 执行真正的安装操作（provider 必须实现该方法）；
          * （可选）对设备加锁，避免并发安装冲突（受注入的 resource_lock_manager 控制）；
          * 全程遵循 `timeout_seconds` 的总时限，返回详细的操作结果便于排查。

        参数
        ----
        package_name (str)
            要安装的应用包名（如 "com.example.app"）。必填。

        version_code (Optional[int|str], default=None)
            指定要安装的 versionCode。若为 None（默认），会从 global_index 中选取当前最新版本。

        device_id (str)
            目标设备标识（例如 adb serial）。**必填**，无默认值。

        device_abis (Optional[List[str]], default=None)
            设备支持的 ABI 列表（按优先级，从高到低），例如 ["arm64-v8a","armeabi-v7a"]。
            若为 None，默认使用 ["arm64-v8a","armeabi-v7a"]（首选 64 位）。

        compare_mode (str, default="existence")
            安装前的版本/存在性比较策略（决定是否跳过安装）：
              - "none"：不比较，总是尝试安装（受 force 控制）。
              - "existence"：只要设备上存在该包（任意版本）就跳过（**默认、宽松**）。
              - "version_code"：按 numeric versionCode 比较（支持跳过相同或更高版本；受 downgrade 控制）。
              - "version_name"：按 versionName 字符串比较（先精确比，再尝试数值段比较）。
              - "prefer_newer"：优先尝试 version_code，比不可用时退回 version_name。

        install_options (Tuple[str,...], default=('-r','-g','-t'))
            传递给 provider.local_adb_install 的安装选项（如 adb install 的参数）。

        allow_remote_fetch (bool, default=True)
            是否允许在本地缓存缺失时从远端 repo 下载 artifact（True：允许；False：不允许，缺失则报错）。

        force (bool, default=False)
            强制安装，忽略比较策略（即使版本相同也会安装）。

        downgrade (bool, default=False)
            是否允许降级安装（当设备上版本高于目标版本时）。默认 False。

        retries (int, default=2)
            当调用 provider.local_adb_install 失败时的最大重试次数（总尝试次数）。

        device_lock (bool, default=False)
            是否对目标设备加锁（使用 resource_lock_manager.acquire_resource / release_resource）。
            默认为 False（不自动加设备级锁）。若为 True，需确保在初始化时注入可用的 lock manager；
            未注入时退化为进程内锁（**无法跨进程/跨主机互斥**）。

        timeout_seconds (int, default=300)
            本次操作的**总超时时间（秒）**。函数在各个阶段都会检查是否超时；若超时会尽快终止并以 timed_out 返回。

        返回值（dict）
        ----
        函数始终返回一个 dict，包含操作的详细记录，主要字段包括但不限于：
          - package_name: str
          - requested_version: 原始输入的 version_code（或 None）
          - resolved_version: 实际用于安装的 version_code（若输入为 None 则为 index 上解析到的最新）
          - container_type: "apk" | "xapk"
          - selected: 被选中的 meta 条目（apk 条目或 xapk.contained_apk 条目）
          - artifact_local_path: 本地缓存的 artifact 路径（apk 或 xapk）
          - device_before: {"version_code": int|None, "version_name": str|None}（安装前探测结果）
          - device_after:  同上（安装后探测结果，若可探测）
          - action: "installed" | "skipped" | "failed" | "timed_out"
          - install_attempts: list of {attempt, start, duration_seconds, success, error?}
          - timed_out: bool
          - notes: list of short diagnostic strings (例如 "existence_skip", "artifact_not_cached_and_no_fetch", ...)
          - timestamp, elapsed_seconds: 操作时间信息

        行为约定与细节
        ----
        * Artifact 选择
          - 使用 `select_best_apk_for_device(meta, device_abis)` 决定安装目标（apk 或 xapk 中的 contained apk）。

        * 缓存与校验
          - 下载时会尽量使用本地缓存；若 meta 提供 `content_sha256`，会校验下载文件与声明 hash 是否一致以保证完整性。
          - `update_cache_for_package` 内部对 artifact 使用 artifact 级别锁，避免并发写入造成损坏。

        * 并发控制
          - 建议注入实现良好的 `resource_lock_manager`（数据库/redis 等实现），以获得跨进程/跨主机的互斥能力。
          - 若未注入，客户端会使用进程内锁作为回退方案（只能保障同一进程内的线程安全）。
          - `device_lock` 为 True 时，方法会尝试获取 key=`device:{device_id}` 的锁，防止同一设备被并发写入。

        * 版本比较语义
          - 在 `compare_mode != "none"` 且 `force == False` 时，方法会尝试探测设备安装的版本（优先使用 provider 提供的查询接口，如 `get_installed_version`；若不可用则回退到 adb dumpsys）。
          - 各 `compare_mode` 的具体判定逻辑见上文“参数详解”部分。`downgrade=True` 用于允许把设备上的较高版本降级到 target。

        * 超时
          - `timeout_seconds` 为此次调用的总时限。函数会在下载/探测/安装循环中检查剩余时间并尽早返回 `timed_out` 状态。

        异常与错误处理
        ----
        函数会在无法进行关键操作时抛出异常（便于上层捕获），典型包括但不限于：
          - `FileNotFoundError`：meta/artifact 在缓存和远端均不存在且 `allow_remote_fetch=False`，或下载失败。
          - `RuntimeError`：provider 不支持 `local_adb_install`、锁管理器异常等。
        此外，函数也会以返回的 `install_attempts` 与 `notes` 提供详细失败信息，调用者应结合异常与返回值做完整的错误处理与日志记录。

        示例（简短）
        ----
        # 安装最新（宽松：若设备已安装任意版本则跳过）
        res = client.install_cached_to_device("com.example.app", device_id="device123")

        # 强制重装最新
        res = client.install_cached_to_device("com.example.app", device_id="device123", force=True)

        # 安装特定 versionCode，按 version_code 比较并禁止降级
        res = client.install_cached_to_device("com.example.app", version_code=200, device_id="device123",
                                              compare_mode="version_code", downgrade=False)
        """
        ...

    def list_cached_packages(self) -> List[Tuple[str, str]]:
        ...
