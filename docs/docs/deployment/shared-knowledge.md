---
id: shared-knowledge
title: Shared Knowledge Base
sidebar_label: Shared Knowledge Base
sidebar_position: 6
---

# Shared Knowledge Base

The organization-wide knowledge base is a special tenant that stores documents accessible to all members and customers.

## Architecture

The `coop-shared` tenant is a standard OpenRAG deployment with a special role:

- **Admin-managed**: Only organization admins can upload/modify documents
- **Read-accessible**: All other tenants can search it alongside their own data
- **Separate index**: `documents-coop-shared` in OpenSearch

```
+-- coop-shared namespace
|   +-- Backend (admin access only)
|   +-- Frontend (admin access only)
|   +-- Langflow
|   +-- Index: documents-coop-shared
|
+-- All tenant namespaces
    +-- Search queries go to:
        documents-{tenant-name} (own data)
        + documents-coop-shared (shared knowledge, read-only)
```

## Setup

### 1. Deploy the Shared Knowledge Tenant

Deploy as a standard tenant with `tenant.name: coop-shared`:

```yaml
# tenants/coop-shared/values.yaml
global:
  tenant:
    name: "coop-shared"
  opensearch:
    indexName: "documents-coop-shared"
  oauth:
    google:
      enabled: true
      clientId: "..."        # Restrict to admin accounts
      clientSecret: "..."

ingress:
  hosts:
    frontend:
      host: "knowledge.openrag.example.com"
    backend:
      host: "api-knowledge.openrag.example.com"
```

### 2. Configure OpenSearch Roles

Each tenant's OpenSearch role includes read-only access to `documents-coop-shared` (see [Data Isolation](data-isolation.md#1-index-level-isolation-opensearch)).

### 3. Enable Cross-Index Search

A small code change is needed to make tenant backends search both their own index and the shared index.

**Backend change** (~20 lines in `src/services/search_service.py`):

Add a new environment variable `OPENSEARCH_SHARED_INDEX_NAME`. When set, the search service queries both indices:

```python
# In search_service.py, search_tool method
shared_index = os.getenv("OPENSEARCH_SHARED_INDEX_NAME", "")
indices = f"{index_name},{shared_index}" if shared_index else index_name
results = await opensearch_client.search(index=indices, body=search_body, params=search_params)
```

OpenSearch natively supports comma-separated index patterns in search queries.

**Helm chart change**: Add a new value `backend.sharedIndexName` that is injected as `OPENSEARCH_SHARED_INDEX_NAME` into the backend deployment.

**Per-tenant configuration**:

```yaml
# In each tenant's values.yaml
backend:
  extraEnv:
    - name: OPENSEARCH_SHARED_INDEX_NAME
      value: "documents-coop-shared"
```

The `coop-shared` tenant itself omits this variable (it only searches its own index).

## Managing Shared Content

Admins manage the shared knowledge base through the `coop-shared` Frontend instance:

1. Navigate to `knowledge.openrag.example.com`
2. Upload documents, connect data sources, configure Langflow flows
3. All documents are indexed under `documents-coop-shared`
4. Changes are immediately available to all tenants

## Access Control

- **Write access**: Only the `coop-shared` tenant's backend can write to `documents-coop-shared`
- **Read access**: All tenants can search `documents-coop-shared` (enforced by OpenSearch roles)
- **No modification**: Tenant users cannot modify or delete shared documents
