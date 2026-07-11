# SmartCity IoT Platform - DevOps Infrastructure

## Overview
This project implements a comprehensive DevOps solution for the SmartCity IoT platform, demonstrating modern infrastructure automation, CI/CD practices, and observability.

## Architecture Components

### Infrastructure
- **AWS EKS** - Kubernetes orchestration
- **RDS PostgreSQL** - Database
- **S3** - Sensor data storage
- **SQS** - Message queuing
- **Secrets Manager** - Secrets management

### CI/CD Pipeline
- **GitHub Actions** - Pipeline automation
- **Trivy** - Container and code scanning
- **Terraform** - Infrastructure as Code
- **Ansible** - Configuration management

### Monitoring
- **Prometheus** - Metrics collection
- **Grafana** - Visualization
- **CloudWatch** - AWS monitoring
- **Custom health checks**

### Security
- **SAST/DAST** - Security scanning
- **Secret scanning** - Leak detection
- **Encryption** - At-rest and in-transit
- **IAM** - Least privilege access

## Prerequisites

### Required Tools
- Terraform >= 1.5.0
- AWS CLI >= 2.0
- kubectl >= 1.27
- Docker >= 24.0
- GitHub CLI (gh) >= 2.0
- Access to GitHub Container Registry (ghcr.io)
- Python >= 3.9

### Environment Setup
```bash
# Clone repository
git clone https://github.com/smartcity/devops-project.git
cd devops-project

# Install dependencies
pip install -r requirements.txt
npm install

# Configure AWS credentials
aws configure


*Deployment Guide*

**1. Infrastructure Provisioning**
`bash
# Initialize Terraform
cd terraform
terraform init

# Plan infrastructure
terraform plan -var="environment=development"

# Apply infrastructure
terraform apply -var="environment=development" -auto-approve
`

**2. CI/CD Pipeline Setup**
`bash
# Configure GitHub CI variables
# Add to GitHub project settings:
# - AWS_ACCESS_KEY_ID
# - AWS_SECRET_ACCESS_KEY
# - DB_PASSWORD
# - GHCR_TOKEN

# Push code to trigger pipeline
git push origin main
`

**3. Application Deployment**
`bash
# Deploy to development
./scripts/automation.py --environment development --action deploy --version v1.0.0

# Deploy to production with blue/green
./scripts/automation.py --environment production --action deploy --version v1.0.0
`

**4. Monitoring Setup**
`bash
# Deploy monitoring stack
./scripts/automation.py --environment production --action monitoring

# Access Grafana
kubectl port-forward -n monitoring svc/grafana 3000:80
# Default credentials: admin/prom-operator
`

**Testing**

***Run Tests***
`bash
# Unit tests
npm test

# Integration tests
npm run test:integration

# Security tests
./scripts/security-scan.sh

# Health check
./scripts/automation.py --environment development --action health
`

**Operational Tasks**

***Database Backup***
`bash
# Automated backup via cron
0 2 * * * /opt/scripts/database-backup.sh

# Manual backup
pg_dump -h $DB_HOST -U $DB_USER smartcity > backup.sql
`

***SSL Certificate Renewal***
`bash
# Renew certificates
certbot renew --webroot-path=/var/www/letsencrypt

# Update Kubernetes secrets
kubectl create secret tls tls-secret --cert=/etc/letsencrypt/live/api/cert.pem --key=/etc/letsencrypt/live/api/privkey.pem -n production --dry-run=client -o yaml | kubectl apply -f -
`

***Log Analysis***
`bash
# View application logs
kubectl logs -f deployment/smartcity-api -n production

# CloudWatch logs
aws logs get-log-events --log-group-name /aws/eks/smartcity/cluster --log-stream-name kube-system

# Elasticsearch logs (if configured)
curl -XGET "http://elasticsearch:9200/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "match": {
      "message": "ERROR"
    }
  }
}'
`


**Incident Response**

***Rollback Procedure***
`bash
# Kubernetes rollback
kubectl rollout undo deployment/smartcity-api -n production

