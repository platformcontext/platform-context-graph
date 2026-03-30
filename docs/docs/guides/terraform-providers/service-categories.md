# Service Category Classification

PlatformContextGraph classifies Terraform resources into service categories (compute, storage, data, networking, security, etc.) to help organize and query infrastructure relationships.

## How It Works

Service categories are derived from the resource type name:

1. **Strip the provider prefix:** `aws_lambda_function` → `lambda_function`
2. **Extract service tokens:** `lambda_function` → `["lambda", "function"]`
3. **Match progressively:** Try `lambda_function`, then `lambda`
4. **Return category or default:** If matched, return the category; otherwise return `infrastructure`

## Built-in Categories

PCG includes mappings for common resource types across all major providers:

| Category | Resource Types | Examples |
|---|---|---|
| **compute** | Serverless, containers, VMs, batch jobs | Lambda, ECS, EC2, Cloud Run, App Engine |
| **storage** | Object storage, container registries, file systems | S3, ECR, GCS, Azure Storage, EFS |
| **data** | Databases, caches, data warehouses | RDS, DynamoDB, Cloud SQL, Spanner, Redis |
| **networking** | DNS, load balancers, CDN, VPCs | Route53, ALB, CloudFront, API Gateway |
| **messaging** | Queues, topics, event buses, workflows | SQS, SNS, Pub/Sub, EventBridge |
| **security** | IAM, secrets, certificates, WAF | IAM roles, KMS, Secrets Manager, ACM |
| **cicd** | Build pipelines, deployments, artifacts | CodeBuild, Cloud Build, GitHub Actions |
| **monitoring** | Logs, metrics, alerting, tracing | CloudWatch, Datadog, Grafana, PagerDuty |
| **governance** | Config, policies, organizations | AWS Config, Azure Policy, resource tags |
| **infrastructure** | Default for unmapped types | Utility providers, generic resources |

## Adding Custom Mappings

To add service category mappings for a new provider or override existing ones, edit `provider_schema.py`.

### Example: Datadog Provider

```python title="src/platform_context_graph/relationships/terraform_evidence/provider_schema.py"
SERVICE_CATEGORIES: dict[str, str] = {
    # ... existing mappings ...

    # --- Datadog (datadog_ prefix) ---
    "monitor": "monitoring",
    "dashboard": "monitoring",
    "synthetics": "monitoring",
    "logs": "monitoring",
    "integration": "monitoring",
    "downtime": "monitoring",
    "service_level_objective": "monitoring",
    "security_monitoring": "security",
}
```

**Key points:**
- Keys are the service portion *after* stripping the provider prefix
- `datadog_monitor` matches on `monitor`
- `datadog_security_monitoring_rule` matches on `security_monitoring`
- Longer prefixes are tried first (e.g., `security_monitoring` before `security`)

### Example: Custom Internal Provider

If you have a custom internal provider:

```python
SERVICE_CATEGORIES: dict[str, str] = {
    # ... existing mappings ...

    # --- Internal (mycompany_ prefix) ---
    "api_gateway": "networking",
    "worker_queue": "messaging",
    "feature_flag": "governance",
    "cost_allocation": "governance",
}
```

## Matching Rules

### Longest Prefix First

Longer token sequences are tried before shorter ones:

```python
SERVICE_CATEGORIES = {
    "cloudwatch_event": "messaging",  # Matches first
    "cloudwatch": "monitoring",       # Matches second
}
```

**Result:**
- `aws_cloudwatch_event_rule` → `messaging`
- `aws_cloudwatch_log_group` → `monitoring`

### Multi-token Resources

Resources with multiple tokens try progressively shorter sequences:

```python
SERVICE_CATEGORIES = {
    "lambda": "compute",
}
```

**Matching:**
- `aws_lambda_function` → tries `lambda_function`, then `lambda` → **compute**
- `aws_lambda_event_source_mapping` → tries `lambda_event_source_mapping`, `lambda_event_source`, `lambda_event`, `lambda` → **compute**

### Default Fallback

Unmapped resource types default to `infrastructure`:

```python
# No mapping exists
resource "random_password" "db_password" {
  length = 16
}
```

**Result:** `infrastructure`

## Provider-Specific Patterns

### AWS

AWS resources use service-specific prefixes:

