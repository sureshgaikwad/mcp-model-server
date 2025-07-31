// github-copilot-chat-handler.js
const { MCPDeploymentClient } = require('./mcp-integration');

class CopilotChatHandler {
    constructor() {
        this.mcpClient = new MCPDeploymentClient(
            process.env.MCP_MODEL_ENDPOINT,
            process.env.MCP_API_KEY
        );
    }

    async handleChatRequest(request) {
        const { prompt, context } = request;
        
        // Parse deployment-related requests
        if (this.isDeploymentRequest(prompt)) {
            return await this.handleDeploymentRequest(prompt, context);
        }
        
        // Parse analysis requests
        if (this.isAnalysisRequest(prompt)) {
            return await this.handleAnalysisRequest(prompt, context);
        }
        
        // Parse status requests
        if (this.isStatusRequest(prompt)) {
            return await this.handleStatusRequest(prompt, context);
        }
        
        return this.getHelpResponse();
    }

    isDeploymentRequest(prompt) {
        const deploymentKeywords = [
            'deploy', 'deployment', 'create deployment', 'deploy this',
            'deploy to openshift', 'deploy to kubernetes', 'deploy app'
        ];
        return deploymentKeywords.some(keyword => 
            prompt.toLowerCase().includes(keyword)
        );
    }

    isAnalysisRequest(prompt) {
        const analysisKeywords = [
            'analyze', 'analysis', 'what type', 'detect', 'examine',
            'what framework', 'what language', 'repository analysis'
        ];
        return analysisKeywords.some(keyword => 
            prompt.toLowerCase().includes(keyword)
        );
    }

    isStatusRequest(prompt) {
        const statusKeywords = [
            'status', 'health', 'running', 'deployed', 'check deployment',
            'is running', 'deployment status'
        ];
        return statusKeywords.some(keyword => 
            prompt.toLowerCase().includes(keyword)
        );
    }

    async handleDeploymentRequest(prompt, context) {
        try {
            const repositoryUrl = this.extractRepositoryUrl(context);
            if (!repositoryUrl) {
                return {
                    response: "I need a repository URL to deploy. Please open a repository in your workspace or provide a GitHub URL.",
                    suggestions: [
                        "Open a repository in VS Code",
                        "Provide a GitHub repository URL",
                        "Use: 'deploy https://github.com/owner/repo'"
                    ]
                };
            }

            const options = this.parseDeploymentOptions(prompt);
            const result = await this.mcpClient.analyzeAndDeploy(repositoryUrl, {
                ...options,
                deployImmediately: true
            });

            if (result.status === 'success') {
                return {
                    response: `✅ **Deployment Successful!**

**Application:** ${result.deployment_config.app_name}
**Type:** ${result.analysis.application_type}
**Namespace:** ${result.deployment_config.namespace}
**URL:** ${result.deployment_config.deployment_result?.url || 'Pending...'}

**Recommendations:**
${result.recommendations.map(rec => `• ${rec}`).join('\n')}

The application has been deployed to OpenShift AI and should be available shortly.`,
                    actions: [
                        {
                            label: "View Deployment Details",
                            action: "showDeploymentDetails",
                            data: result
                        },
                        {
                            label: "Check Status",
                            action: "checkDeploymentStatus",
                            data: {
                                namespace: result.deployment_config.namespace,
                                appName: result.deployment_config.app_name
                            }
                        }
                    ]
                };
            } else {
                return {
                    response: `❌ **Deployment Failed**

**Error:** ${result.error}

**Suggestions:**
- Check repository permissions
- Verify the repository contains valid application code
- Try with a different branch or configuration

Would you like me to analyze the repository first to identify issues?`,
                    suggestions: [
                        "Analyze repository structure",
                        "Check deployment requirements",
                        "Try with different settings"
                    ]
                };
            }
        } catch (error) {
            return {
                response: `❌ **Error during deployment:** ${error.message}

Please check:
- MCP model endpoint is accessible
- GitHub repository permissions
- OpenShift cluster connectivity`,
                suggestions: [
                    "Check model endpoint configuration",
                    "Verify repository access",
                    "Test with a simpler repository"
                ]
            };
        }
    }

    async handleAnalysisRequest(prompt, context) {
        try {
            const repositoryUrl = this.extractRepositoryUrl(context);
            if (!repositoryUrl) {
                return {
                    response: "Please provide a repository URL or open a repository in your workspace to analyze.",
                    suggestions: ["Open repository in VS Code", "Provide GitHub URL"]
                };
            }

            const result = await this.mcpClient.analyzeAndDeploy(repositoryUrl, {
                deployImmediately: false
            });

            if (result.status === 'success') {
                const analysis = result.analysis;
                return {
                    response: `📊 **Repository Analysis Results**

**Repository:** ${analysis.repository}
**Application Type:** ${analysis.application_type}
**Primary Language:** ${analysis.language}
**Size:** ${this.formatSize(analysis.size)}

**Key Files Detected:**
${analysis.file_structure.key_files.map(file => `• ${file.name}`).join('\n')}

**Dependencies:** ${analysis.dependencies.dependencies.length} packages
**Package Managers:** ${analysis.dependencies.package_managers.join(', ')}

**Docker Analysis:**
${analysis.docker_analysis.has_dockerfile ? '✅ Dockerfile found' : '❌ No Dockerfile detected'}
${analysis.docker_analysis.base_image ? `Base Image: ${analysis.docker_analysis.base_image}` : ''}

**Deployment Readiness:**
${this.assessDeploymentReadiness(analysis)}

**Recommendations:**
${result.recommendations.map(rec => `• ${rec}`).join('\n')}`,
                    actions: [
                        {
                            label: "Deploy Now",
                            action: "deployRepository",
                            data: { repositoryUrl, analysis }
                        },
                        {
                            label: "Generate Deployment Config",
                            action: "generateConfig",
                            data: result.deployment_config
                        }
                    ]
                };
            } else {
                return {
                    response: `❌ **Analysis Failed:** ${result.error}`,
                    suggestions: ["Check repository URL", "Verify repository access"]
                };
            }
        } catch (error) {
            return {
                response: `❌ **Analysis Error:** ${error.message}`,
                suggestions: ["Check repository permissions", "Try again later"]
            };
        }
    }

