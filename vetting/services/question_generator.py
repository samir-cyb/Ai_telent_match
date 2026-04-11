import json
import google.generativeai as genai
from django.conf import settings

# Configure Gemini
genai.configure(api_key='AIzaSyA3wGaElzQirAxAD-BK6LCQjJtFJe6DZlU')

class QuestionGenerator:
    """Generate coding challenges using Gemini API"""
    
    LANGUAGE_IDS = {
        'python': 71,
        'javascript': 63,
        'java': 62,
        'cpp': 54
    }
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-pro')
    
    def generate_challenge(self, job, difficulty='medium'):
        """
        Generate a coding challenge based on job requirements
        """
        skills = [s.name for s in job.required_skills.all()]
        skills_str = ', '.join(skills)
        
        prompt = f"""
        Create a coding challenge for a job: {job.title}
        Required Skills: {skills_str}
        Difficulty: {difficulty}
        
        Generate a JSON object with the following structure:
        {{
            "title": "Specific challenge title",
            "description": "Detailed problem description with examples",
            "starter_code": "Python function template with TODO comments",
            "test_cases": [
                {{"input": "function_input_1", "expected": "expected_output_1", "is_public": true}},
                {{"input": "function_input_2", "expected": "expected_output_2", "is_public": false}},
                {{"input": "function_input_3", "expected": "expected_output_3", "is_public": false}}
            ],
            "skill_tags": ["relevant", "skill", "tags"],
            "language": "python",
            "hints": ["hint1", "hint2"]
        }}
        
        Constraints:
        - Must be solvable in 45 minutes
        - Must test practical {skills_str} knowledge
        - Include 2 public test cases (visible to candidate) and 2-3 hidden test cases
        - Starter code should have clear function signature and docstring
        - For Python, use type hints where appropriate
        - Make it a real-world scenario, not abstract algorithm
        """
        
        try:
            response = self.model.generate_content(prompt)
            text = response.text
            
            # Extract JSON from markdown if present
            if '```json' in text:
                text = text.split('```json')[1].split('```')[0]
            elif '```' in text:
                text = text.split('```')[1].split('```')[0]
            
            data = json.loads(text.strip())
            
            # Validate structure
            required_keys = ['title', 'description', 'starter_code', 'test_cases']
            for key in required_keys:
                if key not in data:
                    raise ValueError(f"Missing key: {key}")
            
            return data
            
        except Exception as e:
            # Fallback challenge if AI fails
            return self._get_fallback_challenge(job, skills_str)
    
    def _get_fallback_challenge(self, job, skills_str):
        """Default challenge if Gemini fails"""
        return {
            "title": f"Data Processing Challenge for {job.title}",
            "description": """
            Write a function `process_data(data: List[Dict]) -> Dict` that processes a list of records.
            
            Requirements:
            - Filter out records where 'active' is False
            - Calculate average of 'score' field
            - Return dict with 'count', 'average_score', and 'top_performer' (name with highest score)
            
            Example:
            Input: [{'name': 'Alice', 'score': 85, 'active': True}, {'name': 'Bob', 'score': 90, 'active': False}]
            Output: {'count': 1, 'average_score': 85.0, 'top_performer': 'Alice'}
            """,
            "starter_code": """
from typing import List, Dict

def process_data(data: List[Dict]) -> Dict:
    \"\"\"
    Process data records and return statistics.
    
    Args:
        data: List of dictionaries containing 'name', 'score', and 'active' keys
        
    Returns:
        Dictionary with count, average_score, and top_performer
    \"\"\"
    # TODO: Implement your solution here
    pass
            """.strip(),
            "test_cases": [
                {"input": "[{'name': 'Alice', 'score': 85, 'active': True}, {'name': 'Bob', 'score': 90, 'active': False}]", 
                 "expected": "{'count': 1, 'average_score': 85.0, 'top_performer': 'Alice'}", 
                 "is_public": True},
                {"input": "[]", 
                 "expected": "{'count': 0, 'average_score': 0.0, 'top_performer': None}", 
                 "is_public": False}
            ],
            "skill_tags": ["python", "data-processing", "list-comprehension"],
            "language": "python",
            "hints": ["Use list comprehension to filter", "Use max() with key parameter"]
        }