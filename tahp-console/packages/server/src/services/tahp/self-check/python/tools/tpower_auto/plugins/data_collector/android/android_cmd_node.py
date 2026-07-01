from typing import Union, Optional, Dict, Any

from data_collector.android.android_collect_node import AndroidCollectNode


class AndroidCmdNode(AndroidCollectNode):
    """
    通过 adb {cmd} 或者 adb shell {shell_cmd} 来收集资料
    params: {'cmd'} or {'shell_cmd'}
    """
    def collect(self, override_params: Optional[Dict[str, Any]] = None) -> Union[str, bytes]:
        shell_cmd = self.get_param(override_params, 'shell_cmd')
        if shell_cmd:
            return self.run_shell(f"{shell_cmd}")

        cmd = self.get_param(override_params, 'cmd')
        assert cmd, 'You did not pass in the cmd or shell_cmd command!'
        return self.run_cmd(cmd)
