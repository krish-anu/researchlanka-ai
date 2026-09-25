output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Public IPv4 address for GitHub EC2_HOST."
  value       = aws_instance.app.public_ip
}

output "public_dns" {
  description = "Public DNS name for the EC2 instance."
  value       = aws_instance.app.public_dns
}

output "ssh_command" {
  description = "SSH command for the provisioned instance."
  value       = "ssh -i <private-key> ubuntu@${aws_instance.app.public_ip}"
}

output "app_url" {
  description = "Frontend URL once Docker Compose is running."
  value       = "http://${aws_instance.app.public_ip}:${var.frontend_port}"
}

output "security_group_id" {
  description = "Security group attached to the app instance."
  value       = aws_security_group.app.id
}
