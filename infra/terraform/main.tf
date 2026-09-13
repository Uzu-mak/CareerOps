terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}
provider "aws" { region = var.aws_region }

data "aws_vpc" "default" { default = true }
data "aws_subnets" "default" { filter { name = "vpc-id" values = [data.aws_vpc.default.id] } }
data "aws_caller_identity" "current" {}

resource "aws_kms_key" "careerops" {
  description             = "CareerOps data/secrets encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}
resource "aws_kms_alias" "careerops" { name = "alias/${var.project}" target_key_id = aws_kms_key.careerops.key_id }

resource "aws_s3_bucket" "artifacts" { bucket_prefix = "${var.project}-artifacts-" }
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" kms_master_key_id = aws_kms_key.careerops.arn } }
}
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true
}

resource "aws_sqs_queue" "discovery_dlq" { name = "${var.project}-discovery-dlq" kms_master_key_id = "alias/aws/sqs" }
resource "aws_sqs_queue" "discovery" {
  name = "${var.project}-discovery"
  visibility_timeout_seconds = 300
  receive_wait_time_seconds = 20
  kms_master_key_id = "alias/aws/sqs"
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.discovery_dlq.arn, maxReceiveCount = 4 })
}
resource "aws_sqs_queue" "application_dlq" { name = "${var.project}-application-dlq" kms_master_key_id = "alias/aws/sqs" }
resource "aws_sqs_queue" "application" {
  name = "${var.project}-application"
  visibility_timeout_seconds = 900
  receive_wait_time_seconds = 20
  kms_master_key_id = "alias/aws/sqs"
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.application_dlq.arn, maxReceiveCount = 3 })
}

