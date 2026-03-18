---
id: scaling
title: Scaling & Optimization
sidebar_label: Scaling & Optimization
sidebar_position: 7
---

# Scaling & Resource Optimization

## Scale-to-Zero for Inactive Tenants

With 10-50 tenants, many will be inactive at any given time. [KEDA](https://keda.sh/) (Kubernetes Event-Driven Autoscaling) can scale tenant deployments to zero replicas when idle.

### KEDA ScaledObject (Per Tenant)

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: backend-scaler
  namespace: customer-acme
spec:
  scaleTargetRef:
    name: customer-acme-openrag-backend
  minReplicaCount: 0
  maxReplicaCount: 1
  idleReplicaCount: 0
  cooldownPeriod: 3600            # 1 hour of inactivity -> scale to 0
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.monitoring.svc.cluster.local:9090
        metricName: nginx_ingress_controller_requests
        query: |
          sum(rate(nginx_ingress_controller_requests_total{
            exported_namespace="customer-acme"
          }[5m]))
        threshold: "0.001"
```

Apply similar ScaledObjects for the frontend and Langflow deployments in the same namespace.

### Startup Latency

When a scaled-to-zero tenant receives a request, pods need ~30-60 seconds to start. The ingress can show a "Loading..." page during startup using nginx custom error pages:

```yaml
# Ingress annotation
nginx.ingress.kubernetes.io/custom-http-errors: "503"
nginx.ingress.kubernetes.io/default-backend: loading-page
```

### Savings

| Scenario | Active Tenants | Idle Tenants | CPU Used | RAM Used |
|----------|----------------|--------------|----------|----------|
| Without KEDA | 30 | 0 | 16.5 | 51Gi |
| With KEDA (50% idle) | 15 | 15 | 8.25 | 25.5Gi |
| With KEDA (80% idle) | 6 | 24 | 3.3 | 10.2Gi |

## Resource Right-Sizing

The default Helm values are generous (4 CPU limit for backend). For most tenants, lower limits work fine:

### Standard Tier (Most Tenants)

```yaml
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
```

Per-tenant footprint: **~550m CPU, ~1.7Gi RAM**

### Premium Tier (High-Volume Customers)

```yaml
backend:
  resources:
    requests: { cpu: "500m", memory: "2Gi" }
    limits: { cpu: "4", memory: "16Gi" }

frontend:
  replicaCount: 2
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 5

langflow:
  resources:
    requests: { cpu: "500m", memory: "1Gi" }
    limits: { cpu: "4", memory: "8Gi" }
```

Per-tenant footprint: **~1.1 CPU, ~3.3Gi RAM** (higher limits for burst capacity)

## Node Pool Strategy

### Recommended Setup

| Node Pool | Purpose | Instance Type | Nodes | Notes |
|-----------|---------|---------------|-------|-------|
| **infra** | OpenSearch, monitoring | 8 CPU, 32Gi RAM | 3-5 | Dedicated, non-preemptible |
| **tenants** | Tenant workloads | 4-8 CPU, 16-32Gi RAM | 2-4 | Can use spot/preemptible instances |

### Using Spot/Preemptible Instances

Tenant workloads can tolerate brief restarts (they're stateless except for PVCs). Use cheaper spot instances for tenant node pools:

```yaml
# Tenant values
nodeSelector:
  node-pool: "tenants"

tolerations:
  - key: "cloud.google.com/gke-spot"    # or equivalent for your provider
    operator: "Equal"
    value: "true"
    effect: "NoSchedule"
```

## OpenSearch Optimization

### Index Lifecycle Management

For the `token_usage` index (which grows continuously), set up ILM:

```json
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": { "max_size": "10gb", "max_age": "30d" }
        }
      },
      "warm": {
        "min_age": "90d",
        "actions": {
          "forcemerge": { "max_num_segments": 1 }
        }
      },
      "delete": {
        "min_age": "365d",
        "actions": { "delete": {} }
      }
    }
  }
}
```

### Shard Strategy

- Small tenants (<10K documents): 1 primary shard, 1 replica
- Medium tenants (10K-100K documents): 2 primary shards, 1 replica
- Large tenants (>100K documents): 3+ primary shards, 1 replica

Configure via index templates:

```json
{
  "index_patterns": ["documents-*"],
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 1
    }
  }
}
```

## Monitoring

### Key Metrics to Track

- Per-tenant CPU/memory usage (Prometheus + Grafana)
- OpenSearch cluster health and index sizes
- Ingress request rates per tenant (for KEDA scaling)
- Token consumption per tenant (for billing)
- Pod restart counts and error rates

### Alerting

- OpenSearch cluster yellow/red health
- Tenant pods in CrashLoopBackOff
- PVC usage >80%
- Token consumption approaching quota limits

## Backup Strategy

### OpenSearch Snapshots

```bash
# Register S3-compatible snapshot repository
curl -XPUT "https://opensearch:9200/_snapshot/backups" \
  -d '{
    "type": "s3",
    "settings": {
      "bucket": "openrag-backups",
      "region": "eu-central-1"
    }
  }'

# Daily snapshot CronJob
curl -XPUT "https://opensearch:9200/_snapshot/backups/daily-$(date +%Y%m%d)" \
  -d '{ "indices": "*", "include_global_state": false }'
```

### PVC Backups

Use [Velero](https://velero.io/) for Kubernetes-native PVC backups:

```bash
velero schedule create daily-backup \
  --schedule="0 3 * * *" \
  --include-namespaces="*" \
  --include-resources="persistentvolumeclaims,persistentvolumes"
```
