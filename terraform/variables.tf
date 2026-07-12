variable "aws_region" {
  description   = "AWS region"
  type          = string
  default       = "eu-west-2"
}

variable "environment" {
  description   = "Environment name"
  type          = string
  default       = "development"
}

variable "db_username" {
  description   = "Database username"
  type          = string
  sensitive     = true
}

variable "db_password" {
  description   = "Database password"
  type          = string
  sensitive     = true
}

variable "vpc_cidr" {
  description   = "VPC CIDR block"
  type          = string
  default       = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description   = "Public subnet CIDR blocks"
  type          = list(string)
  default       = [ "10.0.1.0/24", "10.0.2.0/24" ]
}

variable "private_subnet_cidrs" {
  description   = "Private subnet CIDR blocks"
  type          = list(string)
  default       = [ "10.0.10.0/24", "10.0.11.0/24" ]
}

variable "kubernetes_version" {
  description   = "Kubernetes version"
  type          = string
  default       = "1.27"
}

variable "node_instance_types" {
  description   = "EC2 instance types for worker nodes"
  type          = list(string)
  default       = [ "t3.medium", "t3.large" ]
}