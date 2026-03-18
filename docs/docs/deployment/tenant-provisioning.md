---
id: tenant-provisioning
title: Tenant Provisioning
sidebar_label: Tenant Provisioning
sidebar_position: 4
---

# Automated Tenant Provisioning

New tenants are provisioned via GitOps (ArgoCD) or manually via Helm CLI.

## GitOps with ArgoCD ApplicationSet (Recommended)

### Tenants Repository

All tenant configurations are managed in a Git repository:

```
openrag-tenants/
  base/
    shared-infrastructure/
      opensearch/          # OpenSearch Helm values
      docling/             # Docling deployment
      ingress/             # Ingress controller config
  tenants/
    coop-shared/
      values.yaml          # Organization shared knowledge base
    member-alice/
      values.yaml          # Alice's configuration
    customer-acme/
      values.yaml          # ACME's configuration
    ...
```

### ArgoCD ApplicationSet

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: openrag-tenants
  namespace: argocd
spec:
  generators:
    - git:
        repoURL: https://git.example.com/openrag/tenants.git
        revision: main
        files:
          - path: "tenants/*/values.yaml"
  template:
    metadata:
      name: "openrag-{{path.basename}}"
    spec:
      project: default
      sources:
        - repoURL: https://github.com/langflow-ai/openrag
          targetRevision: v0.3.2
          path: kubernetes/helm/openrag
          helm:
            valueFiles:
              - "$values/tenants/{{path.basename}}/values.yaml"
        - repoURL: https://git.example.com/openrag/tenants.git
          targetRevision: main
          ref: values
      destination:
        namespace: "{{path.basename}}"
        server: https://kubernetes.default.svc
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

### Workflow

**Add a new customer**: Push a `values.yaml` to the tenants repo. ArgoCD will:
1. Detect the new directory
2. Create the namespace
3. Deploy the Helm release
4. Sync + health check automatically

**Remove a customer**: Delete the directory. ArgoCD cleans up (`prune: true`).

**Update a customer**: Modify the `values.yaml`. ArgoCD syncs the changes.

## Example Tenant Values File

```yaml
# tenants/customer-acme/values.yaml
global:
  tenant:
    name: "customer-acme"
  imageTag: "0.3.2"
  opensearch:
    host: "opensearch-coordinating.opensearch.svc.cluster.local"
    port: 9200
    indexName: "documents-customer-acme"
    username: "tenant-customer-acme"
    password: "<from Sealed Secret>"
  docling:
    host: "docling-serve.docling.svc.cluster.local"
  oauth:
    google:
      enabled: true
      clientId: "..."
      clientSecret: "..."

backend:
  resources:
    requests: { cpu: "250m", memory: "1Gi" }
    limits: { cpu: "2", memory: "4Gi" }

frontend:
  replicaCount: 1
  resources:
    requests: { cpu: "50m", memory: "128Mi" }
    limits: { cpu: "500m", memory: "512Mi" }

langflow:
  resources:
    requests: { cpu: "250m", memory: "512Mi" }
    limits: { cpu: "2", memory: "4Gi" }

llmProviders:
  anthropic:
    enabled: true
    apiKey: "<customer's own key or managed key>"

ingress:
  hosts:
    frontend:
      host: "acme.openrag.example.com"
    backend:
      host: "api-acme.openrag.example.com"
    langflow:
      enabled: true
      host: "langflow-acme.openrag.example.com"
  tls:
    enabled: true
    certManager:
      enabled: true
      issuerRef:
        name: "letsencrypt-prod"
        kind: "ClusterIssuer"
```

## Manual Provisioning (Helm CLI)

For initial setup or when ArgoCD is not yet deployed:

```bash
helm install openrag-customer-acme ./kubernetes/helm/openrag \
  -f values-customer-acme.yaml \
  -n customer-acme --create-namespace
```

## Additional Provisioning Steps

ArgoCD handles the Helm release, but some steps need additional automation:

### 1. OpenSearch Security Role + User

Create via OpenSearch Security REST API (automate in a provisioning script):

```bash
# Create role
curl -XPUT "https://opensearch:9200/_plugins/_security/api/roles/tenant_customer_acme" \
  -H 'Content-Type: application/json' \
  -u admin:$ADMIN_PASSWORD \
  -d '{
    "index_permissions": [
      {
        "index_patterns": [
          "documents-customer-acme",
          "conversations-customer-acme",
          "api_keys-customer-acme",
          "knowledge_filters-customer-acme"
        ],
        "allowed_actions": ["crud", "create_index", "manage", "indices:data/*"]
      },
      {
        "index_patterns": ["documents-coop-shared"],
        "allowed_actions": ["read", "search"]
      }
    ]
  }'

# Create user
curl -XPUT "https://opensearch:9200/_plugins/_security/api/internalusers/tenant-customer-acme" \
  -H 'Content-Type: application/json' \
  -u admin:$ADMIN_PASSWORD \
  -d '{
    "password": "<generated-password>",
    "backend_roles": ["tenant_customer_acme"]
  }'

# Create role mapping
curl -XPUT "https://opensearch:9200/_plugins/_security/api/rolesmapping/tenant_customer_acme" \
  -H 'Content-Type: application/json' \
  -u admin:$ADMIN_PASSWORD \
  -d '{
    "users": ["tenant-customer-acme"]
  }'
```

### 2. DNS Record (if no wildcard)

Create an A/CNAME record for `acme.openrag.example.com` pointing to the ingress controller.

With wildcard DNS (`*.openrag.example.com`), this step is not needed.

### 3. Welcome Email

Send the tenant admin their login URL and initial setup instructions.

### 4. OAuth Client Registration (if using Keycloak)

Register a new OAuth client for the tenant in the OIDC provider.

## Tenant Deprovisioning

1. Create final billing report
2. Optional: Export tenant data (documents, conversations)
3. `helm uninstall openrag-customer-acme -n customer-acme`
4. `kubectl delete namespace customer-acme`
5. Clean up OpenSearch indices and security roles
6. Remove DNS record (if not wildcard)
