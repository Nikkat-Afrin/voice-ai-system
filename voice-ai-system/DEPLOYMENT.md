# Azure Voice AI System Deployment Guide

This guide provides step-by-step instructions for deploying the Azure-based real-time voice conversational AI system to production.

## Prerequisites

### Required Azure Services
- Azure subscription with billing enabled
- Azure CLI installed and authenticated
- Docker installed locally
- Git repository access

### Azure Permissions
- Owner or Contributor role on the subscription
- Ability to create and manage:
  - Resource Groups
  - Container Apps
  - Container Registry
  - Cognitive Services (Speech, OpenAI)
  - AI Search
  - Log Analytics

## Deployment Options

### Option 1: Automated Deployment (Recommended)

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd voice-ai-system
   ```

2. **Configure Environment**
   ```bash
   cp env.example .env
   # Edit .env with your Azure service keys (optional for automated deployment)
   ```

3. **Run Deployment Script**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

   The script will:
   - Create all required Azure resources
   - Build and push the Docker image
   - Deploy to Azure Container Apps
   - Configure environment variables and secrets

### Option 2: Infrastructure as Code (Bicep)

1. **Deploy Infrastructure**
   ```bash
   az deployment group create \
     --resource-group voice-ai-rg \
     --template-file bicep/main.bicep \
     --parameters projectName=voice-ai environment=prod
   ```

2. **Build and Deploy Application**
   ```bash
   # Build and push Docker image
   az acr build \
     --registry voiceairegistry \
     --image voice-ai:latest \
     --file Dockerfile \
     .
   
   # Deploy to Container Apps
   az containerapp update \
     --name voice-ai-app \
     --resource-group voice-ai-rg \
     --image voiceairegistry.azurecr.io/voice-ai:latest
   ```

### Option 3: Manual Deployment

#### Step 1: Create Azure Resources

1. **Resource Group**
   ```bash
   az group create --name voice-ai-rg --location eastus
   ```

2. **Container Registry**
   ```bash
   az acr create \
     --resource-group voice-ai-rg \
     --name voiceairegistry \
     --sku Basic \
     --admin-enabled true
   ```

3. **Log Analytics Workspace**
   ```bash
   az monitor log-analytics workspace create \
     --resource-group voice-ai-rg \
     --workspace-name voice-ai-logs \
     --location eastus
   ```

4. **Container Apps Environment**
   ```bash
   az containerapp env create \
     --name voice-ai-env \
     --resource-group voice-ai-rg \
     --location eastus
   ```

5. **Azure AI Search**
   ```bash
   az search service create \
     --resource-group voice-ai-rg \
     --name voice-ai-search \
     --sku Standard \
     --location eastus
   ```

6. **Speech Service**
   ```bash
   az cognitiveservices account create \
     --name voice-ai-speech \
     --resource-group voice-ai-rg \
     --kind SpeechServices \
     --sku S0 \
     --location eastus
   ```

7. **OpenAI Service**
   ```bash
   az cognitiveservices account create \
     --name voice-ai-openai \
     --resource-group voice-ai-rg \
     --kind OpenAI \
     --sku S0 \
     --location eastus
   ```

#### Step 2: Build and Push Docker Image

```bash
# Login to ACR
az acr login --name voiceairegistry

# Build and push
az acr build \
  --registry voiceairegistry \
  --image voice-ai:latest \
  --file Dockerfile \
  .
```

#### Step 3: Deploy Container App

```bash
# Get service keys
SPEECH_KEY=$(az cognitiveservices account keys list \
  --name voice-ai-speech \
  --resource-group voice-ai-rg \
  --query key1 --output tsv)

OPENAI_KEY=$(az cognitiveservices account keys list \
  --name voice-ai-openai \
  --resource-group voice-ai-rg \
  --query key1 --output tsv)

SEARCH_KEY=$(az search admin-key show \
  --service-name voice-ai-search \
  --resource-group voice-ai-rg \
  --query primaryKey --output tsv)

# Deploy Container App
az containerapp create \
  --name voice-ai-app \
  --resource-group voice-ai-rg \
  --environment voice-ai-env \
  --image voiceairegistry.azurecr.io/voice-ai:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10 \
  --cpu 2.0 \
  --memory 4.0Gi \
  --registry-server voiceairegistry.azurecr.io \
  --env-vars \
    "AZURE_SPEECH_KEY=$SPEECH_KEY" \
    "AZURE_SPEECH_REGION=eastus" \
    "AZURE_OPENAI_ENDPOINT=https://voice-ai-openai.openai.azure.com/" \
    "AZURE_OPENAI_KEY=$OPENAI_KEY" \
    "AZURE_SEARCH_ENDPOINT=https://voice-ai-search.search.windows.net" \
    "AZURE_SEARCH_KEY=$SEARCH_KEY" \
    "ENVIRONMENT=production"
```

## Post-Deployment Configuration

### 1. Configure Azure AI Search Index

```bash
# Create search index for RAG
az search index create \
  --service-name voice-ai-search \
  --resource-group voice-ai-rg \
  --name rag-index \
  --schema @search-index-schema.json
```

### 2. Set Up Monitoring

```bash
# Enable Application Insights
az containerapp update \
  --name voice-ai-app \
  --resource-group voice-ai-rg \
  --enable-app-insights
