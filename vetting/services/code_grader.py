import ast
import re
import json
from typing import Dict, List, Any, Optional

# Gemini client reused from question_generator
from google import genai
_MODEL = 'gemini-2.5-flash-lite'


# ──────────────────────────────────────────────────────────────────────────────
# SECURITY PATTERNS
# ──────────────────────────────────────────────────────────────────────────────
_DANGEROUS_CALLS = [
    ('eval',        'HIGH',   'eval() executes arbitrary code — major security risk'),
    ('exec',        'HIGH',   'exec() executes arbitrary code — major security risk'),
    ('compile',     'MEDIUM', 'compile() with exec/eval is dangerous'),
    ('__import__',  'HIGH',   'Dynamic import can bypass restrictions'),
    ('os.system',   'HIGH',   'Shell command execution'),
    ('os.popen',    'HIGH',   'Shell command execution'),
    ('subprocess',  'MEDIUM', 'Subprocess spawning — use with care'),
    ('open(',       'LOW',    'File I/O — ensure path is safe'),
    ('socket',      'MEDIUM', 'Network access'),
    ('pickle',      'MEDIUM', 'Pickle deserialization can execute arbitrary code'),
    ('globals()',   'LOW',    'Accessing global namespace'),
    ('locals()',    'LOW',    'Accessing local namespace'),
    ('getattr',     'LOW',    'Dynamic attribute access — verify inputs'),
    ('setattr',     'LOW',    'Dynamic attribute setting — verify inputs'),
    ('delattr',     'LOW',    'Dynamic attribute deletion'),
    ('__builtins__','HIGH',   'Accessing builtins directly'),
]

_RISK_SCORE = {'HIGH': 30, 'MEDIUM': 15, 'LOW': 5}


# ──────────────────────────────────────────────────────────────────────────────
# SMART PARTIAL MATCHING
# ──────────────────────────────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    return s.strip().lower().replace('\r\n', '\n').replace('\r', '\n')


def _smart_match_score(actual: str, expected: str) -> float:
    """
    Returns 0.0 – 1.0 credit for this test case.
    1.0  = exact match (after normalization)
    0.5  = numeric near-match (within 1% relative tolerance)
    0.0  = no match
    """
    a = _normalize(actual)
    e = _normalize(expected)

    if a == e:
        return 1.0

    # Try numeric comparison
    try:
        av = float(a)
        ev = float(e)
        rel = abs(av - ev) / (abs(ev) + 1e-9)
        if rel < 0.01:       # within 1%
            return 1.0
        if rel < 0.10:       # within 10%
            return 0.5
    except ValueError:
        pass

    # Partial string overlap (student forgot trailing newline, etc.)
    if e and a.replace(' ', '') == e.replace(' ', ''):
        return 0.9  # only whitespace difference

    if e and (a in e or e in a):
        return 0.3

    return 0.0


def smart_run_test_cases(executor, code: str, language: str, test_cases: list) -> Dict:
    """Run test cases with smart partial credit scoring."""
    results = []
    total_credit = 0.0

    for i, test in enumerate(test_cases):
        execution = executor.execute(code, language, test.get('input', ''))
        actual = (execution.get('stdout') or '').strip()
        expected = str(test.get('expected', '')).strip()

        credit = _smart_match_score(actual, expected)
        passed = credit == 1.0
        if passed:
            total_credit += 1.0
        else:
            total_credit += credit

        results.append({
            'test_number': i + 1,
            'input': test.get('input', ''),
            'expected': expected,
            'actual': actual,
            'passed': passed,
            'credit': round(credit, 2),
            'error': execution.get('stderr') or execution.get('compile_output', ''),
            'execution_time': execution.get('time', 0),
            'is_public': test.get('is_public', True),
        })

    total = len(test_cases)
    score = (total_credit / total * 100) if total > 0 else 0

    return {
        'total': total,
        'passed': sum(1 for r in results if r['passed']),
        'failed': sum(1 for r in results if not r['passed']),
        'score': round(score, 2),
        'details': results,
    }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN GRADER
