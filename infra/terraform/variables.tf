variable "aws_region" { type=string default="us-west-2" }
variable "project" { type=string default="careerops" }
variable "image" { type=string description="ECR image URI for CareerOps" }
variable "db_username" { type=string default="careerops" }
variable "db_password" { type=string sensitive=true }
variable "bedrock_model_id" { type=string default="anthropic.claude-3-5-sonnet-20241022-v2:0" }
variable "ses_from_email" { type=string default="" }
variable "ses_to_email" { type=string default="" }
variable "adzuna_app_id" { type=string default="" sensitive=true }
variable "adzuna_app_key" { type=string default="" sensitive=true }
variable "usajobs_api_key" { type=string default="" sensitive=true }
variable "usajobs_user_agent" { type=string default="" }
variable "slack_webhook_url" { type=string default="" sensitive=true }
variable "discord_webhook_url" { type=string default="" sensitive=true }
variable "telegram_bot_token" { type=string default="" sensitive=true }
variable "telegram_chat_id" { type=string default="" }
variable "job_alert_imap_host" { type=string default="" }
variable "job_alert_imap_port" { type=number default=993 }
variable "job_alert_imap_user" { type=string default="" }
variable "job_alert_imap_password" { type=string default="" sensitive=true }
variable "job_alert_imap_folder" { type=string default="INBOX" }
variable "alert_ingest_token" { type=string default="" sensitive=true }
