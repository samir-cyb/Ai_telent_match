import requests
import base64
from datetime import datetime, timedelta
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
        Enhanced GitHub validation with commit frequency, open-source signals,
        and skill detection from repository topics.
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
            
            # 3. Analyze repositories (includes topics & commit frequency)
            analysis = self._analyze_repositories(repos)
            
            # 4. Get organizations for open-source signal
            orgs = self._fetch_organizations(username)
            open_source_bonus = self._calculate_open_source_score(orgs)
            
            # 5. Calculate base validation score
            base_score = self._calculate_github_score(user_data, repos, analysis)
            
            # 6. Final score = base + commit_score + open_source_bonus (capped 100)
            final_score = min(100, base_score + analysis.get('commit_score', 0) + open_source_bonus)
            
            # 7. Detect skills from languages and topics
            language_skills = self._detect_skills_from_languages(analysis['languages'])
            topic_skills = self._extract_skills_from_topics(analysis.get('topics', set()))
            all_suggested = list(set(language_skills + topic_skills))
            
            return {
                'valid': True,
                'score': final_score,
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
                'suggested_skills': all_suggested,
                'open_source_contributor': len(orgs) > 0,
                'commit_frequency_score': analysis.get('commit_score', 0)
            }
            
        except Exception as e:
            return {'valid': False, 'score': 0, 'error': str(e)}
    
    def _fetch_organizations(self, username):
        """Fetch organizations the user belongs to."""
        orgs_url = f'https://api.github.com/users/{username}/orgs'
        try:
            resp = requests.get(orgs_url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return []
    
    def _calculate_open_source_score(self, orgs):
        """Return bonus points (0-15) for membership in organizations."""
        if not orgs:
            return 0
        # Each organization gives up to 5 points, max 15
        return min(len(orgs) * 5, 15)
    
    def _analyze_repositories(self, repos):
        """
        Analyze repository quality, topics, and commit activity.
        Returns dict with keys: languages, topics, estimated_commits,
        quality_score, commit_score, verified_projects.
        """
        languages = {}
        topics = set()
        quality_indicators = {
            'has_readme': 0,
            'has_description': 0,
            'is_fork': 0,
            'recent_commits': 0,
            'total_stars': 0
        }
        verified_projects = []
        commit_count_estimate = 0
        recent_activity_count = 0   # repos pushed in last 90 days
        
        for repo in repos:
            # Language detection
            lang = repo.get('language')
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
            
            # Fetch topics (requires custom Accept header)
            topics_url = f'https://api.github.com/repos/{repo["owner"]["login"]}/{repo["name"]}/topics'
            topics_headers = self.headers.copy()
            topics_headers['Accept'] = 'application/vnd.github.mercy-preview+json'
            try:
                topics_resp = requests.get(topics_url, headers=topics_headers, timeout=5)
                if topics_resp.status_code == 200:
                    repo_topics = topics_resp.json().get('names', [])
                    topics.update(repo_topics)
            except Exception:
                pass
            
            # Quality checks
            if repo.get('description'):
                quality_indicators['has_description'] += 1
            if not repo.get('fork'):
                # Check for README by attempting to fetch it
                readme_url = f'https://api.github.com/repos/{repo["owner"]["login"]}/{repo["name"]}/readme'
                try:
                    readme_resp = requests.get(readme_url, headers=self.headers, timeout=5)
                    if readme_resp.status_code == 200:
                        quality_indicators['has_readme'] += 1
                except Exception:
                    pass
                
                # Recent activity (last 3 months)
                pushed_at = repo.get('pushed_at')
                if pushed_at:
                    try:
                        pushed_date = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
                        days_since_push = (datetime.now(pushed_date.tzinfo) - pushed_date).days
                        if days_since_push < 90:
                            quality_indicators['recent_commits'] += 1
                            recent_activity_count += 1
                    except Exception:
                        pass
                
                # Stars indicate quality
                quality_indicators['total_stars'] += repo.get('stargazers_count', 0)
                
                # High-quality project detection
                if (repo.get('description') or readme_resp.status_code == 200):
                    verified_projects.append({
                        'name': repo['name'],
                        'url': repo['html_url'],
                        'language': lang,
                        'stars': repo.get('stargazers_count', 0),
                        'description': repo.get('description', '')
                    })
            else:
                quality_indicators['is_fork'] += 1
            
            # Estimate commits (rough approximation)
            commit_count_estimate += repo.get('size', 0) / 10
        
        total_repos = len(repos)
        if total_repos == 0:
            quality_score = 0
            commit_score = 0
        else:
            quality_score = (
                (quality_indicators['has_readme'] / total_repos * 30) +
                (quality_indicators['has_description'] / total_repos * 20) +
                ((total_repos - quality_indicators['is_fork']) / total_repos * 30) +
                (min(quality_indicators['recent_commits'] / 3, 1) * 20)
            )
            # Commit frequency score: up to 30 points based on proportion of repos active in last 90 days
            commit_score = min((recent_activity_count / total_repos) * 30, 30)
        
        return {
            'languages': languages,
            'topics': topics,
            'estimated_commits': int(commit_count_estimate),
            'quality_score': min(100, quality_score),
            'commit_score': commit_score,
            'verified_projects': verified_projects[:5]
        }
    
    def _extract_skills_from_topics(self, topics):
        """Map GitHub topics to skill categories."""
        skill_mapping = {
            'react': ['React', 'Frontend'],
            'django': ['Django', 'Backend'],
            'flask': ['Flask', 'Backend'],
            'tensorflow': ['TensorFlow', 'AI/ML'],
            'pytorch': ['PyTorch', 'AI/ML'],
            'javascript': ['JavaScript', 'Frontend'],
            'typescript': ['TypeScript', 'Frontend'],
            'nodejs': ['Node.js', 'Backend'],
            'express': ['Express.js', 'Backend'],
            'vue': ['Vue.js', 'Frontend'],
            'angular': ['Angular', 'Frontend'],
            'aws': ['AWS', 'DevOps'],
            'docker': ['Docker', 'DevOps'],
            'kubernetes': ['Kubernetes', 'DevOps'],
            'machine-learning': ['Machine Learning', 'AI/ML'],
            'data-science': ['Data Science', 'Data Science'],
            'sql': ['SQL', 'Data Science'],
            'mongodb': ['MongoDB', 'Backend'],
            'postgresql': ['PostgreSQL', 'Backend'],
            'html': ['HTML', 'Frontend'],
            'css': ['CSS', 'Frontend', 'Design']
        }
        suggested = set()
        for topic in topics:
            topic_lower = topic.lower()
            if topic_lower in skill_mapping:
                for skill in skill_mapping[topic_lower]:
                    suggested.add(skill)
        return list(suggested)
    
    def _calculate_github_score(self, user_data, repos, analysis):
        """Calculate 0-100 validation score (original logic extended with commit_score)."""
        score = 0
        
        # Account age (max 20 points)
        created_at = datetime.fromisoformat(user_data.get('created_at', '').replace('Z', '+00:00'))
        account_age_years = (datetime.now(created_at.tzinfo) - created_at).days / 365
        score += min(account_age_years * 4, 20)
        
        # Activity level (max 30 points)
        public_repos = user_data.get('public_repos', 0)
        score += min(public_repos * 2, 30)
        
        # Code quality (max 30 points) – use quality_score from analysis
        score += analysis['quality_score'] * 0.3
        
        # Social proof (max 20 points)
        followers = user_data.get('followers', 0)
        score += min(followers * 2, 20)
        
        # (Note: commit_score is added separately in validate_student_github, not here)
        
        return min(100, int(score))
    
    def _detect_skills_from_languages(self, languages):
        """Map GitHub languages to skill categories (unchanged)."""
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
        """Verify that a specific project URL belongs to the student (unchanged)."""
        if not project_url or username not in project_url:
            return False
        
        try:
            
            parts = project_url.replace('https://github.com/', '').split('/')
            
            if len(parts) >= 2:
                repo_owner, repo_name = parts[0], parts[1]
                
            if repo_owner.lower() != username.lower():
                return False
                repo_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}'
            resp = requests.get(repo_url, headers=self.headers, timeout=10)
            return resp.status_code == 200
            
            return False
        except Exception:
            return False
    
    def fetch_repository_details(self, username, repo_name):
        """Fetch detailed information about a specific repository (unchanged)."""
        try:
            repo_url = f'https://api.github.com/repos/{username}/{repo_name}'
            
            repo_resp = requests.get(repo_url, headers=self.headers, timeout=10)
            
            if repo_resp.status_code != 200:
                return None
            
            repo_data = repo_resp.json()
    
            lang_url = f'https://api.github.com/repos/{username}/{repo_name}/languages'
            lang_resp = requests.get(lang_url, headers=self.headers, timeout=10)
            languages = lang_resp.json() if lang_resp.status_code == 200 else {}
    
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
        """Calculate complexity score (1-5) based on repository metrics (unchanged)."""
        if not repo_details:
            return 1
        
        score = 1

        size = repo_details.get('size', 0)
        if size > 1000:
            score += 1
            
        languages = repo_details.get('languages', {})
        if len(languages) > 2:
            score += 1
            
        stars = repo_details.get('stars', 0)
        if stars > 10:
            score += 1
            
        if repo_details.get('readme'):
            score += 1
            
        return min(5, score)