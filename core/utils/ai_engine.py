import logging
import numpy as np
from datetime import datetime, timedelta
from django.db.models import Avg, Count
from core.models import AIFeedbackLog, Application, Job, Student, StudentSkill, MatchExplanation, Skill, StudentBehaviorLog
from django.utils import timezone

logger = logging.getLogger('ai_engine')

# Default matching weights per department category.
# Trust weight increased (signal is now meaningful).
# Activity weight reduced (was easy to farm before; now computed dynamically).
# Company custom_weights always override these via merge (see __init__).
DEPARTMENT_DEFAULT_WEIGHTS = {
    'tech': {
        # Skills dominate; trust now meaningful (GitHub + vetting tests)
        'skills': 0.42, 'cgpa': 0.15, 'projects': 0.25,
        'activity': 0.06, 'trust': 0.12,
    },
    'engineering': {
        'skills': 0.37, 'cgpa': 0.25, 'projects': 0.22,
        'activity': 0.04, 'trust': 0.12,
    },
    'business': {
        # LinkedIn + ECA now power trust, so trust gets more weight
        'skills': 0.25, 'cgpa': 0.22, 'projects': 0.10,
        'activity': 0.18, 'trust': 0.25,
    },
    'design': {
        # Portfolio/Behance in trust; activity somewhat relevant
        'skills': 0.20, 'cgpa': 0.10, 'projects': 0.42,
        'activity': 0.12, 'trust': 0.16,
    },
    'science': {
        # Research papers feed trust; activity least important
        'skills': 0.30, 'cgpa': 0.33, 'projects': 0.20,
        'activity': 0.03, 'trust': 0.14,
    },
    'humanities': {
        # LinkedIn + ECA in trust; activity still relevant
        'skills': 0.20, 'cgpa': 0.22, 'projects': 0.10,
        'activity': 0.25, 'trust': 0.23,
    },
    'any': {
        'skills': 0.37, 'cgpa': 0.18, 'projects': 0.20,
        'activity': 0.12, 'trust': 0.13,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# IMPLICIT KNOWLEDGE MAP
# Keys   : lowercase skill/technology name (matches project.tech_stack entries)
# Values : list of lower-case skills that are *implied* by knowing this tech.
#          These count as partial credit (×0.5) when matching job requirements.
#
# Covers TWO worlds:
#   TECH    — Mobile, Frontend, Backend, Data/ML, DB, DevOps, Systems, Game
#   NON-TECH— Business, Design/Creative, Research/Science/Humanities, HR
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_TECH_IMPLIES = {
    # ── MOBILE ───────────────────────────────────────────────────────────────
    'flutter':          ['dart', 'firebase', 'sqlite', 'rest api', 'mobile development',
                         'state management', 'android', 'ios'],
    'dart':             ['flutter', 'mobile development', 'object-oriented programming'],
    'react native':     ['javascript', 'mobile development', 'rest api', 'redux',
                         'expo', 'android', 'ios'],
    'android':          ['java', 'kotlin', 'sqlite', 'rest api', 'mobile development', 'gradle'],
    'kotlin':           ['android', 'java', 'mobile development', 'object-oriented programming'],
    'swift':            ['ios', 'mobile development', 'xcode', 'rest api', 'objective-c'],
    'ios':              ['swift', 'objective-c', 'xcode', 'mobile development', 'rest api'],
    'objective-c':      ['ios', 'swift', 'mobile development', 'xcode'],

    # ── FRONTEND ──────────────────────────────────────────────────────────────
    'react':            ['javascript', 'html', 'css', 'rest api', 'frontend development',
                         'jsx', 'redux', 'typescript'],
    'vue':              ['javascript', 'html', 'css', 'frontend development', 'vuex'],
    'vue.js':           ['javascript', 'html', 'css', 'frontend development', 'vuex'],
    'angular':          ['typescript', 'javascript', 'html', 'css', 'frontend development', 'rxjs'],
    'next.js':          ['react', 'javascript', 'typescript', 'html', 'css', 'rest api', 'frontend development'],
    'nuxt.js':          ['vue.js', 'javascript', 'html', 'css', 'frontend development'],
    'svelte':           ['javascript', 'html', 'css', 'frontend development'],
    'javascript':       ['html', 'css', 'frontend development', 'rest api', 'node.js'],
    'typescript':       ['javascript', 'html', 'css', 'frontend development', 'object-oriented programming'],
    'html':             ['css', 'frontend development', 'javascript'],
    'css':              ['html', 'frontend development', 'javascript'],
    'bootstrap':        ['css', 'html', 'frontend development', 'javascript'],
    'tailwind':         ['css', 'html', 'frontend development'],
    'tailwindcss':      ['css', 'html', 'frontend development'],

    # ── BACKEND ───────────────────────────────────────────────────────────────
    'django':           ['python', 'postgresql', 'sqlite', 'rest api', 'backend development',
                         'html', 'css', 'orm'],
    'flask':            ['python', 'rest api', 'backend development', 'sqlite', 'jinja2'],
    'fastapi':          ['python', 'rest api', 'backend development', 'async programming', 'pydantic'],
    'node.js':          ['javascript', 'express', 'rest api', 'backend development', 'mongodb'],
    'express':          ['javascript', 'node.js', 'rest api', 'backend development'],
    'express.js':       ['javascript', 'node.js', 'rest api', 'backend development'],
    'spring boot':      ['java', 'postgresql', 'rest api', 'backend development', 'maven', 'microservices'],
    'spring':           ['java', 'rest api', 'backend development', 'maven'],
    'laravel':          ['php', 'mysql', 'rest api', 'backend development', 'mvc'],
    'codeigniter':      ['php', 'mysql', 'backend development', 'mvc'],
    'ruby on rails':    ['ruby', 'postgresql', 'rest api', 'backend development', 'mvc'],
    'asp.net':          ['c#', 'sql server', 'rest api', 'backend development', 'mvc'],
    '.net':             ['c#', 'sql server', 'rest api', 'backend development'],
    'graphql':          ['rest api', 'backend development', 'api design'],
    'grpc':             ['microservices', 'backend development', 'protobuf'],
    'rest api':         ['backend development', 'json', 'http', 'api design'],

    # ── DATA / ML / AI ───────────────────────────────────────────────────────
    'tensorflow':       ['python', 'machine learning', 'numpy', 'pandas', 'data science',
                         'deep learning', 'keras'],
    'pytorch':          ['python', 'machine learning', 'numpy', 'deep learning', 'data science'],
    'keras':            ['tensorflow', 'python', 'machine learning', 'deep learning'],
    'scikit-learn':     ['python', 'machine learning', 'numpy', 'pandas', 'data science'],
    'pandas':           ['python', 'data analysis', 'numpy', 'data science'],
    'numpy':            ['python', 'data analysis', 'data science', 'mathematics'],
    'matplotlib':       ['python', 'data visualization', 'data analysis', 'numpy'],
    'seaborn':          ['python', 'data visualization', 'pandas', 'statistics'],
    'machine learning': ['python', 'data science', 'statistics', 'numpy', 'pandas', 'algorithms'],
    'deep learning':    ['python', 'tensorflow', 'pytorch', 'machine learning', 'mathematics'],
    'data science':     ['python', 'statistics', 'data analysis', 'machine learning', 'numpy', 'pandas'],
    'nlp':              ['python', 'machine learning', 'data science', 'transformers'],
    'computer vision':  ['python', 'opencv', 'deep learning', 'tensorflow', 'pytorch'],
    'opencv':           ['python', 'computer vision', 'image processing'],
    'r':                ['data analysis', 'statistics', 'data science', 'ggplot2'],
    'matlab':           ['data analysis', 'signal processing', 'embedded systems', 'mathematics'],
    'jupyter':          ['python', 'data science', 'data analysis', 'numpy', 'pandas'],

    # ── DATABASES ─────────────────────────────────────────────────────────────
    'postgresql':       ['sql', 'database design', 'backend development', 'orm'],
    'mysql':            ['sql', 'database design', 'backend development'],
    'mongodb':          ['nosql', 'database design', 'backend development', 'json'],
    'sqlite':           ['sql', 'database design'],
    'redis':            ['caching', 'backend development', 'nosql'],
    'firebase':         ['nosql', 'real-time database', 'mobile development', 'cloud computing'],
    'sql':              ['database design', 'data analysis', 'postgresql', 'mysql', 'backend development'],
    'nosql':            ['mongodb', 'database design', 'backend development'],
    'elasticsearch':    ['nosql', 'backend development', 'search', 'data analysis'],

    # ── DEVOPS / CLOUD ────────────────────────────────────────────────────────
    'docker':           ['linux', 'devops', 'shell scripting', 'containerization'],
    'kubernetes':       ['docker', 'devops', 'linux', 'cloud computing', 'containerization'],
    'aws':              ['cloud computing', 'devops', 'linux', 's3', 'ec2'],
    'gcp':              ['cloud computing', 'devops', 'linux', 'google cloud'],
    'azure':            ['cloud computing', 'devops', 'linux', 'microsoft'],
    'linux':            ['shell scripting', 'devops', 'bash', 'command line'],
    'bash':             ['linux', 'shell scripting', 'devops'],
    'shell scripting':  ['linux', 'bash', 'devops', 'automation'],
    'ci/cd':            ['devops', 'git', 'automation', 'docker'],
    'github actions':   ['ci/cd', 'devops', 'git', 'automation'],
    'jenkins':          ['ci/cd', 'devops', 'automation'],
    'terraform':        ['devops', 'cloud computing', 'infrastructure as code'],
    'git':              ['version control', 'github', 'collaboration'],

    # ── SYSTEMS / EMBEDDED / HARDWARE ──────────────────────────────────────
    'c++':              ['object-oriented programming', 'data structures', 'algorithms',
                         'embedded systems', 'systems programming', 'memory management'],
    'c':                ['embedded systems', 'systems programming', 'algorithms',
                         'data structures', 'memory management'],
    'embedded systems': ['c', 'c++', 'iot', 'microcontrollers', 'circuit design', 'rtos'],
    'arduino':          ['c++', 'embedded systems', 'iot', 'electronics', 'circuit design'],
    'raspberry pi':     ['python', 'linux', 'iot', 'embedded systems', 'electronics'],
    'iot':              ['c', 'c++', 'embedded systems', 'networking', 'sensors'],
    'rtos':             ['c', 'embedded systems', 'real-time systems', 'microcontrollers'],
    'verilog':          ['digital electronics', 'fpga', 'circuit design', 'hardware design'],
    'vhdl':             ['digital electronics', 'fpga', 'circuit design', 'hardware design'],
    'fpga':             ['verilog', 'vhdl', 'digital electronics', 'hardware design'],
    'circuit design':   ['electronics', 'embedded systems', 'matlab', 'pcb design'],
    'microcontrollers': ['c', 'embedded systems', 'iot', 'electronics'],

    # ── GAME DEVELOPMENT ─────────────────────────────────────────────────────
    'unity':            ['c#', 'game development', '3d graphics', 'physics simulation',
                         'animation', 'shader programming'],
    'unreal engine':    ['c++', 'game development', '3d graphics', 'blueprint scripting',
                         'physics simulation'],
    'game development': ['c++', 'mathematics', 'physics simulation', '3d graphics', 'algorithms'],
    'c#':               ['object-oriented programming', 'unity', '.net', 'backend development'],
    'opengl':           ['c++', '3d graphics', 'shader programming', 'graphics programming'],
    'webgl':            ['javascript', '3d graphics', 'shader programming', 'frontend development'],

    # ── MOBILE-CROSS PLATFORM ─────────────────────────────────────────────────
    'xamarin':          ['c#', 'mobile development', 'rest api', 'android', 'ios'],
    'ionic':            ['javascript', 'typescript', 'mobile development', 'angular', 'rest api'],
    'capacitor':        ['javascript', 'mobile development', 'web development'],

    # ─── BLOCKCHAIN / WEB3 ────────────────────────────────────────────────────
    'solidity':         ['blockchain', 'ethereum', 'smart contracts', 'web3', 'javascript'],
    'blockchain':       ['solidity', 'cryptography', 'distributed systems', 'web3'],
    'web3':             ['blockchain', 'javascript', 'solidity', 'ethereum'],

    # ═══════════════════════════════════════════════════════════════════════════
    # NON-TECH BACKGROUND
    # ═══════════════════════════════════════════════════════════════════════════

    # ── BUSINESS / MANAGEMENT ────────────────────────────────────────────────
    'marketing':        ['digital marketing', 'content creation', 'social media',
                         'market research', 'analytics', 'brand management'],
    'digital marketing':['seo', 'social media', 'content creation', 'google analytics',
                         'email marketing', 'ppc', 'analytics'],
    'seo':              ['digital marketing', 'content creation', 'google analytics', 'writing'],
    'social media':     ['content creation', 'digital marketing', 'analytics', 'communication'],
    'content creation': ['writing', 'social media', 'digital marketing', 'video editing',
                         'storytelling'],
    'market research':  ['data analysis', 'strategic planning', 'microsoft excel',
                         'statistics', 'presentation', 'report writing'],
    'business plan':    ['strategic planning', 'financial modeling', 'market research',
                         'presentation', 'microsoft excel', 'communication'],
    'financial modeling':['microsoft excel', 'data analysis', 'accounting',
                          'financial analysis', 'statistics'],
    'financial analysis':['accounting', 'microsoft excel', 'data analysis',
                          'financial modeling', 'reporting'],
    'excel':            ['data analysis', 'microsoft office', 'financial modeling',
                         'reporting', 'spreadsheets'],
    'microsoft excel':  ['data analysis', 'microsoft office', 'financial modeling',
                         'reporting', 'spreadsheets'],
    'microsoft office': ['microsoft excel', 'microsoft word', 'presentation',
                         'microsoft powerpoint', 'productivity'],
    'accounting':       ['financial analysis', 'microsoft excel', 'bookkeeping',
                         'reporting', 'auditing'],
    'sales':            ['crm', 'communication', 'negotiation', 'customer relationship',
                         'business development'],
    'crm':              ['sales', 'customer relationship', 'communication', 'data analysis'],
    'business development': ['sales', 'market research', 'strategic planning',
                              'communication', 'negotiation'],
    'project management':   ['leadership', 'communication', 'strategic planning',
                              'team management', 'risk management', 'agile'],
    'agile':            ['project management', 'scrum', 'team management', 'communication'],
    'scrum':            ['agile', 'project management', 'team management'],
    'leadership':       ['team management', 'communication', 'strategic planning',
                         'project management', 'decision making'],
    'communication':    ['presentation', 'writing', 'interpersonal skills',
                         'public speaking', 'reporting'],
    'negotiation':      ['communication', 'sales', 'business development', 'conflict resolution'],
    'strategic planning':   ['market research', 'business development', 'financial modeling',
                              'leadership', 'decision making'],
    'operations management': ['process improvement', 'supply chain', 'logistics',
                               'project management', 'lean management'],
    'supply chain':     ['logistics', 'operations management', 'procurement', 'data analysis'],
    'logistics':        ['supply chain', 'operations management', 'procurement'],

    # ── DESIGN / CREATIVE ───────────────────────────────────────────────────
    'figma':            ['ui/ux', 'prototyping', 'user research', 'design systems',
                         'wireframing', 'interaction design'],
    'adobe xd':         ['ui/ux', 'prototyping', 'wireframing', 'user research'],
    'ui/ux':            ['figma', 'adobe xd', 'prototyping', 'user research',
                         'wireframing', 'interaction design', 'usability testing'],
    'ux design':        ['figma', 'user research', 'prototyping', 'wireframing',
                         'usability testing', 'interaction design'],
    'ui design':        ['figma', 'adobe xd', 'design systems', 'typography',
                         'color theory', 'visual design'],
    'adobe photoshop':  ['graphic design', 'photo editing', 'visual design',
                         'adobe creative suite', 'image editing'],
    'adobe illustrator':['graphic design', 'vector design', 'visual design',
                         'adobe creative suite', 'logo design', 'typography'],
    'adobe indesign':   ['graphic design', 'print design', 'typography',
                         'layout design', 'adobe creative suite'],
    'graphic design':   ['adobe photoshop', 'adobe illustrator', 'visual design',
                         'typography', 'color theory', 'brand design'],
    'video editing':    ['adobe premiere', 'after effects', 'storytelling',
                         'content creation', 'motion graphics'],
    'adobe premiere':   ['video editing', 'after effects', 'content creation',
                         'storytelling', 'color grading'],
    'after effects':    ['motion graphics', 'video editing', 'animation',
                         'adobe premiere', 'visual effects'],
    'photography':      ['photo editing', 'adobe lightroom', 'visual storytelling',
                         'adobe photoshop', 'composition'],
    'adobe lightroom':  ['photo editing', 'photography', 'color grading'],
    'motion graphics':  ['after effects', 'video editing', 'animation', 'visual design'],
    'branding':         ['graphic design', 'logo design', 'visual identity',
                         'typography', 'marketing'],
    'logo design':      ['graphic design', 'adobe illustrator', 'branding', 'typography'],
    '3d modeling':      ['blender', 'maya', '3d design', 'rendering', 'animation'],
    'blender':          ['3d modeling', '3d design', 'animation', 'rendering'],
    'autocad':          ['engineering drawing', 'cad design', 'technical drawing', 'mechanical design'],
    'solidworks':       ['3d modeling', 'cad design', 'mechanical design', 'product design'],

    # ── RESEARCH / SCIENCE / HUMANITIES ─────────────────────────────────────
    'research':         ['data analysis', 'academic writing', 'literature review',
                         'statistics', 'methodology', 'critical thinking'],
    'data analysis':    ['statistics', 'microsoft excel', 'python', 'reporting',
                         'data visualization', 'sql'],
    'statistics':       ['data analysis', 'r', 'microsoft excel', 'research',
                         'probability', 'data science'],
    'academic writing': ['research', 'literature review', 'communication',
                         'writing', 'critical analysis'],
    'writing':          ['communication', 'content creation', 'research',
                         'editing', 'storytelling'],
    'journalism':       ['writing', 'research', 'communication', 'interviewing',
                         'content creation', 'editing'],
    'economics':        ['data analysis', 'statistics', 'financial analysis',
                         'microsoft excel', 'market research', 'econometrics'],
    'econometrics':     ['statistics', 'data analysis', 'r', 'economics', 'python'],
    'public policy':    ['research', 'data analysis', 'communication', 'writing',
                         'strategic planning'],
    'sociology':        ['research', 'statistics', 'academic writing', 'data analysis'],
    'psychology':       ['research', 'statistics', 'academic writing', 'data analysis',
                         'communication'],
    'environmental science': ['data analysis', 'research', 'statistics', 'gis', 'reporting'],
    'gis':              ['data analysis', 'mapping', 'environmental science',
                         'geospatial analysis'],
    'spss':             ['statistics', 'data analysis', 'research', 'survey analysis'],
    'survey design':    ['research', 'statistics', 'data analysis', 'communication'],
    'qualitative research': ['research', 'academic writing', 'interviewing', 'thematic analysis'],
    'quantitative research': ['statistics', 'data analysis', 'research', 'spss'],

    # ── HR / PEOPLE ──────────────────────────────────────────────────────────
    'human resources':  ['recruitment', 'employee relations', 'communication',
                         'hrm', 'leadership', 'training & development'],
    'hrm':              ['recruitment', 'employee relations', 'communication',
                         'leadership', 'training & development', 'hr policies'],
    'recruitment':      ['communication', 'human resources', 'interviewing',
                         'talent management', 'negotiation'],
    'talent management':['recruitment', 'human resources', 'leadership',
                         'performance management', 'training & development'],
    'training & development': ['hrm', 'leadership', 'communication',
                                'learning design', 'curriculum development'],
    'performance management': ['leadership', 'hrm', 'communication',
                                'strategic planning', 'kpis'],

    # ── HEALTHCARE / BIO-SCIENCES ────────────────────────────────────────────
    'clinical research':['data analysis', 'statistics', 'research', 'academic writing',
                         'spss', 'medical writing'],
    'bioinformatics':   ['python', 'r', 'data science', 'machine learning', 'statistics',
                         'molecular biology'],
    'public health':    ['research', 'statistics', 'data analysis', 'epidemiology',
                         'spss', 'reporting'],
    'epidemiology':     ['statistics', 'data analysis', 'public health', 'research', 'spss'],

    # ── EDUCATION ────────────────────────────────────────────────────────────
    'curriculum development': ['training & development', 'academic writing',
                                'communication', 'learning design'],
    'e-learning':       ['curriculum development', 'content creation',
                         'learning management systems', 'instructional design'],
    'instructional design': ['curriculum development', 'e-learning',
                              'communication', 'multimedia'],
}


class AIMatchingEngine:
    def __init__(self, company=None, job=None):
        self.company = company
        self.job = job

        # 1. Start from department-based defaults (from the job, if available)
        dept_cat = getattr(job, 'department_category', 'any') or 'any'
        base_weights = DEPARTMENT_DEFAULT_WEIGHTS.get(dept_cat, DEPARTMENT_DEFAULT_WEIGHTS['any']).copy()

        # 2. Company custom_weights override department defaults
        if company and company.custom_weights:
            base_weights = {**base_weights, **company.custom_weights}

        # 3. Job-level custom_weights have the highest priority
        if job and job.custom_weights:
            base_weights = {**base_weights, **job.custom_weights}

        self.weights = base_weights
        self.department_category = dept_cat

        # A/B Testing
        self.ab_test_variant = None
    
    def get_ab_test_weights(self, student):
        """Apply A/B testing variant weights if applicable"""
        if not student.ab_test_group or student.ab_test_group == 'control':
            return self.weights
        
        # Variant A: Enhanced weighting with more emphasis on projects and verified skills
        if student.ab_test_group == 'variant_a':
            return {
                'skills': 0.35,
                'cgpa': 0.15,
                'projects': 0.30,  # Increased project weight
                'activity': 0.10,
                'trust': 0.10
            }
        
        # Variant B: Activity-focused weighting
        if student.ab_test_group == 'variant_b':
            return {
                'skills': 0.30,
                'cgpa': 0.15,
                'projects': 0.20,
                'activity': 0.25,  # Increased activity weight
                'trust': 0.10
            }
        
        return self.weights
    
    # Semantic skill similarity groups.
    # If a student has skill A and job requires skill B (a related skill),
    # they receive PARTIAL_SEMANTIC_SCORE credit instead of zero.
    SKILL_SIMILARITY_GROUPS = {
        # Frontend frameworks
        'react': ['vue', 'angular', 'svelte', 'next.js', 'nuxt'],
        'vue': ['react', 'angular', 'svelte'],
        'angular': ['react', 'vue', 'svelte'],
        # Backend frameworks
        'django': ['flask', 'fastapi', 'rails', 'laravel', 'express'],
        'flask': ['django', 'fastapi', 'express'],
        'fastapi': ['django', 'flask', 'express'],
        'express': ['django', 'flask', 'fastapi', 'spring boot'],
        # Languages (similar paradigm)
        'python': ['r', 'julia', 'matlab'],
        'javascript': ['typescript'],
        'typescript': ['javascript'],
        'java': ['kotlin', 'scala', 'c#'],
        'c#': ['java', 'kotlin'],
        'kotlin': ['java', 'swift'],
        'swift': ['kotlin', 'objective-c'],
        # Data / ML
        'tensorflow': ['pytorch', 'keras'],
        'pytorch': ['tensorflow', 'keras'],
        'pandas': ['numpy', 'polars'],
        'scikit-learn': ['xgboost', 'lightgbm'],
        # Databases
        'postgresql': ['mysql', 'mariadb', 'sqlite'],
        'mysql': ['postgresql', 'mariadb', 'sqlite'],
        'mongodb': ['couchdb', 'dynamodb', 'firestore'],
        # Cloud
        'aws': ['gcp', 'azure'],
        'gcp': ['aws', 'azure'],
        'azure': ['aws', 'gcp'],
        # Design
        'figma': ['sketch', 'adobe xd', 'invision'],
        'adobe photoshop': ['gimp', 'affinity photo'],
        # Business / Office
        'excel': ['google sheets', 'tableau', 'power bi', 'financial modeling'],
        'tableau': ['power bi', 'looker', 'excel', 'google data studio'],
        'power bi': ['tableau', 'excel', 'looker'],
        # Marketing
        'seo': ['digital marketing', 'google analytics', 'sem', 'content marketing'],
        'digital marketing': ['seo', 'social media marketing', 'content marketing', 'google analytics'],
        'google analytics': ['seo', 'digital marketing', 'data analysis'],
        'copywriting': ['content creation', 'content marketing', 'writing', 'communication'],
        'content creation': ['copywriting', 'social media marketing', 'writing'],
        'social media marketing': ['digital marketing', 'content creation', 'copywriting'],
        # Finance / Accounting
        'financial modeling': ['financial analysis', 'excel', 'valuation', 'accounting'],
        'financial analysis': ['financial modeling', 'accounting', 'excel', 'bloomberg'],
        'accounting': ['financial analysis', 'bookkeeping', 'excel', 'auditing'],
        'bloomberg': ['financial analysis', 'financial modeling'],
        # HR
        'recruitment': ['human resources', 'talent acquisition', 'talent management'],
        'human resources': ['recruitment', 'talent management', 'employee relations'],
        'talent management': ['human resources', 'recruitment', 'training & development'],
        # Design / Creative
        'adobe photoshop': ['adobe illustrator', 'figma', 'gimp', 'canva', 'graphic design'],
        'adobe illustrator': ['adobe photoshop', 'figma', 'graphic design', 'canva'],
        'adobe premiere': ['video editing', 'after effects', 'final cut pro'],
        'after effects': ['adobe premiere', 'motion graphics', 'video editing'],
        'canva': ['adobe photoshop', 'adobe illustrator', 'figma', 'graphic design'],
        'graphic design': ['adobe photoshop', 'adobe illustrator', 'canva', 'figma'],
        # Project / Operations
        'project management': ['agile', 'scrum', 'pmp', 'operations management'],
        'agile': ['scrum', 'project management', 'kanban'],
        'scrum': ['agile', 'project management'],
        # Communication / Soft skills
        'communication': ['presentation', 'public speaking', 'writing'],
        'leadership': ['project management', 'team management', 'management'],
    }
    PARTIAL_SEMANTIC_SCORE = 0.4  # credit for a semantically similar skill

    def calculate_skill_match(self, student, job):
        """
        Semantic skill matching with cross-validation boost.

        Scoring per required skill:
          - Exact match + cross_validated:  proficiency_multiplier × 1.2  (capped 1.0)
          - Exact match (not cross-validated): proficiency_multiplier (0.5/0.8/1.0)
          - Semantic similar skill found:   PARTIAL_SEMANTIC_SCORE (0.4)
          - Not found at all:               0 (added to missing list)
        """
        required_skills = list(job.required_skills.all())
        student_skills_qs = StudentSkill.objects.filter(student=student).select_related('skill')

        # Build lookup: lowercase name → {level, cross_validated}
        student_skills_by_name = {}
        for ss in student_skills_qs:
            student_skills_by_name[ss.skill.name.lower()] = {
                'level': ss.proficiency_level,
                'cross_validated': getattr(ss, 'cross_validated', False),
            }

        if not required_skills:
            return 1.0, []

        matched = 0.0
        missing = []
        direct_match_count = 0  # tracks exact (non-semantic) matches

        prof_map = {'Beginner': 0.5, 'Intermediate': 0.8, 'Expert': 1.0}

        for required_skill in required_skills:
            req_lower = required_skill.name.lower()

            if req_lower in student_skills_by_name:
                # Exact match
                entry = student_skills_by_name[req_lower]
                multiplier = prof_map.get(entry['level'], 0.5)
                if entry['cross_validated']:
                    multiplier = min(multiplier * 1.2, 1.0)  # CV+LinkedIn verified → boost
                matched += multiplier
                direct_match_count += 1
            else:
                # Try semantic partial match
                similar_names = self.SKILL_SIMILARITY_GROUPS.get(req_lower, [])
                found_similar = False
                for sim_name in similar_names:
                    if sim_name in student_skills_by_name:
                        matched += self.PARTIAL_SEMANTIC_SCORE
                        found_similar = True
                        break
                if not found_similar:
                    missing.append(required_skill)

        return matched / len(required_skills), missing, direct_match_count
    
    def calculate_cgpa_score(self, student, job):
        """Normalize CGPA to 0-1 scale."""
        cgpa     = float(student.cgpa) if student.cgpa else None
        min_cgpa = float(job.min_cgpa) if job.min_cgpa else None

        if cgpa is None:
            # Unknown CGPA — return neutral 0.5, not 0.0 (which unfairly penalises students
            # from universities with different grading systems who haven't filled this in)
            return 0.5 if min_cgpa else 0.5

        if min_cgpa is None:
            return min(cgpa / 4.0, 1.0)

        if cgpa < min_cgpa:
            return 0.0

        return min(cgpa / 4.0, 1.0)
    
    def calculate_project_score(self, student, job=None):
        """
        Job-aware project scoring (0.0 → 1.0).

        Without job context → complexity-based fallback (backward-compatible).
        With job context → 3-layer scoring per project:
          1. Direct overlap   : project.tech_stack ∩ job.required_skills      (weight ×1.0)
          2. Implied knowledge: PROJECT_TECH_IMPLIES(tech_stack) ∩ job skills (weight ×0.5)
          3. Complexity       : project.complexity_score / 5                   (multiplier)
          4. Verification     : GitHub-verified ×1.5, manually verified ×1.2, else ×1.0

        Top-3 projects by contribution are used for the final score.
        A depth bonus (+2% per project beyond 3, max +10%) rewards breadth.

        Debug breakdown is attached to student._project_breakdown.
        """
        log = logging.getLogger('ai_engine.projects')
        projects = list(student.projects.prefetch_related('tech_stack').all())

        def _multiplier(p):
            if p.verified and p.github_url:
                return 1.5   # GitHub-verified — strongest proof (tech students)
            if p.verified and p.live_url:
                return 1.5   # Live-deployed & verified — equally strong (design/business portfolios)
            if p.verified:
                return 1.2   # manually verified, no public URL
            return 1.0

        # ── FALLBACK: no job or no required skills ────────────────────────────
        if job is None:
            if not projects:
                student._project_breakdown = {
                    'mode': 'no_job_context', 'projects': [], 'final': 0.0,
                }
                return 0.0
            total = 0.0
            proj_debug = []
            for p in projects:
                mult = _multiplier(p)
                contrib = (p.complexity_score or 1) * mult
                total += contrib
                proj_debug.append({
                    'title': p.title,
                    'complexity': p.complexity_score or 1,
                    'multiplier': mult,
                    'verified': p.verified,
                    'contribution': round(contrib, 2),
                })
            final = min(total / 25.0, 1.0)
            student._project_breakdown = {
                'mode': 'no_job_context',
                'projects': proj_debug,
                'total_raw': round(total, 2),
                'final': round(final, 3),
                'note': 'Pass job= to get job-relevant scoring',
            }
            log.debug('[Projects] no-job fallback → %.3f', final)
            return final

        # ── JOB-AWARE SCORING ────────────────────────────────────────────────
        job_skills = {s.name.lower() for s in job.required_skills.all()}

        if not job_skills:
            # Job has no required skills → complexity fallback
            if not projects:
                student._project_breakdown = {
                    'mode': 'no_job_skills', 'projects': [], 'final': 0.0,
                }
                return 0.0
            total = 0.0
            proj_debug = []
            for p in projects:
                mult = _multiplier(p)
                contrib = (p.complexity_score or 1) * mult
                total += contrib
                proj_debug.append({
                    'title': p.title, 'complexity': p.complexity_score or 1,
                    'multiplier': mult, 'contribution': round(contrib, 2),
                })
            final = min(total / 25.0, 1.0)
            student._project_breakdown = {
                'mode': 'no_job_skills', 'projects': proj_debug,
                'total_raw': round(total, 2), 'final': round(final, 3),
            }
            return final

        if not projects:
            student._project_breakdown = {
                'mode': 'job_relevant', 'job_skills': sorted(job_skills),
                'all_projects': [], 'top_3_used': [],
                'weighted_sum': 0, 'depth_bonus': 0, 'final': 0.0,
            }
            return 0.0

        proj_scores = []
        for p in projects:
            project_tech = {s.name.lower() for s in p.tech_stack.all()}

            # Layer 1: Direct skill overlap
            direct_match = project_tech & job_skills
            direct_score = len(direct_match) / len(job_skills)

            # Layer 2: Implied knowledge (from PROJECT_TECH_IMPLIES)
            implied_from_project = set()
            for tech in project_tech:
                for implied_skill in PROJECT_TECH_IMPLIES.get(tech, []):
                    implied_from_project.add(implied_skill.lower())

            # Only count implied skills that aren't already in the direct match
            implied_gap = (job_skills - direct_match) & implied_from_project
            implied_score = (len(implied_gap) / len(job_skills)) * 0.5

            relevance = min(direct_score + implied_score, 1.0)

            # Layer 3: Complexity (1–5 → 0.20–1.00)
            complexity = min(max(p.complexity_score or 1, 1), 5) / 5.0

            # Layer 4: Verification multiplier
            mult = _multiplier(p)

            contribution = relevance * complexity * mult

            proj_scores.append({
                'title':          p.title,
                'tech_stack':     sorted(project_tech),
                'direct_match':   sorted(direct_match),
                'implied_match':  sorted(implied_gap),
                'relevance':      round(relevance, 3),
                'direct_score':   round(direct_score, 3),
                'implied_score':  round(implied_score, 3),
                'complexity':     round(complexity, 2),
                'multiplier':     mult,
                'contribution':   round(contribution, 3),
                'verified':       p.verified,
                'github_url':     p.github_url or '',
            })

        # Sort best-first, take top-3
        proj_scores.sort(key=lambda x: x['contribution'], reverse=True)
        top_3 = proj_scores[:3]

        # Max possible: 3 perfect projects (relevance=1 × complexity=1 × mult=1.5)
        MAX_POSSIBLE = 4.5

        weighted_sum = sum(p['contribution'] for p in top_3)

        # Depth bonus: +2% per project beyond 3, max +10%
        depth_bonus = min(max(len(proj_scores) - 3, 0) * 0.02, 0.10)

        final = min((weighted_sum / MAX_POSSIBLE) + depth_bonus, 1.0)

        student._project_breakdown = {
            'mode':         'job_relevant',
            'job_skills':   sorted(job_skills),
            'all_projects': proj_scores,
            'top_3_used':   top_3,
            'weighted_sum': round(weighted_sum, 3),
            'max_possible': MAX_POSSIBLE,
            'depth_bonus':  round(depth_bonus, 3),
            'total_projects': len(proj_scores),
            'final':        round(final, 3),
        }

        log.debug(
            '[Projects] student=%s job=%s final=%.3f '
            'top3=[%s] depth_bonus=%.2f',
            getattr(student, 'id', '?'),
            getattr(job, 'id', '?'),
            final,
            ', '.join(f"{p['title']}({p['contribution']:.2f})" for p in top_3),
            depth_bonus,
        )
        return final
    
    def calculate_activity_score(self, student):
        """
        Multi-signal activity score (0.0 → 1.0).
        Computed fresh from DB — rewards real engagement, not just logins.

        Signal budget (100 pts total):
          vetting_tests       : completed×8 + passed×5   → max 25 pts
          application_quality : shortlisted/hired ratio   → max 20 pts
          login_regularity    : login_frequency/20×15     → max 15 pts
          ai_interviews       : completed×8               → max 15 pts
          profile_freshness   : days since last update    → max 10 pts
          certifications      : count×3                   → max 10 pts
          spam_penalty        : excess apps, 0 success    → max −10 pts
        """
        import logging
        log = logging.getLogger('ai_engine.activity')
        breakdown = {}

        # 1. Vetting tests (max 25 pts)
        try:
            from vetting.models import VettingResult
            tests_completed = VettingResult.objects.filter(
                session__student=student
            ).count()
            tests_passed = VettingResult.objects.filter(
                session__student=student, passed=True
            ).count()
            test_pts = min(tests_completed * 8 + tests_passed * 5, 25)
        except Exception as exc:
            log.debug('[Activity] vetting query failed: %s', exc)
            test_pts = 0
        breakdown['vetting_tests'] = test_pts

        # 2. Application quality (max 20 pts)
        total_apps = Application.objects.filter(student=student).count()
        success_apps = Application.objects.filter(
            student=student, status__in=['shortlisted', 'interview', 'hired']
        ).count()
        if total_apps >= 3:
            quality_ratio = success_apps / total_apps
            app_pts = min(round(quality_ratio * 20), 20)
        elif total_apps > 0:
            app_pts = min(total_apps * 2, 10)   # partial credit for new students
        else:
            app_pts = 0
        breakdown['application_quality'] = app_pts

        # 3. Login regularity (max 15 pts)
        # login_frequency field counts total logins; 20+ logins = fully active
        login_freq = int(student.login_frequency or 0)
        login_pts = min(round((login_freq / 20) * 15), 15)
        breakdown['login_regularity'] = login_pts

        # 4. AI Interview completed (max 15 pts)
        try:
            from core.models import AIInterview
            interviews_done = AIInterview.objects.filter(
                application__student=student, status='completed'
            ).count()
            interview_pts = min(interviews_done * 8, 15)
        except Exception as exc:
            log.debug('[Activity] ai_interview query failed: %s', exc)
            interview_pts = 0
        breakdown['ai_interviews'] = interview_pts

        # 5. Profile freshness (max 10 pts) — actively maintaining profile
        try:
            days_since = (timezone.now() - student.updated_at).days
            if days_since <= 7:
                fresh_pts = 10
            elif days_since <= 30:
                fresh_pts = 7
            elif days_since <= 90:
                fresh_pts = 3
            else:
                fresh_pts = 0
        except Exception:
            fresh_pts = 0
        breakdown['profile_freshness'] = fresh_pts

        # 6. Certifications (max 10 pts)
        certs = getattr(student, 'certifications', []) or []
        cert_pts = min(len(certs) * 3, 10)
        breakdown['certifications'] = cert_pts

        # 7. Spam penalty (max −10 pts)
        spam_penalty = 0
        if total_apps > 10 and success_apps == 0:
            spam_penalty = min((total_apps - 10) * 1, 10)
        breakdown['spam_penalty'] = -spam_penalty

        raw_pts = (
            test_pts + app_pts + login_pts +
            interview_pts + fresh_pts + cert_pts - spam_penalty
        )
        final = max(0.0, min(raw_pts / 100.0, 1.0))

        # Attach breakdown for debug endpoint
        student._activity_breakdown = breakdown
        student._activity_raw = raw_pts

        log.debug(
            '[Activity] student=%s | %s | raw=%s | final=%s%%',
            student.id,
            ' | '.join(f'{k}={v}' for k, v in breakdown.items()),
            raw_pts,
            round(final * 100, 1),
        )
        return final
    
    def calculate_contextual_factors(self, student, job):
        """Additional contextual adjustments"""
        factors = {
            'availability_penalty': 0,
            'competition_factor': 1.0,
            'reapplication_penalty': 0
        }
        
        # Graduation timing
        if student.graduation_date:
            months_until_grad = (student.graduation_date - timezone.now().date()).days / 30
            if months_until_grad > 6:
                factors['availability_penalty'] = -0.1
        
        # Competition density
        applicant_count = Application.objects.filter(job=job).count()
        if applicant_count > 50:
            factors['competition_factor'] = 0.95
        if applicant_count > 100:
            factors['competition_factor'] = 0.9
        
        # Previous rejection (3-month cooldown)
        recent_rejection = Application.objects.filter(
            student=student,
            job__company=job.company,
            status='rejected',
            updated_at__gte=timezone.now() - timedelta(days=90)
        ).exists()
        
        if recent_rejection:
            factors['reapplication_penalty'] = -0.2
        
        # Intent signals from behavior logs
        viewed_count = StudentBehaviorLog.objects.filter(
            student=student,
            job=job,
            action='viewed'
        ).count()
        
        if viewed_count > 3:
            # Student is very interested
            factors['interest_bonus'] = 0.05
        
        return factors
    
    def generate_explanation(self, student, job, scores, missing_skills, factors):
        """Generate human-readable explanation for the match score"""
        recommendations = []
        
        # Skill gap advice
        if missing_skills:
            skill_names = [s.name for s in missing_skills]
            recommendations.append(f"To qualify for this role, you should learn: {', '.join(skill_names)}")
        
        # CGPA advice
        if scores['cgpa'] < 0.7 and job.min_cgpa:
            recommendations.append(f"Consider improving your CGPA (current: {student.cgpa}, required: {job.min_cgpa})")
        
        # Project advice — enriched with job-relevant breakdown
        if scores['projects'] < 0.5:
            proj_bd = getattr(student, '_project_breakdown', {})
            mode = proj_bd.get('mode', '')
            if mode == 'job_relevant':
                all_projs = proj_bd.get('all_projects', [])
                job_skills_needed = proj_bd.get('job_skills', [])
                if not all_projs:
                    recommendations.append(
                        f"You have no projects. Build 2–3 projects using "
                        f"{', '.join(job_skills_needed[:4]) or 'the required technologies'} "
                        f"to significantly boost your match score."
                    )
                else:
                    irrelevant = [p for p in all_projs if p.get('relevance', 0) < 0.15]
                    unverified = [p for p in all_projs if not p.get('verified')]
                    if irrelevant and len(irrelevant) == len(all_projs):
                        # All projects are off-topic
                        recommendations.append(
                            f"None of your projects match this job's tech stack "
                            f"({', '.join(job_skills_needed[:3])}). "
                            f"Build a relevant project to improve your score."
                        )
                    elif irrelevant:
                        recommendations.append(
                            "Some of your projects don't match this role. "
                            "Prioritise projects that use the job's required technologies."
                        )
                    elif unverified:
                        recommendations.append(
                            "Link your projects to your GitHub and verify them — "
                            "verified projects receive a 1.5× score multiplier."
                        )
                    else:
                        recommendations.append(
                            "Increase your project complexity (more features, live deployment, "
                            "README documentation) to push your project score higher."
                        )
            else:
                recommendations.append(
                    "Build 2–3 more projects with higher complexity and link them to GitHub to improve your score."
                )
        
        # Trust score advice
        if scores['trust'] < 0.6:
            recommendations.append("Complete your profile verification and take skill assessments to boost trust score")
        
        # A/B test info
        ab_test_info = None
        if student.ab_test_group and student.ab_test_group != 'control':
            ab_test_info = {
                'group': student.ab_test_group,
                'description': self._get_ab_test_description(student.ab_test_group)
            }
        
        # Radar chart data for visualization
        radar_data = {
            'labels': ['Skills', 'CGPA', 'Projects', 'Activity', 'Trust'],
            'student_scores': [
                scores['skills'] * 100,
                scores['cgpa'] * 100,
                scores['projects'] * 100,
                scores['activity'] * 100,
                scores['trust'] * 100
            ],
            'job_requirements': [
                80,  # Skills threshold
                float(job.min_cgpa or 3.0) / 4.0 * 100 if job.min_cgpa else 60,
                60,  # Project threshold
                40,  # Activity threshold
                50   # Trust threshold
            ]
        }
        
        return {
            'breakdown': scores,
            'recommendations': recommendations,
            'radar_chart': radar_data,
            'contextual_factors': factors,
            'missing_skills': [{'id': str(s.id), 'name': s.name} for s in missing_skills] if missing_skills else [],
            'ab_test_info': ab_test_info
        }
    
    def _get_ab_test_description(self, group):
        """Get description for A/B test group"""
        descriptions = {
            'variant_a': 'Enhanced project-weighted algorithm',
            'variant_b': 'Activity-focused algorithm'
        }
        return descriptions.get(group, 'Standard algorithm')
    
    def _linkedin_trust_bonus(self, student):
        """
        Compute LinkedIn trust bonus (0–0.20) using linkedin_score when available,
        falling back to flat URL bonus so existing profiles aren't penalised.
        """
        ls = getattr(student, 'linkedin_score', 0) or 0
        if ls > 0:
            # linkedin_score 0–100 → bonus 0–0.20 (proportional, richer profile = higher trust)
            return (ls / 100.0) * 0.20
        # Fallback: just having the URL gives a small flat bonus
        return 0.07 if student.linkedin_url else 0.0

    def calculate_trust_score_dept_aware(self, student):
        """
        Multi-signal trust score (0.0 → 1.0).
        Requires real proof — much harder to game than before.

        Signal budget (100 pts total):
          profile_completeness  : 7 core fields          → max 20 pts
          vetting_passed        : passed tests × 8       → max 25 pts
          skill_depth           : expert/mid/cv'd skills → max 15 pts
          external_validation   : dept-specific signals  → max 25 pts
          documents             : CV + LinkedIn PDF       → max 10 pts
          certifications        : count (capped)         → max  5 pts
          spam_penalty          : spammy apps, 0 success → max  −5 pts
        """
        import logging
        log = logging.getLogger('ai_engine.trust')
        breakdown = {}
        score_pts = 0

        dept_cat = (
            getattr(student, 'department_category', None)
            or student.get_department_category()
        )

        # ── 1. Profile completeness — field-by-field (max 20 pts) ──────────
        fields_status = {
            'name':        bool(student.name),
            'email':       bool(student.email),
            'department':  bool(student.department),
            'cgpa':        bool(student.cgpa),
            'cv_uploaded': bool(student.resume),
            'skills_3+':   StudentSkill.objects.filter(student=student).count() >= 3,
            'projects_1+': student.projects.count() >= 1,
        }
        filled = sum(fields_status.values())
        profile_pts = round((filled / len(fields_status)) * 20)
        score_pts += profile_pts
        breakdown['profile_completeness'] = profile_pts
        breakdown['_profile_fields'] = fields_status

        # ── 2. Vetting tests passed — strongest trust signal (max 25 pts) ──
        try:
            from vetting.models import VettingResult
            tests_passed = VettingResult.objects.filter(
                session__student=student, passed=True
            ).count()
            vetting_pts = min(tests_passed * 8, 25)
        except Exception as exc:
            log.debug('[Trust] vetting query failed: %s', exc)
            vetting_pts = 0
        score_pts += vetting_pts
        breakdown['vetting_passed'] = vetting_pts

        # ── 3. Skill depth (max 15 pts) ────────────────────────────────────
        skills_qs          = StudentSkill.objects.filter(student=student)
        expert_count       = skills_qs.filter(proficiency_level='Expert').count()
        intermediate_count = skills_qs.filter(proficiency_level='Intermediate').count()
        cv_count           = skills_qs.filter(cross_validated=True).count()
        skill_pts = min(expert_count * 4 + intermediate_count * 2 + cv_count * 2, 15)
        score_pts += skill_pts
        breakdown['skill_depth'] = skill_pts
        breakdown['_skill_detail'] = {
            'expert': expert_count,
            'intermediate': intermediate_count,
            'cross_validated': cv_count,
        }

        # ── 4. Department-specific external validation (max 25 pts) ────────
        ext_pts = 0
        ext_detail = {}

        if dept_cat == 'tech':
            if student.github_score and student.github_score > 0:
                gh_pts = round((float(student.github_score) / 100.0) * 20)
                ext_pts += gh_pts
                ext_detail['github'] = f'{student.github_score}/100 → {gh_pts} pts'
            elif student.github_username:
                ext_pts += 5
                ext_detail['github'] = 'username only → 5 pts'
            if student.linkedin_score:
                li_pts = round((float(student.linkedin_score) / 100.0) * 5)
                ext_pts += li_pts
                ext_detail['linkedin'] = f'{student.linkedin_score}/100 → {li_pts} pts'

        elif dept_cat == 'design':
            if student.portfolio_url:
                ext_pts += 15
                ext_detail['portfolio'] = '+15 pts'
            if getattr(student, 'behance_url', ''):
                ext_pts += 5
                ext_detail['behance'] = '+5 pts'
            if student.linkedin_score:
                li_pts = round((float(student.linkedin_score) / 100.0) * 5)
                ext_pts += li_pts
                ext_detail['linkedin'] = f'{student.linkedin_score}/100 → {li_pts} pts'

        elif dept_cat in ('business', 'humanities'):
            if student.linkedin_score:
                li_pts = round((float(student.linkedin_score) / 100.0) * 15)
                ext_pts += li_pts
                ext_detail['linkedin'] = f'{student.linkedin_score}/100 → {li_pts} pts'
            eca_list = getattr(student, 'eca_activities', []) or []
            eca_pts = min(len(eca_list) * 3, 7)
            ext_pts += eca_pts
            ext_detail['eca'] = f'{len(eca_list)} × 3 = {eca_pts} pts'
            cert_list = getattr(student, 'certifications', []) or []
            cert_ext = min(len(cert_list), 3)
            ext_pts += cert_ext
            ext_detail['certs_ext'] = f'{len(cert_list)} → {cert_ext} pts'

        elif dept_cat == 'science':
            papers = getattr(student, 'research_papers', []) or []
            paper_pts = min(len(papers) * 6, 18)
            ext_pts += paper_pts
            ext_detail['papers'] = f'{len(papers)} × 6 = {paper_pts} pts'
            if student.linkedin_score:
                li_pts = round((float(student.linkedin_score) / 100.0) * 7)
                ext_pts += li_pts
                ext_detail['linkedin'] = f'{student.linkedin_score}/100 → {li_pts} pts'

        else:  # engineering / any
            if student.linkedin_score:
                li_pts = round((float(student.linkedin_score) / 100.0) * 15)
                ext_pts += li_pts
                ext_detail['linkedin'] = f'{student.linkedin_score}/100 → {li_pts} pts'
            if student.github_score:
                gh_pts = round((float(student.github_score) / 100.0) * 10)
                ext_pts += gh_pts
                ext_detail['github'] = f'{student.github_score}/100 → {gh_pts} pts'

        ext_pts = min(ext_pts, 25)
        score_pts += ext_pts
        breakdown['external_validation'] = ext_pts
        breakdown['_ext_detail'] = ext_detail

        # ── 5. CV + LinkedIn PDF uploaded (max 10 pts) ─────────────────────
        cv_pts    = 5 if student.resume else 0
        li_pdf_pts = round((float(student.linkedin_score or 0) / 100.0) * 5)
        doc_pts   = min(cv_pts + li_pdf_pts, 10)
        score_pts += doc_pts
        breakdown['documents'] = doc_pts
        breakdown['_doc_detail'] = {'cv': cv_pts, 'linkedin_pdf': li_pdf_pts}

        # ── 6. Certifications bonus (max 5 pts) ────────────────────────────
        certs_all = getattr(student, 'certifications', []) or []
        cert_pts  = min(len(certs_all), 5)
        score_pts += cert_pts
        breakdown['certifications'] = cert_pts

        # ── 7. Spam / inconsistency penalty (max −5 pts) ───────────────────
        total_apps   = Application.objects.filter(student=student).count()
        success_apps = Application.objects.filter(
            student=student, status__in=['shortlisted', 'interview', 'hired']
        ).count()
        penalty_pts = 0
        if total_apps > 15 and success_apps == 0:
            penalty_pts = min((total_apps - 15), 5)
        breakdown['spam_penalty'] = -penalty_pts
        score_pts -= penalty_pts

        final = max(0.0, min(score_pts / 100.0, 1.0))

        # Attach breakdown for debug endpoint
        student._trust_breakdown = breakdown
        student._trust_raw = score_pts

        log.debug(
            '[Trust] student=%s dept=%s | %s | raw=%s | final=%s%%',
            student.id, dept_cat,
            ' | '.join(
                f'{k}={v}' for k, v in breakdown.items()
                if not k.startswith('_')
            ),
            score_pts,
            round(final * 100, 1),
        )
        return final

    def calculate_match(self, student, job, save_explanation=True):
        """Main matching algorithm with A/B testing and department-aware support"""
        # Get appropriate weights based on A/B test group
        weights = self.get_ab_test_weights(student)

        # Base scores
        skill_score, missing_skills, direct_match_count = self.calculate_skill_match(student, job)

        # ── Hard gate: skills are non-negotiable ───────────────────────────────
        # Fires when:
        #   (a) skill_score is literally 0, OR
        #   (b) student has ZERO direct (exact) skill matches — only tangential
        #       semantic credit (e.g. Tableau → Excel) — prevents a Data Science
        #       student from scoring 42% on a Marketing job just because both
        #       fields happen to use spreadsheet tools.
        job_has_required_skills = job.required_skills.exists()
        if job_has_required_skills and (skill_score == 0 or direct_match_count == 0):
            zero_scores = {
                'skills': 0.0, 'cgpa': 0.0, 'projects': 0.0,
                'activity': 0.0, 'trust': 0.0, 'final': 0.0,
                'weights_used': weights,
            }
            explanation_data = self.generate_explanation(
                student, job, zero_scores, missing_skills, {}
            )
            return 0.0, explanation_data
        # ──────────────────────────────────────────────────────────────────────

        cgpa_score = self.calculate_cgpa_score(student, job)
        project_score = self.calculate_project_score(student, job=job)
        activity_score = self.calculate_activity_score(student)
        trust_score = self.calculate_trust_score_dept_aware(student)

        # Contextual adjustments
        factors = self.calculate_contextual_factors(student, job)

        # Weighted calculation
        base_score = (
            skill_score * weights['skills'] +
            cgpa_score * weights['cgpa'] +
            project_score * weights['projects'] +
            activity_score * weights['activity'] +
            trust_score * weights['trust']
        )

        # ── Department mismatch penalty ────────────────────────────────────────
        # When a student applies outside their domain (e.g., a tech student for
        # a business role), apply a 20% penalty to prevent high-CGPA candidates
        # from dominating rankings in fields unrelated to their training.
        # Penalty does NOT fire when either dept is 'any'/None, or when
        # the domains are closely related (tech ↔ engineering).
        DEPT_MISMATCH_FACTOR = 0.80
        job_dept  = (getattr(job,     'department_category', None) or 'any').lower()
        stud_dept = (
            getattr(student, 'department_category', None) or
            (student.get_department_category()
             if hasattr(student, 'get_department_category') else 'any') or
            'any'
        ).lower()
        RELATED_PAIRS = {frozenset({'tech', 'engineering'})}
        dept_mismatch = (
            job_dept  not in ('any',) and
            stud_dept not in ('any',) and
            job_dept  != stud_dept and
            frozenset({job_dept, stud_dept}) not in RELATED_PAIRS
        )
        if dept_mismatch:
            base_score *= DEPT_MISMATCH_FACTOR
            logger.debug(
                '[DeptPenalty] student=%s(%s) job=%s(%s) penalty=×%.2f',
                getattr(student, 'id', '?'), stud_dept,
                getattr(job, 'id', '?'), job_dept,
                DEPT_MISMATCH_FACTOR,
            )
        # ──────────────────────────────────────────────────────────────────────

        # Apply contextual adjustments
        adjusted_score = base_score * factors.get('competition_factor', 1.0)
        adjusted_score += factors.get('availability_penalty', 0)
        adjusted_score += factors.get('reapplication_penalty', 0)
        adjusted_score += factors.get('interest_bonus', 0)

        # Clamp to 0-100
        final_score = max(0, min(100, adjusted_score * 100))

        scores = {
            'skills': skill_score,
            'cgpa': cgpa_score,
            'projects': project_score,
            'activity': activity_score,
            'trust': trust_score,
            'final': final_score,
            'weights_used': weights  # Include weights for transparency
        }

        explanation_data = self.generate_explanation(student, job, scores, missing_skills, factors)

        return final_score, explanation_data
    
    def generate_smart_recommendations(self, student, top_n=5):
        """
        Return top N jobs ranked by match score, each with:
          - fit_percentage: current match %
          - gap_skills: list of skills the student is missing
          - potential_score: estimated score if gap skills were added
          - is_reachable: True if potential_score >= 70 (worth pursuing)

        Also returns career_guide: the most impactful skills to add across
        all near-miss jobs (60–85% fit range).
        """
        active_jobs = Job.objects.filter(status='active').prefetch_related('required_skills', 'company')
        results = []

        for job in active_jobs:
            engine = AIMatchingEngine(company=job.company, job=job)
            score, explanation = engine.calculate_match(student, job, save_explanation=False)
            missing = explanation.get('missing_skills', [])

            # Estimate potential score: assume adding each missing skill at Intermediate
            # gives the average contribution of that skill to the total weight
            skills_weight = engine.weights.get('skills', 0.35)
            req_count = job.required_skills.count()
            if req_count > 0 and missing:
                # Each missing skill contributes skills_weight * 0.8 / req_count (Intermediate)
                gain_per_skill = (skills_weight * 0.8 / req_count) * 100
                potential = min(score + gain_per_skill * len(missing), 100)
            else:
                potential = score

            results.append({
                'job_id': str(job.id),
                'job_title': job.title,
                'company_name': job.company.name,
                'fit_percentage': round(score, 1),
                'potential_score': round(potential, 1),
                'gap_skills': missing,
                'is_reachable': potential >= 70,
                'department_category': job.department_category or 'any',
            })

        # Sort: prioritise reachable jobs closest to 80% fit
        results.sort(key=lambda x: (
            -x['is_reachable'],
            -x['fit_percentage'],
        ))
        top_jobs = results[:top_n]

        # Career guide: find the most commonly missing skills across 60–85% fit jobs
        near_miss_jobs = [r for r in results if 55 <= r['fit_percentage'] <= 85]
        skill_frequency: dict = {}
        for r in near_miss_jobs:
            for s in r['gap_skills']:
                key = s['name']
                skill_frequency[key] = skill_frequency.get(key, 0) + 1

        # Top 5 highest-impact skills to learn
        top_gap_skills = sorted(skill_frequency.items(), key=lambda x: -x[1])[:5]
        career_guide = []
        for skill_name, job_count in top_gap_skills:
            career_guide.append({
                'skill': skill_name,
                'unlocks_jobs': job_count,
                'message': f"Adding '{skill_name}' would improve your fit for {job_count} job{'s' if job_count > 1 else ''}",
            })

        return {
            'top_jobs': top_jobs,
            'career_guide': career_guide,
            'total_active_jobs': len(results),
        }

    def smart_apply(self, student, threshold=70, max_applications=5):
        """Auto-apply student to best matching jobs"""
        active_jobs = Job.objects.filter(status='active')
        matches = []
        
        for job in active_jobs:
            # Skip if already applied
            if Application.objects.filter(student=student, job=job).exists():
                continue
            
            score, explanation = self.calculate_match(student, job, save_explanation=False)
            
            if score >= threshold:
                matches.append({
                    'job': job,
                    'score': score,
                    'explanation': explanation
                })
        
        # Sort by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)
        
        # Auto-apply to top N
        applied = []
        for match in matches[:max_applications]:
            app = Application.objects.create(
                student=student,
                job=match['job'],
                match_score=match['score'],
                is_auto_applied=True,
                status='applied'
            )
            
            # Save explanation
            MatchExplanation.objects.create(
                application=app,
                score_breakdown=match['explanation']['breakdown'],
                recommendations=match['explanation']['recommendations'],
                radar_chart_data=match['explanation']['radar_chart']
            )
            
            # Add skill gaps
            for skill_data in match['explanation']['missing_skills']:
                skill = Skill.objects.get(id=skill_data['id'])
                app.explanation.skill_gaps.add(skill)
            
            applied.append({
                'application_id': str(app.id),
                'job_title': match['job'].title,
                'company': match['job'].company.name,
                'score': match['score']
            })
        
        return applied
    
    # ──────────────────────────────────────────────────────────────────────
    # RL WEIGHT AGENT
    # ──────────────────────────────────────────────────────────────────────

    def _get_candidate_features(self, student, job):
        """Return normalised 0-1 feature scores for a student/job pair."""
        return {
            'skills':   round(self.calculate_skill_match(student, job)[0], 4),
            'cgpa':     round(self.calculate_cgpa_score(student, job), 4),
            'projects': round(self.calculate_project_score(student, job=job), 4),
            'activity': round(self.calculate_activity_score(student), 4),
            'trust':    round(float(student.trust_score or 0) / 100.0, 4),
        }

    @staticmethod
    def _normalise_weights(raw):
        """Clip to min 0.05 per key, then normalise to sum=1."""
        clipped = {k: max(0.05, v) for k, v in raw.items()}
        total   = sum(clipped.values())
        return {k: round(v / total, 6) for k, v in clipped.items()}

    def update_weights_from_feedback(self, company, application, trigger='hire'):
        """
        RL update called on:
          trigger='hire'   → reward +1.0  (learning_rate 0.07)
          trigger='reject' → reward -1.0  (learning_rate 0.04, weaker signal)
        """
        student  = application.student
        job      = application.job
        reward   = 1.0 if trigger == 'hire' else -1.0
        lr       = 0.07 if trigger == 'hire' else 0.04

        features       = self._get_candidate_features(student, job)
        current        = company.get_weights()

        # Core RL update:
        # reward=+1 → push weights TOWARD high-feature dimensions
        # reward=-1 → push weights AWAY from high-feature dimensions
        new_weights = {}
        for key in current:
            # centre feature around 0.5 so neutral features produce zero delta
            # use .get() so unknown/custom keys default to 0.5 (zero delta) instead of KeyError
            feat_val = features.get(key, 0.5)
            delta = lr * reward * (feat_val - 0.5)
            new_weights[key] = current[key] + delta

        new_weights = self._normalise_weights(new_weights)
        weight_delta = {k: round(new_weights[k] - current[k], 6) for k in current}

        # Persist
        company.custom_weights = new_weights
        if trigger == 'hire':
            company.successful_hire_patterns.append({
                'date':       datetime.now().isoformat(),
                'student_id': str(student.id),
                'job_id':     str(job.id),
                'features':   features,
            })
        company.save()

        from core.models import AIFeedbackLog
        AIFeedbackLog.objects.create(
            company=company,
            application=application,
            trigger=trigger,
            reward=reward,
            candidate_features=features,
            previous_weights=current,
            adjusted_weights=new_weights,
            weight_delta=weight_delta,
            adjustment_reason=(
                f"{'Hired' if trigger == 'hire' else 'Rejected shortlisted'} "
                f"{student.name} for {job.title}"
            ),
        )
        return new_weights

    def learn_from_manual_edit(self, company, manual_weights):
        """
        Called when a company manually overrides weights.
        We record the event so the chart shows human corrections,
        and we do a soft-learn: move 30% toward the manual values
        (agent respects company intent without blindly overwriting its own learning).
        """
        current = company.get_weights()

        # Soft-pull: blend current + manual
        blended = {k: current[k] + 0.30 * (manual_weights.get(k, current[k]) - current[k]) for k in current}
        new_weights  = self._normalise_weights(blended)
        weight_delta = {k: round(new_weights[k] - current[k], 6) for k in current}

        # Persist the blended weights (was missing — manual edits were silently ignored by RL)
        company.custom_weights = new_weights
        company.save()

        from core.models import AIFeedbackLog
        AIFeedbackLog.objects.create(
            company=company,
            application=None,
            trigger='manual',
            reward=0.0,
            candidate_features={},
            previous_weights=current,
            adjusted_weights=new_weights,
            weight_delta=weight_delta,
            adjustment_reason='Company manually edited weights — agent soft-learned.',
        )
        return new_weights


class ABTestFramework:
    """A/B Testing framework for matching algorithms"""
    
    VARIANTS = ['control', 'variant_a', 'variant_b']
    
    @staticmethod
    def assign_variant(student):
        """Randomly assign student to A/B test variant"""
        import random
        variant = random.choice(ABTestFramework.VARIANTS)
        student.ab_test_group = variant
        student.save()
        return variant
    
    @staticmethod
    def calculate_variant_performance():
        """Calculate performance metrics for each variant"""
        results = {}
        
        for variant in ABTestFramework.VARIANTS:
            apps = Application.objects.filter(student__ab_test_group=variant)
            
            total = apps.count()
            hired = apps.filter(status='hired').count()
            shortlisted = apps.filter(status='shortlisted').count()
            interviews = apps.filter(status='interview').count()
            
            # Calculate conversion rates
            hire_rate = (hired / total * 100) if total > 0 else 0
            shortlist_rate = (shortlisted / total * 100) if total > 0 else 0
            interview_rate = (interviews / total * 100) if total > 0 else 0
            
            # Average match scores
            avg_score = apps.aggregate(Avg('match_score'))['match_score__avg'] or 0
            
            results[variant] = {
                'total': total,
                'hired': hired,
                'shortlisted': shortlisted,
                'interviews': interviews,
                'hire_rate': round(hire_rate, 2),
                'shortlist_rate': round(shortlist_rate, 2),
                'interview_rate': round(interview_rate, 2),
                'avg_match_score': round(avg_score, 2)
            }
        
        return results
    
    @staticmethod
    def get_statistical_significance():
        """Calculate statistical significance between variants"""
        # Simplified - in production use proper statistical tests
        performance = ABTestFramework.calculate_variant_performance()
        
        control_rate = performance['control']['hire_rate']
        variant_a_rate = performance['variant_a']['hire_rate']
        variant_b_rate = performance['variant_b']['hire_rate']
        
        def calculate_improvement(variant_rate):
            if control_rate == 0:
                return 0
            return round(((variant_rate - control_rate) / control_rate) * 100, 1)
        
        return {
            'control': performance['control'],
            'variant_a': {
                **performance['variant_a'],
                'improvement': calculate_improvement(variant_a_rate),
                'significant': abs(variant_a_rate - control_rate) > 5  # 5% threshold
            },
            'variant_b': {
                **performance['variant_b'],
                'improvement': calculate_improvement(variant_b_rate),
                'significant': abs(variant_b_rate - control_rate) > 5
            }
        }