    async handleStatusRequest(prompt, context) {
        const { namespace, appName } = this.parseStatusRequest(prompt);
        
        if (!namespace || !appName) {
            return {
                response: "Please specify the application name and namespace. Example: 'check status of myapp in development namespace'",
                suggestions: [
                    "check status of <app-name> in <namespace>",
                    "deployment status myapp development"
                ]
            };
        }

        try {
            const status = await this.mcpClient.getDeploymentStatus(namespace, appName);
            
            return {
                response: `📊 **Deployment Status: ${appName}**

**Namespace:** ${namespace}
**Replicas:** ${status.deployment?.readyReplicas}/${status.deployment?.replicas}
**Status:** ${this.getDeploymentStatus(status)}

**Pods:**
${status.pods?.map(pod => `• ${pod.name}: ${pod.phase} (Ready: ${pod.ready ? '✅' : '❌'})`).join('\n')}

**Services:**
${status.services?.map(svc => `• ${svc.name}: ${svc.type} (${svc.clusterIP})`).join('\n')}

**Routes:**
${status.routes?.map(route => `• ${route.url}`).join('\n') || 'No external routes configured'}`,
                actions: status.routes?.length > 0 ? [
                    {
                        label: "Open Application",
                        action: "openUrl",
                        data: { url: status.routes[0].url }
                    }
                ] : []
            };
        } catch (error) {
            return {
                response: `❌ **Status Check Failed:** ${error.message}`,
                suggestions: ["Verify application name and namespace", "Check if application is deployed"]
            };
        }
    }

    extractRepositoryUrl(context) {
        // Extract from current workspace or context
        if (context.workspaceUri) {
            // Get Git remote URL from workspace
            return this.getGitRemoteUrl(context.workspaceUri);
        }
        
        // Extract from chat context if URL is mentioned
        const urlPattern = /https:\/\/github\.com\/[\w-]+\/[\w-]+/;
        const match = context.prompt?.match(urlPattern);
        return match ? match[0] : null;
    }

    parseDeploymentOptions(prompt) {
        const options = {};
        
        // Extract namespace
        const namespacePattern = /(?:in|to|namespace)\s+(\w+)/i;
        const namespaceMatch = prompt.match(namespacePattern);
        if (namespaceMatch) {
            options.namespace = namespaceMatch[1];
        }
        
        // Extract branch
        const branchPattern = /(?:branch|from)\s+(\w+)/i;
        const branchMatch = prompt.match(branchPattern);
        if (branchMatch) {
            options.branch = branchMatch[1];
        }
        
        return options;
    }

    parseStatusRequest(prompt) {
        // Extract app name and namespace from status request
        const patterns = [
            /status of (\w+) in (\w+)/i,
            /(\w+) in (\w+) namespace/i,
            /deployment (\w+) (\w+)/i
        ];
        
        for (const pattern of patterns) {
            const match = prompt.match(pattern);
            if (match) {
                return { appName: match[1], namespace: match[2] };
            }
        }
        
        return { namespace: null, appName: null };
    }

    formatSize(sizeKb) {
        if (sizeKb < 1024) return `${sizeKb} KB`;
        if (sizeKb < 1024 * 1024) return `${(sizeKb / 1024).toFixed(1)} MB`;
        return `${(sizeKb / (1024 * 1024)).toFixed(1)} GB`;
    }

    assessDeploymentReadiness(analysis) {
        const issues = [];
        if (!analysis.docker_analysis.has_dockerfile) issues.push('No Dockerfile');
        if (!analysis.documentation.setup_instructions) issues.push('Missing setup instructions');
        if (analysis.application_type === 'generic') issues.push('Unknown application type');
        
        return issues.length === 0 ? '✅ Ready for deployment' : `⚠️ Issues: ${issues.join(', ')}`;
    }

    getDeploymentStatus(status) {
        if (!status.deployment) return '❌ Not found';
        if (status.deployment.readyReplicas === status.deployment.replicas) {
            return '✅ Running';
        } else if (status.deployment.readyReplicas === 0) {
            return '⏳ Starting';
        } else {
            return '⚠️ Partially running';
        }
    }

    getHelpResponse() {
        return {
            response: `🚀 **MCP OpenShift Deployment Assistant**

I can help you deploy applications to OpenShift AI! Here's what I can do:

**Deployment Commands:**
- "Deploy this repository to OpenShift"
- "Deploy to development namespace"
- "Deploy from main branch"

**Analysis Commands:**
- "Analyze this repository"
- "What type of application is this?"
- "Check if this is ready for deployment"

**Status Commands:**
- "Check status of myapp in development"
- "Is my deployment running?"
- "Show deployment health"

**Examples:**
- "Deploy https://github.com/myorg/webapp to production"
- "Analyze current repository for deployment"
- "Check status of api-server in staging namespace"

What would you like me to help you with?`,
            suggestions: [
                "Deploy current repository",
                "Analyze repository structure", 
                "Check deployment status",
                "Show deployment examples"
            ]
        };
    }
}

module.exports = { CopilotChatHandler };
