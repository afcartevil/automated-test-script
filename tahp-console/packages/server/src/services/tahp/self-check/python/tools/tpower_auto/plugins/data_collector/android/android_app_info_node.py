from typing import Optional, Dict, Any

from data_collector.android.android_collect_node import AndroidCollectNode


class AndroidAppInfoNode(AndroidCollectNode):
    def collect(self, override_params: Optional[Dict[str, Any]] = None) -> str:
        packages = self.get_param(override_params, 'packages')
        assert packages, 'No packages param found for AndroidAppInfoNode collect!'
        lines = []
        for pkg in packages:
            out = self.run_shell(f"dumpsys package {pkg}")
            vm = None
            vc = None
            for line in out.splitlines():
                line = line.strip()
                if line.startswith('versionName='):
                    vm = line.split('=', 1)[1]
                if line.startswith('versionCode='):
                    vc = line.split('=', 1)[1].split(' ')[0]
                if vm and vc:
                    break
            if vm is None or vc is None:
                lines.append(f"{pkg}: not installed")
            else:
                lines.append(f"{pkg}: versionName={vm} | versionCode={vc}")
        return '\n'.join(lines)
