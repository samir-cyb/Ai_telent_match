import requests
import base64
from datetime import datetime
from django.conf import settings

class GitHubValidator:
    def __init__(self):
        self.token = settings.GITHUB_TOKEN
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.graphql_url = 'https://api.github.com/graphql'
    
    def validate_student_github(self, username):
        """
        Ethical GitHub validation using official API
        Returns validation score and detected skills
        """
        if not username:
            return {'valid': False, 'score': 0, 'error': 'No username provided'}
        
        try:
            # 1. Check user exists and get basic info
            user_url = f'https://api.github.com/users/{username}'
            user_resp = requests.get(user_url, headers=self.headers, timeout=10)
            
            if user_resp.status_code != 200:
                return {'valid': False, 'score': 0, 'error': 'User not found'}
            
            user_data = user_resp.json()
            
            # 2. Get repositories (max 100)
            repos_url = f'https://api.github.com/users/{username}/repos?per_page=100&sort=updated'
            repos_resp = requests.get(repos_url, headers=self.headers, timeout=10)
            repos = repos_resp.json() if repos_resp.status_code == 200 else []
            
            # 3. Analyze repositories
            analysis = self._analyze_repositories(repos)
            
            # 4. Calculate validation score
            score = self._calculate_github_score(user_data, repos, analysis)
            
            # 5. Detect skills from languages
            detected_skills = self._detect_skills_from_languages(analysis['languages'])
            
            return {
                'valid': True,
                'score': score,
                'username': username,
                'profile': {
                    'followers': user_data.get('followers', 0),
                    'following': user_data.get('following', 0),
                    'public_repos': user_data.get('public_repos', 0),
                    'created_at': user_data.get('created_at'),
                    'bio': user_data.get('bio', '')
                },
                'detected_languages': analysis['languages'],
                'total_commits_approx': analysis['estimated_commits'],
                'repo_quality_score': analysis['quality_score'],
                'verified_projects': analysis['verified_projects'],
                'suggested_skills': detected_skills
            }
            
        except Exception as e:
            return {'valid': False, 'score': 0, 'error': str(e)}
    
    def _analyze_repositories(self, repos):
        """Analyze repository quality and extract skill signals"""
        languages = {}
        quality_indicators = {
            'has_readme': 0,
            'has_description': 0,
            'is_fork': 0,
            'recent_commits': 0,
            'total_stars': 0
        }
        verified_projects = []
        
        for repo in repos:
            # Language detection
            lang = repo.get('language')
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
            
            # Quality checks
            if repo.get('description'):
                quality_indicators['has_description'] += 1
            if not repo.get('fork'):
                # Check for README by attempting to fetch it
                readme_url = f'https://api.github.com/repos/{repo["owner"]["login"]}/{repo["name"]}/readme'
                readme_resp = requests.get(readme_url, headers=self.headers, timeout=5)
                if readme_resp.status_code == 200:
                    quality_indicators['has_readme'] += 1
                
                # Recent activity (last 3 months)
                pushed_at = repo.get('pushed_at')
                if pushed_at:
                    pushed_date = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
                    days_since_push = (datetime.now(pushed_date.tzinfo) - pushed_date).days
                    if days_since_push < 90:
                        quality_indicators['recent_commits'] += 1
                
                # Stars indicate quality
                quality_indicators['total_stars'] += repo.get('stargazers_count', 0)
                
                # High-quality project detection
                if (repo.get('stargazers_count', 0) > 5 or 
                    readme_resp.status_code == 200 and repo.get('description')):
                    verified_projects.append({
                        'name': repo['name'],
                        'url': repo['html_url'],
                        'language': lang,
                        'stars': repo.get('stargazers_count', 0),
                        'description': repo.get('description', '')
                    })
            else:
                quality_indicators['is_fork'] += 1
        
        # Calculate quality score (0-100)
        total_repos = len(repos)
        if total_repos == 0:
            quality_score = 0
        else:
            quality_score = (
                (quality_indicators['has_readme'] / total_repos * 30) +
                (quality_indicators['has_description'] / total_repos * 20) +
                ((total_repos - quality_indicators['is_fork']) / total_repos * 30) +
                (min(quality_indicators['recent_commits'] / 3, 1) * 20)  # Cap at 20%
            )
        
        # Estimate commits (rough approximation)
        estimated_commits = sum(r.get('size', 0) / 10 for r in repos)  # Size proxy
        
        return {
            'languages': languages,
            'estimated_commits': int(estimated_commits),
            'quality_score': min(100, quality_score),
            'verified_projects': verified_projects[:5]  # Top 5
        }
    
    def _calculate_github_score(self, user_data, repos, analysis):
        """Calculate 0-100 validation score"""
        score = 0
        
        # Account age (max 20 points)
        created_at = datetime.fromisoformat(user_data.get('created_at', '').replace('Z', '+00:00'))
        account_age_years = (datetime.now(created_at.tzinfo) - created_at).days / 365
        score += min(account_age_years * 4, 20)
        
        # Activity level (max 30 points)
        public_repos = user_data.get('public_repos', 0)
        score += min(public_repos * 2, 30)
        
        # Code quality (max 30 points)
        score += analysis['quality_score'] * 0.3
        
        # Social proof (max 20 points)
        followers = user_data.get('followers', 0)
        score += min(followers * 2, 20)
        
        return min(100, int(score))
    
    def _detect_skills_from_languages(self, languages):
        """Map GitHub languages to skill categories"""
        skill_mapping = {
            'Python': ['Python', 'Backend', 'Data Science', 'AI/ML'],
            'JavaScript': ['JavaScript', 'Frontend', 'Full Stack'],
            'TypeScript': ['TypeScript', 'Frontend', 'Full Stack'],
            'Java': ['Java', 'Backend'],
            'Go': ['Go', 'Backend', 'DevOps'],
            'Rust': ['Rust', 'Backend', 'Systems'],
            'C++': ['C++', 'Systems', 'Game Development'],
            'C#': ['C#', 'Backend', 'Game Development'],
            'Ruby': ['Ruby', 'Backend'],
            'PHP': ['PHP', 'Backend'],
            'Swift': ['Swift', 'Mobile', 'iOS'],
            'Kotlin': ['Kotlin', 'Mobile', 'Android', 'Backend'],
            'HTML': ['HTML', 'Frontend'],
            'CSS': ['CSS', 'Frontend', 'Design'],
            'R': ['R', 'Data Science'],
            'Scala': ['Scala', 'Data Science', 'Backend'],
            'Shell': ['DevOps', 'Systems'],
            'Dockerfile': ['DevOps', 'Docker'],
        }
        
        suggested = set()
        for lang in languages.keys():
            if lang in skill_mapping:
                suggested.update(skill_mapping[lang])
        
        return list(suggested)
    
    def verify_project_link(self, username, project_url):
        """Verify that a specific project URL belongs to the student"""
        if not project_url or username not in project_url:
            return False
        
        try:
            # Extract repo name from URL (FIXED syntax error)
            parts = project_url.replace('https://github.com/', '').split('/')
            if len(parts) >= 2:
                repo_owner, repo_name = parts[0], parts[1]
                
                # Verify ownership
                if repo_owner.lower() != username.lower():
                    return False
                
                # Check repo exists and is accessible
                repo_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}'
                resp = requests.get(repo_url, headers=self.headers, timeout=10)
                return resp.status_code == 200
            
            return False
        except Exception:
            return False
    
    def fetch_repository_details(self, username, repo_name):
        """Fetch detailed information about a specific repository"""
        try:
            repo_url = f'https://api.github.com/repos/{username}/{repo_name}'
            repo_resp = requests.get(repo_url, headers=self.headers, timeout=10)
            
            if repo_resp.status_code != 200:
                return None
            
            repo_data = repo_resp.json()
            
            # Get languages used
            lang_url = f'https://api.github.com/repos/{username}/{repo_name}/languages'
            lang_resp = requests.get(lang_url, headers=self.headers, timeout=10)
            languages = lang_resp.json() if lang_resp.status_code == 200 else {}
            
            # Get README content
            readme_url = f'https://api.github.com/repos/{username}/{repo_name}/readme'
            readme_resp = requests.get(readme_url, headers=self.headers, timeout=10)
            readme_content = None
            if readme_resp.status_code == 200:
                readme_data = readme_resp.json()
                if 'content' in readme_data:
                    readme_content = base64.b64decode(readme_data['content']).decode('utf-8')
            
            return {
                'name': repo_data['name'],
                'description': repo_data.get('description', ''),
                'stars': repo_data.get('stargazers_count', 0),
                'forks': repo_data.get('forks_count', 0),
                'languages': languages,
                'readme': readme_content,
                'created_at': repo_data.get('created_at'),
                'updated_at': repo_data.get('updated_at'),
                'size': repo_data.get('size', 0)
            }
            
        except Exception as e:
            return None
    
    def calculate_project_complexity(self, repo_details):
        """Calculate complexity score (1-5) based on repository metrics"""
        if not repo_details:
            return 1
        
        score = 1
        
        # Size factor
        size = repo_details.get('size', 0)
        if size > 1000:  # KB
            score += 1
        
        # Languages diversity
        languages = repo_details.get('languages', {})
        if len(languages) > 2:
            score += 1
        
        # Stars indicate complexity/quality
        stars = repo_details.get('stars', 0)
        if stars > 10:
            score += 1
        
        # README presence indicates documentation
        if repo_details.get('readme'):
            score += 1
        
        return min(5, score)