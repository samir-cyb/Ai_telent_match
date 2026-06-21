import json
import io
import mimetypes
from google import genai
from PIL import Image
from django.conf import settings

# Initialize the client using the modern SDK layout
client = genai.Client(api_key=settings.GEMINI_API_KEY)

class ResumeParser:
    def __init__(self):
        self.model = 'gemini-2.5-flash-lite'
        self.prompt = """You are an expert resume parser. Extract structured information from the provided resume and return ONLY a raw JSON object. Do not use markdown, code blocks, or backticks.

Required JSON structure:
{
    "name": "Full Name or null",
    "cgpa": null or float,
    "skills": [
        {"name": "Skill Name", "category": "One of: Frontend, Backend, AI/ML, Design, Soft Skills, DevOps, Data Science, Uncategorized", "level": "Beginner|Intermediate|Expert"}
    ],
    "projects": [
        {"title": "Project Title", "description": "Brief description", "tech_stack": ["Tech1", "Tech2"], "complexity": 3}
    ],
    "experiences": [
        {"company_name": "Company", "role": "Job Title", "start_date": "YYYY-MM-DD or null", "end_date": "YYYY-MM-DD or null", "is_current": false, "description": "Responsibilities"}
    ]
}

Rules:
- CGPA must be a number (float) or null. Convert percentage to 4.0 scale if needed.
- Skills level must be exactly: Beginner, Intermediate, or Expert.
- Project complexity must be an integer from 1 to 5.
- Dates must be ISO format (YYYY-MM-DD) or null.
- If a field is missing, use null or empty arrays.
- Respond with raw JSON only, no extra text."""

    def parse_resume(self, file_obj):
        try:
            print(f"[DEBUG] ResumeParser started for file: {getattr(file_obj, 'name', 'unknown')}")
            
            mime_type = getattr(file_obj, 'content_type', None)
            if not mime_type:
                mime_type, _ = mimetypes.guess_type(file_obj.name)
            print(f"[DEBUG] Detected MIME type: {mime_type}")
            
            # Handle Images (JPEG/PNG)
            if mime_type and mime_type.startswith('image/'):
                print("[DEBUG] Processing as image")
                image = Image.open(file_obj)
                response = client.models.generate_content(
                    model=self.model,
                    contents=[self.prompt, image]
                )
            
            # Handle PDFs
            else:
                print("[DEBUG] Processing as PDF/document")
                file_obj.seek(0)
                file_bytes = file_obj.read()
                
                # Debug: try text extraction
                text_content = ""
                try:
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                        for page in pdf.pages:
                            txt = page.extract_text()
                            if txt:
                                text_content += txt + "\n"
                    print(f"[DEBUG] pdfplumber extracted {len(text_content)} characters")
                except Exception as pdf_err:
                    print(f"[DEBUG] pdfplumber extraction skipped/error: {pdf_err}")
                
                # Try multimodal PDF upload via SDK
                try:
                    from google.genai import types
                    pdf_part = types.Part.from_bytes(data=file_bytes, mime_type='application/pdf')
                    response = client.models.generate_content(
                        model=self.model,
                        contents=[self.prompt, pdf_part]
                    )
                    print("[DEBUG] Sent PDF bytes directly to Gemini")
                except Exception as byte_err:
                    print(f"[DEBUG] Direct PDF bytes failed: {byte_err}")
                    # Fallback to extracted text
                    if text_content and len(text_content) > 50:
                        response = client.models.generate_content(
                            model=self.model,
                            contents=f"{self.prompt}\n\nRESUME TEXT CONTENT:\n{text_content}"
                        )
                        print("[DEBUG] Sent extracted text to Gemini")
                    else:
                        print("[DEBUG] No usable content extracted from PDF")
                        return self._empty_schema()
            
            print(f"[DEBUG] Gemini response text (first 500 chars): {response.text[:500]}")
            
            result = json.loads(response.text)
            print(f"[DEBUG] JSON parsed successfully")
            
            return self._normalize_result(result)
            
        except Exception as e:
            print(f"[DEBUG] Fatal error in parse_resume: {e}")
            import traceback
            print(traceback.format_exc())
            return self._empty_schema()
    
    def _normalize_result(self, result):
        normalized = {
            'name': result.get('name') if result.get('name') else None,
            'cgpa': float(result['cgpa']) if result.get('cgpa') is not None else None,
            'skills': [],
            'projects': [],
            'experiences': []
        }
        
        for skill in result.get('skills', []):
            normalized['skills'].append({
                'name': skill.get('name', 'Unknown'),
                'category': skill.get('category', 'Uncategorized'),
                'level': skill.get('level', 'Beginner'),
                'verified': False
            })
        
        for proj in result.get('projects', []):
            tech_stack = proj.get('tech_stack', [])
            if isinstance(tech_stack, str):
                tech_stack = [t.strip() for t in tech_stack.split(',') if t.strip()]
            normalized['projects'].append({
                'title': proj.get('title', 'Untitled'),
                'description': proj.get('description', ''),
                'tech_stack': tech_stack,
                'complexity': min(max(int(proj.get('complexity', 3)), 1), 5),
                'github_url': proj.get('github_url') if proj.get('github_url') else None,
                'verified': False
            })
        
        for exp in result.get('experiences', []):
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
        
        print(f"[DEBUG] Normalized result: {json.dumps(normalized, indent=2)}")
        return normalized
    
    def _empty_schema(self):
        return {
            'name': None,
            'cgpa': None,
            'skills': [],
            'projects': [],
            'experiences': []
        }