#!/usr/bin/env python3
"""
Auto Patch Merger - Remote Execution Version

This script automates the process of merging MTK modem patches:
1. Connects to Linux fortress machine via harness
2. Uploads and configures non-interactive merge script on remote
3. Runs non-interactive merge script on remote server
4. Automatically resolves merge conflicts on remote
5. Generates report on remote server
6. Completes all steps except final push
"""

import os
import sys
import subprocess
import re
import json
import base64
import time
from datetime import datetime


class AutoPatchMerger:
    def __init__(self, config):
        self.config = config
        self.skill_dir = os.path.dirname(os.path.abspath(__file__))
        self.ai_pick_side_path = config.get("ai_pick_side_path")
        out_dir = config.get("output_dir") or os.getcwd()
        try:
            self.output_dir = os.path.abspath(out_dir)
        except Exception:
            self.output_dir = os.getcwd()
        self.report_data = {
            'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': '',
            'success': False,
            'config': {},
            'steps': [],
            'conflicts': {
                'total': 0,
                'resolved': 0,
                'failed': 0,
                'files': []
            },
            'git_info': {},
            'errors': []
        }
        # Setup local log file
        self.log_dir = os.path.join(self.output_dir, 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.log_dir, f"execution_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
        # Delay configuration (in seconds) to prevent bridge disconnect
        self.enable_harness_delay = os.environ.get('APM_ENABLE_HARNESS_DELAY', '').lower() in ('1', 'true', 'yes')
        if self.enable_harness_delay:
            self.short_delay = 2
            self.medium_delay = 5
            self.long_delay = 10
        else:
            self.short_delay = 0
            self.medium_delay = 0
            self.long_delay = 0
        self.log(
            f"Harness delay enabled: {int(self.enable_harness_delay)} (short={self.short_delay}, medium={self.medium_delay}, long={self.long_delay})"
        )
        
        # Path configuration - auto convert between mapped and remote
        self.mapped_work_dir = None
        self.remote_work_dir = None
        
        work_dir = config.get('work_dir') or config.get('remote_work_dir')
        if work_dir:
            work_dir = os.path.normpath(work_dir)
            mapped_prefix = config.get('mapped_prefix', 'Z:')
            remote_prefix = config.get('remote_prefix', '/work/user/code')
            
            # Check if it's a Windows mapped path
            if work_dir.startswith(mapped_prefix):
                self.mapped_work_dir = work_dir
                # Auto convert to remote path
                rel_path = work_dir[len(mapped_prefix):].replace('\\', '/')
                self.remote_work_dir = f"{remote_prefix}{rel_path}"
                self.log(f"Auto-converted paths:")
                self.log(f"  Mapped: {self.mapped_work_dir}")
                self.log(f"  Remote: {self.remote_work_dir}")
            else:
                # It's already a remote path
                self.remote_work_dir = work_dir
                self.log(f"Using remote path only: {self.remote_work_dir}")
        else:
            self.remote_work_dir = '/home/user/modem'
            self.log(f"Using default remote path: {self.remote_work_dir}")
        
        # Verify mapped directory if available
        if self.mapped_work_dir:
            if os.path.exists(self.mapped_work_dir):
                self.log(f"Using mapped directory for file transfers: {self.mapped_work_dir}")
            else:
                self.log(f"Warning: Mapped directory not found: {self.mapped_work_dir}, will use base64 method instead")
                self.mapped_work_dir = None
        
    def wait(self, seconds):
        """Wait for specified seconds with log message"""
        if not getattr(self, 'enable_harness_delay', True):
            return
        if seconds > 0:
            self.log(f"  Waiting {seconds} seconds to stabilize bridge connection...")
            import time
            time.sleep(seconds)
    
    def log(self, message):
        """Log message with timestamp to both console and file"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        if hasattr(self, 'log_file') and self.log_file:
            self.log_file.write(log_line + '\n')
            self.log_file.flush()
    
    def close_log_file(self):
        """Close the log file"""
        if hasattr(self, 'log_file') and self.log_file:
            self.log_file.close()
    
    def add_step(self, step_name, status, details=''):
        """Add step to report"""
        self.report_data['steps'].append({
            'name': step_name,
            'status': status,
            'details': details,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    
    def run_harness_command(self, command, working_dir=None, max_retries=3, retry_delay=10, delay_after=0):
        """Run command on remote machine via Transsion Harness bridge-exec with retry logic"""
        import sys
        # Proper harness command format: harness remote-runner bridge-exec --command "<command>"
        # For multiple commands or working directory, use bash -c
        if not getattr(self, 'enable_harness_delay', True):
            delay_after = 0
        
        if working_dir:
            command_str = ' '.join(command)
            remote_cmd = f"cd {working_dir} && {command_str}"
        else:
            remote_cmd = ' '.join(command)
        
        # Build argument list or shell command
        if sys.platform == "win32":
            # On Windows, escape double quotes properly for shell
            escaped_remote_cmd = remote_cmd.replace('"', '\\"')
            full_cmd = f'harness --json remote-runner bridge-exec --i-understand-this-runs-raw-shell --command "{escaped_remote_cmd}"'
            self.log(f"Running remote command: {full_cmd}")
        else:
            full_args = ["harness", "--json", "remote-runner", "bridge-exec", "--i-understand-this-runs-raw-shell", "--command", remote_cmd]
            self.log(f"Running remote command: {' '.join(full_args)}")
        
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                if sys.platform == "win32":
                    result = subprocess.run(
                        full_cmd,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        shell=True,
                        timeout=300  # 5 minutes timeout per attempt
                    )
                else:
                    result = subprocess.run(
                        full_args,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=300  # 5 minutes timeout per attempt
                    )
                
                # Parse JSON output from harness
                try:
                    output_json = json.loads(result.stdout)
                    
                    if result.stdout:
                        status = output_json.get('status', 'unknown')
                        exit_code = output_json.get('exit_code', 1)
                        self.log(f"[Harness] status: {status}, exit_code: {exit_code}")
                        if output_json.get('output'):
                            self.log(output_json.get('output'))
                    
                    if result.stderr:
                        self.log(f"[Harness STDERR] {result.stderr.strip()}")
                    
                    # Check for timeout or bridge error
                    if output_json.get('status') == 'error':
                        error_msg = (output_json.get('error', '') or '').strip()
                        output_msg = (output_json.get('output', '') or '').strip()
                        combined_msg = (error_msg + " " + output_msg).strip()
                        combined_lower = combined_msg.lower()
                        if 'timeout' in combined_lower or 'timed out' in combined_lower or 'bridge' in combined_lower:
                            last_error = combined_msg
                            if attempt < max_retries:
                                self.log(f"Bridge error detected (attempt {attempt}/{max_retries}): {combined_msg}")
                                delay = 60 - (attempt * 10)  # First: 50s, Second: 40s, Third: 30s
                                self.log(f"Retrying in {delay} seconds (OTP may be required)...")
                                import time
                                time.sleep(delay)
                                continue
                            else:
                                self.log(f"Max retries ({max_retries}) reached. Last error: {combined_msg}")
                                # Return a wrapper object with error info
                                wrapper = type('', (), {})()
                                wrapper.returncode = 1
                                wrapper.stdout = ''
                                wrapper.stderr = combined_msg
                                return wrapper
                    
                    # Create a wrapper object that simulates subprocess.CompletedProcess
                    wrapper = type('', (), {})()
                    wrapper.returncode = output_json.get('exit_code', 1)
                    wrapper.stdout = output_json.get('output', '')
                    wrapper.stderr = result.stderr
                    # Add delay after successful command
                    if delay_after > 0:
                        self.wait(delay_after)
                    return wrapper
                except (json.JSONDecodeError, TypeError, ValueError):
                    # Fallback to raw output if JSON parsing fails
                    if result.stdout:
                        self.log(result.stdout.strip())
                    if result.stderr:
                        self.log(f"STDERR: {result.stderr.strip()}")
                    
                    # Check if this looks like a bridge error even without JSON
                    if result.stderr and ('bridge' in result.stderr.lower() or 'timeout' in result.stderr.lower()):
                        last_error = result.stderr
                        if attempt < max_retries:
                            self.log(f"Bridge error detected (attempt {attempt}/{max_retries}): JSON parse failed")
                            delay = 60 - (attempt * 10)  # First: 50s, Second: 40s, Third: 30s
                            self.log(f"Retrying in {delay} seconds (OTP may be required)...")
                            import time
                            time.sleep(delay)
                            continue
                    
                    # Add delay after command even if JSON parse fails
                    if delay_after > 0:
                        self.wait(delay_after)
                    return result
                    
            except subprocess.TimeoutExpired:
                last_error = f"Command timed out after 300 seconds (attempt {attempt}/{max_retries})"
                self.log(last_error)
                if attempt < max_retries:
                    delay = 60 - (attempt * 10)  # First: 50s, Second: 40s, Third: 30s
                    self.log(f"Retrying in {delay} seconds (OTP may be required)...")
                    import time
                    time.sleep(delay)
                continue
            except Exception as e:
                last_error = str(e)
                self.log(f"Error running harness command: {e}")
                if attempt < max_retries:
                    delay = 60 - (attempt * 10)  # First: 50s, Second: 40s, Third: 30s
                    self.log(f"Retrying in {delay} seconds (OTP may be required)...")
                    import time
                    time.sleep(delay)
                    continue
                else:
                    self.log(f"Max retries ({max_retries}) reached. Last error: {last_error}")
                    wrapper = type('', (), {})()
                    wrapper.returncode = 1
                    wrapper.stdout = ''
                    wrapper.stderr = last_error
                    return wrapper
        
        # All retries failed
        wrapper = type('', (), {})()
        wrapper.returncode = 1
        wrapper.stdout = ''
        wrapper.stderr = last_error or "Max retries exceeded"
        return wrapper
    
    def check_bridge_connection(self):
        """Check if harness bridge to bastion is active, try to start it if not"""
        # Skip bridge check if already confirmed working
        if os.environ.get('SKIP_BRIDGE_CHECK', '').lower() == 'true':
            self.log("Skipping bridge check (SKIP_BRIDGE_CHECK=true)")
            return True
        
        self.log("Checking harness bridge connection status...")
        
        # First check if bridge is already active
        bridge_active = self._test_bridge_connection()
        
        if bridge_active:
            return True
        
        # If bridge not active, try to start it
        self.log("Bridge not active, attempting to start bridge...")
        
        if self._start_bridge_service():
            # Polling with more frequent checks (total 60 seconds)
            import time
            total_wait_time = 60
            check_interval = 5
            elapsed = 0
            
            self.log(f"Polling bridge connection for up to {total_wait_time} seconds (checking every {check_interval}s)...")
            
            while elapsed < total_wait_time:
                # Test connection
                bridge_active = self._test_bridge_connection()
                if bridge_active:
                    self.log(f"Bridge connection established successfully after {elapsed} seconds")
                    return True
                
                # Wait for next check
                time.sleep(check_interval)
                elapsed += check_interval
                remaining = total_wait_time - elapsed
                if remaining > 0:
                    self.log(f"  Waiting... {remaining} seconds remaining")
            
            # All retries failed
            self.log("Bridge started but connection test failed after polling for 60 seconds")
            self.log("Please check if you have completed the OTP verification in the bridge terminal")
            return False
        else:
            self.log("Could not start bridge automatically")
            self.log("Please run 'harness remote-runner bridge-serve' in a terminal to start the bridge")
            return False
    
    def _test_bridge_connection(self):
        """Test if bridge connection is working"""
        import sys
        try:
            self.log("  Testing bridge connection with harness command...")
            # On Windows, use shell=True to find harness in PATH
            if sys.platform == "win32":
                result = subprocess.run(
                    'harness --json remote-runner bridge-exec --i-understand-this-runs-raw-shell --command "echo bridge_check"',
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=True,
                    timeout=15
                )
            else:
                result = subprocess.run(
                    ["harness", "--json", "remote-runner", "bridge-exec", "--i-understand-this-runs-raw-shell", "--command", "echo bridge_check"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15
                )
            
            self.log(f"  Bridge test - return code: {result.returncode}")
            if result.stdout:
                self.log(f"  Bridge test - stdout: {result.stdout.strip()}")
            if result.stderr:
                self.log(f"  Bridge test - stderr: {result.stderr.strip()}")
            
            try:
                import json
                output_json = json.loads(result.stdout)
                
                status = output_json.get("status", "unknown")
                exit_code = output_json.get("exit_code", -1)
                
                self.log(f"  Bridge test - parsed status: {status}, exit_code: {exit_code}")
                
                if status == "ok" and exit_code == 0:
                    self.log(f"  Bridge connection is active (remote: {output_json.get('output', '').strip()})")
                    return True
                else:
                    self.log(f"  Bridge test failed - status not ok or exit_code != 0")
                    return False
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                self.log(f"  Bridge test - JSON decode error: {e}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log("  Bridge test - timeout after 30 seconds")
            return False
        except Exception as e:
            self.log(f"  Bridge test - exception: {type(e).__name__}: {e}")
            return False
    
    def _start_bridge_service(self):
        """Try to start the bridge service in a new window"""
        try:
            import sys
            import os
            
            if sys.platform == "win32":
                # On Windows, start a new PowerShell window
                subprocess.Popen(
                    [
                        "powershell",
                        "-NoExit",
                        "-Command",
                        "harness remote-runner bridge-serve"
                    ],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                # On other platforms, try to start in background
                subprocess.Popen(
                    ["harness", "remote-runner", "bridge-serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            
            return True
        except Exception as e:
            self.log(f"Failed to start bridge automatically: {e}")
            return False
    
    def copy_file_via_mapped_dir(self, local_path, remote_relative_path, content=None):
        """Copy file via mapped network drive if available
        
        Args:
            local_path: Path to local file (if content is None)
            remote_relative_path: Relative path on remote (starting from remote_work_dir)
            content: Optional content to write (if provided, local_path is ignored)
        
        Returns:
            bool: True if successful
        """
        if not self.mapped_work_dir:
            return False
            
        try:
            if not os.path.exists(self.mapped_work_dir):
                self.log(f"Mapped directory not found: {self.mapped_work_dir}")
                return False
                
            remote_full_path = os.path.join(self.mapped_work_dir, remote_relative_path.replace('/', os.sep))
            remote_dir = os.path.dirname(remote_full_path)
            
            # Create directory if needed
            if not os.path.exists(remote_dir):
                os.makedirs(remote_dir, exist_ok=True)
                self.log(f"Created directory: {remote_dir}")
                
            # Write content or copy file
            if content is not None:
                # Ensure Linux line endings (LF)
                content = content.replace('\r\n', '\n').replace('\r', '\n')
                with open(remote_full_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                self.log(f"Written content to mapped path: {remote_full_path}")
            else:
                import shutil
                # Read local file with correct line endings
                with open(local_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                content = content.replace('\r\n', '\n').replace('\r', '\n')
                with open(remote_full_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                self.log(f"Copied file to mapped path: {local_path} -> {remote_full_path}")
                
            return True
        except Exception as e:
            self.log(f"Failed to copy via mapped directory: {e}")
            return False

    def _mapped_git_exec(self, args, timeout=2):
        """Run a lightweight git command against the mapped worktree."""
        if not self.mapped_work_dir or not os.path.exists(self.mapped_work_dir):
            return None
        started = time.perf_counter()
        try:
            kwargs = {
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "timeout": timeout,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(["git", "-C", self.mapped_work_dir, *args], **kwargs)
            elapsed = (time.perf_counter() - started) * 1000
            self.log(f"[Mapped git] {' '.join(args)} rc={result.returncode} elapsed_ms={elapsed:.0f}")
            return result
        except subprocess.TimeoutExpired:
            elapsed = (time.perf_counter() - started) * 1000
            self.log(f"[Mapped git] {' '.join(args)} timeout elapsed_ms={elapsed:.0f}")
            return None
        except Exception as e:
            self.log(f"[Mapped git] {' '.join(args)} failed: {e}")
            return None

    def _mapped_git_rev_parse(self, rev, timeout=2):
        result = self._mapped_git_exec(["rev-parse", rev], timeout=timeout)
        if result and result.returncode == 0 and result.stdout:
            value = result.stdout.strip().splitlines()
            if value:
                return value[-1].strip()
        return None

    def _probe_mapped_repo_state(self):
        """Probe merge state from mapped worktree using local fs/index only."""
        if not self.mapped_work_dir or not os.path.exists(self.mapped_work_dir):
            return {"available": False, "reason": "mapped_unavailable", "merge_head": False, "ls_files": [], "index_lock": False}

        merge_head = os.path.exists(os.path.join(self.mapped_work_dir, ".git", "MERGE_HEAD"))
        index_lock = os.path.exists(os.path.join(self.mapped_work_dir, ".git", "index.lock"))
        result = self._mapped_git_exec(["ls-files", "-u"], timeout=2)
        if not result or result.returncode != 0:
            return {
                "available": False,
                "reason": "mapped_git_failed",
                "merge_head": merge_head,
                "ls_files": [],
                "index_lock": index_lock,
            }

        files = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            tab_index = line.rfind("\t")
            if tab_index < 0:
                continue
            file_path = line[tab_index + 1 :].strip()
            if file_path:
                files.append(file_path)

        return {
            "available": True,
            "reason": "",
            "merge_head": merge_head,
            "ls_files": sorted(set(files)),
            "index_lock": index_lock,
        }
            
    def configure_md_merge(self):
        """Upload and configure non-interactive merge script to remote server"""
        self.log("Uploading and configuring non-interactive merge script...")
        
        node_branch = self.config.get("NODE_BRANCH", "master")
        current_commit = self._mapped_git_rev_parse(node_branch, timeout=2)
        if current_commit:
            self.log(f"Current commit ID (mapped): {current_commit}")
        else:
            get_commit_cmd = ['git', 'rev-parse', node_branch]
            commit_result = self.run_harness_command(get_commit_cmd, self.remote_work_dir, delay_after=self.short_delay)
            if commit_result and commit_result.returncode == 0:
                current_commit = commit_result.stdout.strip()
            else:
                current_commit = ""

        if current_commit:
            self.log(f"Current commit ID: {current_commit}")
        else:
            self.log("Warning: Could not get current commit ID")
            
        # Read local non-interactive script template
        local_script_path = os.path.join(os.path.dirname(__file__), 'md_merge_noninteractive.sh')
        with open(local_script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Replace placeholders with actual values
        script_content = script_content.replace('NODE_BRANCH=', f'NODE_BRANCH={self.config.get("NODE_BRANCH", "master")}')
        script_content = script_content.replace('target_BRANCH=', f'target_BRANCH={self.config.get("target_BRANCH")}')
        script_content = script_content.replace('AP_lable=', f'AP_lable={self.config.get("AP_lable")}')
        script_content = script_content.replace('DESCRIPTION=基线升级', f'DESCRIPTION={self.config.get("DESCRIPTION", "基线升级")}')
        script_content = script_content.replace('JIRAID=', f'JIRAID={self.config.get("JIRAID")}')
        if current_commit:
            script_content = script_content.replace('before_node_commit_id=', f'before_node_commit_id={current_commit}')
        
        # Try to copy via mapped directory first
        success = self.copy_file_via_mapped_dir(None, "tools/md_merge_noninteractive.sh", content=script_content)
        
        if not success:
            # Fallback to base64 method
            self.log("Falling back to base64 upload method...")
            remote_script_path = f"{self.remote_work_dir}/tools/md_merge_noninteractive.sh"
            content_base64 = base64.b64encode(script_content.encode('utf-8')).decode('utf-8')
            write_cmd = [f"mkdir -p {self.remote_work_dir}/tools"]
            self.run_harness_command(write_cmd, self.remote_work_dir, delay_after=self.short_delay)
            write_cmd = [f'echo "{content_base64}" | base64 -d > "{remote_script_path}"']
            result = self.run_harness_command(write_cmd, self.remote_work_dir, delay_after=self.short_delay)
            success = result and result.returncode == 0
        
        if success:
            self.add_step("上传非交互式脚本", "success", "已上传并配置非交互式合并脚本")
            self.log("Non-interactive merge script uploaded successfully")
            return True
        else:
            self.add_step("上传非交互式脚本", "failed", "脚本上传失败")
            self.report_data['errors'].append("Failed to upload non-interactive merge script")
            return False
    
    def upload_scripts(self):
        """Upload helper scripts to remote server"""
        self.log("Uploading helper scripts to remote...")
        
        scripts = [
            ("md_post_merge.sh", "tools/md_post_merge.sh"),
            ("md_continue_after_conflict.sh", "tools/md_continue_after_conflict.sh"),
        ]
        all_ok = True
        
        for local_name, remote_rel in scripts:
            try:
                local_path = os.path.join(os.path.dirname(__file__), local_name)
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                content = content.replace("NODE_BRANCH=", f'NODE_BRANCH={self.config.get("NODE_BRANCH", "master")}')
                content = content.replace("target_BRANCH=", f'target_BRANCH={self.config.get("target_BRANCH")}')
                content = content.replace("AP_lable=", f'AP_lable={self.config.get("AP_lable")}')
                content = content.replace("DESCRIPTION=基线升级", f'DESCRIPTION={self.config.get("DESCRIPTION", "基线升级")}')
                content = content.replace("JIRAID=", f'JIRAID={self.config.get("JIRAID")}')
                
                success = self.copy_file_via_mapped_dir(None, remote_rel, content=content)
                if not success:
                    remote_full = f"{self.remote_work_dir}/{remote_rel}"
                    content_base64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
                    self.run_harness_command([f"mkdir -p {self.remote_work_dir}/tools"], self.remote_work_dir, delay_after=self.short_delay)
                    result = self.run_harness_command([f'echo "{content_base64}" | base64 -d > "{remote_full}"'], self.remote_work_dir, delay_after=self.short_delay)
                    success = bool(result and result.returncode == 0)
                
                if not success:
                    all_ok = False
            except Exception as e:
                self.log(f"Failed to upload helper script {local_name}: {e}")
                all_ok = False
        
        if all_ok:
            self.add_step("上传脚本", "success", "后续流程脚本已上传")
            self.log("Helper scripts uploaded successfully")
            return True
        
        self.add_step("上传脚本", "failed", "后续流程脚本上传失败")
        self.report_data["errors"].append("Failed to upload helper scripts")
        return False
    
    def run_md_merge(self):
        """Run non-interactive merge script on remote server"""
        self.log("Running non-interactive merge script on remote server...")

        before_head = self._mapped_git_rev_parse("HEAD", timeout=2)
        if before_head:
            self.log(f"Current HEAD before merge (mapped): {before_head}")
        else:
            before_head_result = self.run_harness_command(['git', 'rev-parse', 'HEAD'], self.remote_work_dir, delay_after=self.short_delay)
            if before_head_result and before_head_result.returncode == 0 and before_head_result.stdout:
                before_head = before_head_result.stdout.strip().splitlines()[-1].strip()

        cmd = ['bash', 'tools/md_merge_noninteractive.sh']
        result = self.run_harness_command(cmd, self.remote_work_dir, delay_after=self.long_delay)

        if not result:
            self.add_step("运行合并脚本", "failed", "脚本执行超时或失败")
            self.report_data['errors'].append("Merge script execution failed")
            return False

        if result.returncode not in (0, 1):
            self.add_step("运行合并脚本", "failed", f"脚本执行失败，返回码: {result.returncode}")
            self.report_data['errors'].append(f"Merge script execution failed with code {result.returncode}")
            if result.stdout:
                self.log(f"Script stdout: {result.stdout}")
            if result.stderr:
                self.log(f"Script stderr: {result.stderr}")
            return False

        merge_head_result = self.run_harness_command(['test', '-f', '.git/MERGE_HEAD'], self.remote_work_dir, delay_after=self.short_delay)
        in_merge = bool(merge_head_result and merge_head_result.returncode == 0)

        if in_merge:
            self.add_step("运行合并脚本", "warning", "检测到合并冲突，需要研发手动处理")
            self.log("Merge conflict detected, manual resolution is required")
            return True

        self._wait_for_remote_repo_stable()

        status_porcelain = ''
        status_result = self.run_harness_command(['git', 'status', '--porcelain'], self.remote_work_dir, delay_after=self.short_delay)
        if status_result and status_result.returncode == 0 and status_result.stdout:
            status_porcelain = status_result.stdout.strip()

        after_head = self._mapped_git_rev_parse("HEAD", timeout=2)
        if after_head:
            self.log(f"Current HEAD after merge (mapped): {after_head}")
        else:
            after_head_result = self.run_harness_command(['git', 'rev-parse', 'HEAD'], self.remote_work_dir, delay_after=self.short_delay)
            if after_head_result and after_head_result.returncode == 0 and after_head_result.stdout:
                after_head = after_head_result.stdout.strip().splitlines()[-1].strip()

        merge_has_effect = bool(in_merge or status_porcelain or (before_head and after_head and before_head != after_head))

        if merge_has_effect:
            self.add_step("运行合并脚本", "success", "合并脚本执行完成")
            return True

        self.log("Warning: No merge effect detected. Check if branches already merged or script did not perform merge.")
        self.add_step("运行合并脚本", "warning", "合并脚本执行完成，但未检测到合并变更")
        return True
    
    def _cleanup_helper_scripts(self):
        """Clean up helper scripts so they don't get committed"""
        self.log("Cleaning up helper scripts...")
        scripts_to_clean = ['tools/md_merge_noninteractive.sh']
        for script in scripts_to_clean:
            rm_cmd = ['rm', '-f', script]
            self.run_harness_command(rm_cmd, self.remote_work_dir, delay_after=self.short_delay)
            if self.mapped_work_dir:
                # Also clean up via mapped path
                mapped_script = os.path.join(self.mapped_work_dir, script.replace('/', os.sep))
                try:
                    if os.path.exists(mapped_script):
                        os.remove(mapped_script)
                        self.log(f"Removed local mapped script: {mapped_script}")
                except Exception as e:
                    self.log(f"Warning: Could not remove {mapped_script}: {e}")

    def _finalize_and_generate_report(self):
        self.report_data['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        has_failed = any(s.get('status') == 'failed' for s in self.report_data.get('steps', []))
        self.report_data['success'] = (not has_failed) and (not self.report_data.get('errors')) and (self.report_data['conflicts'].get('failed', 0) == 0)
        report_step_label = getattr(self, "report_step_label", None)
        if report_step_label:
            self.log(f"\n[{report_step_label}] Generate report...")
        else:
            self.log("\n[Step 9] Generating report...")
        return self.generate_report()
    
    def resolve_conflicts(self):
        """Resolve conflicts on remote server using Python (primary) or Shell (fallback)"""
        self.log("Resolving conflicts on remote server...")
        
        # Check if there are any conflict files using multiple methods
        has_conflicts = self._detect_conflicts()
        
        if not has_conflicts:
            self.log("No conflicts detected, skipping conflict resolution")
            self.add_step("检查合并冲突", "success", "未发现冲突")
            return True
        
        self.log("Conflicts detected, automatic resolution has been removed.")

        mapped_conflict_files = self._conflict_files_from_mapped_log()
        if mapped_conflict_files:
            self.report_data['conflicts']['files'] = mapped_conflict_files
            self.report_data['conflicts']['total'] = len(mapped_conflict_files)
        else:
            conflict_total = self._count_conflict_files()
            if conflict_total > 0:
                self.report_data['conflicts']['total'] = conflict_total
        
        unmerged = self.run_harness_command(['GIT_PAGER=cat', 'git', 'diff', '--name-only', '--diff-filter=U'], self.remote_work_dir, delay_after=self.short_delay)
        if unmerged and unmerged.returncode == 0 and unmerged.stdout:
            cleaned = re.sub(r'\x1b\[[0-9;]*[A-Za-z]|\x1b.', '', unmerged.stdout)
            unmerged_files = [line.strip() for line in cleaned.splitlines() if line.strip()]
        else:
            unmerged_files = []

        if unmerged_files:
            if self.report_data['conflicts']['total'] <= 0:
                self.report_data['conflicts']['total'] = len(unmerged_files)
            else:
                self.report_data['conflicts']['total'] = max(self.report_data['conflicts']['total'], len(unmerged_files))
            existing = self.report_data['conflicts'].get('files') or []
            self.report_data['conflicts']['files'] = sorted(set(existing + unmerged_files))

        self.add_step("解决合并冲突", "warning", "检测到冲突，当前版本不再自动解冲突，请研发手动处理")
        self.report_data['errors'].append("manual_conflict_resolution_required")
        return False

    def _aimodel_chat(self, messages, timeout=120, retries=2):
        return None

    def _extract_first_json_object(self, text):
        if not isinstance(text, str):
            return None

        decoder = json.JSONDecoder()
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        if not starts:
            return None
        start = min(starts)
        for i in range(start, min(len(text), start + 5000)):
            if text[i] not in "{[":
                continue
            try:
                obj, end = decoder.raw_decode(text[i:])
                return obj
            except Exception:
                continue
        return None

    def _has_rd_marker(self, text):
        return bool(re.search(r'//.*?\b(?:TDD|RD|R&D)\s*:', text or '', re.IGNORECASE))

    def _has_added_block_marker(self, text):
        return bool(re.search(r'//.*?\bTDD\s*:\s*Added\b', text or '', re.IGNORECASE))

    def _has_modify_block_marker(self, text):
        return bool(re.search(r'//.*?\bTDD\s*:\s*Modify\b', text or '', re.IGNORECASE))

    def _looks_like_added_tail_block(self, text):
        raw = text or ""
        if not re.search(r'//.*?\bTDD\s*:\s*Added\b.*\bend\b', raw, re.IGNORECASE):
            return False
        if re.search(r'\bcase\s+[^:\r\n]+:', raw, re.IGNORECASE):
            return False
        cleaned = re.sub(r'(?m)//.*$', '', raw)
        return bool(re.search(r'(?m)^\s*(break\s*;|\})', cleaned))

    def _normalize_comment_insensitive_text(self, text):
        normalized = []
        for line in (text or "").splitlines():
            code = re.sub(r'//.*$', '', line).strip()
            if code:
                normalized.append(re.sub(r'\s+', ' ', code))
        return "\n".join(normalized)

    def _extract_case_labels(self, text):
        return sorted(set(m.group(0).strip() for m in re.finditer(r'\bcase\s+[^:\r\n]+:', text or '', re.IGNORECASE)))

    def _extract_case_blocks(self, text):
        raw = text or ""
        starts = list(re.finditer(r'(?m)^[ \t]*case\s+[^:\r\n]+:', raw, re.IGNORECASE))
        if not starts:
            return None
        prefix = raw[: starts[0].start()]
        blocks = []
        for i, match in enumerate(starts):
            start = match.start()
            end = starts[i + 1].start() if i + 1 < len(starts) else len(raw)
            label = match.group(0).strip()
            blocks.append(
                {
                    "label": label,
                    "text": raw[start:end],
                }
            )
        return {"prefix": prefix, "blocks": blocks}

    def _brace_balance(self, text):
        raw = text or ""
        raw = re.sub(r'/\*[\s\S]*?\*/', '', raw)
        raw = re.sub(r'(?m)//.*$', '', raw)
        return raw.count("{") - raw.count("}")

    def _is_case_label_list(self, text):
        raw = text or ""
        cleaned = re.sub(r'/\*[\s\S]*?\*/', '', raw)
        cleaned = re.sub(r'(?m)//.*$', '', cleaned)
        lines = [x.strip() for x in cleaned.splitlines() if x.strip()]
        if not lines:
            return False
        for line in lines:
            if not re.match(r'(?i)^case\s+[^:\r\n]+:\s*$', line):
                return False
        return True

    def _case_chunk_complete(self, text):
        raw = text or ""
        if not re.search(r'\bcase\s+[^:\r\n]+:', raw, re.IGNORECASE):
            return True
        if self._is_case_label_list(raw):
            return True
        if self._brace_balance(raw) != 0:
            return False
        cleaned = re.sub(r'/\*[\s\S]*?\*/', '', raw)
        cleaned = re.sub(r'(?m)//.*$', '', cleaned)
        if not re.search(r'(?m)^\s*(break\s*;|return\b|goto\b|continue\b|throw\b)', cleaned):
            return False
        return True

    def _preferred_case_side(self, head_text, patch_text):
        head_added = self._has_added_block_marker(head_text)
        patch_added = self._has_added_block_marker(patch_text)
        if head_added and not patch_added:
            return "HEAD"
        if patch_added and not head_added:
            return "Patch"
        head_rd = self._has_rd_marker(head_text)
        patch_rd = self._has_rd_marker(patch_text)
        if head_rd and not patch_rd:
            return "HEAD"
        if patch_rd and not head_rd:
            return "Patch"
        return "Patch"

    def _extract_sbp_id_def_blocks(self, text):
        raw = text or ""
        pattern = re.compile(
            r'(?ms)^[ \t]*SBP_ID_DEF\(\s*([A-Za-z0-9_]+)\s*,[^\)]*\)\s*\r?\n.*?^[ \t]*SBP_ID_DEF_END[ \t]*$'
        )
        matches = list(pattern.finditer(raw))
        if not matches:
            return None
        prefix = raw[: matches[0].start()]
        if prefix.strip():
            return None
        blocks = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            block_text = raw[m.start() : end]
            gap = raw[m.end() : end]
            if gap.strip():
                return None
            blocks.append({"key": (m.group(1) or "").strip(), "text": block_text})
        return {"prefix": prefix, "blocks": blocks} if blocks else None

    def _extract_sbp_id_def_fallback_blocks(self, text):
        raw = text or ""
        pattern = re.compile(r'(?m)^[ \t]*SBP_ID_DEF\(\s*([A-Za-z0-9_]+)\s*,')
        matches = list(pattern.finditer(raw))
        if not matches:
            return None
        prefix = raw[: matches[0].start()]
        blocks = []
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            block_text = raw[m.start() : end]
            blocks.append({"key": (m.group(1) or "").strip(), "text": block_text})
        return {"prefix": prefix, "blocks": blocks} if blocks else None

    def _extract_sbp_id_def_keys(self, text):
        keys = set()
        for m in re.finditer(r'(?m)^[ \t]*SBP_ID_DEF\(\s*([A-Za-z0-9_]+)\s*,', text or ""):
            k = (m.group(1) or "").strip()
            if k:
                keys.add(k)
        return keys or None

    def _fix_sbp_id_def_end_before_next_def(self, text):
        raw = text or ""
        if "SBP_ID_DEF(" not in raw:
            return raw
        out = []
        in_block = False
        start_pat = re.compile(r'^\s*SBP_ID_DEF\(\s*[A-Za-z0-9_]+\s*,')
        end_pat = re.compile(r'^\s*SBP_ID_DEF_END\b')
        for line in raw.splitlines(True):
            if start_pat.match(line):
                if in_block:
                    nl = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "\n")
                    out.append("SBP_ID_DEF_END" + nl)
                in_block = True
                out.append(line)
                continue
            if end_pat.match(line):
                in_block = False
                out.append(line)
                continue
            out.append(line)
        if in_block:
            trailing = raw.endswith("\r\n")
            nl = "\r\n" if trailing else ("\n" if raw.endswith("\n") else "\n")
            out.append("SBP_ID_DEF_END" + nl)
        return "".join(out)

    def _merge_sbp_id_def_blocks(self, head_text, patch_text):
        head_info = self._extract_sbp_id_def_blocks(head_text) or self._extract_sbp_id_def_fallback_blocks(head_text)
        patch_info = self._extract_sbp_id_def_blocks(patch_text) or self._extract_sbp_id_def_fallback_blocks(patch_text)
        if not head_info or not patch_info:
            return None

        preferred = self._preferred_case_side(head_text or "", patch_text or "")
        preferred_info = head_info if preferred == "HEAD" else patch_info
        other_info = patch_info if preferred == "HEAD" else head_info

        def better_block(existing, candidate):
            a = existing or ""
            b = candidate or ""
            a_rd = self._has_rd_marker(a)
            b_rd = self._has_rd_marker(b)
            if b_rd and not a_rd:
                return candidate
            return existing

        mapping = {}
        preferred_order = []
        other_order = []
        for item in preferred_info["blocks"]:
            k = item["key"]
            if k not in mapping:
                preferred_order.append(k)
            mapping[k] = item["text"]
        for item in other_info["blocks"]:
            k = item["key"]
            if k not in mapping:
                other_order.append(k)
                mapping[k] = item["text"]
                continue
            mapping[k] = better_block(mapping.get(k), item["text"])

        out = [preferred_info.get("prefix") or ""]
        out.extend(mapping[k] for k in preferred_order if mapping.get(k) is not None)
        out.extend(mapping[k] for k in other_order if mapping.get(k) is not None)
        merged = "".join(out)
        merged = self._append_merge_newline(merged, head_text, patch_text)
        return merged if merged.strip() else None

    def _extract_sbp_feature_calls(self, text):
        items = []
        for raw in (text or "").splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            m = re.match(
                r'^\s*sbp_set_md_feature\(\s*([A-Za-z0-9_]+)\s*,.*\)\s*;\s*(?://.*)?$',
                line,
            )
            if not m:
                return None
            items.append({"key": m.group(1), "line": raw})
        return items or None

    def _append_merge_newline(self, merged_text, *source_texts):
        merged = merged_text or ""
        if not merged or merged.endswith(("\n", "\r")):
            return merged
        newline = "\r\n" if any("\r\n" in (text or "") for text in source_texts) else "\n"
        return merged + newline

    def _merge_sbp_feature_calls(self, head_text, patch_text):
        head_items = self._extract_sbp_feature_calls(head_text)
        patch_items = self._extract_sbp_feature_calls(patch_text)
        if not head_items or not patch_items:
            return None

        preferred = self._preferred_case_side(head_text or "", patch_text or "")
        preferred_items = head_items if preferred == "HEAD" else patch_items
        other_items = patch_items if preferred == "HEAD" else head_items

        def better_line(existing, candidate):
            a = existing or ""
            b = candidate or ""
            a_rd = self._has_rd_marker(a)
            b_rd = self._has_rd_marker(b)
            if b_rd and not a_rd:
                return candidate
            return existing

        mapping = {}
        preferred_order = []
        other_order = []
        for item in preferred_items:
            k = item["key"]
            if k not in mapping:
                preferred_order.append(k)
            mapping[k] = item["line"]
        for item in other_items:
            k = item["key"]
            if k not in mapping:
                other_order.append(k)
                mapping[k] = item["line"]
                continue
            mapping[k] = better_line(mapping.get(k), item["line"])

        out_lines = [mapping[k] for k in preferred_order] + [mapping[k] for k in other_order]
        merged = "\n".join(x.rstrip("\r\n") for x in out_lines if x is not None)
        merged = self._append_merge_newline(merged, head_text, patch_text)
        return merged if merged.strip() else None

    def _extract_assignment_keys(self, text):
        keys = []
        for raw in (text or '').splitlines():
            line = raw.strip().rstrip(';')
            if not line or '=' not in line:
                continue
            left = line.split('=', 1)[0].strip()
            if not left or ' ' in left and '(' in left:
                continue
            keys.append(left)
        return keys

    def _classify_assignment_line(self, raw):
        stripped = (raw or "").strip()
        if not stripped:
            return {"kind": "passthrough", "raw": raw}
        if stripped.startswith("#"):
            return {"kind": "passthrough", "raw": raw}
        if stripped.startswith("//"):
            return {"kind": "passthrough", "raw": raw}
        if stripped.startswith("/*") or stripped.startswith("*") or stripped.endswith("*/"):
            return {"kind": "passthrough", "raw": raw}
        code = raw.split("//", 1)[0].rstrip()
        if not code.strip():
            return {"kind": "passthrough", "raw": raw}
        if not code.strip().endswith(";"):
            return None
        if not re.search(r"(?<![=!<>])=(?![=])", code):
            return None
        left = code.split("=", 1)[0].strip()
        if not left:
            return None
        if "(" in left or ")" in left:
            return None
        return {"kind": "assignment", "raw": raw, "key": left}

    def _extract_assignment_merge_info(self, text):
        order = []
        mapping = {}
        items = []
        for raw in (text or "").splitlines():
            item = self._classify_assignment_line(raw)
            if item is None:
                return None
            items.append(item)
            if item["kind"] != "assignment":
                continue
            key = item["key"]
            if key not in mapping:
                order.append(key)
            mapping[key] = item["raw"]
        return {"order": order, "map": mapping, "items": items} if mapping else None

    def _extract_assignment_map(self, text):
        info = self._extract_assignment_merge_info(text)
        if not info:
            return None
        return {"order": info["order"], "map": info["map"]}

    def _can_merge_assignments(self, head_text, patch_text):
        return bool(self._extract_assignment_merge_info(head_text) and self._extract_assignment_merge_info(patch_text))

    def _merge_assignments_by_key(self, head_text, patch_text):
        head_info = self._extract_assignment_merge_info(head_text)
        patch_info = self._extract_assignment_merge_info(patch_text)
        if not head_info or not patch_info:
            return None

        def choose_line(head_line, patch_line):
            h = head_line or ""
            p = patch_line or ""
            if head_line is None:
                return patch_line
            if patch_line is None:
                return head_line
            h_rd = self._has_rd_marker(h)
            p_rd = self._has_rd_marker(p)
            if h_rd and not p_rd:
                return head_line
            if p_rd and not h_rd:
                return patch_line
            return patch_line

        out_lines = []
        emitted = set()
        preferred = self._preferred_case_side(head_text, patch_text)
        preferred_info = head_info if preferred == "HEAD" else patch_info
        other_info = patch_info if preferred == "HEAD" else head_info
        for item in preferred_info["items"]:
            if item["kind"] != "assignment":
                out_lines.append(item["raw"])
                continue
            key = item["key"]
            emitted.add(key)
            out_lines.append(choose_line(head_info["map"].get(key), patch_info["map"].get(key)))
        for k in other_info["order"]:
            if k in emitted:
                continue
            out_lines.append(other_info["map"].get(k))
        merged = "\n".join((x or "").rstrip("\r\n") for x in out_lines if x is not None)
        merged = self._append_merge_newline(merged, head_text, patch_text)
        return merged if merged.strip() else None

    def _can_keep_both(self, head_text, patch_text):
        head_sbp = self._extract_sbp_feature_calls(head_text)
        patch_sbp = self._extract_sbp_feature_calls(patch_text)
        if head_sbp and patch_sbp:
            head_keys = {x["key"] for x in head_sbp}
            patch_keys = {x["key"] for x in patch_sbp}
            if head_keys.isdisjoint(patch_keys):
                return True
            if self._merge_sbp_feature_calls(head_text, patch_text):
                return True
            preferred = self._preferred_case_side(head_text, patch_text)
            if preferred == "HEAD" and (patch_keys - head_keys):
                return True
            if preferred == "Patch" and (head_keys - patch_keys):
                return True
            return False

        head_sbp_id = self._extract_sbp_id_def_blocks(head_text)
        patch_sbp_id = self._extract_sbp_id_def_blocks(patch_text)
        if head_sbp_id and patch_sbp_id:
            head_keys = {x["key"] for x in head_sbp_id["blocks"] if x.get("key")}
            patch_keys = {x["key"] for x in patch_sbp_id["blocks"] if x.get("key")}
            if head_keys.isdisjoint(patch_keys):
                return True
            if self._merge_sbp_id_def_blocks(head_text, patch_text):
                return True
            preferred = self._preferred_case_side(head_text, patch_text)
            if preferred == "HEAD" and (patch_keys - head_keys):
                return True
            if preferred == "Patch" and (head_keys - patch_keys):
                return True
            return False

        head_sbp_id_keys = self._extract_sbp_id_def_keys(head_text)
        patch_sbp_id_keys = self._extract_sbp_id_def_keys(patch_text)
        if head_sbp_id_keys and patch_sbp_id_keys:
            head_keys = set(head_sbp_id_keys)
            patch_keys = set(patch_sbp_id_keys)
            if head_keys.isdisjoint(patch_keys):
                return True
            if self._merge_sbp_id_def_blocks(head_text, patch_text):
                return True
            preferred = self._preferred_case_side(head_text, patch_text)
            if preferred == "HEAD" and (patch_keys - head_keys):
                return True
            if preferred == "Patch" and (head_keys - patch_keys):
                return True
            return False

        if self._can_merge_assignments(head_text, patch_text):
            return True

        head_cases = self._extract_case_labels(head_text)
        patch_cases = self._extract_case_labels(patch_text)
        if not (head_cases and patch_cases):
            return False
        head_set = set(head_cases)
        patch_set = set(patch_cases)
        if head_set.isdisjoint(patch_set):
            return self._case_chunk_complete(head_text) and self._case_chunk_complete(patch_text)
        preferred = self._preferred_case_side(head_text, patch_text)
        if not preferred:
            return False
        if preferred == "HEAD" and (patch_set - head_set):
            return self._case_chunk_complete(head_text) and self._case_chunk_complete(patch_text)
        if preferred == "Patch" and (head_set - patch_set):
            return self._case_chunk_complete(head_text) and self._case_chunk_complete(patch_text)
        return False

    def _merge_both_content(self, head_text, patch_text):
        head = head_text or ""
        patch = patch_text or ""
        if not head.strip():
            return patch
        if not patch.strip():
            return head
        if head.strip() == patch.strip():
            preferred = self._preferred_case_side(head, patch)
            return head if preferred == "HEAD" else patch

        merged_sbp = self._merge_sbp_feature_calls(head, patch)
        if merged_sbp:
            return merged_sbp

        merged_sbp_id = self._merge_sbp_id_def_blocks(head, patch)
        if merged_sbp_id:
            return self._fix_sbp_id_def_end_before_next_def(merged_sbp_id)

        merged_assign = self._merge_assignments_by_key(head, patch)
        if merged_assign:
            return self._fix_sbp_id_def_end_before_next_def(merged_assign)

        head_case_info = self._extract_case_blocks(head)
        patch_case_info = self._extract_case_blocks(patch)
        if head_case_info and patch_case_info:
            preferred = self._preferred_case_side(head, patch)
            preferred_info = head_case_info if preferred == "HEAD" else patch_case_info
            other_info = patch_case_info if preferred == "HEAD" else head_case_info
            preferred_labels = {item["label"] for item in preferred_info["blocks"]}
            merged_parts = [preferred_info["prefix"]]
            merged_parts.extend(item["text"] for item in preferred_info["blocks"])
            merged_parts.extend(item["text"] for item in other_info["blocks"] if item["label"] not in preferred_labels)
            merged = "".join(merged_parts)
            merged = self._append_merge_newline(merged, head, patch)
            if merged.strip():
                return self._fix_sbp_id_def_end_before_next_def(merged)

        left = head.rstrip("\r\n")
        right = patch.lstrip("\r\n")
        if not left:
            return right
        if not right:
            return left
        merged = left + ("\r\n" if ("\r\n" in head or "\r\n" in patch) else "\n") + right
        return self._fix_sbp_id_def_end_before_next_def(self._append_merge_newline(merged, head, patch))

    def _normalize_pick_side_decision(self, decision, suggestion, keypoints, head_text, patch_text):
        normalized = str(decision or "").strip()
        if normalized not in ("HEAD", "Patch", "Both", "Manual"):
            normalized = "Manual"

        all_text = " ".join(
            [str(suggestion or "")]
            + [str(x or "") for x in (keypoints or [])]
        ).lower()
        can_keep_both = self._can_keep_both(head_text, patch_text)
        preserve_both_hint = any(
            token in all_text
            for token in (
                "preserve both",
                "keep both",
                "manual resolution",
                "both sides add different switch/case",
                "同时保留",
                "保留双方",
                "人工合并",
            )
        )

        if can_keep_both and normalized in ("HEAD", "Patch"):
            normalized = "Both"
        elif can_keep_both and preserve_both_hint:
            normalized = "Both"
        elif preserve_both_hint and normalized != "Both":
            normalized = "Manual"
        elif normalized == "Both" and not can_keep_both:
            normalized = "Manual"
        return normalized

    def _normalize_pick_side_decision_detail(self, decision, suggestion, keypoints, head_text, patch_text):
        raw = str(decision or "").strip()
        allowed = ("HEAD", "Patch", "Both", "Manual")
        normalized = raw if raw in allowed else "Manual"
        reason = "as_is"
        if raw not in allowed:
            reason = "invalid_decision"

        all_text = " ".join(
            [str(suggestion or "")]
            + [str(x or "") for x in (keypoints or [])]
        ).lower()
        can_keep_both = self._can_keep_both(head_text, patch_text)
        preserve_both_hint = any(
            token in all_text
            for token in (
                "preserve both",
                "keep both",
                "manual resolution",
                "both sides add different switch/case",
                "同时保留",
                "保留双方",
                "人工合并",
            )
        )

        if can_keep_both and normalized in ("HEAD", "Patch"):
            normalized = "Both"
            reason = "head_patch_forced_to_both"
        elif can_keep_both and preserve_both_hint:
            normalized = "Both"
            reason = "hint_forced_to_both"
        elif preserve_both_hint and normalized != "Both":
            normalized = "Manual"
            reason = "hint_forced_to_manual"
        elif normalized == "Both" and not can_keep_both:
            normalized = "Manual"
            reason = "both_not_allowed_by_can_keep_both"

        return {
            "rawDecision": raw if raw in allowed else "Manual",
            "decision": normalized,
            "canKeepBoth": bool(can_keep_both),
            "preserveBothHint": bool(preserve_both_hint),
            "normalizeReason": reason,
        }

    def _normalize_conflict_match(self, content, match, index=None):
        if isinstance(match, dict):
            start = int(match.get("start", 0))
            end = int(match.get("end", start))
            head = match.get("head") or ""
            patch = match.get("patch") or ""
            raw_block = match.get("rawBlock")
            source_indexes = list(match.get("sourceIndexes") or ([] if index is None else [index]))
            start_line = match.get("startLine")
            end_line = match.get("endLine")
        else:
            start = match.start()
            end = match.end()
            head = match.group("head") or ""
            patch = match.group("patch") or ""
            raw_block = match.group(0) or content[start:end]
            source_indexes = [] if index is None else [index]
            start_line = None
            end_line = None
        if raw_block is None:
            raw_block = content[start:end]
        if start_line is None:
            start_line = content[:start].count("\n") + 1
        if end_line is None:
            end_line = content[:end].count("\n") + 1
        return {
            "index": index,
            "start": start,
            "end": end,
            "startLine": start_line,
            "endLine": end_line,
            "head": head,
            "patch": patch,
            "rawBlock": raw_block,
            "sourceIndexes": source_indexes,
        }

    def _build_raw_conflict_prompt_block(self, content, match, index, context_lines=2):
        def is_conflict_marker(line):
            stripped = (line or "").lstrip()
            return stripped.startswith("<<<<<<<") or stripped.startswith("=======") or stripped.startswith(">>>>>>>")

        def collect_before_context(prefix_text):
            lines = prefix_text.splitlines()
            collected = []
            for line in reversed(lines):
                if is_conflict_marker(line):
                    break
                collected.append(line)
                if len(collected) >= context_lines:
                    break
            return list(reversed(collected))

        def collect_after_context(suffix_text):
            lines = suffix_text.splitlines()
            collected = []
            for line in lines:
                if is_conflict_marker(line):
                    break
                collected.append(line)
                if len(collected) >= context_lines:
                    break
            return collected

        block = self._normalize_conflict_match(content, match, index)
        start = block["start"]
        end = block["end"]
        head = block["head"]
        patch = block["patch"]
        start_line = block["startLine"]
        end_line = block["endLine"]
        before_lines = collect_before_context(content[:start])
        after_lines = collect_after_context(content[end:])
        return {
            "index": index,
            "start": start,
            "end": end,
            "startLine": start_line,
            "endLine": end_line,
            "head": head,
            "patch": patch,
            "contextBefore": "\n".join(before_lines),
            "contextAfter": "\n".join(after_lines),
            "rawBlock": block["rawBlock"],
            "sourceIndexes": list(block.get("sourceIndexes") or []),
        }

    def _sanitize_ai_replacement(self, replacement, *source_texts):
        if not isinstance(replacement, str):
            return None
        cleaned = replacement.replace("\r\n", "\n").replace("\r", "\n").strip("\r\n")
        if re.search(r'(?m)^(<<<<<<<|=======|>>>>>>>)', cleaned):
            return None
        return self._append_merge_newline(cleaned, *source_texts) if cleaned else ""

    def _texts_equivalent_for_pick_side(self, left, right):
        left_raw = (left or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        right_raw = (right or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if left_raw == right_raw:
            return True
        return self._normalize_comment_insensitive_text(left_raw) == self._normalize_comment_insensitive_text(right_raw)

    def _validate_ai_decision_replacement(self, decision, replacement, head_text, patch_text, raw_block_text):
        if replacement is None:
            return {"ok": True, "decision": decision, "replacement": None, "reason": "no_replacement"}

        if decision == "HEAD":
            if self._texts_equivalent_for_pick_side(replacement, head_text):
                return {"ok": True, "decision": decision, "replacement": replacement, "reason": "replacement_matches_head"}
            return {"ok": False, "decision": decision, "replacement": None, "reason": "replacement_conflicts_with_head"}

        if decision == "Patch":
            if self._texts_equivalent_for_pick_side(replacement, patch_text):
                return {"ok": True, "decision": decision, "replacement": replacement, "reason": "replacement_matches_patch"}
            return {"ok": False, "decision": decision, "replacement": None, "reason": "replacement_conflicts_with_patch"}

        if decision == "Both":
            if self._texts_equivalent_for_pick_side(replacement, head_text):
                return {"ok": False, "decision": decision, "replacement": None, "reason": "both_replacement_equals_head"}
            if self._texts_equivalent_for_pick_side(replacement, patch_text):
                return {"ok": False, "decision": decision, "replacement": None, "reason": "both_replacement_equals_patch"}
            merged_local = self._merge_both_content(head_text, patch_text)
            if self._texts_equivalent_for_pick_side(replacement, merged_local):
                return {"ok": True, "decision": decision, "replacement": replacement, "reason": "replacement_matches_local_both"}
            return {"ok": True, "decision": decision, "replacement": replacement, "reason": "replacement_kept_for_both"}

        if decision == "Manual":
            if self._texts_equivalent_for_pick_side(replacement, raw_block_text):
                return {"ok": True, "decision": decision, "replacement": replacement, "reason": "manual_keeps_raw_block"}
            return {"ok": False, "decision": decision, "replacement": None, "reason": "manual_should_not_replace"}

        return {"ok": False, "decision": "Manual", "replacement": None, "reason": "unknown_decision"}

    def _build_conflict_blocks(self, content, matches):
        blocks = []
        if not matches:
            return blocks
        normalized_matches = [self._normalize_conflict_match(content, m, idx) for idx, m in enumerate(matches)]

        def has_case_or_tdd(text):
            txt = text or ""
            return self._has_added_block_marker(txt) or self._has_modify_block_marker(txt) or bool(re.search(r'\bcase\s+[^:\r\n]+:', txt, re.IGNORECASE))

        def should_merge(prev_block, next_block, gap_text):
            if not prev_block or next_block is None:
                return False
            if '<<<<<<<' in (gap_text or '') or '=======' in (gap_text or '') or '>>>>>>>' in (gap_text or ''):
                return False
            gap_lines = len((gap_text or '').splitlines())
            if gap_lines > 20:
                return False
            prev_head = prev_block["head"]
            prev_patch = prev_block["patch"]
            next_head = next_block["head"]
            next_patch = next_block["patch"]
            if has_case_or_tdd(prev_head) or has_case_or_tdd(prev_patch) or has_case_or_tdd(next_head) or has_case_or_tdd(next_patch):
                return True
            if gap_lines <= 8:
                return True
            return False

        for block in normalized_matches:
            start = block["start"]
            end = block["end"]
            head = block["head"]
            patch = block["patch"]
            if blocks:
                gap = content[blocks[-1]["end"] : start]
                if should_merge(blocks[-1], block, gap):
                    blocks[-1]["end"] = end
                    blocks[-1]["endLine"] = block["endLine"]
                    blocks[-1]["head"] += gap + head
                    blocks[-1]["patch"] += gap + patch
                    blocks[-1]["rawBlock"] = content[blocks[-1]["start"] : end]
                    blocks[-1]["sourceIndexes"].extend(block.get("sourceIndexes") or [])
                    continue
            blocks.append(dict(block))
        return blocks

    def _build_pick_side_heuristic(self, head_text, patch_text):
        head = (head_text or '').strip()
        patch = (patch_text or '').strip()
        head_rd = self._has_rd_marker(head)
        patch_rd = self._has_rd_marker(patch)
        head_added = self._has_added_block_marker(head)
        patch_added = self._has_added_block_marker(patch)
        head_modify = self._has_modify_block_marker(head)
        patch_modify = self._has_modify_block_marker(patch)

        if head == patch:
            preferred = self._preferred_case_side(head, patch)
            return {
                "decision": preferred,
                "suggestion": "两侧内容相同；若存在研发标记则保留研发侧，否则采用 Patch。",
                "keyPoints": ["HEAD 与 Patch 内容一致"],
            }
        if head == "" and patch != "":
            return {
                "decision": "Patch",
                "suggestion": "HEAD 侧为空，选择 Patch 侧内容。",
                "keyPoints": ["HEAD 侧为空", "Patch 侧非空"],
            }
        if patch == "" and head != "":
            return {
                "decision": "HEAD",
                "suggestion": "Patch 侧为空，选择 HEAD 侧内容。",
                "keyPoints": ["Patch 侧为空", "HEAD 侧非空"],
            }
        head_norm = self._normalize_comment_insensitive_text(head)
        patch_norm = self._normalize_comment_insensitive_text(patch)
        if head_norm and head_norm == patch_norm:
            preferred = self._preferred_case_side(head, patch)
            return {
                "decision": preferred,
                "suggestion": "双方有效代码一致；若存在研发标记则保留研发侧，否则采用 Patch。",
                "keyPoints": ["去除 // 注释后代码一致"],
            }
        head_cases = self._extract_case_labels(head)
        patch_cases = self._extract_case_labels(patch)
        head_set = set(head_cases)
        patch_set = set(patch_cases)

        head_sbp = self._extract_sbp_feature_calls(head)
        patch_sbp = self._extract_sbp_feature_calls(patch)
        if head_sbp and patch_sbp:
            head_keys = {x["key"] for x in head_sbp}
            patch_keys = {x["key"] for x in patch_sbp}
            if head_keys.isdisjoint(patch_keys):
                return {
                    "decision": "Both",
                    "suggestion": "双方修改了不同的 sbp_set_md_feature 配置项，建议同时保留两侧配置。",
                    "keyPoints": [
                        f"HEAD keys: {', '.join(sorted(head_keys)[:6])}",
                        f"Patch keys: {', '.join(sorted(patch_keys)[:6])}",
                    ],
                }
            if self._merge_sbp_feature_calls(head, patch):
                if head_rd or patch_rd:
                    return {
                        "decision": "Both",
                        "suggestion": "检测到可按特性 key 合并的配置块：重复 key 保留研发值，其余保留另一侧非冲突项。",
                        "keyPoints": ["sbp_set_md_feature 存在重复 key", "重复 key 优先保留研发值"],
                    }
                return {
                    "decision": "Both",
                    "suggestion": "检测到可按特性 key 合并的配置块：重复 key 采用 Patch，其余保留双方非冲突项。",
                    "keyPoints": ["sbp_set_md_feature 存在重复 key", "重复 key 优先采用 Patch"],
                }
            return {
                "decision": "Manual",
                "suggestion": "双方修改了同名 sbp_set_md_feature 配置项，存在覆盖风险，建议人工确认。",
                "keyPoints": [
                    f"HEAD keys: {', '.join(sorted(head_keys)[:6])}",
                    f"Patch keys: {', '.join(sorted(patch_keys)[:6])}",
                ],
            }

        head_sbp_id = self._extract_sbp_id_def_blocks(head)
        patch_sbp_id = self._extract_sbp_id_def_blocks(patch)
        if head_sbp_id and patch_sbp_id:
            head_keys = {x["key"] for x in head_sbp_id["blocks"] if x.get("key")}
            patch_keys = {x["key"] for x in patch_sbp_id["blocks"] if x.get("key")}
            if head_keys.isdisjoint(patch_keys):
                return {
                    "decision": "Both",
                    "suggestion": "双方新增/修改了不同的 SBP_ID_DEF 配置块，建议同时保留两侧配置。",
                    "keyPoints": [
                        f"HEAD keys: {', '.join(sorted(head_keys)[:6])}",
                        f"Patch keys: {', '.join(sorted(patch_keys)[:6])}",
                    ],
                }
            if self._merge_sbp_id_def_blocks(head, patch):
                if head_rd or patch_rd:
                    return {
                        "decision": "Both",
                        "suggestion": "检测到可按 SBP_ID_DEF key 合并的配置块：重复 key 保留研发值，其余保留另一侧非冲突配置。",
                        "keyPoints": ["SBP_ID_DEF 存在重复 key", "重复 key 优先保留研发值"],
                    }
                return {
                    "decision": "Both",
                    "suggestion": "检测到可按 SBP_ID_DEF key 合并的配置块：重复 key 采用 Patch，其余保留双方非冲突配置。",
                    "keyPoints": ["SBP_ID_DEF 存在重复 key", "重复 key 优先采用 Patch"],
                }
            return {
                "decision": "Manual",
                "suggestion": "双方修改了同名 SBP_ID_DEF 配置块，存在覆盖风险，建议人工确认。",
                "keyPoints": [
                    f"HEAD keys: {', '.join(sorted(head_keys)[:6])}",
                    f"Patch keys: {', '.join(sorted(patch_keys)[:6])}",
                ],
            }

        head_sbp_id_keys = self._extract_sbp_id_def_keys(head)
        patch_sbp_id_keys = self._extract_sbp_id_def_keys(patch)
        if head_sbp_id_keys and patch_sbp_id_keys:
            head_keys = set(head_sbp_id_keys)
            patch_keys = set(patch_sbp_id_keys)
            if head_keys.isdisjoint(patch_keys):
                return {
                    "decision": "Both",
                    "suggestion": "双方新增/修改了不同的 SBP_ID_DEF 配置项，建议同时保留两侧配置。",
                    "keyPoints": [
                        f"HEAD keys: {', '.join(sorted(head_keys)[:6])}",
                        f"Patch keys: {', '.join(sorted(patch_keys)[:6])}",
                    ],
                }
            if self._merge_sbp_id_def_blocks(head, patch):
                if head_rd or patch_rd:
                    return {
                        "decision": "Both",
                        "suggestion": "检测到可按 SBP_ID_DEF key fallback 合并的配置块：重复 key 保留研发值，其余保留另一侧非冲突配置。",
                        "keyPoints": ["SBP_ID_DEF fallback 命中重复 key", "重复 key 优先保留研发值"],
                    }
                return {
                    "decision": "Both",
                    "suggestion": "检测到可按 SBP_ID_DEF key fallback 合并的配置块：重复 key 采用 Patch，其余保留双方非冲突配置。",
                    "keyPoints": ["SBP_ID_DEF fallback 命中重复 key", "重复 key 优先采用 Patch"],
                }
            return {
                "decision": "Manual",
                "suggestion": "双方修改了同名 SBP_ID_DEF 配置项，存在覆盖风险，建议人工确认。",
                "keyPoints": [
                    f"HEAD keys: {', '.join(sorted(head_keys)[:6])}",
                    f"Patch keys: {', '.join(sorted(patch_keys)[:6])}",
                ],
            }

        if self._can_merge_assignments(head, patch):
            if head_rd or patch_rd:
                return {
                    "decision": "Both",
                    "suggestion": "检测到可按赋值目标合并的配置块：重复 key 保留研发值，其余保留 Patch 的非冲突配置。",
                    "keyPoints": ["可按赋值目标逐行合并", "重复 key 优先保留研发值"],
                }
            return {
                "decision": "Both",
                "suggestion": "检测到可按赋值目标合并的配置块：重复 key 采用 Patch，其余保留双方非冲突配置。",
                "keyPoints": ["可按赋值目标逐行合并", "重复 key 优先采用 Patch"],
            }

        if head_added and not patch_added:
            if self._looks_like_added_tail_block(head) and patch_cases:
                return {
                    "decision": "Manual",
                    "suggestion": "检测到 HEAD 侧仅包含研发 Added 尾块，而 Patch 侧进入新的 case。为避免误丢 Patch 的独立 case，建议按整段 case 重新判断。",
                    "keyPoints": [
                        "HEAD 侧疑似仅包含 TDD Added 尾块",
                        f"Patch cases: {', '.join(patch_cases[:4])}",
                    ],
                }
            if head_cases and patch_cases and (patch_set - head_set):
                return {
                    "decision": "Both",
                    "suggestion": "HEAD 侧包含研发 Added 代码块，同时 Patch 侧还有额外新增 case，保留研发 case 并追加 Patch 独有 case。",
                    "keyPoints": [
                        "HEAD 侧包含 TDD Added 标记",
                        f"Patch extra cases: {', '.join(sorted(patch_set - head_set)[:4])}",
                    ],
                }
            return {
                "decision": "HEAD",
                "suggestion": "检测到 HEAD 侧为研发 Added 代码块，优先保留 HEAD。",
                "keyPoints": ["HEAD 侧包含 TDD Added 标记"],
            }
        if patch_added and not head_added:
            if head_cases and patch_cases and (head_set - patch_set):
                return {
                    "decision": "Both",
                    "suggestion": "Patch 侧包含研发 Added 代码块，同时 HEAD 侧还有额外新增 case，保留研发 case 并追加 HEAD 独有 case。",
                    "keyPoints": [
                        "Patch 侧包含 TDD Added 标记",
                        f"HEAD extra cases: {', '.join(sorted(head_set - patch_set)[:4])}",
                    ],
                }
            return {
                "decision": "Patch",
                "suggestion": "检测到 Patch 侧为研发 Added 代码块，优先保留 Patch。",
                "keyPoints": ["Patch 侧包含 TDD Added 标记"],
            }
        if head_modify or patch_modify:
            if head_cases and patch_cases and head_set.isdisjoint(patch_set):
                if not (self._case_chunk_complete(head_text) and self._case_chunk_complete(patch_text)):
                    return {
                        "decision": "Manual",
                        "suggestion": "检测到 Modify 标记且双方为不完整 case 片段（可能缺少 break/}），为避免生成编译错误代码，建议人工合并。",
                        "keyPoints": ["存在 TDD Modify 标记", "case 块疑似不完整"],
                    }
                return {
                    "decision": "Both",
                    "suggestion": "检测到 Modify 标记，但双方新增/修改的 case 不相交，可按顺序同时保留两侧新增内容。",
                    "keyPoints": [
                        "存在 TDD Modify 标记",
                        f"HEAD cases: {', '.join(head_cases[:4])}",
                        f"Patch cases: {', '.join(patch_cases[:4])}",
                    ],
                }
            if self._can_merge_assignments(head, patch):
                return {
                    "decision": "Both",
                    "suggestion": "检测到 Modify 标记，已按赋值项逐行合并：有研发注释的保留研发，其余采用 Patch。",
                    "keyPoints": ["存在 TDD Modify 标记", "按赋值目标逐行合并"],
                }
            return {
                "decision": "Manual",
                "suggestion": "检测到 Modify 代码块，按规范需逐行评估，暂不自动选边。",
                "keyPoints": ["存在 TDD Modify 标记"],
            }

        if head_cases and patch_cases and head_set.isdisjoint(patch_set):
            if not (self._case_chunk_complete(head_text) and self._case_chunk_complete(patch_text)):
                return {
                    "decision": "Manual",
                    "suggestion": "双方在同一位置新增了不同 case，但 case 片段疑似不完整（可能缺少 break/}），为避免生成编译错误代码，建议人工合并。",
                    "keyPoints": ["case 块疑似不完整"],
                }
            return {
                "decision": "Both",
                "suggestion": "双方在同一位置新增了不同 case，可按顺序同时保留两侧新增内容。",
                "keyPoints": [
                    f"HEAD cases: {', '.join(head_cases[:4])}",
                    f"Patch cases: {', '.join(patch_cases[:4])}",
                ],
            }
        if head_rd and not patch_rd:
            return {
                "decision": "HEAD",
                "suggestion": "HEAD 侧包含研发注释，优先保留研发修改。",
                "keyPoints": ["HEAD 侧包含研发注释", "Patch 侧无研发注释"],
            }
        if patch_rd and not head_rd:
            return {
                "decision": "Patch",
                "suggestion": "Patch 侧包含研发注释，优先保留 Patch 侧研发修改。",
                "keyPoints": ["Patch 侧包含研发注释", "HEAD 侧无研发注释"],
            }
        if head_cases and patch_cases and head_set != patch_set:
            if not head_rd and not patch_rd:
                if patch_set.issuperset(head_set):
                    return {
                        "decision": "Patch",
                        "suggestion": "双方存在部分重复 case，Patch 已覆盖重复内容且包含全部新增 case，优先采用 Patch。",
                        "keyPoints": [
                            f"HEAD cases: {', '.join(head_cases[:4])}",
                            f"Patch cases: {', '.join(patch_cases[:4])}",
                        ],
                    }
                if self._case_chunk_complete(head_text) and self._case_chunk_complete(patch_text):
                    return {
                        "decision": "Both",
                        "suggestion": "双方存在部分重复 case；重复部分采用 Patch，双方各自独有 case 同时保留。",
                        "keyPoints": [
                            f"HEAD cases: {', '.join(head_cases[:4])}",
                            f"Patch cases: {', '.join(patch_cases[:4])}",
                        ],
                    }
            return {
                "decision": "Manual",
                "suggestion": "双方 case 集合存在交叉且不完全一致，需人工合并以避免重复或覆盖。",
                "keyPoints": [
                    f"HEAD cases: {', '.join(head_cases[:4])}",
                    f"Patch cases: {', '.join(patch_cases[:4])}",
                ],
            }

        head_lines = [x.strip() for x in head.splitlines() if x.strip()]
        patch_lines = [x.strip() for x in patch.splitlines() if x.strip()]
        if len(head_lines) == 1 and len(patch_lines) == 1 and not head_rd and not patch_rd:
            head_keys = self._extract_assignment_keys(head)
            patch_keys = self._extract_assignment_keys(patch)
            if len(head_keys) == 1 and head_keys == patch_keys:
                return {
                    "decision": "Patch",
                    "suggestion": "检测到同一参数的无研发注释差异，按规范优先采用 Patch 版本。",
                    "keyPoints": [f"同一赋值目标: {head_keys[0]}", "双方均无研发注释"],
                }

        return None

    def _should_force_head_for_script_conflict(self, rel_path):
        rel = (rel_path or "").replace("\\", "/").lstrip("./")
        return rel == "rlk_amdp.sh" or rel.startswith("tools/")

    def _remote_bash_rc(self, bash_script, delay_after=0):
        """Run a bash snippet remotely and return parsed rc from '__RC:<n>__' marker."""
        safe_script = bash_script.replace("'", "'\"'\"'")
        cmd = [f"bash -lc '{safe_script}'"]
        result = self.run_harness_command(cmd, self.remote_work_dir, delay_after=delay_after)
        if not result or not getattr(result, "stdout", None):
            return None
        m = re.search(r'__RC:(\d+)__', result.stdout)
        if not m:
            return None
        return int(m.group(1))

    def _remote_bash_out(self, bash_script, delay_after=0):
        safe_script = bash_script.replace("'", "'\"'\"'")
        cmd = [f"bash -lc '{safe_script}'"]
        result = self.run_harness_command(cmd, self.remote_work_dir, delay_after=delay_after)
        if not result:
            return ''
        return result.stdout or ''

    def _strip_progress_noise(self, text):
        cleaned = re.sub(r'\x1b\[[0-9;]*[A-Za-z]|\x1b.', '', text or '')
        lines = []
        saw_progress = False
        for raw in cleaned.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("Updating files:"):
                saw_progress = True
                continue
            lines.append(line)
        return {"lines": lines, "saw_progress": saw_progress}

    def _probe_remote_repo_state(self):
        out = self._remote_bash_out(
            "set +e; "
            "if [ -f .git/MERGE_HEAD ]; then echo __APM_MERGE_HEAD__:1; else echo __APM_MERGE_HEAD__:0; fi; "
            "echo __APM_DIFF_BEGIN__; "
            "GIT_PAGER=cat git diff --name-only --diff-filter=U 2>/dev/null || true; "
            "echo __APM_DIFF_END__; "
            "echo __APM_LS_BEGIN__; "
            "git ls-files -u 2>/dev/null | cut -f2 | sort -u || true; "
            "echo __APM_LS_END__",
            delay_after=0,
        )
        parsed = self._strip_progress_noise(out)
        lines = parsed["lines"]

        def collect(begin_marker, end_marker):
            collecting = False
            items = []
            for line in lines:
                if line == begin_marker:
                    collecting = True
                    continue
                if line == end_marker:
                    collecting = False
                    continue
                if collecting:
                    items.append(line)
            return items

        merge_head = any(line == "__APM_MERGE_HEAD__:1" for line in lines)
        diff_files = sorted(set(collect("__APM_DIFF_BEGIN__", "__APM_DIFF_END__")))
        ls_files = sorted(set(collect("__APM_LS_BEGIN__", "__APM_LS_END__")))
        return {
            "merge_head": merge_head,
            "diff_files": diff_files,
            "ls_files": ls_files,
            "busy": parsed["saw_progress"],
        }

    def _wait_for_remote_repo_stable(self, max_wait=45, poll_interval=3, required_stable=2):
        import time

        self.log(
            f"[Merge settle] Waiting for remote repo to stabilize: max_wait={max_wait}s interval={poll_interval}s stable_reads={required_stable}"
        )
        if self.mapped_work_dir:
            self.log("[Merge settle] mapped-first mode enabled (local ls-files + single remote confirmation)")
        started = time.perf_counter()
        stable_hits = 0
        prev_signature = None
        last_probe = None
        attempt = 0

        while True:
            attempt += 1
            local_probe = None
            if self.mapped_work_dir:
                local_probe = self._probe_mapped_repo_state()
                if not local_probe.get("available"):
                    self.log(f"[Merge settle] probe={attempt} mapped probe unavailable: {local_probe.get('reason', 'unknown')}, fallback to remote")
                    local_probe = None
                elif local_probe.get("index_lock"):
                    self.log(f"[Merge settle] probe={attempt} mapped index.lock detected, fallback to remote")
                    local_probe = None

            if local_probe:
                probe = {
                    "merge_head": local_probe["merge_head"],
                    "diff_files": [],
                    "ls_files": local_probe["ls_files"],
                    "busy": False,
                }
                last_probe = probe
                signature = (
                    probe["merge_head"],
                    tuple(probe["ls_files"]),
                )

                if signature == prev_signature:
                    stable_hits += 1
                    self.log(
                        f"[Merge settle] probe={attempt} mapped stable={stable_hits}/{required_stable} merge_head={int(probe['merge_head'])} ls={len(probe['ls_files'])}"
                    )
                else:
                    prev_signature = signature
                    stable_hits = 1
                    self.log(
                        f"[Merge settle] probe={attempt} mapped snapshot merge_head={int(probe['merge_head'])} ls={len(probe['ls_files'])}"
                    )

                if stable_hits >= required_stable:
                    self.log(f"[Merge settle] mapped snapshot stable, running remote confirmation")
                    remote_probe = self._probe_remote_repo_state()
                    confirmed_files = sorted(set((remote_probe.get("diff_files") or []) + (remote_probe.get("ls_files") or [])))
                    local_files = sorted(set(probe["ls_files"]))
                    if remote_probe.get("busy"):
                        self.log(f"[Merge settle] remote confirmation still busy, continue polling")
                        stable_hits = 0
                        prev_signature = None
                    else:
                        self.log(
                            f"[Merge settle] remote confirmation merge_head={int(remote_probe['merge_head'])} diff={len(remote_probe['diff_files'])} ls={len(remote_probe['ls_files'])}"
                        )
                        if bool(remote_probe["merge_head"]) != bool(probe["merge_head"]) or confirmed_files != local_files:
                            self.log("[Merge settle] mapped/remote mismatch, using remote snapshot")
                        elapsed = time.perf_counter() - started
                        self.log(f"[Merge settle] repo stable after {elapsed:.2f}s")
                        return remote_probe
            else:
                probe = self._probe_remote_repo_state()
                last_probe = probe
                signature = (
                    probe["merge_head"],
                    tuple(probe["diff_files"]),
                    tuple(probe["ls_files"]),
                )

                if probe["busy"]:
                    stable_hits = 0
                    prev_signature = None
                    self.log(f"[Merge settle] probe={attempt} repo still updating, waiting...")
                elif signature == prev_signature:
                    stable_hits += 1
                    self.log(
                        f"[Merge settle] probe={attempt} stable={stable_hits}/{required_stable} merge_head={int(probe['merge_head'])} diff={len(probe['diff_files'])} ls={len(probe['ls_files'])}"
                    )
                else:
                    prev_signature = signature
                    stable_hits = 1
                    self.log(
                        f"[Merge settle] probe={attempt} snapshot merge_head={int(probe['merge_head'])} diff={len(probe['diff_files'])} ls={len(probe['ls_files'])}"
                    )

                if stable_hits >= required_stable:
                    elapsed = time.perf_counter() - started
                    self.log(f"[Merge settle] repo stable after {elapsed:.2f}s")
                    return last_probe

            elapsed = time.perf_counter() - started
            if elapsed >= max_wait:
                self.log(
                    f"[Merge settle] timeout after {elapsed:.2f}s, continue with last snapshot merge_head={int(last_probe['merge_head'])} diff={len(last_probe['diff_files'])} ls={len(last_probe['ls_files'])}"
                )
                return last_probe

            time.sleep(poll_interval)

    def _conflict_files_from_mapped_log(self):
        if not self.mapped_work_dir:
            return []
        p = os.path.join(self.mapped_work_dir, 'log', 'merge_conflict.log')
        if not os.path.exists(p):
            return []
        try:
            with open(p, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines()
        except Exception:
            return []
        files = []
        for line in lines:
            m = re.search(r'Merge conflict in\s+(.+)$', line)
            if m:
                fp = m.group(1).strip()
                if fp:
                    files.append(fp)
        return sorted(set(files))

    def _count_conflict_files(self):
        out = self._remote_bash_out(
            "set +e; "
            "n1=$(git diff --name-only --diff-filter=U 2>/dev/null | sed \"/^[[:space:]]*$/d\" | sort -u | wc -l); "
            "n2=0; "
            "if [ -f log/merge_conflict.log ]; then "
            "  n2=$(grep -E \"Merge conflict in \" log/merge_conflict.log 2>/dev/null "
            "    | sed -E \"s/.*Merge conflict in //;s/[[:space:]]*$//\" "
            "    | sort -u | wc -l); "
            "fi; "
            "echo \"${n1} ${n2}\"",
            delay_after=self.short_delay,
        ).strip()
        nums = [int(x) for x in out.split() if x.isdigit()]
        return max(nums) if nums else 0

    def _verify_conflicts_cleared(self):
        """Verify there are no remaining conflict markers or unmerged files on remote"""
        unmerged = self.run_harness_command(['GIT_PAGER=cat', 'git', 'diff', '--name-only', '--diff-filter=U'], self.remote_work_dir, delay_after=self.short_delay)
        if unmerged and unmerged.returncode == 0 and unmerged.stdout:
            cleaned = re.sub(r'\x1b\[[0-9;]*[A-Za-z]|\x1b.', '', unmerged.stdout)
            unmerged_files = [line.strip() for line in cleaned.splitlines() if line.strip()]
        else:
            unmerged_files = []

        if unmerged_files:
            self.log("Verification failed: unmerged files remain")
            self.log("\n".join(unmerged_files))
            return False

        rc = self._remote_bash_rc("set +e; git grep -q '^<<<<<<<' -- . >/dev/null 2>&1; rc=$?; echo __RC:${rc}__", delay_after=self.short_delay)
        if rc == 0:
            self.log("Verification failed: conflict markers remain in worktree")
            return False
        if rc not in (0, 1, None):
            self.log(f"Warning: marker scan returned unexpected rc: {rc}")
        return True
    
    def _detect_conflicts(self):
        """Detect conflicts using multiple methods like merge-conflict-resolver"""
        # Method 1: Check merge_conflict.log (most reliable)
        cat_cmd = ['cat', 'log/merge_conflict.log']
        cat_result = self.run_harness_command(cat_cmd, self.remote_work_dir, delay_after=self.short_delay)
        if cat_result and cat_result.returncode == 0:
            if 'CONFLICT' in cat_result.stdout or 'Automatic merge failed' in cat_result.stdout:
                self.log("Found conflicts in merge_conflict.log")
                return True
        
        # Method 2: Check git status for conflict markers
        check_cmd = ['git', 'status', '--porcelain']
        check_result = self.run_harness_command(check_cmd, self.remote_work_dir, delay_after=self.short_delay)
        
        if check_result and check_result.returncode == 0:
            conflict_codes = ['UU', 'AA', 'DD', 'AU', 'UA', 'UD', 'DU']
            for line in check_result.stdout.split('\n'):
                status = line.strip()[:2]
                if status in conflict_codes:
                    self.log(f"Found conflict via git status: {line.strip()}")
                    return True
        
        # Method 3: Check for MERGE_HEAD (indicates merge in progress)
        merge_head_cmd = ['test', '-f', '.git/MERGE_HEAD']
        merge_head_result = self.run_harness_command(merge_head_cmd, self.remote_work_dir, delay_after=self.short_delay)
        if merge_head_result and merge_head_result.returncode == 0:
            self.log("Found MERGE_HEAD, merge in progress")
            return True
        
        return False
    
    def continue_merge(self):
        """Complete merge commit on remote"""
        self.log("Completing merge commit on remote...")
        
        # First check if we are in a merge state
        check_cmd = ['test', '-f', '.git/MERGE_HEAD']
        check_result = self.run_harness_command(check_cmd, self.remote_work_dir, delay_after=self.short_delay)
        
        if check_result and check_result.returncode == 0:
            unmerged_check = self.run_harness_command(['GIT_PAGER=cat', 'git', 'diff', '--name-only', '--diff-filter=U'], self.remote_work_dir, delay_after=self.short_delay)
            if unmerged_check and unmerged_check.returncode == 0 and unmerged_check.stdout:
                cleaned = re.sub(r'\x1b\[[0-9;]*[A-Za-z]|\x1b.', '', unmerged_check.stdout)
                unmerged_files = [line.strip() for line in cleaned.splitlines() if line.strip()]
            else:
                unmerged_files = []

            if unmerged_files:
                self.add_step("完成合并提交", "failed", "仍存在未解决的冲突文件，已阻止提交")
                self.report_data['errors'].append(f"Unmerged files remain:\n" + "\n".join(unmerged_files))
                return False

            marker_rc = self._remote_bash_rc("set +e; git grep -q '^<<<<<<<' -- . >/dev/null 2>&1; rc=$?; echo __RC:${rc}__", delay_after=self.short_delay)
            if marker_rc == 0:
                self.add_step("完成合并提交", "failed", "检测到工作区仍存在冲突标记（<<<<<<<），已阻止提交")
                self.report_data['errors'].append("Conflict markers detected in worktree")
                return False

            # We are in a merge state, continue with git add and commit
            commit_msg = f"ID: {self.config.get('JIRAID')}"
            commit_msg += f" DESCRIPTION: MTK Patch {self.config.get('AP_lable')} {self.config.get('DESCRIPTION', 'BASELINE_UPGRADE')}"
            commit_msg += " TYPE:patch AFFECT_PROJECTS:ALL TEST_SUGGESTIONS:basic test"
            
            # Clean up helper scripts first so they don't get committed
            self._cleanup_helper_scripts()
            
            # First do git add
            add_result = self.run_harness_command(['git', 'add', '.'], self.remote_work_dir, delay_after=self.short_delay)
            
            if add_result and add_result.returncode == 0:
                marker_cached_rc = self._remote_bash_rc("set +e; git grep --cached -q '^<<<<<<<' >/dev/null 2>&1; rc=$?; echo __RC:${rc}__", delay_after=self.short_delay)
                if marker_cached_rc == 0:
                    self.add_step("完成合并提交", "failed", "git add 后仍检测到冲突标记（<<<<<<<），已阻止提交")
                    self.report_data['errors'].append("Conflict markers detected in index")
                    return False

                # Then commit - use heredoc to safely pass commit message with special chars
                # Escape single quotes in commit message for shell
                escaped_msg = commit_msg.replace("'", "'\"'\"'")
                commit_cmd = [f"git commit -m '{escaped_msg}'"]
                commit_result = self.run_harness_command(commit_cmd, self.remote_work_dir, delay_after=self.medium_delay)
                
                if commit_result and commit_result.returncode == 0:
                    self.add_step("完成合并提交", "success", "合并提交已完成")
                    return True
                else:
                    self.add_step("完成合并提交", "failed", "合并提交失败（commit 返回非0）")
                    self.report_data['errors'].append("git commit failed")
                    return False
            else:
                self.add_step("完成合并提交", "failed", "git add 失败")
                self.report_data['errors'].append("git add failed")
                return False
        else:
            self.add_step("完成合并提交", "info", "不在合并状态，无需提交")
            return True
    
    def generate_report(self):
        """Generate HTML report on local machine"""
        self.log("Generating report locally...")

        has_failed = any(s.get('status') == 'failed' for s in self.report_data.get('steps', []))
        if has_failed:
            status_text = 'Failed'
            status_class = 'failed'
        elif self.report_data.get('errors') or self.report_data['conflicts'].get('failed', 0) > 0:
            status_text = 'Partial Success'
            status_class = 'partial'
        else:
            status_text = 'Success'
            status_class = 'success'
        
        report_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Patch Merge Report - {datetime.now().strftime('%Y%m%d_%H%M%S')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #2c3e50; }}
        .status {{ padding: 8px 16px; border-radius: 4px; font-weight: bold; }}
        .success {{ background: #d4edda; color: #155724; }}
        .partial {{ background: #fff3cd; color: #856404; }}
        .failed {{ background: #f8d7da; color: #721c24; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .summary-box {{ flex: 1; padding: 20px; text-align: center; border-radius: 8px; }}
        .summary-success {{ background: #d4edda; }}
        .summary-failed {{ background: #f8d7da; }}
        .summary-total {{ background: #d1ecf1; }}
        .step {{ margin: 10px 0; padding: 10px; border-left: 4px solid #27ae60; }}
        .config-item {{ margin: 5px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Patch Merge Report</h1>
        <p><strong>Generate Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Status:</strong> <span class="status {status_class}">{status_text}</span></p>
        
        <h2>Config Info</h2>
        <div class="config-item"><strong>NODE_BRANCH:</strong> {self.config.get('NODE_BRANCH')}</div>
        <div class="config-item"><strong>target_BRANCH:</strong> {self.config.get('target_BRANCH')}</div>
        <div class="config-item"><strong>AP_lable:</strong> {self.config.get('AP_lable')}</div>
        <div class="config-item"><strong>JIRAID:</strong> {self.config.get('JIRAID')}</div>
        <div class="config-item"><strong>DESCRIPTION:</strong> {self.config.get('DESCRIPTION')}</div>
        
        <h2>Conflict Stats</h2>
        <div class="summary">
            <div class="summary-box summary-total"><strong>{self.report_data['conflicts']['total']}</strong><br>Total Conflicts</div>
            <div class="summary-box summary-success"><strong>{self.report_data['conflicts']['resolved']}</strong><br>Resolved</div>
            <div class="summary-box summary-failed"><strong>{self.report_data['conflicts']['failed']}</strong><br>Failed</div>
        </div>
        
        <h2>Execution Steps</h2>
"""

        for step in self.report_data['steps']:
            status_color = '#27ae60' if step['status'] == 'success' else '#e74c3c' if step['status'] == 'failed' else '#f39c12'
            report_content += f"""        <div class="step" style="border-left-color: {status_color};">
            <strong>{step['name']}</strong>
            <span style="float:right;">{step['timestamp']}</span>
            {f"<br><small>{step['details']}</small>" if step['details'] else ""}
        </div>
"""

        report_content += f"""        <h2>Next Steps</h2>
        <ol>
            <li>Review and verify merge results on remote server</li>
            <li>Resolve any remaining conflicts manually if needed</li>
            <li>Run code compilation test</li>
            <li>If the web continue flow has completed successfully, commit and push have already been executed automatically</li>
        </ol>
    </div>
</body>
</html>"""
        
        local_report_dir = os.path.join(self.output_dir, 'artifacts')
        os.makedirs(local_report_dir, exist_ok=True)
        local_report_path = os.path.join(local_report_dir, f"patch_merge_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        with open(local_report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        self.log(f"Report generated locally: {local_report_path}")
        return local_report_path
    
    def run(self):
        """Main execution flow - all operations via harness on remote"""
        self.log("=" * 60)
        self.log("Auto Patch Merger (Remote Execution via Harness)")
        self.log("=" * 60)
        self.log(f"Remote work directory: {self.remote_work_dir}")
        
        # Save config
        self.report_data['config'] = self.config
        
        # Step 1: Check harness bridge connection status
        self.log("\n[Step 1] Checking harness bridge connection...")
        if not self.check_bridge_connection():
            self.add_step("检测 Harness 桥接", "failed", "桥接连接失败，请先启动桥接服务")
            self.report_data['errors'].append("Bridge connection check failed")
            report_path = self._finalize_and_generate_report()
            if report_path:
                self.log(f"Report: {report_path}")
            return False
        self.add_step("检测 Harness 桥接", "success", "桥接连接正常")
        
        # Step 2: Upload non-interactive merge script
        self.log("\n[Step 2] Uploading non-interactive merge script...")
        if not self.configure_md_merge():
            return False
        self.wait(self.medium_delay)
            
        # Step 3: Upload scripts
        self.log("\n[Step 3] Uploading scripts to remote...")
        self.upload_scripts()
        self.wait(self.short_delay)
        
        # Step 4: Run non-interactive merge script
        self.log("\n[Step 4] Running non-interactive merge script...")
        if not self.run_md_merge():
            report_path = self._finalize_and_generate_report()
            if report_path:
                self.log(f"Report: {report_path}")
            return False
        # Note: long delay already added in run_md_merge
            
        # Step 5: Resolve conflicts on remote
        self.log("\n[Step 5] Resolving conflicts on remote...")
        if not self.resolve_conflicts():
            report_path = self._finalize_and_generate_report()
            if report_path:
                self.log(f"Report: {report_path}")
            self.close_log_file()
            return False
        
        # Step 6: Complete merge
        self.log("\n[Step 6] Completing merge...")
        if not self.continue_merge():
            report_path = self._finalize_and_generate_report()
            if report_path:
                self.log(f"Report: {report_path}")
            self.close_log_file()
            return False
        
        # Step 7: Get final git status
        self.log("\n[Step 7] Getting final git status...")
        status_result = self.run_harness_command(['git', 'status'], self.remote_work_dir, delay_after=self.short_delay)
        
        report_path = self._finalize_and_generate_report()
        
        self.log("\n" + "=" * 60)
        self.log("Auto Patch Merger Completed!")
        self.log("=" * 60)
        if report_path:
            self.log(f"Report: {report_path}")
        self.log(f"Execution log: {self.log_file_path}")
        self.log("\nNext steps:")
        self.log("1. Review the changes on remote server")
        self.log("2. Resolve any remaining conflicts manually if needed")
        self.log("3. If the continue flow finishes successfully, commit and push are already done automatically")
        
        # Close log file
        self.close_log_file()
        return True


def main():
    """Main function"""
    config = {
        'NODE_BRANCH': 'master',
        'target_BRANCH': 'PRODUCT_V_v0mp1rc_NR15_common',
        'AP_lable': 'V13.29',
        'DESCRIPTION': 'BASELINE_UPGRADE',
        'JIRAID': 'AR-UIF-0001-001-010',
        'work_dir': '/home/user/modem'
    }
    
    # Load from config file if provided
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            config.update(json.load(f))
    
    # Verify required config
    required = ['target_BRANCH', 'AP_lable', 'JIRAID']
    missing = [k for k in required if not config.get(k)]
    if not (config.get('work_dir') or config.get('remote_work_dir')):
        missing.append('work_dir (or remote_work_dir)')
    if missing:
        print(f"Error: Missing required config: {', '.join(missing)}")
        return 1
    
    merger = None
    try:
        merger = AutoPatchMerger(config)
        success = merger.run()
        return 0 if success else 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        if merger and hasattr(merger, 'log'):
            merger.log(f"Unexpected error: {e}")
        return 1
    finally:
        if merger and hasattr(merger, 'close_log_file'):
            merger.close_log_file()


if __name__ == "__main__":
    sys.exit(main())