| Prefix | Category | Examples |
|---|---|---|
| `lambda` | compute | `aws_lambda_function`, `aws_lambda_layer` |
| `s3` | storage | `aws_s3_bucket`, `aws_s3_object` |
| `rds` | data | `aws_rds_cluster`, `aws_rds_instance` |
| `route53` | networking | `aws_route53_zone`, `aws_route53_record` |
| `iam` | security | `aws_iam_role`, `aws_iam_policy` |

### GCP

GCP resources use `cloud_` or `compute_` prefixes:

| Prefix | Category | Examples |
|---|---|---|
| `cloud_run` | compute | `google_cloud_run_service` |
| `compute` | compute | `google_compute_instance` |
| `storage` | storage | `google_storage_bucket` |
| `sql` | data | `google_sql_database_instance` |
| `pubsub` | messaging | `google_pubsub_topic` |

### Azure

Azure resources use resource-type suffixes:

| Suffix | Category | Examples |
|---|---|---|
| `kubernetes_cluster` | compute | `azurerm_kubernetes_cluster` |
| `storage_account` | storage | `azurerm_storage_account` |
| `postgresql` | data | `azurerm_postgresql_server` |
| `dns_a_record` | networking | `azurerm_dns_a_record` |

## Querying by Category

Categories appear in MCP tool responses and can be queried via Cypher:

### Find All Compute Resources

```cypher
MATCH (repo:Repository)-[:REPO_CONTAINS]->(file:File)-[:CONTAINS]->(res:TerraformResource)
WHERE res.service_category = 'compute'
RETURN repo.name, file.relative_path, res.resource_type, res.name
```

### Count Resources by Category

```cypher
MATCH (res:TerraformResource)
RETURN res.service_category as category, count(*) as count
ORDER BY count DESC
```

### Find Orphan Storage Resources

```cypher
MATCH (repo:Repository)-[:REPO_CONTAINS]->(file:File)-[:CONTAINS]->(res:TerraformResource)
WHERE res.service_category = 'storage'
  AND NOT EXISTS {
    MATCH (res)<-[:DEPENDS_ON]-(:Repository)
  }
RETURN repo.name, res.name, res.resource_type
```

## Testing Category Mappings

Test your custom mappings:

```python
from platform_context_graph.relationships.terraform_evidence.provider_schema import (
    classify_resource_category
)

# Test a resource type
category = classify_resource_category("datadog_monitor")
print(f"datadog_monitor → {category}")  # monitoring

category = classify_resource_category("datadog_security_monitoring_rule")
print(f"datadog_security_monitoring_rule → {category}")  # security

category = classify_resource_category("random_password")
print(f"random_password → {category}")  # infrastructure (default)
```

## Best Practices

### 1. Match Provider Conventions

Align your category mappings with how the provider organizes its documentation:

- AWS groups by service (Lambda, S3, RDS)
- GCP groups by product (Cloud Run, Cloud Storage)
- Azure groups by resource type suffix

### 2. Use Broad Categories

Prefer broad categories over fine-grained ones:

- ✅ `compute` covers Lambda, ECS, EC2, VMs, containers
- ❌ Don't create `serverless`, `containers`, `vms` as separate categories

### 3. Be Consistent Across Providers

Map equivalent resources to the same category:

| Resource | Provider | Category |
|---|---|---|
| `aws_lambda_function` | AWS | compute |
| `google_cloud_run_service` | GCP | compute |
| `azurerm_function_app` | Azure | compute |

### 4. Document Rationale

When adding mappings for a new provider, add a comment explaining the provider's naming conventions:

```python
# --- Datadog (datadog_ prefix) ---
# Datadog uses *_monitoring for security products, direct names for observability
"monitor": "monitoring",
"security_monitoring": "security",
```

## Validation

Run tests to ensure your mappings load correctly:

```bash
PYTHONPATH=src uv run python -m pytest tests/unit/relationships/test_terraform_provider_schema.py::TestClassifyResourceCategory -v
```

## See Also

- [Terraform Provider Support](index.md) — overview of schema-driven extraction
- [Adding Providers](adding-providers.md) — contribute new provider support
- [Relationship Mapping Reference](../../reference/relationship-mapping.md) — evidence to relationships flow