```

### 3. Configure Custom Domain (Optional)

```bash
# Add custom domain
az containerapp hostname add \
  --name voice-ai-app \
  --resource-group voice-ai-rg \
  --hostname your-domain.com
```

## CI/CD Pipeline Setup

### GitHub Actions

1. **Add Repository Secrets**
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`

2. **Configure Service Principal**
   ```bash
   az ad sp create-for-rbac \
     --name voice-ai-sp \
     --role contributor \
     --scopes /subscriptions/<subscription-id>/resourceGroups/voice-ai-rg
   ```

3. **Enable GitHub Actions**
   - Push to main branch triggers deployment
   - Pull requests run tests only

## Environment Variables

### Required Variables
```bash
AZURE_SPEECH_KEY=your_speech_key
AZURE_SPEECH_REGION=eastus
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com/
AZURE_OPENAI_KEY=your_openai_key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_KEY=your_search_key
AZURE_SEARCH_INDEX=rag-index
```

### Optional Variables
```bash
ENVIRONMENT=production
LOG_LEVEL=info
WEBSOCKET_MAX_CONNECTIONS=1000
WEBSOCKET_TIMEOUT=300
```

## Security Configuration

### 1. Network Security
```bash
# Configure private endpoints (optional)
az network private-endpoint create \
  --name voice-ai-pe \
  --resource-group voice-ai-rg \
  --vnet-name your-vnet \
  --subnet your-subnet \
  --private-connection-resource-id <container-app-id>
```

### 2. Managed Identity
```bash
# Enable managed identity
az containerapp identity assign \
  --name voice-ai-app \
  --resource-group voice-ai-rg \
  --system-assigned
```

### 3. Key Vault Integration
```bash
# Store secrets in Key Vault
az keyvault secret set \
  --vault-name your-keyvault \
  --name azure-speech-key \
  --value $SPEECH_KEY
```

## Monitoring and Logging

### 1. Application Insights
- Performance monitoring
- Error tracking
- User analytics
- Custom metrics

### 2. Log Analytics
- Centralized logging
- Query capabilities
- Alerting rules

### 3. Health Checks
```bash
# Test health endpoint
curl https://your-app-url.azurecontainerapps.io/health
```

## Scaling Configuration

### Auto-scaling Rules
```bash
# Configure scaling rules
az containerapp revision set-mode \
  --name voice-ai-app \
  --resource-group voice-ai-rg \
  --mode multiple

az containerapp update \
  --name voice-ai-app \
  --resource-group voice-ai-rg \
  --min-replicas 1 \
  --max-replicas 10 \
  --scale-rule-name http-scaling \
  --scale-rule-type http \
  --scale-rule-metadata concurrentRequests=100
```

## Troubleshooting

### Common Issues

1. **Container App Not Starting**
   ```bash
   # Check logs
   az containerapp logs show \
     --name voice-ai-app \
     --resource-group voice-ai-rg
   ```

2. **WebSocket Connection Issues**
   - Verify Container Apps WebSocket support
   - Check CORS configuration
   - Validate SSL certificates

3. **Azure Service Authentication**
   ```bash
   # Test service connectivity
   az cognitiveservices account show \
     --name voice-ai-speech \
     --resource-group voice-ai-rg
   ```

### Performance Optimization

1. **Resource Allocation**
   - CPU: 2.0 cores minimum
   - Memory: 4.0Gi minimum
   - Adjust based on load testing

2. **Caching Strategy**
   - Implement Redis for session storage
   - Use CDN for static assets
   - Enable response caching

3. **Database Optimization**
   - Use Azure AI Search for RAG
   - Implement connection pooling
   - Optimize query performance

## Cost Optimization

### Resource Sizing
- Start with minimal resources
- Monitor usage patterns
- Scale based on actual demand

### Reserved Instances
```bash
# Purchase reserved capacity for cost savings
az cognitiveservices account create \
  --name voice-ai-speech \
  --resource-group voice-ai-rg \
  --kind SpeechServices \
  --sku S0 \
  --location eastus \
  --capacity 1
```

## Backup and Recovery

### 1. Configuration Backup
```bash
# Export Container App configuration
az containerapp show \
  --name voice-ai-app \
  --resource-group voice-ai-rg \
  --output json > backup-config.json
```

### 2. Data Backup
- Azure AI Search: Built-in backup
- Session data: Implement persistent storage
- Logs: Azure Monitor retention policies

## Maintenance

### Regular Tasks
1. **Security Updates**
   - Update base images
   - Patch dependencies
   - Review access permissions

2. **Performance Monitoring**
   - Review metrics
   - Optimize resource usage
   - Update scaling rules

3. **Backup Verification**
   - Test recovery procedures
   - Validate data integrity
   - Update documentation

## Support and Resources

### Documentation
- [Azure Container Apps](https://docs.microsoft.com/en-us/azure/container-apps/)
- [Azure Speech Services](https://docs.microsoft.com/en-us/azure/cognitive-services/speech-service/)
- [Azure OpenAI](https://docs.microsoft.com/en-us/azure/cognitive-services/openai/)

### Community
- Azure Community Forums
- GitHub Issues
- Stack Overflow

### Professional Support
- Azure Support Plans
- Microsoft Consulting Services
- Partner Solutions 