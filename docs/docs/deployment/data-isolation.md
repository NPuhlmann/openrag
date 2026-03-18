---
id: data-isolation
title: Data Isolation
sidebar_label: Data Isolation
sidebar_position: 3
---

# Data Isolation

Data isolation is enforced at three layers: OpenSearch index level, Kubernetes network level, and storage level.

## 1. Index-Level Isolation (OpenSearch)

Each tenant has its own OpenSearch indices. Isolation is enforced by:

1. **`OPENSEARCH_INDEX_NAME`** in the Helm chart -- each tenant's backend reads/writes only its own index
2. **OpenSearch Security Roles** -- even if a bug occurs, a tenant user can only access their own indices

### OpenSearch Security Role (Per Tenant)

For each tenant, create a security role that restricts index access:

```yaml
# Role: tenant_customer_acme
tenant_customer_acme:
  cluster_permissions: []
  index_permissions:
    - index_patterns:
        - "documents-customer-acme"
        - "conversations-customer-acme"
        - "api_keys-customer-acme"
        - "knowledge_filters-customer-acme"
      allowed_actions:
        - "crud"
        - "create_index"
        - "manage"
        - "indices:data/*"
    - index_patterns:
        - "documents-coop-shared"
      allowed_actions:
        - "read"
        - "search"            # Read-only access to shared knowledge
```

Create a corresponding role mapping to bind the tenant's OpenSearch user to this role:

```yaml
tenant_customer_acme:
  backend_roles: []
  users:
    - "tenant-customer-acme"
```

### Provisioning OpenSearch Roles

Roles can be created via the OpenSearch Security REST API:

```bash
curl -XPUT "https://opensearch:9200/_plugins/_security/api/roles/tenant_customer_acme" \
  -H 'Content-Type: application/json' \
  -u admin:password \
  -d @role-definition.json
```

This should be automated as part of tenant provisioning (see [Tenant Provisioning](tenant-provisioning.md)).

## 2. Network-Level Isolation (Kubernetes Network Policies)

Each tenant namespace gets a NetworkPolicy that restricts communication:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: tenant-isolation
  namespace: customer-acme
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
  ingress:
    - from:
      - namespaceSelector:
          matchLabels:
            app.kubernetes.io/name: ingress-nginx
  egress:
    - to:                               # OpenSearch
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: opensearch
      ports:
        - port: 9200
          protocol: TCP
    - to:                               # Docling
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: docling
      ports:
        - port: 5001
          protocol: TCP
    - to:                               # External LLM APIs
      - ipBlock:
          cidr: 0.0.0.0/0
          except:
            - 10.0.0.0/8
            - 172.16.0.0/12
            - 192.168.0.0/16
    - to:                               # Cluster DNS
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
```

This ensures:
- Tenants can only receive traffic from the ingress controller
- Tenants can only connect to OpenSearch, Docling, external APIs, and DNS
- **No cross-tenant pod communication** is possible

## 3. Storage-Level Isolation

Each tenant has its own PersistentVolumeClaims:
- `keys` (1Gi) -- RSA keys for JWT signing
- `config` (1Gi) -- Application configuration including LLM keys
- `langflow-data` (10Gi) -- Langflow SQLite database and custom flows

No shared storage between tenants. PVCs are created per Helm release in the tenant's namespace.

## 4. Multi-User Within a Tenant

Within a customer tenant, multiple employees can work together:

- All users authenticate via OAuth/OIDC (provider configurable per tenant)
- Each user gets a unique `user_id` from the OAuth `sub` claim
- Documents have `owner` and `allowed_users` fields for ACL within the tenant
- OpenSearch Document-Level Security (DLS) can filter within the tenant index by user
- All users in a tenant share the same LLM keys and Langflow flows

### Existing ACL Fields in Document Schema

The OpenSearch document mapping already includes:

```python
"owner": {"type": "keyword"}              # Document owner user_id
"allowed_users": {"type": "keyword"}      # List of user emails with read access
"allowed_groups": {"type": "keyword"}     # List of group IDs with read access
"user_permissions": {"type": "object"}    # Fine-grained per-user permissions
"group_permissions": {"type": "object"}   # Per-group permissions
```

These fields are populated automatically:
- **Uploaded files**: `owner` = uploading user
- **Google Drive**: `allowed_users` extracted from sharing permissions
- **OneDrive/SharePoint**: `allowed_users` extracted from SharePoint permissions
