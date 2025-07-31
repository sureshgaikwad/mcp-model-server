# model/model.py
import json
import logging
import asyncio
from typing import Dict, Any, List
import yaml
import base64
import re
from github import Github
from kubernetes import client, config as k8s_config
import openai

logger = logging.getLogger(__name__)

class MCPDeploymentModel:
    """
    MCP Model that analyzes code repositories and generates deployment configurations
    """
    
    def __init__(self):
        self.github_client = None
        self.k8s_client = None
        self.deployment_patterns = self._load_deployment_patterns()
        self.setup_clients()
    
    def setup_clients(self):
        """Initialize GitHub and Kubernetes clients"""
        try:
            # GitHub client
            github_token = os.environ.get('GITHUB_TOKEN')
            if github_token:
                self.github_client = Github(github_token)
            
            # Kubernetes client
            k8s_config.load_incluster_config()
            self.k8s_client = client.ApiClient()
            
            logger.info("Clients initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize clients: {e}")
    
    def _load_deployment_patterns(self) -> Dict[str, Any]:
        """Load predefined deployment patterns for different application types"""
        return {
            "node_js": {
                "indicators": ["package.json", "node_modules", "app.js", "server.js"],
                "port": 3000,
                "health_path": "/health",
                "base_image": "node:18-alpine",
                "build_command": "npm install && npm run build",
                "start_command": "npm start"
            },
            "python_flask": {
                "indicators": ["requirements.txt", "app.py", "wsgi.py", "flask"],
                "port": 5000,
                "health_path": "/health",
                "base_image": "python:3.11-slim",
                "build_command": "pip install -r requirements.txt",
                "start_command": "python app.py"
            },
            "python_django": {
                "indicators": ["requirements.txt", "manage.py", "settings.py", "django"],
                "port": 8000,
                "health_path": "/health/",
                "base_image": "python:3.11-slim",
                "build_command": "pip install -r requirements.txt && python manage.py collectstatic --noinput",
                "start_command": "python manage.py runserver 0.0.0.0:8000"
            },
            "java_spring": {
                "indicators": ["pom.xml", "build.gradle", "src/main/java", "spring"],
                "port": 8080,
                "health_path": "/actuator/health",
                "base_image": "openjdk:17-jre-slim",
                "build_command": "mvn clean package -DskipTests",
                "start_command": "java -jar target/*.jar"
            },
            "go": {
                "indicators": ["go.mod", "main.go", "*.go"],
                "port": 8080,
                "health_path": "/health",
                "base_image": "golang:1.21-alpine",
                "build_command": "go mod download && go build -o app .",
                "start_command": "./app"
            },
            "react": {
                "indicators": ["package.json", "src/App.js", "public/index.html", "react"],
                "port": 80,
                "health_path": "/",
                "base_image": "nginx:alpine",
                "build_command": "npm install && npm run build",
                "start_command": "nginx -g 'daemon off;'",
                "static_site": True
            },
            "machine_learning": {
                "indicators": ["requirements.txt", "model.pkl", "*.ipynb", "tensorflow", "pytorch", "scikit-learn"],
                "port": 8000,
                "health_path": "/health",
                "base_image": "python:3.11-slim",
                "build_command": "pip install -r requirements.txt",
                "start_command": "python serve.py",
                "resources": {
                    "requests": {"cpu": "500m", "memory": "1Gi"},
                    "limits": {"cpu": "2000m", "memory": "4Gi"}
                }
            }
        }
    
    async def predict(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main prediction method - analyzes repository and returns deployment configuration
        """
        try:
            repository_url = request_data.get('repository_url')
            branch = request_data.get('branch', 'main')
            namespace = request_data.get('namespace', 'default')
            deployment_type = request_data.get('deployment_type', 'auto')
            
            if not repository_url:
                raise ValueError("repository_url is required")
            
            # Analyze repository
            analysis_result = await self.analyze_repository(repository_url, branch)
            
            # Generate deployment configuration
            deployment_config = await self.generate_deployment_config(
                analysis_result, namespace, deployment_type
            )
            
            # Deploy if requested
            deploy_immediately = request_data.get('deploy_immediately', False)
            if deploy_immediately:
                deployment_result = await self.deploy_application(deployment_config)
                deployment_config['deployment_result'] = deployment_result
            
            return {
                'status': 'success',
                'analysis': analysis_result,
                'deployment_config': deployment_config,
                'recommendations': self._generate_recommendations(analysis_result)
            }
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'recommendations': ['Check repository URL and permissions']
            }
    
    async def analyze_repository(self, repository_url: str, branch: str) -> Dict[str, Any]:
        """Analyze repository structure and detect application type"""
        try:
            # Extract owner/repo from URL
            repo_path = repository_url.replace('https://github.com/', '').replace('.git', '')
            repo = self.github_client.get_repo(repo_path)
            
            # Get repository contents
            contents = repo.get_contents("", ref=branch)
            file_structure = self._analyze_file_structure(contents, repo, branch)
            
            # Detect application type
            app_type = self._detect_application_type(file_structure)
            
            # Analyze dependencies
            dependencies = await self._analyze_dependencies(repo, branch, app_type)
            
            # Get README and documentation
            documentation = self._get_documentation(repo)
            
            # Analyze Dockerfile if exists
            docker_analysis = self._analyze_dockerfile(repo, branch)
            
            return {
                'repository': repo_path,
                'branch': branch,
                'application_type': app_type,
                'file_structure': file_structure,
                'dependencies': dependencies,
                'documentation': documentation,
                'docker_analysis': docker_analysis,
                'size': repo.size,
                'language': repo.language,
                'topics': repo.get_topics()
            }
            
        except Exception as e:
            logger.error(f"Repository analysis failed: {e}")
            raise
    
    def _analyze_file_structure(self, contents, repo, branch, path="", max_depth=3, current_depth=0):
        """Recursively analyze repository file structure"""
        if current_depth >= max_depth:
            return {}
        
        structure = {
            'files': [],
            'directories': {},
            'key_files': []
        }
        
        for content in contents:
            if content.type == "file":
                structure['files'].append(content.name)
                if self._is_key_file(content.name):
                    structure['key_files'].append({
                        'name': content.name,
                        'path': content.path,
                        'size': content.size
                    })
            elif content.type == "dir" and current_depth < max_depth - 1:
                try:
                    subcontents = repo.get_contents(content.path, ref=branch)
                    structure['directories'][content.name] = self._analyze_file_structure(
                        subcontents, repo, branch, content.path, max_depth, current_depth + 1
                    )
                except:
                    structure['directories'][content.name] = {'error': 'Cannot access'}
        
        return structure
    
    def _is_key_file(self, filename: str) -> bool:
        """Check if file is important for deployment decision"""
        key_files = [
            'package.json', 'requirements.txt', 'pom.xml', 'build.gradle',
            'go.mod', 'Dockerfile', 'docker-compose.yml', 'kubernetes.yaml',
            'deployment.yaml', '.github', 'README.md', 'app.py', 'main.py',
            'server.js', 'app.js', 'index.js', 'manage.py'
        ]
        return any(key in filename.lower() for key in key_files)
    
    def _detect_application_type(self, file_structure: Dict[str, Any]) -> str:
        """Detect application type based on file structure"""
        all_files = self._get_all_files(file_structure)
        
        scores = {}
        for app_type, pattern in self.deployment_patterns.items():
            score = 0
            for indicator in pattern['indicators']:
                if any(indicator.lower() in file.lower() for file in all_files):
                    score += 1
            scores[app_type] = score
        
        # Return the type with highest score, or 'generic' if no match
        if scores:
            best_match = max(scores.items(), key=lambda x: x[1])
            return best_match[0] if best_match[1] > 0 else 'generic'
        return 'generic'
    
    def _get_all_files(self, structure: Dict[str, Any], files=None) -> List[str]:
        """Recursively get all files from structure"""
        if files is None:
            files = []
        
        files.extend(structure.get('files', []))
        for subdir in structure.get('directories', {}).values():
            if isinstance(subdir, dict):
                self._get_all_files(subdir, files)
        
        return files
    
    async def _analyze_dependencies(self, repo, branch: str, app_type: str) -> Dict[str, Any]:
        """Analyze project dependencies"""
        dependencies = {
            'package_managers': [],
            'dependencies': [],
            'dev_dependencies': [],
            'security_vulnerabilities': []
        }
        
        try:
            # Analyze based on application type
            if app_type in ['node_js', 'react']:
                package_json = repo.get_contents("package.json", ref=branch)
                content = json.loads(package_json.decoded_content.decode())
                dependencies['dependencies'] = list(content.get('dependencies', {}).keys())
                dependencies['dev_dependencies'] = list(content.get('devDependencies', {}).keys())
                dependencies['package_managers'].append('npm')
                
            elif app_type in ['python_flask', 'python_django', 'machine_learning']:
                try:
                    requirements = repo.get_contents("requirements.txt", ref=branch)
                    deps = requirements.decoded_content.decode().split('\n')
                    dependencies['dependencies'] = [dep.split('==')[0].strip() for dep in deps if dep.strip()]
                    dependencies['package_managers'].append('pip')
                except:
                    # Try Pipfile
                    try:
                        pipfile = repo.get_contents("Pipfile", ref=branch)
                        dependencies['package_managers'].append('pipenv')
                    except:
                        pass
            
            elif app_type == 'java_spring':
                try:
                    pom = repo.get_contents("pom.xml", ref=branch)
                    dependencies['package_managers'].append('maven')
                except:
                    try:
                        gradle = repo.get_contents("build.gradle", ref=branch)
                        dependencies['package_managers'].append('gradle')
                    except:
                        pass
            
            elif app_type == 'go':
                try:
                    go_mod = repo.get_contents("go.mod", ref=branch)
                    dependencies['package_managers'].append('go-modules')
                except:
                    pass
                    
        except Exception as e:
            logger.warning(f"Dependency analysis failed: {e}")
        
        return dependencies
    
    def _get_documentation(self, repo) -> Dict[str, Any]:
        """Extract documentation and README content"""
        docs = {
            'readme': None,
            'has_docs': False,
            'setup_instructions': False
        }
        
        try:
            readme = repo.get_readme()
            docs['readme'] = readme.decoded_content.decode()[:1000]  # First 1000 chars
            docs['setup_instructions'] = any(word in docs['readme'].lower() 
                                           for word in ['install', 'setup', 'run', 'start'])
        except:
            pass
        
        return docs
    
    def _analyze_dockerfile(self, repo, branch: str) -> Dict[str, Any]:
        """Analyze existing Dockerfile"""
        analysis = {
            'has_dockerfile': False,
            'base_image': None,
            'exposed_ports': [],
            'custom_dockerfile': False
        }
        
        try:
            dockerfile = repo.get_contents("Dockerfile", ref=branch)
            content = dockerfile.decoded_content.decode()
            analysis['has_dockerfile'] = True
            analysis['custom_dockerfile'] = True
            
            # Extract base image
            for line in content.split('\n'):
                if line.strip().startswith('FROM'):
                    analysis['base_image'] = line.split()[1]
                elif line.strip().startswith('EXPOSE'):
                    port = line.split()[1]
                    analysis['exposed_ports'].append(int(port))
                    
        except:
            pass
        
        return analysis
    
    async def generate_deployment_config(self, analysis: Dict[str, Any], 
                                       namespace: str, deployment_type: str) -> Dict[str, Any]:
        """Generate Kubernetes deployment configuration"""
        app_type = analysis['application_type']
        app_name = analysis['repository'].split('/')[-1].lower().replace('_', '-')
        
        # Get deployment pattern
        pattern = self.deployment_patterns.get(app_type, self.deployment_patterns['node_js'])
        
        # Generate configurations
        config = {
            'app_name': app_name,
            'namespace': namespace,
            'application_type': app_type,
            'deployment': self._generate_deployment_yaml(analysis, pattern, app_name, namespace),
            'service': self._generate_service_yaml(app_name, namespace, pattern),
            'route': self._generate_route_yaml(app_name, namespace),
            'dockerfile': self._generate_dockerfile(analysis, pattern) if not analysis['docker_analysis']['has_dockerfile'] else None,
            'github_actions': self._generate_github_actions(analysis, app_name, namespace),
            'resources_needed': self._calculate_resources(analysis, pattern)
        }
        
        return config
    
    def _generate_deployment_yaml(self, analysis: Dict[str, Any], pattern: Dict[str, Any], 
                                app_name: str, namespace: str) -> Dict[str, Any]:
        """Generate Kubernetes Deployment YAML"""
        
        # Determine resource requirements
        resources = pattern.get('resources', {
            'requests': {'cpu': '100m', 'memory': '128Mi'},
            'limits': {'cpu': '500m', 'memory': '512Mi'}
        })
        
        # Special handling for ML workloads
        if analysis['application_type'] == 'machine_learning':
            resources = {
                'requests': {'cpu': '500m', 'memory': '1Gi'},
                'limits': {'cpu': '2000m', 'memory': '4Gi'}
            }
        
        deployment = {
            'apiVersion': 'apps/v1',
            'kind': 'Deployment',
            'metadata': {
                'name': app_name,
                'namespace': namespace,
                'labels': {
                    'app': app_name,
                    'managed-by': 'mcp-model-server',
                    'app-type': analysis['application_type']
                }
            },
            'spec': {
                'replicas': 1,
                'selector': {
                    'matchLabels': {'app': app_name}
                },
                'template': {
                    'metadata': {
                        'labels': {'app': app_name}
                    },
                    'spec': {
                        'containers': [{
                            'name': app_name,
                            'image': f'quay.io/your-org/{app_name}:latest',
                            'ports': [{
                                'containerPort': pattern['port'],
                                'protocol': 'TCP'
                            }],
                            'env': [
                                {'name': 'PORT', 'value': str(pattern['port'])},
                                {'name': 'NODE_ENV', 'value': 'production'}
                            ],
                            'resources': resources,
                            'readinessProbe': {
                                'httpGet': {
                                    'path': pattern['health_path'],
                                    'port': pattern['port']
                                },
                                'initialDelaySeconds': 10,
                                'periodSeconds': 5
                            },
                            'livenessProbe': {
                                'httpGet': {
                                    'path': pattern['health_path'],
                                    'port': pattern['port']
                                },
                                'initialDelaySeconds': 30,
                                'periodSeconds': 10
                            }
                        }]
                    }
                }
            }
        }
        
        return deployment
    
    def _generate_service_yaml(self, app_name: str, namespace: str, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Kubernetes Service YAML"""
        return {
            'apiVersion': 'v1',
            'kind': 'Service',
            'metadata': {
                'name': app_name,
                'namespace': namespace,
                'labels': {'app': app_name}
            },
            'spec': {
                'selector': {'app': app_name},
                'ports': [{
                    'port': 80,
                    'targetPort': pattern['port'],
                    'protocol': 'TCP'
                }],
                'type': 'ClusterIP'
            }
        }
    
    def _generate_route_yaml(self, app_name: str, namespace: str) -> Dict[str, Any]:
        """Generate OpenShift Route YAML"""
        return {
            'apiVersion': 'route.openshift.io/v1',
            'kind': 'Route',
            'metadata': {
                'name': app_name,
                'namespace': namespace,
                'labels': {'app': app_name}
            },
            'spec': {
                'to': {
                    'kind': 'Service',
                    'name': app_name
                },
                'port': {'targetPort': 80},
                'tls': {
                    'termination': 'edge',
                    'insecureEdgeTerminationPolicy': 'Redirect'
                }
            }
        }
    
    def _generate_dockerfile(self, analysis: Dict[str, Any], pattern: Dict[str, Any]) -> str:
        """Generate Dockerfile if not present"""
        app_type = analysis['application_type']
        
        dockerfile_templates = {
            'node_js': f"""FROM {pattern['base_image']}
WORKDIR /app
COPY package*.json ./
RUN {pattern['build_command']}
COPY . .
EXPOSE {pattern['port']}
USER 1001
CMD ["{pattern['start_command'].split()[0]}", "{pattern['start_command'].split()[1]}"]""",

            'python_flask': f"""FROM {pattern['base_image']}
WORKDIR /app
COPY requirements.txt .
RUN {pattern['build_command']}
COPY . .
EXPOSE {pattern['port']}
USER 1001
CMD ["{pattern['start_command'].split()[0]}", "{pattern['start_command'].split()[1]}"]""",

            'react': f"""FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

FROM {pattern['base_image']}
COPY --from=build /app/build /usr/share/nginx/html
COPY --from=build /app/nginx.conf /etc/nginx/nginx.conf
EXPOSE {pattern['port']}
CMD ["{pattern['start_command'].split()[0]}", "{' '.join(pattern['start_command'].split()[1:])}"]"""
        }
        
        return dockerfile_templates.get(app_type, dockerfile_templates['node_js'])
    
    def _generate_github_actions(self, analysis: Dict[str, Any], app_name: str, namespace: str) -> Dict[str, Any]:
        """Generate GitHub Actions workflow"""
        return {
            'name': f'Deploy {app_name}',
            'on': {
                'push': {'branches': ['main']},
                'workflow_dispatch': {}
            },
            'jobs': {
                'deploy': {
                    'runs-on': 'ubuntu-latest',
                    'steps': [
                        {'uses': 'actions/checkout@v4'},
                        {
                            'name': 'Deploy via MCP Model',
                            'run': f'''
curl -X POST ${{{{ secrets.MCP_MODEL_ENDPOINT }}}}/v1/models/mcp-deployment:predict \\
  -H "Content-Type: application/json" \\
  -d "{{
    \\"instances\\": [{{
      \\"repository_url\\": \\"${{{{ github.repository }}}}\\",
      \\"branch\\": \\"${{{{ github.ref_name }}}}\\",
      \\"namespace\\": \\"{namespace}\\",
      \\"deploy_immediately\\": true
    }}]
  }}"
                            '''
                        }
                    ]
                }
            }
        }
    
    def _calculate_resources(self, analysis: Dict[str, Any], pattern: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate required resources based on analysis"""
        base_resources = pattern.get('resources', {
            'requests': {'cpu': '100m', 'memory': '128Mi'},
            'limits': {'cpu': '500m', 'memory': '512Mi'}
        })
        
        # Adjust based on dependencies and repo size
        if analysis.get('size', 0) > 100000:  # Large repo
            base_resources['requests']['memory'] = '256Mi'
            base_resources['limits']['memory'] = '1Gi'
        
        if len(analysis.get('dependencies', {}).get('dependencies', [])) > 50:  # Many deps
            base_resources['requests']['cpu'] = '200m'
            base_resources['limits']['cpu'] = '1000m'
        
        return base_resources
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate deployment recommendations"""
        recommendations = []
        
        if not analysis['docker_analysis']['has_dockerfile']:
            recommendations.append("Consider adding a Dockerfile for consistent deployments")
        
        if not analysis['documentation']['setup_instructions']:
            recommendations.append("Add setup instructions to README for better maintainability")
        
        if analysis['application_type'] == 'generic':
            recommendations.append("Could not detect application type - manual configuration may be needed")
        
        if len(analysis['dependencies']['dependencies']) > 100:
            recommendations.append("Large number of dependencies detected - consider optimization")
        
        if analysis['application_type'] == 'machine_learning':
            recommendations.append("ML workload detected - consider GPU resources for training")
        
        return recommendations
    
    async def deploy_application(self, deployment_config: Dict[str, Any]) -> Dict[str, Any]:
        """Deploy the application to OpenShift"""
        try:
            namespace = deployment_config['namespace']
            app_name = deployment_config['app_name']
            
            # Create namespace if not exists
            await self._ensure_namespace(namespace)
            
            # Apply deployment
            deployment_result = await self._apply_kubernetes_resource(
                deployment_config['deployment']
            )
            
            # Apply service
            service_result = await self._apply_kubernetes_resource(
                deployment_config['service']
            )
            
            # Apply route
            route_result = await self._apply_kubernetes_resource(
                deployment_config['route']
            )
            
            return {
                'status': 'deployed',
                'app_name': app_name,
                'namespace': namespace,
                'deployment': deployment_result,
                'service': service_result,
                'route': route_result,
                'url': f"https://{app_name}-{namespace}.apps.your-cluster.com"
            }
            
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    async def _ensure_namespace(self, namespace: str):
        """Ensure namespace exists"""
        # Implementation for namespace creation
        pass
    
    async def _apply_kubernetes_resource(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Apply Kubernetes resource"""
        # Implementation for applying K8s resources
        pass
