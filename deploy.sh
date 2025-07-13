#!/bin/bash

# Configuration
RESOURCE_GROUP="voice-ai-rg"
LOCATION="eastus"
REGISTRY_NAME="voiceairegistry"
APP_NAME="voice-ai-app"
ENV_NAME="voice-ai-env"
SEARCH_SERVICE="voice-ai-search"
SPEECH_SERVICE="voice-ai-speech"
OPENAI_SERVICE="voice-ai-openai"

echo "🚀 Deploying Azure Voice AI System..."

# Create resource group
echo "Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Log Analytics workspace
echo "Creating Log Analytics workspace..."
az monitor log-analytics workspace create \
  --resource-group $RESOURCE_GROUP \
  --workspace-name voice-ai-logs \
  --location $LOCATION

# Create Container Registry
echo "Creating Container Registry..."
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $REGISTRY_NAME \
  --sku Basic \
  --admin-enabled true

# Create Azure AI Search
echo "Creating Azure AI Search..."
az search service create \
  --resource-group $RESOURCE_GROUP \
  --name $SEARCH_SERVICE \
  --sku Standard \
  --location $LOCATION

# Create Speech Service
echo "Creating Speech Service..."
az cognitiveservices account create \
  --name $SPEECH_SERVICE \
  --resource-group $RESOURCE_GROUP \
  --kind SpeechServices \
  --sku S0 \
  --location $LOCATION

# Create OpenAI Service
echo "Creating OpenAI Service..."
az cognitiveservices account create \
  --name $OPENAI_SERVICE \
  --resource-group $RESOURCE_GROUP \
  --kind OpenAI \
  --sku S0 \
  --location $LOCATION

# Build and push Docker image
echo "Building and pushing Docker image..."
az acr build \
  --registry $REGISTRY_NAME \
  --image voice-ai:latest \
  --file Dockerfile \
  .

# Create Container Apps environment
echo "Creating Container Apps environment..."
az containerapp env create \
  --name $ENV_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Get service keys
SPEECH_KEY=$(az cognitiveservices account keys list \
  --name $SPEECH_SERVICE \
  --resource-group $RESOURCE_GROUP \
  --query key1 --output tsv)

OPENAI_KEY=$(az cognitiveservices account keys list \
  --name $OPENAI_SERVICE \
  --resource-group $RESOURCE_GROUP \
  --query key1 --output tsv)

SEARCH_KEY=$(az search admin-key show \
  --service-name $SEARCH_SERVICE \
  --resource-group $RESOURCE_GROUP \
  --query primaryKey --output tsv)

# Deploy Container App
echo "Deploying Container App..."
az containerapp create \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $ENV_NAME \
  --image $REGISTRY_NAME.azurecr.io/voice-ai:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10 \
  --cpu 2.0 \
  --memory 4.0Gi \
  --registry-server $REGISTRY_NAME.azurecr.io \
  --env-vars \
    "AZURE_SPEECH_KEY=$SPEECH_KEY" \
    "AZURE_SPEECH_REGION=$LOCATION" \
    "AZURE_OPENAI_ENDPOINT=https://$OPENAI_SERVICE.openai.azure.com/" \
    "AZURE_OPENAI_KEY=$OPENAI_KEY" \
    "AZURE_SEARCH_ENDPOINT=https://$SEARCH_SERVICE.search.windows.net" \
    "AZURE_SEARCH_KEY=$SEARCH_KEY" \
    "ENVIRONMENT=production"

# Get application URL
APP_URL=$(az containerapp show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

echo "✅ Deployment complete!"
echo "🌐 Application URL: https://$APP_URL"
echo "📊 Health Check: https://$APP_URL/health"
echo "📖 API Docs: https://$APP_URL/docs" 