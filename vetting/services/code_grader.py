import ast
import re
from typing import Dict, List, Any

class CodeGrader:
    """3-Layer grading system for code evaluation"""
    
    def __init__(self):
        pass
    
    def grade(self, code: str, test_results: Dict, language: str = 'python') -> Dict:
        """
        Execute full 3-layer grading
        Returns: {
            'layer1_score': float,
            'layer2_score': float,
            'layer3_score': float or None,
            'final_score': float,
            'details': dict
        }
        """
        # Layer 1: Correctness (already computed in test_results)
        layer1_score = test_results.get('score', 0)
        
        # Layer 2: Static Analysis
        layer2_result = self._static_analysis(code, language)
        layer2_score = layer2_result['score']
        
        # Layer 3: AI Evaluation (only if Layer 1 > 60 to save costs)
        layer3_score = None
        if layer1_score > 60:
            layer3_score = self._ai_evaluation(code, test_results)
        
        # Calculate weighted final score
        final_score = (layer1_score * 0.50) + (layer2_score * 0.30)
        if layer3_score is not None:
            final_score += (layer3_score * 0.20)
        else:
            # Redistribute weights if no AI layer
            final_score = (layer1_score * 0.625) + (layer2_score * 0.375)
        
        return {
            'layer1_test_score': round(layer1_score, 2),
            'layer2_static_score': round(layer2_score, 2),
            'layer3_ai_score': round(layer3_score, 2) if layer3_score else None,
            'final_score': round(final_score, 2),
            'passed': final_score >= 70,
            'details': {
                'test_cases': test_results,
                'static_analysis': layer2_result,
                'quality_issues': layer2_result.get('issues', [])
            }
        }
    
    def _static_analysis(self, code: str, language: str) -> Dict:
        """Analyze code quality for Python"""
        if language != 'python':
            return {'score': 50, 'issues': ['Static analysis only available for Python in MVP']}
        
        score = 100
        issues = []
        
        # Initialize variables to avoid undefined errors in exception handlers
        functions = []
        comment_lines = []
        lines = code.split('\n')
        
        try:
            tree = ast.parse(code)
            
            # Check 1: Function exists and has docstring
            functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            if not functions:
                score -= 20
                issues.append("No function defined")
            else:
                main_func = functions[0]
                if not ast.get_docstring(main_func):
                    score -= 10
                    issues.append("Missing docstring")
            
            # Check 2: Function length (not too long)
            if functions:
                func = functions[0]
                lines = func.end_lineno - func.lineno if func.end_lineno else 50
                if lines > 30:
                    score -= 10
                    issues.append(f"Function too long ({lines} lines, max 30 recommended)")
            
            # Check 3: Variable naming (snake_case)
            names = [node.id for node in ast.walk(tree) if isinstance(node, ast.Name)]
            bad_names = [n for n in names if len(n) == 1 and n not in ['i', 'j', 'k', 'n', 'x', 'y']]
            if bad_names:
                score -= 5
                issues.append(f"Single letter variable names: {bad_names}")
            
            # Check 4: Imports used
            imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)]
            from_imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            
            # Check 5: List comprehensions (Pythonic)
            list_comps = [node for node in ast.walk(tree) if isinstance(node, ast.ListComp)]
            if not list_comps and any('list' in str(type(node)) for node in ast.walk(tree)):
                # Only penalize if they used loops instead of comprehensions where appropriate
                loops = [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.While))]
                if len(loops) > 0:
                    score -= 5
                    issues.append("Consider using list comprehensions instead of loops")
            
            # Check 6: Comments
            comment_lines = [l for l in lines if l.strip().startswith('#')]
            if len(comment_lines) < 1 and len(lines) > 10:
                score -= 5
                issues.append("Add comments to explain complex logic")
            
            # Check 7: Error handling
            try_blocks = [node for node in ast.walk(tree) if isinstance(node, ast.Try)]
            if not try_blocks and 'input' in code.lower():
                score -= 5
                issues.append("Consider adding error handling for input validation")
            
        except SyntaxError as e:
            score = 0
            issues.append(f"Syntax error: {str(e)}")
        except Exception as e:
            score -= 10
            issues.append(f"Analysis error: {str(e)}")
        
        return {
            'score': max(0, score),
            'issues': issues,
            'metrics': {
                'function_count': len(functions),
                'line_count': len(code.split('\n')),
                'comment_count': len(comment_lines)
            }
        }
    
    def _ai_evaluation(self, code: str, test_results: Dict) -> float:
        """
        AI Layer - Use Gemini for elegance evaluation
        Returns score 0-100
        """
        # For MVP, we'll use a heuristic-based approach instead of API call
        # to save costs. In production, replace with actual Gemini call.
        
        score = 50  # Base score
        
        # Check for Pythonic patterns
        if 'import' in code and 'from' in code:
            score += 10  # Proper imports
        
        if any(pattern in code for pattern in ['list comprehension', 'generator', 'map(', 'filter(']):
            score += 15  # Functional programming
        
        if 'class ' in code and 'def __init__' in code:
            score += 10  # OOP approach
        
        if test_results.get('score', 0) == 100:
            score += 20  # All tests passed bonus
        
        return min(100, score)
        
        # PRODUCTION VERSION (uncomment when ready to use Gemini):
        """
        try:
            prompt = f\"\"\"
            Evaluate this Python code for elegance and best practices (0-100):
            
            ```python
            {code}
            ```
            
            Consider:
            - Readability and clarity
            - Pythonic idioms
            - Algorithm efficiency
            - Code organization
            
            Return only a number between 0 and 100.
            \"\"\"
            
            # Call Gemini API here
            # response = model.generate_content(prompt)
            # return float(response.text.strip())
            
        except:
            return 50
        """