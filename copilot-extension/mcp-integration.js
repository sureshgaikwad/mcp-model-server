// copilot-extension/mcp-integration.js
class MCPDeploymentClient {
    constructor(modelEndpoint, apiKey) {
        this.modelEndpoint = modelEndpoint;
        this.apiKey = apiKey;
    }

    async analyzeAndDeploy(repositoryUrl, options = {}) {
        const payload = {
            instances: [{
                repository_url: repositoryUrl,
                branch: options.branch || 'main',
                namespace: options.namespace || 'default',
                deployment_type: options.deploymentType || 'auto',
                deploy_immediately: options.deployImmediately || false
            }]
        };

        try {
            const response = await fetch(`${this.modelEndpoint}/v1/models/mcp-deployment:predict`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.apiKey}`
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            return result.predictions[0];
        } catch (error) {
            console.error('MCP Model call failed:', error);
            throw error;
        }
    }

    async getDeploymentStatus(namespace, appName) {
        const payload = {
            instances: [{
                action: 'get_status',
                namespace: namespace,
                app_name: appName
            }]
        };

        const response = await fetch(`${this.modelEndpoint}/v1/models/mcp-deployment:predict`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.apiKey}`
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        return result.predictions[0];
    }
}

// GitHub Copilot Integration
const vscode = require('vscode');

class CopilotMCPProvider {
    constructor() {
        this.mcpClient = new MCPDeploymentClient(
            process.env.MCP_MODEL_ENDPOINT,
            process.env.MCP_API_KEY
        );
    }

    async deployCurrentRepository() {
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            vscode.window.showErrorMessage('No workspace folder found');
            return;
        }

        const gitExtension = vscode.extensions.getExtension('vscode.git')?.exports;
        const git = gitExtension?.getAPI(1);
        const repository = git?.repositories[0];

        if (!repository) {
            vscode.window.showErrorMessage('No Git repository found');
            return;
        }

        const remoteUrl = repository.state.remotes[0]?.fetchUrl || repository.state.remotes[0]?.pushUrl;
        if (!remoteUrl) {
            vscode.window.showErrorMessage('No remote repository URL found');
            return;
        }

        try {
            vscode.window.showInformationMessage('Analyzing repository and generating deployment...');
            
            const result = await this.mcpClient.analyzeAndDeploy(remoteUrl, {
                deployImmediately: true,
                namespace: 'development'
            });

            if (result.status === 'success') {
                vscode.window.showInformationMessage(
                    `✅ Deployment successful! App: ${result.deployment_config.app_name}`
                );
                
                // Show deployment details
                this.showDeploymentDetails(result);
            } else {
                vscode.window.showErrorMessage(`❌ Deployment failed: ${result.error}`);
            }
        } catch (error) {
            vscode.window.showErrorMessage(`❌ Error: ${error.message}`);
        }
    }

    showDeploymentDetails(result) {
        const panel = vscode.window.createWebviewPanel(
            'mcpDeployment',
            'MCP Deployment Results',
            vscode.ViewColumn.One,
            {}
        );

        panel.webview.html = this.getDeploymentWebviewContent(result);
    }

    getDeploymentWebviewContent(result) {
        return `
<!DOCTYPE html>
<html>
<head>
    <title>MCP Deployment Results</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .success { color: green; }
        .error { color: red; }
        .warning { color: orange; }
        .code-block { background: #f5f5f5; padding: 10px; border-radius: 5px; }
        .recommendation { background: #e8f4fd; padding: 10px; margin: 10px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>🚀 MCP Deployment Results</h1>
    
    <h2>Analysis Summary</h2>
    <p><strong>Repository:</strong> ${result.analysis.repository}</p>
    <p><strong>Application Type:</strong> ${result.analysis.application_type}</p>
    <p><strong>Language:</strong> ${result.analysis.language}</p>
    <p><strong>Branch:</strong> ${result.analysis.branch}</p>
    
    <h2>Deployment Configuration</h2>
    <p><strong>App Name:</strong> ${result.deployment_config.app_name}</p>
    <p><strong>Namespace:</strong> ${result.deployment_config.namespace}</p>
    
    ${result.deployment_config.deployment_result ? `
    <h2 class="success">✅ Deployment Status</h2>
    <p><strong>Status:</strong> ${result.deployment_config.deployment_result.status}</p>
    <p><strong>URL:</strong> <a href="${result.deployment_config.deployment_result.url}" target="_blank">${result.deployment_config.deployment_result.url}</a></p>
    ` : ''}
    
    <h2>Recommendations</h2>
    ${result.recommendations.map(rec => `<div class="recommendation">💡 ${rec}</div>`).join('')}
    
    <h2>Generated Kubernetes Configuration</h2>
    <div class="code-block">
        <pre><code>${JSON.stringify(result.deployment_config.deployment, null, 2)}</code></pre>
    </div>
    
    ${result.deployment_config.dockerfile ? `
    <h2>Generated Dockerfile</h2>
    <div class="code-block">
        <pre><code>${result.deployment_config.dockerfile}</code></pre>
    </div>
    ` : ''}
</body>
</html>`;
    }
}

module.exports = { CopilotMCPProvider };
