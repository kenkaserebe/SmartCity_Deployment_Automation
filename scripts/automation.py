#!/usr/bin/env python3
"""
DevOps Automation Script - SmartCity Platform

This script provides a CLI interface for:
- Infrastructure provisioning (Terraform/CloudFormation)
- Application deployment (Blue/Green on EKS)
- Secrets management (AWS Secrets Manager)
- Monitoring stack deployment (Helm)
- System health checks
- Automated testing

Environment Variables:
    REGISTRY: Container registry (default: ghcr.io)
    IMAGE_NAME: Repository name (default: smartcity/iot-api)
    AWS_DEFAULT_REGION: AWS region (default: eu-west-2)
"""

import boto3
import json
import subprocess
import requests
import os
import sys
import time
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional

# ===============================================================
# LOGGING CONFIGURATION
# ===============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s -%(message)s',
    handlers=[
        logging.FileHandler('/var/log/devops_automation.log') if os.path.exists('/var/log') else logging.StreamHandler(),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ===============================================================
# MAIN AUTOMATION CLASS
# ===============================================================
class DevOpsAutomation:
    """Orchestrates DevOps tasks for the SmartCity platform on AWS + GitHub"""

    def __init__(self, environment: str = 'development'):
        """
        Initialize the automation client.

        Args:
            environment: Target environment (development, staging, production)
        """
        self.environment = environment
        self.region = os.getenv('AWS_DEFAULT_REGION', 'eu-west-2')

        # Container registry settings (GitHub Container Registry)
        self.registry = os.getenv('REGISTRY', 'ghcr.io')
        self.image_repo = os.getenv('IMAGE_NAME', 'smartcity/iot-api')

        # AWS clients
        self.cf_client = boto3.client('cloudformation', region_name=self.region)
        self.ecs_client = boto3.client('ecs', region_name=self.region)
        self.secrets_client = boto3.client('secretmanager', region_name=self.region)
        self.s3_client = boto3.client('s3', region_name=self.region)
        self.eks_client = boto3.client('eks', region_name=self.region)

        # Load environment-specific configuration
        self.config = self._load_config()

        logger.info(f"Initialized DevOpsAutomation for environment: {environment}")
        logger.info(f"Using container registry: {self.registry}/{self.image_repo}")

    # ---------------------------------------------------------------------
    # CONFIGURATION
    # ---------------------------------------------------------------------

    def _load_config(self) -> Dict[str, Any]:
        """Load environment-specific configuration from JSON file or defaults"""
        config_path = f'config/{self.environment}.json'
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found. Using defaults.")
            return {
                'project_name': 'smartcity',
                'ecs_cluster': f'smartcity-cluster-{self.environment}',
                'eks_cluster': f'smartcity-eks-{self.environment}',
                'namespace': self.environment,
                'replicas': 3 if self.environment == 'production' else 1,
                'health_check_endpoints': [
                    'https://api.smartcity.local/health',
                    'https://api.smartcity.local/ready'
                ]
            }
        
    # ----------------------------------------------------------------------
    # INFRASTRUCTURE PROVISIONING (Terraform / CloudFormation)
    # ----------------------------------------------------------------------
    def deploy_infrastructure(self, stack_name: str, template_file: str) -> bool:
        """
        Deploy AWS infrastructure using CloudFormation.

        Args:
            stack_name: Name of the CloudFormation stack
            template_file: Path to the CloudFormation YAML/JSON template

        Returns:
            bool: True if deployment succeded
        """
        try:
            with open(template_file, 'r') as f:
                template_body = f.read()

            full_stack_name = f"{stack_name}-{self.environment}"

            logger.info(f"Deploying CloudFormation stack: {full_stack_name}")

            response = self.cf_client.create_stack(
                StackName=full_stack_name,
                TemplateBody=template_body,
                Parameters=[
                    {'ParameterKey': 'Environment', 'ParameterValue': self.environment},
                    {'ParameterKey': 'ProjectName', 'ParameterValue': self.config.get('project_name', 'smartcity')}
                ],
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM'],
                Tags=[
                    {'Key': 'Project', 'Value': self.config.get('project_name', 'smartcity')},
                    {'Key': 'Environment', 'Value': self.environment},
                    {'Key': 'ManagedBy', 'Value': 'DevOpsAutomation'}
                ]
            )

            stack_id = response['StackId']
            logger.info(f"Stack creation initiated: {stack_id}")

            # Wait for stack creation to complete
            waiter = self.cf_client.get_waiter('stack_create_complete')
            waiter.wait(
                StackName=full_stack_name,
                waiterConfig={'Delay': 30, 'MaxAttempts': 60}
            )

            logger.info(f"✅ Stack {full_stack_name} created successfully.")
            return True
        
        except self.cf_client.exceptions.AlreadyExistsException:
            logger.warning(f"Stack {full_stack_name} already exists. Attempting update...")
            return self._update_infrastructure(stack_name, template_file)
        
        except Exception as e:
            logger.error(f"X Failed to deploy stack: {e}")
            return False
        
    def _update_infrastructure(self, stack_name: str, template_file: str) -> bool:
        """Update an existing CloudFormation stack."""
        try:
            with open(template_file, 'r') as f:
                template_body = f.read()

            full_stack_name = f"{stack_name}-{self.environment}"

            self.cf_client.update_stack(
                StackName=full_stack_name,
                TemplateBody=template_body,
                Parameters=[
                    {'ParameterKey': 'Environment', 'ParameterValue': self.environment},
                    {'ParameterKey': 'ProjectName', 'ParameterValue': self.config.get('project_name', 'smartcity')}
                ],
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
            )

            waiter = self.cf_client.get_waiter('stack_update_complete')
            waiter.wait(StackName=full_stack_name, WaiterConfig={'Delay': 30, 'MaxAttempts': 60})

            logger.info(f"✅ Stack {full_stack_name} updated successfully.")
            return True
        except Exception as e:
            logger.error(f"X Failed to update stack: {e}")
            return False
        
    # ----------------------------------------------------------------------
    # SECRETS MANAGEMENT (AWS Secrets Manager)
    # ----------------------------------------------------------------------
    def update_secrets(self, secret_name: str, secret_value: Dict[str, Any]) -> bool:
        """
        Store or update a secret in AWS Secrets Manager.

        Args:
            secret_name: Name of the secret
            secret_value: Dictionary of key-value pairs to store

        Returns:
            bool: True if successful
        """
        try:
            full_secret_name = f"{self.config.get('project_name', 'smartcity')}/{secret_name}-{self.environment}"

            response = self.secrets_client.put_secret_value(
                SecretId=full_secret_name,
                SecretString=json.dumps(secret_value)
            )
            logger.info(f"✅ Secret {full_secret_name} updated successfully.")
            return True
        except self.secrets_client.exceptions.ResourceNotFoundException:
            # Secret doesn't exist, create it
            try:
                self.secrets_client.create_secret(
                    Name=full_secret_name,
                    SecretString=json.dumps(secret_value),
                    Tags=[
                        {'Key': 'Environment', 'Value': self.environment},
                        {'Key': 'Project', 'Value': self.config.get('project_name', 'smartcity')}
                    ]
                )
                logger.info(f"✅ Secrets {full_secret_name} created successfully.")
                return True
            except Exception as e:
                logger.error(f"X Failed to create secret: {e}")
                return False
        except Exception as e:
            logger.error(f"X Failed to update secret: {e}")
            return False
        
    def get_secret(self, secret_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a secret from AWS Secrets Manager."""
        try:
            full_secret_name = f"{self.config.get('project_name', 'smartcity')}/{secret_name}-{self.environment}"
            response = self.secrets_client.get_secret_value(SecretId=full_secret_name)
            return json.loads(response['SecretString'])
        except Exception as e:
            logger.error(f"X Failed to retrieve secret {secret_name}: {e}")
            return None
        
    # --------------------------------------------------------------------
    # MONITORING STACK (Prometheus + Grafana via Helm)
    # --------------------------------------------------------------------
    def setup_monitoring(self) -> bool:
        """
        Deploy the monitoring stack (Prometheus, Grafana) using Helm.

        Returns:
            bool: True if deployment succeeded
        """
        try:
            # Check if Helm is installed
            subprocess.run(['helm', 'version'], check=True, capture_output=True)

            # Add Prometheus community repo if not already added
            subprocess.run(
                ['helm', 'repo', 'add', 'prometheus-community', 'https://prometheus-community.github.io/helm-charts'],
                check=True, capture_output=True
            )
            subprocess.run(['helm', 'repo', 'update'], check=True, capture_output=True)

            # Deploy Prometheus
            logger.info("Deploying Prometheus...")
            prom_cmd = [
                'helm', 'upgrade', '--install', 'prometheus', 'prometheus-community/prometheus', '-n', 'monitoring', '--create-namespace', '-f', 'helm/prometheus-values.yaml', '--set', f'prometheus.prometheusSpec.containers[0].env[0].name=ENVIRONMENT', '--set', f'prometheus.prometheusSpec.containers[0].env[0].value={self.environment}'
            ]
            subprocess.run(prom_cmd, check=True)
            logger.info("✅ Prometheus deployed.")

            # Deploy Grafana
            logger.info("Deploying Grafana...")
            grafana_cmd = [
                'helm', 'upgrade', '--install', 'grafana', 'grafana/grafana', '-n', 'monitoring', '-f', 'helm/grafana-values.yaml', '--set', f'grafana.ini.server.root_url=https://grafana.{self.environment}.smartcity.local'
            ]
            subprocess.run(grafana_cmd, check=True)

            # Retrieve Grafana admin password
            try: 
                get_pass = subprocess.run(
                    ['kubectl', 'get', 'secret', '-n', 'monitoring', 'grafana', '-o', 'jsonpath="{.data.admin-password}"'],
                    capture_output=True, text=True, check=True
                )
                logger.info(f"Grafana admin password (base64 encoded): {get_pass.stdout}")
            except:
                pass
            logger.info("✅ Monitoring stack deployed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"X Failed to setup monitoring: {e.stderr.decode() if e.stderr else str(e)}")
            return False
        except FileNotFoundError:
            logger.error("X Helm not found. Please install Helm (https://helm.sh/docs/intro/install/)")
            return False
        
    # ----------------------------------------------------------------------
    # APPLICATION DEPLOYMENT (Blue/Green on EKS)
    # ----------------------------------------------------------------------
    def deploy_application(self, version: str, environment: str) -> bool:
        """
        Deploy a new version of the application using Blue/Green strategy.

        This method:
        1. Determines which color (blue/green) is currently active.
        2. Deploys the new version to the inactive color.
        3. Waits for the new pods to become healthy.
        4. Switches the service selector to route traffic to the new version.
        5. Scales down the old version.

        Args:
            version: Docker image tag (e.g., 'v1.2.3' or 'sha-abc123')
            environment: Target Kubernetes namespace (dev, staging, prod)

        Returns:
            bool: True if deployment succeeded
        """
        try:
            full_image = f"{self.registry}/{self.image_repo}:{version}"
            namespace = environment
            deployment_base = "smartcity-api"

            logger.info(f"🚀 Starting Blue/Green deployment for {full_image} in namespace {namespace}")

            # Step 1: Determine current active color
            current_color = self._get_active_color(namespace, deployment_base)
            if current_color is None:
                logger.warning("No active deployment found. Defaulting to 'blue'.")
                current_color = "blue"
            new_color = "green" if current_color == "blue" else "blue"
            old_color = current_color

            logger.info(f"📊 Current active: {current_color}. Deploying new version to: {new_color}")

            # Step 2: Update the inactive deployment with the new image
            new_deployment_name = f"{deployment_base}-{new_color}"
            logger.info(f"Updating deployment: {new_deployment_name}")

            update_cmd = [
                'kubectl', 'set', 'image', f'deployment/{new_deployment_name}', f'api={full_image}', '-n', namespace
            ]
            subprocess.run(update_cmd, check=True)

            # Step 3: Scale up the new deployment (if it was scaled to 0)
            scale_up_cmd = [
                'kubectl', 'scale', 'deployment', new_deployment_name, '--replicas', str(self.config.get('replicas', 3)), '-n', namespace
            ]
            subprocess.run(scale_up_cmd, check=True)

            # Step 4: Wait for rollout to complete
            logger.info(f"⏳ Waiting for {new_deployment_name} to become healthy...")
            rollout_cmd = [
                'kubectl', 'rollout', 'status', f'deployment/{new_deployment_name}', '-n', namespace, '--timeout=300s'
            ]
            subprocess.run(rollout_cmd, check=True)
            logger.info(f"✅ {new_deployment_name} is healthy.")

            # Step 5: Switch service traffic to the new color
            logger.info(f"🔄 Switching service traffic from {old_color} to {new_color}...")
            patch_cmd = [
                'kubectl', 'patch', 'service', deployment_base, '-n', namespace, '-p', f'{{"spec":{{"selector":{{"version":"{new_color}"}}}}}}'
            ]
            subprocess.run(patch_cmd, check=True)

            # Step 6: Wait for the switch to propagate
            logger.info("⏳ Waiting 60 seconds for traffic to settle...")
            time.sleep(60)

            # Step 7: Scale down the old deployment
            logger.info(f"📉 Scaling down old deployment: {deployment_base}-{old_color}")
            scale_down_cmd = [
                'kubectl', 'scale', 'deployment', f'{deployment_base}-{old_color}', '--replicas=0', '-n', namespace
            ]
            subprocess.run(scale_down_cmd, check=True)

            logger.info(f"✅ Blue/Green deployment complete! Active version: {new_color} ({version})")

            # Step 8: Verify healthy endpoint
            self._verify_deployment(namespace)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"X Deployment failed: {e.stderr.decode() if e.stderr else str(e)}")
            return False
        except Exception as e:
            logger.error(f"X Unexpected error during deployment: {e}")
            return False
        
    def _get_active_color(self, namespace: str, service_name: str) -> Optional[str]:
        """Query Kubernetes service to determine which color is currently receiving traffic"""
        try:
            cmd = [
                'kubectl', 'get', 'service', service_name, '-n', namespace, '-o', 'jsonpath="{.spec.selector.version}"'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            color = result.stdout.strip().strip('"')
            return color if color else None
        except subprocess.CalledProcessError:
            return None
        
    def _verify_deployment(self, namespace: str) -> bool:
        """Perform a post-deployment health check on the API endpoint."""
        try:
            # Port-forward to test internally
            port_forward_cmd = [
                'kubectl', 'port-forward', f'service/smartcity-api', '-n', namespace, '8888:80', '--address=0.0.0.0'
            ]
            for endpoint in self.config.get('healt_check_endpoints', []):
                try:
                    resp = requests.get(endpoint, timeout=10)
                    if resp.status_code == 200:
                        logger.info(f"✅ Health check passed for {endpoint}")
                    else:
                        logger.warning(f"⚠️ Health check returned status {resp.status_code} for {endpoint}")
                except requests.RequestException as e:
                    logger.warning(f"⚠️ Could not reach {endpoint}: {e}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Post-deployment verification failed: {e}")
            return False
        
    # ---------------------------------------------------------------------
    # KUBERNETES UTILITIES (EKS Update Kubeconfig)
    # ---------------------------------------------------------------------
    def update_kubeconfig(self) -> bool:
        """Update local kubeconfig to point to the EKS cluster."""
        try:
            cluster_name = self.config.get('eks_cluster', f'smartcity-eks-{self.environment}')
            cmd = [
                'aws', 'eks', 'update-kubeconfig', '--region', self.region, '--name', cluster_name
            ]
            subprocess.run(cmd, check=True)
            logger.info(f"✅ Kubeconfig updated for cluster: {cluster_name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"X Failed to update kubeconfig: {e}")
            return False
        
    # --------------------------------------------------------------
    # HEALTH CHECK
    # --------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a comprehensive health check across infrastructure and application

        Returns:
            Dict containing health status for all services.
        """
        status = {
            'timestamp': datetime.now().isoformat(), 'environment': self.environment, 'region': self.region, 'services': {}
        }

        # Check EKS cluster
        try:
            cluster_name = self.config.get('eks_cluster', f'smartcity-eks-{self.environment}')
            response = self.eks_client.describe_cluster(name=cluster_name)
            status['services']['eks'] = {
                'status': response['cluster']['status'], 'version': response['cluster']['version'], 'endpoint': response['cluster']['endpoint']
            }
        except Exception as e:
            status['services']['eks'] = {'status': 'error', 'error': str(e)}

        # Check pods
        try:
            cmd = ['kubectl', 'get', 'pods', '-n', self.environment, '--no-headers']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')
            running = sum(1 for line in lines if 'Running' in line)
            total = len(lines)
            status['services']['pods'] = {
                'running': running, 'total': total, 'health': running == total if total > 0 else False
            }
        except Exception as e:
            status['services']['pods'] = {'status': 'error', 'error': str(e)}

        # Check API endpoints
        for endpoint in self.config.get('health_check_endpoints', []):
            try:
                resp = requests.get(endpoint, timeout=10, verify=False)
                status['services'][endpoint] = {
                    'status_code': resp.status_code, 'ok': resp.status_code == 200, 'response_time': resp.elapsed.total_seconds()
                }
            except requests.RequestException as e:
                status['services'][endpoint] = {
                    'status': 'error', 'error': str(e)
                }

        return status
    
    # -----------------------------------------------------------------
    # TEST EXECUTION
    # -----------------------------------------------------------------
    def run_tests(self, test_type: str = 'all') -> Dict[str, Any]:
        """
        Run automated tests (unit, integration, or all).

        Args:
            test_type: 'unit', 'integration', or 'all'

        Returns:
            Dict containing test results
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'environment': self.environment,
            'test_type': test_type,
            'results': {}
        }

        # Ensure npm is available
        try:
            subprocess.run(['npm', '--version'], check=True, capture_output=True)
        except FileNotFoundError:
            logger.error("X npm not found. Please install Node.js.")
            results['results']['error'] = 'npm not found'
            return results
        
        if test_type in ['all', 'unit']:
            try:
                logger.info("Running unit tests...")
                result = subprocess.run(
                    ['npm', 'test', '--', '--coverage', '--watchAll=false'], capture_output=True, text=True, timeout=300, cwd=os.path.dirname(os.path.abspath(__file__)) + '/..'
                )
                results['results']['unit_tests'] = {
                    'success': result.returncode == 0, 'output': result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout, 'error': result.stderr[-500:] if result.stderr else None
                }
                logger.info(f"Unit tests {'PASSED' if result.returncode == 0 else 'FAILED'}")
            except subprocess.TimeoutExpired:
                results['results']['unit_tests'] = {'success': False, 'error': 'Timeout (300s)'}
            except Exception as e:
                results['results']['unit_tests'] = {'success': False, 'error': str(e)}

        if test_type in ['all', 'integration']:
            try:
                logger.info("Running integration tests...")
                result = subprocess.run(
                    ['npm', 'run', 'test:integration'], capture_output=True, text=True, timeout=300, cwd=os.path.dirname(os.path.abspath(__file__)) + '/..'
                )
                results['results']['integration_tests'] = {
                    'success': result.returncode == 0, 'output': result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout, 'error': result.stderr[-500:] if result.stderr else None
                }
                logger.info(f"Integration tests {'PASSED' if result.returncode == 0 else 'FAILED'}")
            except subprocess.TimeoutExpired:
                results['results']['integration_tests'] = {'success': False, 'error': 'Timeout (300s)'}
            except Exception as e:
                results['results']['integration_tests'] = {'success': False, 'error': str(e)}
        return results
    
    # ==========================================================================
    # CLI ENTRY POINT
    # ==========================================================================
    def main():
        parser = argparse.ArgumentParser(
            description='DevOps Automation Tool - SmartCity Platform (GitHub + AWS)', epilog='Example: ./automation.py -e production -a deploy -v v1.2.3'
        )
        parser.add_argument(
            '--environment', '-e', default='development', choices=['development', 'staging', 'production'], help='Target environment (default: development)'
        )
        parser.add_argument(
            '--action', '-a', choices=['deploy', 'health', 'test', 'monitoring', 'secrets', 'kubeconfig'], required=True, help='Action to perform'
        )
        parser.add_argument(
            '--version', '-v', help='Container image version/tag to deploy (required for deploy action)'
        )
        parser.add_argument(
            '--stack', '-s', help='CloudFormation stack name (required for infrastructure deployment)'
        )
        parser.add_argument(
            '--template', '-t', help='CloudFormation template file path (required for infrastructure deployment)'
        )
        parser.add_argument(
            '--test-type', choices=['unit', 'integration', 'all'], default='all', help='Type of tests to run (default: all)'
        )
        parser.add_argument(
            '--secret-name', help='Name of the secret to manage (for secrets action)'
        )
        parser.add_argument(
            '--secret-file', help='JSON file containing secret values (for secrets action)'
        )

        args = parser.parse_args()

        # Initialize automation client
        automation = DevOpsAutomation(args.environment)

        # Execute the requested action
        success = True

        try:
            if args.action == 'deploy':
                if args.version:
                    # First ensure kubeconfig is up-to-date
                    automation.update_kubeconfig()
                    success = automation.deploy_application(args.version, args.environment)
                else:
                    logger.error("X --version is required for deploy action")
                    success = False
            elif args.action == 'health':
                status = automation.health_check()
                print(json.dumps(status, indent=2))
                success = True
            elif args.action == 'test':
                results = automation.run_tests(args.test_type)
                print(json.dumps(results, indent=2))
                # Determine overall success
                if 'unit_tests' in results['results']:
                    success = results['results']['unit_tests'].get('success', False)
                if 'integration_tests' in results['results']:
                    success = success and results['results']['integration_tests'].get('success', False)
                # If only integration was requested, override
                if args.test_type == 'integration':
                    success = results['results'].get('integration_tests', {}).get('success', False)
            elif args.action == 'monitoring':
                success = automation.setup_monitoring()

            elif args.action == 'secrets':
                if args.secret_name:
                    if args.secret_file:
                        try:
                            with open(args.secret_file, 'r') as f:
                                secret_data = json.load(f)
                            success = automation.update_secrets(args.secret_name, secret_data)
                        except FileNotFoundError:
                            logger.error(f"X Secret file {args.secret_file} not found")
                            success = False
                    else:
                        # If no file provided, prompt for key-value pairs interactively
                        logger.info(f"Enter secret values for '{args.secret_name}' (key=value, empty line to finish):")
                        secret_data = {}
                        while True:
                            line = input("> ").strip()
                            if not line:
                                break
                            if '=' in line:
                                key, val = line.split('=', 1)
                                secret_data[key.strip()] = val.strip()
                        if secret_data:
                            success = automation.update_secrets(args.secret_name, secret_data)
                        else:
                            logger.error("X No secret data provided")
                            success = False
            elif args.action == 'kubeconfig':
                success = automation.update_kubeconfig()

            else:
                logger.error(f"X Unknown action: {args.action}")
                success = False
        except KeyboardInterrupt:
            logger.warning("⚠️ Operation interrupted by user")
            success = False
        except Exception as e:
            logger.error(f"X Unhandled exception: {e}", exc_info=True)
            success = False

        # Exit with appropriate code
        sys.exit(0 if success else 1)

    if __name__ == '__main__':
        main()