# ──────────────────────────────────────────────────────────────────────────────
class CodeGrader:
    """
    4-Layer grading:
      Layer 1 — Correctness (test cases, 50%)
      Layer 2 — Static quality analysis (20%)
      Layer 3 — Complexity & security scan (10%)
      Layer 4 — Gemini AI detailed review (20%)
    """

    def grade(self, code: str, test_results: Dict, language: str = 'python') -> Dict:
        layer1_score = test_results.get('score', 0)

        # Layer 2: static quality
        l2 = self._static_analysis(code, language)
        layer2_score = l2['score']

        # Layer 3: complexity + security
        l3 = self._complexity_security(code, language)
        layer3_score = l3['score']

        # Layer 4: AI review (always run — gives most value)
        l4 = self._ai_review(code, test_results, language)
        layer4_score = l4['score']

        # Weighted final
        final_score = (
            layer1_score  * 0.50 +
            layer2_score  * 0.20 +
            layer3_score  * 0.10 +
            layer4_score  * 0.20
        )

        return {
            'layer1_test_score':    round(layer1_score, 2),
            'layer2_static_score':  round(layer2_score, 2),
            'layer3_ai_score':      round(layer4_score, 2),   # kept field name for DB compat
            'final_score':          round(final_score, 2),
            'passed':               final_score >= 60,
            'details': {
                'test_cases':        test_results,
                'static_analysis':   l2,
                'quality_issues':    l2.get('issues', []),
                'complexity':        l3.get('complexity', {}),
                'security':          l3.get('security', {}),
                'ai_review':         l4,
            },
        }

    # ── LAYER 2: Static quality ───────────────────────────────────────────────
    def _static_analysis(self, code: str, language: str) -> Dict:
        if language != 'python':
            return {'score': 50, 'issues': ['Static analysis only available for Python'],
                    'metrics': {}}

        score = 100
        issues = []
        suggestions = []
        metrics = {'line_count': len(code.splitlines()),
                   'function_count': 0, 'comment_count': 0, 'has_docstring': False}

        try:
            tree = ast.parse(code)
            lines = code.splitlines()
            metrics['comment_count'] = sum(1 for l in lines if l.strip().startswith('#'))

            functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            metrics['function_count'] = len(functions)

            # 1. Function check
            if not functions:
                score -= 20
                issues.append('No function defined — wrap your solution in a function')
            else:
                fn = functions[0]
                if not ast.get_docstring(fn):
                    score -= 10
                    issues.append('Missing docstring on main function')
                else:
                    metrics['has_docstring'] = True

                fn_len = (fn.end_lineno or fn.lineno) - fn.lineno
                metrics['function_length'] = fn_len
                if fn_len > 40:
                    score -= 10
                    issues.append(f'Function is {fn_len} lines — consider splitting into helpers')

            # 2. Type hints
            if functions:
                fn = functions[0]
                if not fn.returns and not fn.args.annotations:
                    score -= 5
                    suggestions.append('Add type hints: def solve(data: list) -> dict')

            # 3. Variable naming
            names = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
            bad = [n for n in set(names)
                   if len(n) == 1 and n not in ('i', 'j', 'k', 'n', 'x', 'y', 'e')]
            if bad:
                score -= 5
                issues.append(f'Non-descriptive variable names: {bad[:4]}')

            # 4. Comments
            if metrics['comment_count'] < 1 and metrics['line_count'] > 8:
                score -= 5
                suggestions.append('Add inline comments explaining your logic')

            # 5. Error handling
            try_blocks = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
            if not try_blocks:
                suggestions.append('Consider adding try/except for robustness')

            # 6. Pythonic bonus
            list_comps = [n for n in ast.walk(tree) if isinstance(n, ast.ListComp)]
            gen_exps   = [n for n in ast.walk(tree) if isinstance(n, ast.GeneratorExp)]
            if list_comps or gen_exps:
                pass  # no penalty — using comprehensions is good

        except SyntaxError as e:
            score = 0
            issues.append(f'Syntax error: {e}')
        except Exception as e:
            score -= 10
            issues.append(f'Analysis error: {e}')

        return {
            'score': max(0, score),
            'issues': issues,
            'suggestions': suggestions,
            'metrics': metrics,
        }

    # ── LAYER 3: Complexity + Security ───────────────────────────────────────
    def _complexity_security(self, code: str, language: str) -> Dict:
        score = 100
        complexity = {}
        security = {'risks': [], 'risk_level': 'SAFE'}
        issues = []

        if language != 'python':
            return {'score': 70, 'complexity': {}, 'security': {'risks': [], 'risk_level': 'N/A'},
                    'issues': []}

        # ── Security scan ────────────────────────────────────────────────────
        total_risk_deduction = 0
        for pattern, level, msg in _DANGEROUS_CALLS:
            if pattern in code:
                security['risks'].append({'pattern': pattern, 'level': level, 'message': msg})
                total_risk_deduction += _RISK_SCORE[level]

        if total_risk_deduction >= 30:
            security['risk_level'] = 'HIGH'
        elif total_risk_deduction >= 15:
            security['risk_level'] = 'MEDIUM'
        elif total_risk_deduction > 0:
            security['risk_level'] = 'LOW'
        else:
            security['risk_level'] = 'SAFE'

        score -= min(total_risk_deduction, 50)

        # ── Complexity analysis ──────────────────────────────────────────────
        try:
            tree = ast.parse(code)

            # Count nesting depth of loops
            def max_loop_depth(node, depth=0):
                if isinstance(node, (ast.For, ast.While)):
                    depth += 1
                children = [max_loop_depth(c, depth) for c in ast.iter_child_nodes(node)]
                return max([depth] + children) if children else depth

            loop_depth = max_loop_depth(tree)

            # Estimate Big-O
            if loop_depth == 0:
                big_o = 'O(1) or O(log n)'
                complexity_rating = 'Excellent'
            elif loop_depth == 1:
                big_o = 'O(n)'
                complexity_rating = 'Good'
            elif loop_depth == 2:
                big_o = 'O(n²)'
                complexity_rating = 'Acceptable'
                score -= 5
                issues.append('Nested loops detected — O(n²) — consider optimising')
            else:
                big_o = f'O(n^{loop_depth}) or worse'
                complexity_rating = 'Poor'
                score -= 15
                issues.append(f'{loop_depth}-level nested loops detected — high complexity')

            # Recursion check
            has_recursion = False
            functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
            for fn in functions:
                calls = [n.func.id for n in ast.walk(fn)
                         if isinstance(n, ast.Call) and hasattr(n.func, 'id')]
                if fn.name in calls:
                    has_recursion = True

            complexity = {
                'big_o': big_o,
                'loop_depth': loop_depth,
                'has_recursion': has_recursion,
                'rating': complexity_rating,
            }

        except SyntaxError:
            complexity = {'big_o': 'N/A', 'rating': 'Syntax Error', 'loop_depth': 0,
                          'has_recursion': False}
        except Exception as e:
            complexity = {'big_o': 'N/A', 'rating': 'Analysis Error', 'loop_depth': 0,
                          'has_recursion': False}

        return {
            'score': max(0, score),
            'complexity': complexity,
            'security': security,
            'issues': issues,
        }

    # ── LAYER 4: Gemini AI Review ─────────────────────────────────────────────
    def _ai_review(self, code: str, test_results: Dict, language: str = 'python') -> Dict:
        passed_pct = test_results.get('score', 0)
        test_details = test_results.get('details', [])
        failed_tests = [t for t in test_details if not t.get('passed')]

        prompt = f"""
You are a senior {language} engineer conducting a code review for a hiring assessment.

=== SUBMITTED CODE ===
```{language}
{code}
```

=== TEST RESULTS ===
Score: {passed_pct}%
Failed tests: {len(failed_tests)} / {len(test_details)}
{chr(10).join(f"- Input: {t['input']!r} | Expected: {t['expected']!r} | Got: {t['actual']!r}" for t in failed_tests[:3]) if failed_tests else "All public tests passed!"}

=== YOUR TASK ===
Write a concise but insightful code review. Return ONLY raw JSON:
{{
  "score": <integer 0-100>,
  "summary": "2-3 sentence overall assessment of the candidate's solution",
  "strengths": ["specific strength 1", "specific strength 2"],
  "weaknesses": ["specific weakness 1"],
  "suggestions": ["actionable improvement 1", "actionable improvement 2"],
  "verdict": "Hire" | "Consider" | "Reject"
}}

Scoring guide:
- 80-100: Elegant, efficient, well-structured, passes tests
- 60-79: Correct approach with minor issues
- 40-59: Partially correct or poor code quality
- 0-39: Incorrect logic or very poor code
"""

        try:
            resp = _client.models.generate_content(model=_MODEL, contents=prompt)
            text = resp.text
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            result = json.loads(text.strip())
            return {
                'score':       max(0, min(int(result.get('score', 50)), 100)),
                'summary':     result.get('summary', ''),
                'strengths':   result.get('strengths', []),
                'weaknesses':  result.get('weaknesses', []),
                'suggestions': result.get('suggestions', []),
                'verdict':     result.get('verdict', 'Consider'),
            }
        except Exception as e:
            print(f'[Grader] AI review failed: {e}')
            # Heuristic fallback
            score = 40
            if passed_pct == 100: score = 80
            elif passed_pct >= 60: score = 60
            return {
                'score': score,
                'summary': 'AI review unavailable — score based on test results and code structure.',
                'strengths': ['Code submitted successfully'],
                'weaknesses': ['Could not run AI analysis'],
                'suggestions': ['Ensure code handles edge cases', 'Add comments and docstrings'],
                'verdict': 'Consider' if passed_pct >= 50 else 'Reject',
            }
