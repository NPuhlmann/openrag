---
id: llm-keys-billing
title: LLM Keys & Billing
sidebar_label: LLM Keys & Billing
sidebar_position: 5
---

# LLM Key Management & Token Billing

## BYOK (Bring Your Own Key)

Each tenant has their own LLM API keys, configured via two options:

### Option A: Helm Values (Admin-Managed)

Keys are stored as Kubernetes Secrets and injected as environment variables into the backend. This is already fully implemented in the Helm chart.

```yaml
llmProviders:
  anthropic:
    enabled: true
    apiKey: "sk-ant-..."   # Store via Sealed Secrets or External Secrets Operator
  openai:
    enabled: true
    apiKey: "sk-..."
```

The Helm chart creates a `llm-providers-secret` per tenant namespace and mounts it into the backend deployment.

**Best practice**: Use [Sealed Secrets](https://sealed-secrets.netlify.app/) or [External Secrets Operator](https://external-secrets.io/) to avoid plaintext keys in Git.

### Option B: UI-Based (Self-Service)

Tenants enter their API key in the OpenRAG Settings UI. The key is stored in `config/config.yaml` on the config PVC. This is already implemented via the Settings API (`src/api/settings.py`).

This works well for cooperative members who want to manage their own keys without admin intervention.

## Token Usage Tracking

Currently, token counts are logged in `src/agent.py` (lines 200-209) but not persisted. Three options for billing:

### Option A: Log-Based Metering (Simple, Recommended for Start)

Structured logs already contain `input_tokens` and `output_tokens` per LLM response.

1. Deploy a log aggregation stack (Loki + Promtail, or use OpenSearch as log store)
2. Create Grafana dashboards that aggregate token consumption per tenant
3. Monthly manual billing from dashboards

**Pros**: No code changes needed. Quick to set up.
**Cons**: Manual billing process. Limited granularity.

### Option B: OpenSearch Usage Index (Automated)

Create a new `token_usage` index in OpenSearch and persist usage documents after each LLM response.

Usage document schema:

```json
{
  "tenant_id": "customer-acme",
  "user_id": "user@acme.de",
  "user_email": "user@acme.de",
  "timestamp": "2026-03-18T10:30:00Z",
  "provider": "anthropic",
  "model": "claude-sonnet-4-5-20250929",
  "input_tokens": 1500,
  "output_tokens": 800,
  "total_tokens": 2300,
  "flow_type": "chat",
  "estimated_cost_eur": 0.0234
}
```

Requires code changes in:
- `src/agent.py` (~100 lines): Persist usage after `response.completed` events
- New `src/api/billing.py`: REST endpoint for usage queries
- New `src/services/billing_service.py`: Aggregation and report generation

**Pros**: Automated. Fine-grained. Per-user tracking.
**Cons**: Requires code changes. Needs cost maintenance (pricing table).

### Option C: LiteLLM Proxy (Infrastructure Solution, Recommended Long-Term)

Deploy [LiteLLM Proxy](https://docs.litellm.ai/) as a shared service. Each tenant gets a virtual key.

```
Tenant Backend -> LiteLLM Proxy -> LLM Provider (OpenAI, Anthropic, etc.)
```

LiteLLM tracks token usage, costs, and rate limits automatically. It provides a dashboard and API for billing out-of-the-box.

**No code changes in OpenRAG needed** -- only configure `OPENAI_API_BASE` to point to the LiteLLM proxy.

```yaml
# Per-tenant Helm values
backend:
  extraEnv:
    - name: OPENAI_API_BASE
      value: "http://litellm-proxy.litellm.svc.cluster.local:4000"
```

**Pros**: No code changes. Built-in billing, rate limiting, key management. Supports all providers.
**Cons**: Additional infrastructure component. Dependency on LiteLLM project.

### Recommended Approach

1. **Start with Option A** (log-based) for initial deployment
2. **Migrate to Option C** (LiteLLM Proxy) when automated billing is needed
3. Consider **Option B** only if custom billing logic is required

## Cost Calculation

For Options A and B, maintain a pricing table:

```yaml
# config/pricing.yaml
providers:
  anthropic:
    claude-sonnet-4-5-20250929:
      input_per_1k_tokens_eur: 0.003
      output_per_1k_tokens_eur: 0.015
    claude-opus-4-20250514:
      input_per_1k_tokens_eur: 0.015
      output_per_1k_tokens_eur: 0.075
  openai:
    gpt-4o:
      input_per_1k_tokens_eur: 0.005
      output_per_1k_tokens_eur: 0.015
```

## Automated Billing Reports

For automated monthly reports, deploy a CronJob that:
1. Queries the billing API (Option B) or LiteLLM API (Option C)
2. Generates a per-tenant report (CSV/JSON)
3. Sends via email, webhook, or uploads to SFTP (for ERP integration like DATEV)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: billing-report
  namespace: monitoring
spec:
  schedule: "0 2 1 * *"   # 1st of each month at 02:00
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: billing-report
              image: openrag/billing-reporter:latest
              env:
                - name: REPORT_FORMAT
                  value: "csv"
                - name: DELIVERY_METHOD
                  value: "email"
          restartPolicy: OnFailure
```

## Usage Quotas (Optional)

For tenants with managed keys, implement quotas:

- Maximum tokens per month per tenant/user
- Warning at 80%, block at 100%
- Configurable per tenant via Helm values

This requires code changes (Phase 6 of the roadmap) or can be handled by LiteLLM Proxy's built-in rate limiting.
