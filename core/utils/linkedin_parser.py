import json
import io
from google import genai
from google.genai import types

# Reuse the same client as resume_parser



class LinkedInParser:
    """
    Parses a LinkedIn PDF export and returns structured data.
    LinkedIn PDFs have a well-known layout: Name/Headline → Contact → About
    → Experience → Education → Skills → Certifications.

    Key difference from CV parsing:
    - We extract connection-count hint if present
    - We capture LinkedIn headline as a seniority signal
    - Output schema is richer (years_of_experience, headline, connections)
    """

    def __init__(self):
        self.model = 'gemini-2.5-flash-lite'
        self.prompt = """You are an expert at parsing LinkedIn profile PDF exports.
Extract structured information and return ONLY a raw JSON object. No markdown, no code blocks, no backticks.

Required JSON structure:
{
    "name": "Full Name or null",
    "headline": "Job title / headline from LinkedIn or null",
    "about": "Summary/About section text or null",
    "connections": null,
    "skills": [
        {"name": "Skill Name", "category": "One of: Frontend, Backend, AI/ML, DevOps, Data Science, Mobile, Cybersecurity, Design, Business, Finance, Marketing, Engineering, Research, Communication, Soft Skills, Uncategorized", "level": "Beginner|Intermediate|Expert"}
    ],
    "experiences": [
        {
            "company_name": "Company Name",
            "role": "Job Title",
            "start_date": "YYYY-MM-DD or YYYY-MM or null",
            "end_date": "YYYY-MM-DD or YYYY-MM or null",
            "is_current": false,
            "description": "Responsibilities or null",
            "duration_months": null
        }
    ],
    "education": [
        {
            "institution": "University Name",
            "degree": "BSc/MSc/etc",
            "field": "Field of study",
            "start_year": null,
            "end_year": null
        }
    ],
    "certifications": [
        {
            "name": "Certification Name",
            "issuer": "Issuing Organization",
            "year": null,
            "url": null
        }
    ],
    "total_experience_months": null
}

Rules:
- For skill level: infer from context (endorsements, job title, years). Default to Intermediate for listed skills.
- For connections: look for "connections" text near the top. Return integer or null.
- For total_experience_months: sum all work experience durations. Return integer or null.
- For dates: prefer YYYY-MM format if only month/year is given.
- is_current = true only if end_date says "Present" or is empty for the latest role.
- Respond with raw JSON only, no extra text."""

    def parse(self, file_obj):
        """Parse a LinkedIn PDF file object. Returns normalized dict."""
        try:
            print(f"[LinkedIn] Parser started for: {getattr(file_obj, 'name', 'unknown')}")
            file_obj.seek(0)
            file_bytes = file_obj.read()

            # Extract text via pdfplumber for fallback
            text_content = ""
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    for page in pdf.pages:
                        txt = page.extract_text()
                        if txt:
                            text_content += txt + "\n"
                print(f"[LinkedIn] Extracted {len(text_content)} chars via pdfplumber")
            except Exception as e:
                print(f"[LinkedIn] pdfplumber failed: {e}")

            # Try direct PDF bytes to Gemini first
            try:
                pdf_part = types.Part.from_bytes(data=file_bytes, mime_type='application/pdf')
                response = client.models.generate_content(
                    model=self.model,
                    contents=[self.prompt, pdf_part]
                )
                print("[LinkedIn] Sent PDF bytes to Gemini")
            except Exception as e:
                print(f"[LinkedIn] Direct PDF bytes failed: {e}, trying text")
                if text_content and len(text_content) > 50:
                    response = client.models.generate_content(
                        model=self.model,
                        contents=f"{self.prompt}\n\nLINKEDIN PROFILE TEXT:\n{text_content}"
                    )
                else:
                    print("[LinkedIn] No usable content")
                    return self._empty()

            print(f"[LinkedIn] Raw response (500): {response.text[:500]}")
            raw = json.loads(response.text)
            return self._normalize(raw)

        except Exception as e:
            import traceback
            print(f"[LinkedIn] Fatal error: {e}")
            print(traceback.format_exc())
            return self._empty()

    def _normalize(self, raw):
        result = {
            'name': raw.get('name'),
            'headline': raw.get('headline'),
            'about': raw.get('about'),
            'connections': raw.get('connections'),
            'total_experience_months': raw.get('total_experience_months'),
            'skills': [],
            'experiences': [],
            'education': [],
            'certifications': [],
        }

        for s in raw.get('skills', []):
            result['skills'].append({
                'name': str(s.get('name', '')).strip(),
                'category': s.get('category', 'Uncategorized'),
                'level': s.get('level', 'Intermediate'),
            })

        for e in raw.get('experiences', []):
            result['experiences'].append({
                'company_name': e.get('company_name', ''),
                'role': e.get('role', ''),
                'start_date': e.get('start_date'),
                'end_date': e.get('end_date'),
                'is_current': bool(e.get('is_current', False)),
                'description': e.get('description', ''),
                'duration_months': e.get('duration_months'),
            })

        for ed in raw.get('education', []):
            result['education'].append({
                'institution': ed.get('institution', ''),
                'degree': ed.get('degree', ''),
                'field': ed.get('field', ''),
                'start_year': ed.get('start_year'),
                'end_year': ed.get('end_year'),
            })

        for c in raw.get('certifications', []):
            result['certifications'].append({
                'name': c.get('name', ''),
                'issuer': c.get('issuer', ''),
                'year': c.get('year'),
                'url': c.get('url'),
            })

        print(f"[LinkedIn] Normalized: {len(result['skills'])} skills, "
              f"{len(result['experiences'])} experiences, "
              f"{len(result['certifications'])} certs")
        return result

    def _empty(self):
        return {
            'name': None, 'headline': None, 'about': None,
            'connections': None, 'total_experience_months': None,
            'skills': [], 'experiences': [], 'education': [], 'certifications': [],
        }


