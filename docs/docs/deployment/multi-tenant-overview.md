---
id: multi-tenant-overview
title: Multi-Tenant Kubernetes Deployment
sidebar_label: Overview
sidebar_position: 1
---

# Multi-Tenant Kubernetes Deployment Concept

This document describes the architecture for deploying OpenRAG as a multi-tenant platform on Kubernetes, designed for cooperatives and service providers who want to offer isolated OpenRAG instances to members and customers.

## Requirements

- **Per-tenant LLM keys**: Each tenant brings their own LLM API token (BYOK) or uses managed keys with per-tenant billing
- **Data isolation**: Each tenant has their own frontend, their own data, no cross-tenant access
- **Shared knowledge base**: Organization-wide knowledge accessible to all tenants (read-only)
- **Automated provisioning**: New customers/members get their own instance via GitOps
- **Multi-user per tenant**: Multiple employees within a tenant share the same instance
- **Token billing**: Per-tenant/per-user token consumption tracking
- **Langflow access**: Each tenant can create and use their own Langflow flows

## Architecture: Hybrid (Shared OpenSearch + Per-Tenant Stacks)

The existing Helm chart (`kubernetes/helm/openrag/`) already supports namespace-per-tenant via `global.tenant.name`. Deep multi-tenancy in the code would require a complete rewrite (no tenant awareness in backend, Langflow uses SQLite, LLM keys are singletons). Therefore: **share OpenSearch and Docling, deploy a lightweight per-tenant stack for each customer.**

```
Kubernetes Cluster
|
+-- Shared Infrastructure (deploy once)
|   +-- OpenSearch Cluster (3 Data + 2 Coordinating) .. Namespace: opensearch
|   +-- Docling (Stateless, 1-2 Replicas) ............ Namespace: docling
|   +-- Ingress Controller (nginx, 2 Replicas) ....... Namespace: ingress-nginx
|   +-- cert-manager .................................. Namespace: cert-manager
|   +-- ArgoCD (GitOps Tenant Management) ............. Namespace: argocd
|   +-- [Optional] Prometheus + Grafana ............... Namespace: monitoring
|   +-- [Later] OIDC Provider (Keycloak etc.) ......... Namespace: auth
|
+-- Organization Tenant ("coop-shared")
|   +-- Backend + Frontend + Langflow ................. Namespace: coop-shared
|   +-- OpenSearch Index: documents-coop-shared
|   +-- Read-only for all members, admin-managed
|
+-- Member/Customer Tenants (1 Helm release each)
    +-- "member-alice" ................................ Namespace: member-alice
    |   +-- Backend + Frontend + Langflow
    |   +-- Index: documents-member-alice
    |   +-- Own LLM API keys
    |
    +-- "customer-acme" ............................... Namespace: customer-acme
    |   +-- Backend + Frontend + Langflow
    |   +-- Index: documents-customer-acme
    |   +-- Multiple employees via OAuth
    |
    +-- ... (10-50 tenants)
```

## Tenant Model

### Hierarchy

| Tenant Type | Description | LLM Keys | Users |
|-------------|-------------|----------|-------|
| **Shared Knowledge** (`coop-shared`) | Organization-wide documents. Admin-managed. Read-only for all. | Organization keys | Admins only |
| **Member Tenants** | 1 member = 1 tenant = 1 namespace. BYOK. | Member's own key | Individual or small team |
| **Customer Tenants** | 1 customer = 1 tenant = 1 namespace. Multiple employees. | Customer-provided or managed | Multiple via OAuth/OIDC |

### Tenant Identity

The Helm chart uses `global.tenant.name` for resource naming and namespace isolation (defined in `_helpers.tpl`, lines 12-37). Each Helm release creates resources prefixed with `{tenant-name}-openrag-*`. No chart changes needed for basic tenancy.

## Resources Per Tenant

| Component | Replicas | CPU Request | RAM Request | Storage |
|-----------|----------|-------------|-------------|---------|
| Backend   | 1        | 250m        | 1Gi         | keys 1Gi, config 1Gi |
| Frontend  | 1        | 50m         | 128Mi       | - (stateless) |
| Langflow  | 1        | 250m        | 512Mi       | data 10Gi (SQLite + Flows) |
| **Total** |          | **550m**    | **~1.7Gi**  | **~12Gi** |

## Cluster Sizing (Example: 30 Tenants, 50% active)

| Component | CPU | RAM | Storage |
|-----------|-----|-----|---------|
| Shared Infrastructure | ~24 | ~70Gi | ~650Gi |
| 15 active tenants | 8.25 | 25.5Gi | 180Gi |
| 15 inactive tenants (Scale-to-Zero) | 0 | 0 | 180Gi (PVCs only) |
| **Total** | **~32 CPU** | **~96Gi** | **~1Ti** |

**Recommended nodes**: 4-5 nodes with 8 CPU, 32Gi RAM each.

## Implementation Roadmap

| Phase | Content | Dependencies |
|-------|---------|--------------|
| **1** | Shared Infra (OpenSearch, Docling, Ingress, cert-manager) + first tenant | K8s cluster available |
| **2** | 5-10 additional tenants, ArgoCD GitOps setup | Phase 1 |
| **3** | Shared Knowledge Base (coop-shared tenant + cross-index search) | Phase 1, small code change |
| **4** | Token tracking (log-based with Grafana dashboard) | Phase 1, monitoring stack |
| **5** | Scale-to-Zero with KEDA | Phase 2, >10 tenants |
| **6** | Automated billing (LiteLLM Proxy or Billing API) | Phase 4 |
| **7** | Auth provider decision and integration (Keycloak/Entra ID) | Independent |
| **8** | Network Policies, security hardening, backup strategy | Ongoing |

## Open Decisions

1. **Auth provider**: Keycloak (self-hosted), Google OAuth, Microsoft Entra ID, or other OIDC provider
2. **Token billing method**: Log-based vs. LiteLLM Proxy vs. custom Billing API
3. **Cluster provider**: Bare metal, Hetzner Cloud, IONOS, or other provider
4. **Backup strategy**: OpenSearch Snapshots (S3-compatible) + Velero for PVCs