resource "aws_security_group" "alb" {
  name_prefix = "${var.project}-alb-"
  vpc_id = data.aws_vpc.default.id
  ingress { from_port = 80 to_port = 80 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] }
  egress { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_security_group" "app" {
  name_prefix = "${var.project}-ecs-"
  vpc_id = data.aws_vpc.default.id
  ingress { from_port = 8000 to_port = 8000 protocol = "tcp" security_groups = [aws_security_group.alb.id] }
  egress { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_security_group" "db" {
  name_prefix = "${var.project}-db-"
  vpc_id = data.aws_vpc.default.id
  ingress { from_port = 5432 to_port = 5432 protocol = "tcp" security_groups = [aws_security_group.app.id] }
  egress { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
}

resource "aws_db_subnet_group" "db" { name = "${var.project}-db" subnet_ids = data.aws_subnets.default.ids }
resource "aws_db_instance" "postgres" {
  identifier = "${var.project}-postgres"
  engine = "postgres"
  engine_version = "16.3"
  instance_class = "db.t4g.micro"
  allocated_storage = 20
  max_allocated_storage = 100
  db_name = "careerops"
  username = var.db_username
  password = var.db_password
  db_subnet_group_name = aws_db_subnet_group.db.name
  vpc_security_group_ids = [aws_security_group.db.id]
  skip_final_snapshot = true
  storage_encrypted = true
  kms_key_id = aws_kms_key.careerops.arn
  backup_retention_period = 7
  publicly_accessible = false
}

resource "aws_secretsmanager_secret" "runtime" {
  name_prefix = "${var.project}/runtime-"
  kms_key_id = aws_kms_key.careerops.arn
}
resource "aws_secretsmanager_secret_version" "runtime" {
  secret_id = aws_secretsmanager_secret.runtime.id
  secret_string = jsonencode({
    DATABASE_URL = "postgresql+psycopg://${var.db_username}:${var.db_password}@${aws_db_instance.postgres.address}:5432/careerops"
    ADZUNA_APP_ID = var.adzuna_app_id
    ADZUNA_APP_KEY = var.adzuna_app_key
    USAJOBS_API_KEY = var.usajobs_api_key
    SLACK_WEBHOOK_URL = var.slack_webhook_url
    DISCORD_WEBHOOK_URL = var.discord_webhook_url
    TELEGRAM_BOT_TOKEN = var.telegram_bot_token
    TELEGRAM_CHAT_ID = var.telegram_chat_id
    JOB_ALERT_IMAP_USER = var.job_alert_imap_user
    JOB_ALERT_IMAP_PASSWORD = var.job_alert_imap_password
    ALERT_INGEST_TOKEN = var.alert_ingest_token
  })
}

resource "aws_lb" "app" {
  name = substr("${var.project}-alb",0,32)
  internal = false
  load_balancer_type = "application"
  security_groups = [aws_security_group.alb.id]
  subnets = data.aws_subnets.default.ids
}
resource "aws_lb_target_group" "app" {
  name = substr("${var.project}-tg",0,32)
  port = 8000
  protocol = "HTTP"
  vpc_id = data.aws_vpc.default.id
  target_type = "ip"
  health_check { path = "/api/health" healthy_threshold = 2 unhealthy_threshold = 3 timeout = 5 interval = 30 matcher = "200" }
}
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.app.arn
  port = 80
  protocol = "HTTP"
  default_action { type = "forward" target_group_arn = aws_lb_target_group.app.arn }
}

resource "aws_ecs_cluster" "main" { name = var.project }
resource "aws_cloudwatch_log_group" "app" { name = "/ecs/${var.project}" retention_in_days = 30 }

resource "aws_iam_role" "task_execution" {
  name = "${var.project}-task-execution"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "execution" { role = aws_iam_role.task_execution.name policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" }
resource "aws_iam_role_policy" "execution_secrets" {
  role = aws_iam_role.task_execution.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.runtime.arn },
    { Effect = "Allow", Action = ["kms:Decrypt"], Resource = aws_kms_key.careerops.arn }
  ] })
}
resource "aws_iam_role" "task" {
  name = "${var.project}-task"
  assume_role_policy = aws_iam_role.task_execution.assume_role_policy
}
resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetObject","s3:PutObject","s3:ListBucket"], Resource = [aws_s3_bucket.artifacts.arn,"${aws_s3_bucket.artifacts.arn}/*"] },
    { Effect = "Allow", Action = ["sqs:ReceiveMessage","sqs:DeleteMessage","sqs:GetQueueAttributes","sqs:SendMessage"], Resource = [aws_sqs_queue.discovery.arn,aws_sqs_queue.application.arn] },
    { Effect = "Allow", Action = ["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"], Resource = "*" },
    { Effect = "Allow", Action = ["ses:SendEmail"], Resource = "*" },
    { Effect = "Allow", Action = ["kms:Decrypt","kms:Encrypt","kms:GenerateDataKey"], Resource = aws_kms_key.careerops.arn }
  ] })
}

locals {
  common_env = [
    { name = "AWS_REGION", value = var.aws_region },
    { name = "LLM_PROVIDER", value = "bedrock" },
    { name = "BEDROCK_MODEL_ID", value = var.bedrock_model_id },
    { name = "S3_BUCKET", value = aws_s3_bucket.artifacts.bucket },
    { name = "SES_FROM_EMAIL", value = var.ses_from_email },
    { name = "SES_TO_EMAIL", value = var.ses_to_email },
    { name = "USAJOBS_USER_AGENT", value = var.usajobs_user_agent },
    { name = "JOB_ALERT_IMAP_HOST", value = var.job_alert_imap_host },
    { name = "JOB_ALERT_IMAP_PORT", value = tostring(var.job_alert_imap_port) },
    { name = "JOB_ALERT_IMAP_FOLDER", value = var.job_alert_imap_folder }
  ]
  runtime_secrets = [
    for key in ["DATABASE_URL","ADZUNA_APP_ID","ADZUNA_APP_KEY","USAJOBS_API_KEY","SLACK_WEBHOOK_URL","DISCORD_WEBHOOK_URL","TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID","JOB_ALERT_IMAP_USER","JOB_ALERT_IMAP_PASSWORD","ALERT_INGEST_TOKEN"] :
    { name = key, valueFrom = "${aws_secretsmanager_secret.runtime.arn}:${key}::" }
  ]
  log_config = { logDriver = "awslogs", options = { "awslogs-group" = aws_cloudwatch_log_group.app.name, "awslogs-region" = var.aws_region } }
}

resource "aws_ecs_task_definition" "app" {
  family = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode = "awsvpc"
  cpu = "512"
  memory = "1024"
  execution_role_arn = aws_iam_role.task_execution.arn
  task_role_arn = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name = "app", image = var.image, essential = true,
    portMappings = [{ containerPort = 8000 }],
    environment = concat(local.common_env,[{ name = "BASE_URL", value = "http://${aws_lb.app.dns_name}" }]),
    secrets = local.runtime_secrets,
    healthCheck = { command = ["CMD-SHELL","python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')\" || exit 1"], interval = 30, timeout = 5, retries = 3, startPeriod = 30 },
    logConfiguration = merge(local.log_config,{ options = merge(local.log_config.options,{ "awslogs-stream-prefix" = "api" }) })
  }])
}
resource "aws_ecs_service" "app" {
  name = "${var.project}-api"
  cluster = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count = 1
  launch_type = "FARGATE"
  depends_on = [aws_lb_listener.http]
  network_configuration { subnets = data.aws_subnets.default.ids security_groups = [aws_security_group.app.id] assign_public_ip = true }
  load_balancer { target_group_arn = aws_lb_target_group.app.arn container_name = "app" container_port = 8000 }
}

resource "aws_ecs_task_definition" "discovery_worker" {
  family = "${var.project}-discovery-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode = "awsvpc"
  cpu = "512"
  memory = "1536"
  execution_role_arn = aws_iam_role.task_execution.arn
  task_role_arn = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name = "discovery-worker", image = var.image, essential = true,
    command = ["python","-m","careerops.workers.sqs_worker"],
    environment = concat(local.common_env,[{ name = "QUEUE_URL", value = aws_sqs_queue.discovery.url },{ name = "APPLICATION_QUEUE_URL", value = aws_sqs_queue.application.url }]),
    secrets = local.runtime_secrets,
    logConfiguration = merge(local.log_config,{ options = merge(local.log_config.options,{ "awslogs-stream-prefix" = "discovery" }) })
  }])
}
resource "aws_ecs_service" "discovery_worker" {
  name = "${var.project}-discovery-worker"
  cluster = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.discovery_worker.arn
  desired_count = 1
  launch_type = "FARGATE"
  network_configuration { subnets = data.aws_subnets.default.ids security_groups = [aws_security_group.app.id] assign_public_ip = true }
}

resource "aws_ecs_task_definition" "browser_worker" {
  family = "${var.project}-browser-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode = "awsvpc"
  cpu = "1024"
  memory = "2048"
  execution_role_arn = aws_iam_role.task_execution.arn
  task_role_arn = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name = "browser-worker", image = var.image, essential = true,
    command = ["python","-m","careerops.workers.application_worker"],
    environment = concat(local.common_env,[{ name = "APPLICATION_QUEUE_URL", value = aws_sqs_queue.application.url }]),
    secrets = local.runtime_secrets,
    logConfiguration = merge(local.log_config,{ options = merge(local.log_config.options,{ "awslogs-stream-prefix" = "browser" }) })
  }])
}
resource "aws_ecs_service" "browser_worker" {
  name = "${var.project}-browser-worker"
  cluster = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.browser_worker.arn
  desired_count = 1
  launch_type = "FARGATE"
  network_configuration { subnets = data.aws_subnets.default.ids security_groups = [aws_security_group.app.id] assign_public_ip = true }
}

resource "aws_iam_role" "scheduler" {
  name = "${var.project}-scheduler"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.discovery.arn }] })
}
resource "aws_scheduler_schedule" "discovery" {
  name = "${var.project}-discovery"
  flexible_time_window { mode = "OFF" }
  schedule_expression = "rate(15 minutes)"
  target {
    arn = "arn:aws:scheduler:::aws-sdk:sqs:sendMessage"
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({ QueueUrl = aws_sqs_queue.discovery.url, MessageBody = jsonencode({ type = "scan_enabled_sources" }) })
  }
}
resource "aws_scheduler_schedule" "daily_report" {
  name = "${var.project}-daily-report"
  flexible_time_window { mode = "OFF" }
  schedule_expression = "cron(0 14 * * ? *)"
  target {
    arn = "arn:aws:scheduler:::aws-sdk:sqs:sendMessage"
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({ QueueUrl = aws_sqs_queue.discovery.url, MessageBody = jsonencode({ type = "daily_report" }) })
  }
}

output "careerops_url" { value = "http://${aws_lb.app.dns_name}" }
output "rds_endpoint" { value = aws_db_instance.postgres.address }
output "artifact_bucket" { value = aws_s3_bucket.artifacts.bucket }
output "discovery_queue" { value = aws_sqs_queue.discovery.url }
output "application_queue" { value = aws_sqs_queue.application.url }
output "runtime_secret_arn" { value = aws_secretsmanager_secret.runtime.arn }
