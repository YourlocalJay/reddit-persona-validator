# AWS deployment configuration

provider "aws" {
  region = var.aws_region
}

# AWS Lightsail container service
resource "aws_lightsail_container_service" "app" {
  name        = "reddit-persona-validator"
  power       = "micro"
  scale       = 1
  is_disabled = false

  private_registry_access {
    ecr_repository_names = [aws_ecr_repository.app.name]
  }

  tags = {
    application = "reddit-persona-validator"
    environment = "production"
  }
}

# ECR repository for container images
resource "aws_ecr_repository" "app" {
  name                 = "reddit-persona-validator"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}
