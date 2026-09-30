import subprocess
import sys
import os
import tempfile
import requests
import json
import base64

class CodeExecutor:
    """
    Execute code safely.
    Priority: Python subprocess (no Docker needed) → Judge0 (if Docker running)
    """

    JUDGE0_URL = "http://localhost:2358"
    LANGUAGE_IDS = {
        'python': 71,
        'javascript': 63,
        'java': 62,
        'cpp': 54,
    }

    def execute(self, code, language, stdin="", timeout=5):
        """Execute code and return standardised result dict."""
        if language == 'python':
            return self._execute_python(code, stdin, timeout)
        # For other languages try Judge0; fall back with a clear message
        return self._execute_judge0(code, language, stdin, timeout)

    # ------------------------------------------------------------------
    # Python executor (no Docker required)
    # ------------------------------------------------------------------
    # Maximum number of Python subprocesses allowed to run concurrently.
    # Prevents server OOM when many students submit at the same time.
    _semaphore = None

    @classmethod
    def _get_semaphore(cls):
        import threading
        if cls._semaphore is None:
            cls._semaphore = threading.Semaphore(10)  # max 10 concurrent executions
        return cls._semaphore

    def _execute_python(self, code, stdin="", timeout=5):
        """Run Python code in a subprocess with strict timeout + concurrency limit."""
        import platform

        # Concurrency guard — if 10 submissions are already running, queue this one.
        sem = self._get_semaphore()
        acquired = sem.acquire(timeout=30)  # wait up to 30s for a slot
        if not acquired:
            return {
                'success': False,
                'stdout': '',
                'stderr': 'Server is busy. Please try again in a moment.',
                'compile_output': '',
                'status': 'Server Busy',
                'status_id': 13,
            }

        # Write code to a temp file so tracebacks show real line numbers
        tmp = tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        )
        try:
            tmp.write(code)
            tmp.close()

            # Resource limits (Linux only) — prevent memory bombs & fork bombs
            preexec = None
            if platform.system() == 'Linux':
                import resource
                def _set_limits():
                    # 256 MB memory limit
                    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
                    # Max 50 processes (stops fork bombs)
                    resource.setrlimit(resource.RLIMIT_NPROC, (50, 50))
                    # Max 10 MB output
                    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
                preexec = _set_limits

            proc = subprocess.run(
                [sys.executable, tmp.name],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=preexec,
            )
            success = proc.returncode == 0
            return {
                'success': success,
                'stdout': proc.stdout or '',
                'stderr': proc.stderr or '',
                'compile_output': '',
                'message': '',
                'time': None,
                'memory': None,
                'status': 'Accepted' if success else 'Runtime Error',
                'status_id': 3 if success else 11,
            }

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Time Limit Exceeded ({timeout}s)',
                'compile_output': '',
                'message': 'Time Limit Exceeded',
                'time': timeout,
                'memory': None,
                'status': 'Time Limit Exceeded',
                'status_id': 5,
            }
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'compile_output': '',
                'status': 'Internal Error',
                'status_id': 13,
            }
        finally:
            sem.release()
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Judge0 executor (Docker fallback for JS/Java/C++)
    # ------------------------------------------------------------------
    def _execute_judge0(self, code, language, stdin="", timeout=5):
        language_id = self.LANGUAGE_IDS.get(language, 71)
        payload = {
            "source_code": code,
            "language_id": language_id,
            "stdin": stdin,
            "cpu_time_limit": timeout,
            "memory_limit": 128000,
            "enable_network": False,
        }
        try:
            resp = requests.post(
                f"{self.JUDGE0_URL}/submissions",
                json=payload,
                headers={"Content-Type": "application/json"},
                params={"wait": "true", "fields": "*"},
                timeout=15,
            )
            if resp.status_code != 201:
                return self._error(f"Judge0 submission failed: {resp.text}")

            result = resp.json()
            status_id = result.get('status', {}).get('id', 0)
            status_desc = result.get('status', {}).get('description', 'Unknown')

            # Judge0 may base64-encode stdout/stderr
            def decode(val):
                if not val:
                    return ''
                try:
                    return base64.b64decode(val).decode('utf-8', errors='replace')
                except Exception:
                    return val

            return {
                'success': status_id == 3,
                'stdout': decode(result.get('stdout', '')),
                'stderr': decode(result.get('stderr', '')),
                'compile_output': decode(result.get('compile_output', '')),
                'message': result.get('message', ''),
                'time': result.get('time', 0),
                'memory': result.get('memory', 0),
                'status': status_desc,
                'status_id': status_id,
            }

        except requests.exceptions.ConnectionError:
            return self._error(
                f'Cannot connect to Judge0 (Docker not running). '
                f'For languages other than Python, please start Judge0 '
                f'via Docker: docker run -d -p 2358:2358 judge0/judge0'
            )
        except Exception as e:
            return self._error(str(e))

    def _error(self, msg):
        return {
            'success': False,
            'stdout': '',
            'stderr': msg,
            'compile_output': '',
            'status': 'Execution Error',
            'status_id': 13,
        }

    # ------------------------------------------------------------------
    # Test case runner
    # ------------------------------------------------------------------
    def run_test_cases(self, code, language, test_cases):
        """Run test cases with smart partial credit scoring."""
        from .code_grader import smart_run_test_cases
        return smart_run_test_cases(self, code, language, test_cases)
