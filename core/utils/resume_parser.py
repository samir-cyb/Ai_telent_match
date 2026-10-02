import json
import io
import mimetypes
from google import genai
from PIL import Image
from core.utils.llm_client import llm_generate as _llm_generate, llm_generate_image as _llm_generate_image

# Gemini client — kept for multimodal (image/PDF bytes) calls



class ResumeParser:
    def __init__(self):
        self.model = 'gemini-3.5-flash-lite'
        self.prompt = """You are an expert resume parser. Extract structured information from the provided resume and return ONLY a raw JSON object. Do not use markdown, code blocks, or backticks.

Required JSON structure:
{
    "name": "Full Name or null",
    "cgpa": null or float,
    "skills": [
        {"name": "Skill Name", "category": "One of: Frontend, Backend, AI/ML, Design, Soft Skills, DevOps, Data Science, Uncategorized", "level": "Beginner|Intermediate|Expert"}
    ],
    "projects": [
        {"title": "Project Title", "description": "Brief description", "tech_stack": ["Tech1", "Tech2"], "complexity": 3, "github_url": null}
    ],
    "experiences": [
        {"company_name": "Company", "role": "Job Title", "start_date": "YYYY-MM-DD or null", "end_date": "YYYY-MM-DD or null", "is_current": false, "description": "Responsibilities"}
    ]
}

SKILL LEVEL RULES (very important — do NOT default everything to Beginner):
- Expert: Used professionally or in research/internships, published papers, led projects with this tech, 2+ years using it, or it's a core skill clearly demonstrated across multiple projects/experiences.
- Intermediate: Used in multiple projects, internship experience, or self-taught with clear practical output.
- Beginner: Only mentioned once, only in coursework, or no evidence of real usage.
- If the candidate has INTERNSHIP experience with a tech → at least Intermediate.
- If the candidate has RESEARCH PAPERS using a tech → Expert for that tech.
- If a tech appears across 3+ projects → at least Intermediate.
- If Python/ML is core to their work and they have internships + research → Expert.

PROJECT TECH STACK RULES (very important — do NOT leave tech_stack empty):
- For EVERY project, list ALL technologies used, even if not explicitly listed — infer from project type:
  - "Chatbot", "Medical Chatbot", "NLP", "conversational AI" → include: Python, NLP, likely TensorFlow or PyTorch, possibly LangChain
  - "RAG", "Retrieval", "LLM", "GPT", "Vector" → include: Python, LangChain or LlamaIndex, OpenAI or HuggingFace, FAISS or Pinecone
  - "Computer Vision", "Image Detection", "Object Detection" → include: Python, OpenCV, TensorFlow or PyTorch
  - "Machine Learning", "Deep Learning", "Neural Network", "MARL", "Reinforcement Learning" → include: Python, TensorFlow or PyTorch, scikit-learn
  - "Web App", "Dashboard" → include obvious framework (Django/Flask/React etc.)
  - "Robotic Arm", "Robotics" → include: Python, ROS or Arduino, relevant sensors
  - "Transportation", "Prediction", "Classification" → include: Python, scikit-learn, Pandas
  - Always include the PRIMARY LANGUAGE even if only implied.
- Project complexity (1-5):
  1=simple script/tutorial, 2=basic app, 3=moderate (APIs/DB/ML model), 4=advanced (multi-component/real-world), 5=research-grade/novel system

GENERAL RULES:
- CGPA must be a number (float) or null. Convert percentage to 4.0 scale if needed (divide by 25).
- Dates must be ISO format (YYYY-MM-DD) or null.
- If a field is missing, use null or empty arrays.
- Respond with raw JSON only, no extra text, no markdown, no backticks."""

    def parse_resume(self, file_obj):
        """Return structured data or an explicit failure; never an empty success."""
        try:
            file_obj.seek(0)
            file_bytes = file_obj.read()
            mime_type = getattr(file_obj, 'content_type', None) or 'application/pdf'
            if file_bytes.startswith(b'%PDF-'):
                mime_type = 'application/pdf'
            response_text = None
            try:
                response_text = _llm_generate_image(self.prompt, file_bytes, mime_type=mime_type)
            except Exception:
                if mime_type != 'application/pdf':
                    raise
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    content = '\n'.join(page.extract_text() or '' for page in pdf.pages)
                if len(content.strip()) > 50:
                    response_text = _llm_generate(self.prompt + '\nDOCUMENT TEXT:\n' + content)
            if not response_text:
                return self._empty_schema()
            text = response_text.strip()
            if text.startswith('```'):
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
            raw = json.loads(text.strip())
            if not isinstance(raw, dict) or not any(raw.get(k) for k in ('name', 'skills', 'projects', 'experiences', 'education')):
                return self._empty_schema()
            result = self._normalize_result(raw)
            result['parse_status'] = 'success'
            return result
        except Exception:
            return self._empty_schema()

    
    def _normalize_result(self, result):
        normalized = {
            'name': result.get('name') if result.get('name') else None,
            'cgpa': float(result['cgpa']) if result.get('cgpa') is not None else None,
            'skills': [],
            'projects': [],
            'experiences': []
        }
        
        for skill in (result.get('skills') or []):
            normalized['skills'].append({
                'name': skill.get('name', 'Unknown'),
                'category': skill.get('category', 'Uncategorized'),
                'level': skill.get('level', 'Beginner'),
                'verified': False
            })
        
        for proj in (result.get('projects') or []):
            tech_stack = proj.get('tech_stack') or []
            if isinstance(tech_stack, str):
                tech_stack = [t.strip() for t in tech_stack.split(',') if t.strip()]
            normalized['projects'].append({
                'title': proj.get('title', 'Untitled'),
                'description': proj.get('description', ''),
                'tech_stack': tech_stack,
                'complexity': min(max(int(3 if proj.get('complexity') is None else proj['complexity']), 1), 5),
                'github_url': proj.get('github_url') if proj.get('github_url') else None,
                'verified': False
            })
        
        for exp in (result.get('experiences') or []):
            start = exp.get('start_date')
            end = exp.get('end_date')
            is_current = bool(exp.get('is_current', False))
            
            if is_current:
                duration = f"{start} to Present" if start else "Present"
            else:
                duration = f"{start} to {end}" if start and end else (start or "Unknown")
            
            normalized['experiences'].append({
                'company': exp.get('company_name', ''),
                'role': exp.get('role', ''),
                'duration': duration,
                'start_date': start,
                'end_date': end,
                'is_current': is_current,
                'description': exp.get('description', ''),
                'verified': False
            })
        
        return normalized
    
    def _empty_schema(self):
        return {
            'parse_status': 'failed',
            'error': 'Document could not be parsed. Check the AI provider and try again; existing profile data is preserved.',
            'name': None,
            'cgpa': None,
            'skills': [],
            'projects': [],
            'experiences': []
        }