#!/bin/bash
# deploy-mcp-model.sh

# Create namespace for MCP models
oc create namespace mcp-ai-models

# Label namespace for OpenShift AI
oc label namespace mcp-ai-models opendatahub.io/dashboard=true
oc label namespace mcp-ai-models modelmeshserving.opendatahub.io/enabled=true

# Create service account with required permissions
oc create serviceaccount mcp-model-sa -n mcp-ai-models

# Apply RBAC
cat <<EOF | oc apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: mcp-model-deployer
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps", "secrets", "namespaces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["route.openshift.io"]
  resources: ["routes"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["serving.kserve.io"]
  resources: ["inferenceservices"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: mcp-model-deployer
subjects:
- kind: ServiceAccount
  name: mcp-model-sa
  namespace: mcp-ai-models
roleRef:
  kind: ClusterRole
  name: mcp-model-deployer
  apiGroup: rbac.authorization.k8s.io
EOF

# Build and push model image
docker build -t quay.io/your-org/mcp-deployment-model:latest -f Dockerfile.model .
docker push quay.io/your-org/mcp-deployment-model:latest

# Deploy the InferenceService
oc apply -f k8s/mcp-inference-service.yaml

# Wait for deployment
echo "Waiting for InferenceService to be ready..."
oc wait --for=condition=Ready inferenceservice/mcp-deployment-model -n mcp-ai-models --timeout=300s

# Get the model endpoint
MODEL_ENDPOINT=$(oc get inferenceservice mcp-deployment-model -n mcp-ai-models -o jsonpath='{.status.url}')
echo "MCP Model endpoint: $MODEL_ENDPOINT"

# Test the model
curl -X POST $MODEL_ENDPOINT/v1/models/mcp-deployment:predict \
  -H "Content-Type: application/json" \
  -d '{
    "instances": [{
      "repository_url": "https://github.com/your-org/sample-app",
      "branch": "main",
      "namespace": "development",
      "deployment_type": "auto"
    }]
  }'
