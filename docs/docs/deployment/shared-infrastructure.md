---
id: shared-infrastructure
title: Shared Infrastructure
sidebar_label: Shared Infrastructure
sidebar_position: 2
---

# Shared Infrastructure

These components are deployed once and shared across all tenants. They represent the majority of the cluster's resource consumption but provide the foundation for all tenant instances.

## OpenSearch Cluster (Self-Hosted)

The existing `Dockerfile` (project root, 139 lines) builds a custom OpenSearch image with:
- jvector plugin (dense vector search)
- neural-search plugin
- OIDC + DLS security setup (security script auto-configures roles)

### Recommended Topology (10-50 Tenants)

| Role | Nodes | CPU | RAM | Storage | Purpose |
|------|-------|-----|-----|---------|---------|
| Data Nodes | 3 | 4 CPU | 16Gi | 200Gi SSD (PVC) | Index storage, shard hosting |
| Coordinating | 2 | 2 CPU | 4Gi | - | Query routing, load balancing |
| **Total** | 5 | 16 CPU | 56Gi | 600Gi | |

Deploy via the [OpenSearch Helm Chart](https://opensearch.org/docs/latest/install-and-configure/install-opensearch/helm/) or a custom StatefulSet based on the existing `openrag-k8s/base/opensearch.yaml`.

### Index Strategy

Each tenant gets its own set of indices. The `OPENSEARCH_INDEX_NAME` value in the Helm chart controls which index a tenant uses -- this is already implemented.

| Index Pattern | Scope | Purpose |
|---------------|-------|---------|
| `documents-{tenant-name}` | Per-tenant | Document chunks + embeddings |
| `conversations-{tenant-name}` | Per-tenant | Chat conversation history |
| `api_keys-{tenant-name}` | Per-tenant | SDK API keys |
| `knowledge_filters-{tenant-name}` | Per-tenant | Saved search filters |
| `documents-coop-shared` | Shared | Organization-wide knowledge (read-only for tenants) |
| `token_usage` | Shared | Token consumption tracking (tenant field in document) |

## Docling (Document Processing)

Stateless service, safe to share. Deploy 1-2 replicas in namespace `docling`. All tenants point to it via `global.docling.host`.

```yaml
global:
  docling:
    host: docling-serve.docling.svc.cluster.local
    port: 5001
    scheme: "http"
```

## Ingress Controller

nginx-ingress with wildcard DNS:

```
*.openrag.example.com -> Ingress Controller LoadBalancer IP
```

Each tenant gets subdomain-based routing:
- `{tenant}.openrag.example.com` -> Frontend
- `api-{tenant}.openrag.example.com` -> Backend
- `langflow-{tenant}.openrag.example.com` -> Langflow (optional)

TLS via cert-manager with Let's Encrypt wildcard certificate (DNS-01 challenge).

### Ingress Annotations (Recommended)

```yaml
ingress:
  className: "nginx"
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
```

## ArgoCD

Used for GitOps-based tenant provisioning. See [Tenant Provisioning](tenant-provisioning.md) for details.

## Monitoring (Optional)

Prometheus + Grafana for:
- Cluster health monitoring
- Per-tenant resource usage dashboards
- Token consumption tracking (log-based metering)
- Alert rules for unhealthy tenants

## Network Architecture

```
*.openrag.example.com (Wildcard DNS -> Ingress LB)
  |
  +-- openrag.example.com           -> coop-shared (Frontend)
  +-- api.openrag.example.com       -> coop-shared (Backend)
  +-- alice.openrag.example.com     -> member-alice (Frontend)
  +-- api-alice.openrag.example.com -> member-alice (Backend)
  +-- acme.openrag.example.com      -> customer-acme (Frontend)
  +-- api-acme.openrag.example.com  -> customer-acme (Backend)
  +-- langflow-acme.openrag.example.com -> customer-acme (Langflow)
```
