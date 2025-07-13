@description('Project name')
param projectName string = 'voice-ai'

@description('Environment name')
param environment string = 'prod'

@description('Location for resources')
param location string = resourceGroup().location

// Variables
var containerAppEnvironmentName = '${projectName}-${environment}-env'
var containerAppName = '${projectName}-${environment}-app'
var containerRegistryName = '${projectName}${environment}registry'
var searchServiceName = '${projectName}-${environment}-search'
var speechServiceName = '${projectName}-${environment}-speech'
var openaiServiceName = '${projectName}-${environment}-openai'

// Log Analytics Workspace
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${projectName}-${environment}-logs'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: containerRegistryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// Container Apps Environment
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// Azure AI Search
resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchServiceName
  location: location
  sku: {
    name: 'standard'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
  }
}

// Speech Service
resource speechService 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: speechServiceName
  location: location
  kind: 'SpeechServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: speechServiceName
    publicNetworkAccess: 'Enabled'
  }
}

// OpenAI Service
resource openaiService 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: openaiServiceName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: openaiServiceName
    publicNetworkAccess: 'Enabled'
  }
}

// Container App
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
        traffic: [
          {
            weight: 100
            latestRevision: true
          }
        ]
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.name
          passwordSecretRef: 'registry-password'
        }
      ]
      secrets: [
        {
          name: 'registry-password'
          value: containerRegistry.listCredentials().passwords[0].value
        }
        {
          name: 'speech-key'
          value: speechService.listKeys().key1
        }
        {
          name: 'openai-key'
          value: openaiService.listKeys().key1
        }
        {
          name: 'search-key'
          value: searchService.listAdminKeys().primaryKey
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'voice-ai-app'
          image: '${containerRegistry.properties.loginServer}/voice-ai:latest'
          resources: {
            cpu: json('2.0')
            memory: '4.0Gi'
          }
          env: [
            {
              name: 'AZURE_SPEECH_KEY'
              secretRef: 'speech-key'
            }
            {
              name: 'AZURE_SPEECH_REGION'
              value: location
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: 'https://${openaiService.properties.endpoint}'
            }
            {
              name: 'AZURE_OPENAI_KEY'
              secretRef: 'openai-key'
            }
            {
              name: 'AZURE_SEARCH_ENDPOINT'
              value: 'https://${searchService.name}.search.windows.net'
            }
            {
              name: 'AZURE_SEARCH_KEY'
              secretRef: 'search-key'
            }
            {
              name: 'ENVIRONMENT'
              value: environment
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 10
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

// Outputs
output containerAppUrl string = containerApp.properties.configuration.ingress.fqdn
output containerRegistryLoginServer string = containerRegistry.properties.loginServer
output searchServiceName string = searchService.name
output speechServiceName string = speechService.name
output openaiServiceName string = openaiService.name 