def calculate_linkedin_score(parsed_data, cross_validated_count=0, total_skills=0):
    """
    Compute a 0-100 linkedin_score from parsed LinkedIn data.

    Scoring breakdown (100 pts total):
      - Cross-validated skills (same in CV + LinkedIn): up to 35 pts
      - LinkedIn-only skills (breadth signal):          up to 15 pts
      - Work experience depth (total months):           up to 25 pts
      - Certifications:                                 up to 15 pts
      - Profile richness (headline + about + edu):      up to 10 pts
    """
    score = 0

    # Cross-validation: 35 pts — each cross-validated skill = 35/10 pts, max 35
    cv_pts = min(cross_validated_count * 3.5, 35)
    score += cv_pts

    # LinkedIn-only skills breadth: 15 pts
    linkedin_only = max(total_skills - cross_validated_count, 0)
    skill_pts = min(linkedin_only * 1.5, 15)
    score += skill_pts

    # Experience depth: 25 pts — 12 months = ~6 pts, 48+ months = 25 pts
    exp_months = parsed_data.get('total_experience_months') or 0
    if exp_months == 0:
        # Estimate from experiences list
        for exp in parsed_data.get('experiences', []):
            dm = exp.get('duration_months')
            if dm:
                exp_months += dm
            elif exp.get('is_current') and exp.get('start_date'):
                exp_months += 6  # conservative estimate
    exp_pts = min((exp_months / 48) * 25, 25)
    score += exp_pts

    # Certifications: 15 pts — each cert = 5 pts, max 3 certs counted
    cert_count = len(parsed_data.get('certifications', []))
    cert_pts = min(cert_count * 5, 15)
    score += cert_pts

    # Profile richness: 10 pts
    richness = 0
    if parsed_data.get('headline'):
        richness += 3
    if parsed_data.get('about'):
        richness += 3
    if parsed_data.get('education'):
        richness += 2
    if (parsed_data.get('connections') or 0) >= 50:
        richness += 2
    score += richness

    return min(round(score), 100)