# Infrastructure rollback via Terraform
terraform plan -destroy -var="environment=production"
terraform apply -destroy -var="environment=production"
`

***Scale Operations***
`bash
# Horizontal scaling
kubectl scale deployment smartcity-api -n production --replicas=10

# Vertical scaling - Update HPA
kubectl edit hpa smartcity-api-hpa -n production
`

**Troubleshooting Guide**

***Common Issues***

****1. Pods Not Starting****
`bash
# Check pod status
kubectl describe pod <pod-name> -n production

# Check events
kubectl get events -n production --sort-by='.lastTimestamp'
`

****2. Database Connection Issues****
`bash
# Test connection
kubectl run -it --rm test-db --image=postgres:15 -- psql -h $DB_HOST -U $DB_USER -d smartcity -c "SELECT 1"

# Check secrets
kubectl get secrets -n production
`

****3. CI/CD Failures****
`bash
# Check pipeline logs in GitHub UI
# Check runner logs
kubectl logs -n github-runner <runner-pod-name>
`

**Performance Optimization**

***Resource Limits***
`yaml
# Update Kubernetes resource limits
resources:
  requests:
    memory: "256Mi"
    cpu: "200m"
  limits:
    memory: "512Mi"
    cpu: "500m"
`

**Database Optimization**

`sql
-- Add indexes
CREATE INDEX idx_sensor_data_timestamp ON sensor_data(timestamp);
CREATE INDEX idx_sensor_data_type ON sensor_data(sensor_type);

-- Query optimization
EXPLAIN ANALYZE SELECT * FROM sensor_data WHERE timestamp > now() - interval '1 day';
`

**Disaster Recovery**

***Backup Strategy***
- Daily RDS snapshots
- S3 cross-region replication
- Kubernetes state backups via Velero

***Recovery Steps***
`bash
# Restore RDS from snapshot
aws rds restore-db-instance-from-db-snapshot --db-instance-identifier smartcity-restored --db-snapshot-identifier latest-snapshot

# Restore S3 data
aws s3 sync s3://backup-bucket/smartcity/ s3://smartcity-sensor-data-production/

# Restore Kubernetes state
velero restore create --from-backup daily-backup
`

**Contact & Support**
- DevOps Team: devops@smartcity.local
- Incident Response: pager@smartcity.local
- Documentation: docs.smartcity.local
- Jira Board: jira.smartcity.local

**License**

Proprietary - All rights reserved
`text

---

## Skills Demonstrated

| Skill | Implementation |
|-------|----------------|
| **Cloud Platforms** | AWS (EKS, RDS, S3, SQS, Secrets Manager) |
| **CI/CD** | GitLab CI with multi-stage pipelines |
| **Infrastructure as Code** | Terraform for AWS resource provisioning |
| **Configuration Management** | Ansible for monitoring setup |
| **Containerization** | Docker multi-stage builds |
| **Orchestration** | Kubernetes with EKS, Helm |
| **Scripting** | Python automation, Bash scripts |
| **Security** | SAST/DAST, secret scanning, Vault integration |
| **Monitoring** | Prometheus, Grafana, CloudWatch |
| **Deployment Strategies** | Blue/Green, Canary |
| **Agile/Lean** | CI/CD, automated testing, fast feedback |

---

## Summary

This project demonstrates a complete, production-ready DevOps solution that:

1. **Automates everything** - From infrastructure provisioning to application deployment
2. **Implements security best practices** - Secret management, scanning, encryption
3. **Provides comprehensive observability** - Monitoring, logging, alerting
4. **Supports modern deployment strategies** - Blue/Green, rolling updates
5. **Scales effectively** - Auto-scaling, load balancing, resilient design
6. **Is well-documented** - Clear operational procedures and troubleshooting guides
`