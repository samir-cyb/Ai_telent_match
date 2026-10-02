"""Execute every candidate language through the existing isolated Judge0 service."""
import requests
from django.conf import settings

class SandboxUnavailable(RuntimeError):
    pass

class CodeExecutor:
    LANGUAGE_IDS = {'python': 71, 'javascript': 63, 'java': 62, 'cpp': 54}

    def execute(self, code, language, stdin='', timeout=5):
        if language not in self.LANGUAGE_IDS:
            return {'success': False, 'stdout': '', 'stderr': 'Unsupported language.',
                    'compile_output': '', 'status': 'Unsupported Language', 'status_id': 13}
        headers = {'Content-Type': 'application/json'}
        if settings.JUDGE0_AUTH_TOKEN:
            headers['X-Auth-Token'] = settings.JUDGE0_AUTH_TOKEN
        payload = {'source_code': code, 'language_id': self.LANGUAGE_IDS[language],
                   'stdin': stdin, 'cpu_time_limit': timeout, 'memory_limit': 128000,
                   'enable_network': False}
        try:
            response = requests.post(
                settings.JUDGE0_URL + '/submissions', json=payload, headers=headers,
                params={'wait': 'true', 'base64_encoded': 'false', 'fields': '*'}, timeout=15)
            if response.status_code != 201:
                raise SandboxUnavailable('Judge0 rejected the submission. Check sandbox configuration.')
            result = response.json()
            status = result.get('status', {})
            if status.get('id', 0) in (0, 1, 2, 13):
                raise SandboxUnavailable('Sandbox result is unavailable. Retry when Judge0 is ready.')
            return {'success': status.get('id') == 3,
                    'stdout': result.get('stdout') or '', 'stderr': result.get('stderr') or '',
                    'compile_output': result.get('compile_output') or '',
                    'message': result.get('message') or '', 'time': result.get('time'),
                    'memory': result.get('memory'), 'status': status.get('description', 'Unknown'),
                    'status_id': status.get('id', 0)}
        except (requests.RequestException, ValueError) as exc:
            raise SandboxUnavailable('Judge0 is unavailable. Start the configured sandbox and retry.') from exc

    def run_test_cases(self, code, language, test_cases):
        from .code_grader import smart_run_test_cases
        return smart_run_test_cases(self, code, language, test_cases)
