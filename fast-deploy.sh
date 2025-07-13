#!/bin/bash

# Fast deployment script for existing Azure resources
# Make sure you're in the voice-ai-system directory and have .env configured

echo "🚀 Starting fast deployment..."

# Load environment variables
source .env

# Extract service names from your .env endpoints
SEARCH_SERVICE=$(echo $AZURE_SEARCH_ENDPOINT | sed 's|https://||' | sed 's|\.search\.windows\.net||')
OPENAI_SERVICE=$(echo $AZURE_OPENAI_ENDPOINT | sed 's|https://||' | sed 's|\.openai\.azure\.com/||')

# Set deployment variables
RESOURCE_GROUP="voice-ai-rg"  # Change if yours is different
REGISTRY_NAME="voiceairegistry"  # Change if yours is different
APP_NAME="voice-ai-app"
ENV_NAME="voice-ai-env"

echo "📋 Using these services:"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Registry: $REGISTRY_NAME"
echo "  Search Service: $SEARCH_SERVICE"
echo "  OpenAI Service: $OPENAI_SERVICE"

# Step 1: Create Container Registry (if it doesn't exist)
echo "🔧 Ensuring Container Registry exists..."
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $REGISTRY_NAME \
  --sku Basic \
  --admin-enabled true \
  --only-show-errors || echo "Registry already exists"

# Step 2: Build and push Docker image
echo "🔨 Building and pushing Docker image..."
az acr build \
  --registry $REGISTRY_NAME \
  --image voice-ai:latest \
  --file Dockerfile \
  .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed!"
    exit 1
fi

# Step 3: Create Container Apps environment (if it doesn't exist)
echo "🌍 Ensuring Container Apps environment exists..."
az containerapp env create \
  --name $ENV_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $AZURE_SPEECH_REGION \
  --only-show-errors || echo "Environment already exists"

# Step 4: Deploy Container App
echo "🚢 Deploying Container App..."
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
    "AZURE_SPEECH_KEY=$AZURE_SPEECH_KEY" \
    "AZURE_SPEECH_REGION=$AZURE_SPEECH_REGION" \
    "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT" \
    "AZURE_OPENAI_KEY=$AZURE_OPENAI_KEY" \
    "AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT" \
    "AZURE_SEARCH_ENDPOINT=$AZURE_SEARCH_ENDPOINT" \
    "AZURE_SEARCH_KEY=$AZURE_SEARCH_KEY" \
    "AZURE_SEARCH_INDEX=$AZURE_SEARCH_INDEX" \
    "ENVIRONMENT=$ENVIRONMENT" \
    "LOG_LEVEL=$LOG_LEVEL" \
    "WEBSOCKET_MAX_CONNECTIONS=$WEBSOCKET_MAX_CONNECTIONS" \
    "WEBSOCKET_TIMEOUT=$WEBSOCKET_TIMEOUT" \
  --only-show-errors

if [ $? -ne 0 ]; then
    echo "❌ Container App deployment failed!"
    exit 1
fi

# Step 5: Get application URL
echo "🌐 Getting application URL..."
APP_URL=$(az containerapp show \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query properties.configuration.ingress.fqdn \
  --output tsv)

echo ""
echo "✅ Deployment Complete!"
echo "🌐 Application URL: https://$APP_URL"
echo "📊 Health Check: https://$APP_URL/health"
echo "📖 API Docs: https://$APP_URL/docs"
echo "🎤 Voice Interface: https://$APP_URL/"
echo ""
echo "🧪 Testing deployment..."

# Test health endpoint
if curl -s "https://$APP_URL/health" > /dev/null; then
    echo "✅ Health check passed!"
else
    echo "⚠️  Health check failed - app might still be starting up"
    echo "   Try again in 2-3 minutes"
fi

echo ""
echo "🎯 Next steps:"
echo "1. Test the voice interface at https://$APP_URL/"
echo "2. Upload documents via POST https://$APP_URL/upload_rag_docs"
echo "3. Monitor logs: az containerapp logs tail --name $APP_NAME --resource-group $RESOURCE_GROUP"