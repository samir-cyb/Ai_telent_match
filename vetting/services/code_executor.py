import requests
import json
import time
from django.conf import settings

class CodeExecutor:
    """Execute code safely using Judge0 API"""
    
    JUDGE0_URL = "http://localhost:2358"  # Docker container port
    
    LANGUAGE_IDS = {
        'python': 71,
        'javascript': 63,
        'java': 62,
        'cpp': 54
    }
    
    def __init__(self):
        self.headers = {
            "Content-Type": "application/json",
            "X-Judge0-User": "ai-talent-match"
        }
    
    def execute(self, code, language, stdin="", timeout=5):
        """
        Execute code and return results
        """
        language_id = self.LANGUAGE_IDS.get(language, 71)
        
        payload = {
            "source_code": code,
            "language_id": language_id,
            "stdin": stdin,
            "cpu_time_limit": timeout,
            "memory_limit": 128000,  # 128MB in KB
            "enable_network": False
        }
        
        try:
            # Submit code
            response = requests.post(
                f"{self.JUDGE0_URL}/submissions",
                json=payload,
                headers=self.headers,
                params={"wait": "true", "fields": "*"}
            )
            
            if response.status_code != 201:
                return {
                    'success': False,
                    'error': f"Submission failed: {response.text}",
                    'stdout': '',
                    'stderr': '',
                    'time': 0,
                    'memory': 0
                }
            
            result = response.json()
            
            # Map Judge0 status codes
            status_id = result.get('status', {}).get('id', 0)
            status_desc = result.get('status', {}).get('description', 'Unknown')
            
            # Status IDs: 1-2: In Queue/Processing, 3: Accepted, 4+: Error states
            success = status_id == 3
            
            return {
                'success': success,
                'stdout': result.get('stdout', '') or '',
                'stderr': result.get('stderr', '') or '',
                'compile_output': result.get('compile_output', '') or '',
                'message': result.get('message', ''),
                'time': result.get('time', 0),
                'memory': result.get('memory', 0),
                'status': status_desc,
                'status_id': status_id
            }
            
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': 'Cannot connect to Judge0. Is Docker running?',
                'stdout': '',
                'stderr': ''
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'stdout': '',
                'stderr': ''
            }
    
    def run_test_cases(self, code, language, test_cases):
        """
        Run multiple test cases and return detailed results
        test_cases: List of dicts with 'input' and 'expected'
        """
        results = []
        passed = 0
        
        for i, test in enumerate(test_cases):
            execution = self.execute(code, language, test.get('input', ''))
            
            # Normalize output (strip whitespace, handle newlines)
            actual = execution['stdout'].strip() if execution['stdout'] else ''
            expected = str(test.get('expected', '')).strip()
            
            test_passed = actual == expected and execution['success']
            if test_passed:
                passed += 1
            
            results.append({
                'test_number': i + 1,
                'input': test.get('input', ''),
                'expected': expected,
                'actual': actual,
                'passed': test_passed,
                'error': execution.get('error') or execution.get('stderr'),
                'execution_time': execution.get('time', 0)
            })
        
        return {
            'total': len(test_cases),
            'passed': passed,
            'failed': len(test_cases) - passed,
            'score': (passed / len(test_cases) * 100) if test_cases else 0,
            'details': results
        }