#!/bin/bash

# Voice AI System Post-Deployment Configuration Script
set -e

# Get the web app URL from command line argument
WEB_APP_URL=$1

if [ -z "$WEB_APP_URL" ]; then
    echo "❌ Web app URL not provided"
    echo "Usage: $0 <web-app-url>"
    exit 1
fi

echo "🔧 Configuring Voice AI System after deployment..."

# Wait for the application to be ready
echo "⏳ Waiting for application to be ready..."
for i in {1..30}; do
    if curl -f -s "https://$WEB_APP_URL/health" > /dev/null; then
        echo "✅ Application is ready!"
        break
    fi
    
    if [ $i -eq 30 ]; then
        echo "❌ Application failed to start within timeout"
        exit 1
    fi
    
    echo "⏳ Attempt $i/30 - waiting for application..."
    sleep 10
done

# Test the application endpoints
echo "🧪 Testing application endpoints..."

# Test health endpoint
echo "Testing health endpoint..."
HEALTH_RESPONSE=$(curl -s "https://$WEB_APP_URL/health")
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo "✅ Health endpoint working"
else
    echo "❌ Health endpoint failed"
    echo "Response: $HEALTH_RESPONSE"
fi

# Test root endpoint
echo "Testing root endpoint..."
ROOT_RESPONSE=$(curl -s "https://$WEB_APP_URL/")
if echo "$ROOT_RESPONSE" | grep -q "Voice AI System API"; then
    echo "✅ Root endpoint working"
else
    echo "❌ Root endpoint failed"
    echo "Response: $ROOT_RESPONSE"
fi

# Test API documentation
echo "Testing API documentation..."
DOCS_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "https://$WEB_APP_URL/docs")
if [ "$DOCS_RESPONSE" = "200" ]; then
    echo "✅ API documentation accessible"
else
    echo "❌ API documentation not accessible (HTTP $DOCS_RESPONSE)"
fi

# Set up monitoring (if Application Insights is configured)
echo "📊 Setting up monitoring..."

# Create a simple monitoring script
cat > monitor.sh << EOF
#!/bin/bash
# Simple monitoring script for Voice AI System

while true; do
    echo "\$(date): Checking application health..."
    
    if curl -f -s "https://$WEB_APP_URL/health" > /dev/null; then
        echo "✅ Application is healthy"
    else
        echo "❌ Application health check failed"
    fi
    
    sleep 300  # Check every 5 minutes
done
EOF

chmod +x monitor.sh

echo "✅ Post-deployment configuration completed!"
echo ""
echo "🌐 Your Voice AI System is now available at: https://$WEB_APP_URL"
echo "📚 API documentation: https://$WEB_APP_URL/docs"
echo "🔍 Health check: https://$WEB_APP_URL/health"
echo ""
echo "📊 To start monitoring, run: ./monitor.sh"
echo ""
echo "🎉 Deployment successful!" 