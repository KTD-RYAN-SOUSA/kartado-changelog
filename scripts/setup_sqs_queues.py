#!/usr/bin/env python3
"""
Script to create SQS queues for push notifications.
Run this script to set up the necessary AWS SQS infrastructure.

Usage:
    python scripts/setup_sqs_queues.py --environment staging
    python scripts/setup_sqs_queues.py --environment production
"""

import argparse
import json
import os
import sys
from typing import Optional

import boto3


def setup_django_for_environment(environment: str):
    """Setup Django with the appropriate settings for the given environment"""

    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Map environment to Django settings
    settings_map = {
        "staging": "RoadLabsAPI.settings.staging",
        "production": "RoadLabsAPI.settings.production",
        "homolog": "RoadLabsAPI.settings.homolog",
        "eco_production": "RoadLabsAPI.settings.eco.production",
        "engie_staging": "RoadLabsAPI.settings.engie.staging",
        "engie_production": "RoadLabsAPI.settings.engie.production",
        "ccr_homolog": "RoadLabsAPI.settings.ccr.homolog",
        "ccr_production": "RoadLabsAPI.settings.ccr.production",
    }

    django_settings = settings_map.get(environment)
    if not django_settings:
        raise ValueError(f"Unknown environment: {environment}")

    print(f"🔧 Using Django settings: {django_settings}")

    # Setup Django
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", django_settings)
    django.setup()

    # Import after Django setup
    from django.conf import settings

    from RoadLabsAPI.settings import credentials

    return settings, credentials


class SQSQueueSetup:
    """Setup SQS queues for push notifications"""

    def __init__(self, environment: str, settings, credentials):
        self.environment = environment
        self.settings = settings
        self.credentials = credentials

        self.sqs_client = boto3.client(
            "sqs",
            aws_access_key_id=credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=getattr(credentials, "AWS_SESSION_TOKEN", None),
            region_name=getattr(settings, "SQS_REGION", "us-east-1"),
        )

        # Queue names based on environment
        self.main_queue_name = getattr(
            settings,
            "SQS_PUSH_NOTIFICATIONS_QUEUE_NAME",
            f"kartado-push-notifications-{environment}",
        )
        self.dlq_name = getattr(
            settings,
            "SQS_PUSH_NOTIFICATIONS_DLQ_NAME",
            f"kartado-push-notifications-dlq-{environment}",
        )

    def create_dead_letter_queue(self) -> Optional[str]:
        """Create the Dead Letter Queue first"""
        print(f"Creating Dead Letter Queue: {self.dlq_name}")

        try:
            response = self.sqs_client.create_queue(
                QueueName=self.dlq_name,
                Attributes={
                    "MessageRetentionPeriod": "1209600",  # 14 days
                    "VisibilityTimeout": "30",
                    "ReceiveMessageWaitTimeSeconds": "20",  # Long polling
                },
            )

            dlq_url = response["QueueUrl"]
            print(f"✅ Created DLQ: {dlq_url}")

            # Get DLQ ARN
            dlq_attributes = self.sqs_client.get_queue_attributes(
                QueueUrl=dlq_url, AttributeNames=["QueueArn"]
            )

            return dlq_attributes["Attributes"]["QueueArn"]

        except self.sqs_client.exceptions.QueueNameExists:
            print(f"⚠️  DLQ {self.dlq_name} already exists")
            # Get existing queue URL and ARN
            dlq_url = self.sqs_client.get_queue_url(QueueName=self.dlq_name)["QueueUrl"]
            dlq_attributes = self.sqs_client.get_queue_attributes(
                QueueUrl=dlq_url, AttributeNames=["QueueArn"]
            )
            return dlq_attributes["Attributes"]["QueueArn"]

        except Exception as e:
            print(f"❌ Failed to create DLQ: {e}")
            return None

    def create_main_queue(self, dlq_arn: str) -> Optional[str]:
        """Create the main processing queue with DLQ configured"""
        print(f"Creating main queue: {self.main_queue_name}")

        # Redrive policy for DLQ
        redrive_policy = {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}

        try:
            response = self.sqs_client.create_queue(
                QueueName=self.main_queue_name,
                Attributes={
                    "MessageRetentionPeriod": "1209600",  # 14 days
                    "VisibilityTimeout": "900",  # 15 minutes (match Lambda timeout)
                    "ReceiveMessageWaitTimeSeconds": "20",  # Long polling
                    "RedrivePolicy": json.dumps(redrive_policy),
                },
            )

            main_queue_url = response["QueueUrl"]
            print(f"✅ Created main queue: {main_queue_url}")

            # Get queue ARN
            queue_attributes = self.sqs_client.get_queue_attributes(
                QueueUrl=main_queue_url, AttributeNames=["QueueArn"]
            )

            return queue_attributes["Attributes"]["QueueArn"]

        except self.sqs_client.exceptions.QueueNameExists:
            print(f"⚠️  Main queue {self.main_queue_name} already exists")
            # Get existing queue URL and ARN
            main_queue_url = self.sqs_client.get_queue_url(
                QueueName=self.main_queue_name
            )["QueueUrl"]
            queue_attributes = self.sqs_client.get_queue_attributes(
                QueueUrl=main_queue_url, AttributeNames=["QueueArn"]
            )
            return queue_attributes["Attributes"]["QueueArn"]

        except Exception as e:
            print(f"❌ Failed to create main queue: {e}")
            return None

    def setup_cloudwatch_alarms(self, queue_arn: str, dlq_arn: str):
        """Set up CloudWatch alarms for monitoring"""
        print("Setting up CloudWatch alarms...")

        cloudwatch = boto3.client(
            "cloudwatch",
            aws_access_key_id=self.credentials.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.credentials.AWS_SECRET_ACCESS_KEY,
            aws_session_token=getattr(self.credentials, "AWS_SESSION_TOKEN", None),
            region_name=getattr(self.settings, "SQS_REGION", "us-east-1"),
        )

        try:
            # Alarm for DLQ messages
            cloudwatch.put_metric_alarm(
                AlarmName=f"SQS-DLQ-Messages-{self.environment}",
                ComparisonOperator="GreaterThanThreshold",
                EvaluationPeriods=1,
                MetricName="ApproximateNumberOfVisibleMessages",
                Namespace="AWS/SQS",
                Period=300,
                Statistic="Average",
                Threshold=5.0,
                ActionsEnabled=True,
                AlarmDescription=f"Alarm when DLQ has messages in {self.environment}",
                Dimensions=[
                    {"Name": "QueueName", "Value": self.dlq_name},
                ],
                Unit="Count",
            )

            # Alarm for main queue depth
            cloudwatch.put_metric_alarm(
                AlarmName=f"SQS-Queue-Depth-{self.environment}",
                ComparisonOperator="GreaterThanThreshold",
                EvaluationPeriods=2,
                MetricName="ApproximateNumberOfVisibleMessages",
                Namespace="AWS/SQS",
                Period=300,
                Statistic="Average",
                Threshold=100.0,
                ActionsEnabled=True,
                AlarmDescription=f"Alarm when main queue depth is high in {self.environment}",
                Dimensions=[
                    {"Name": "QueueName", "Value": self.main_queue_name},
                ],
                Unit="Count",
            )

            print("✅ CloudWatch alarms created")

        except Exception as e:
            print(f"⚠️  Failed to create CloudWatch alarms: {e}")

    def print_configuration(self, main_queue_arn: str, dlq_arn: str):
        """Print configuration to be added to Zappa settings"""
        print("\n" + "=" * 60)
        print("🎉 SQS SETUP COMPLETE!")
        print("=" * 60)
        print(f"\nEnvironment: {self.environment}")
        print(f"Main Queue ARN: {main_queue_arn}")
        print(f"DLQ ARN: {dlq_arn}")

        print(f"\n📝 Add this to your zappa_settings.json for {self.environment}:")
        print("-" * 50)
        print(
            f"""
            "event_source": {{
                "arn": "{main_queue_arn}",
                "batch_size": 3,
                "maximum_batching_window_in_seconds": 5
            }}"""
        )

        print("\n🔧 Environment variables to set:")
        print("-" * 50)
        print(f"SQS_PUSH_NOTIFICATIONS_QUEUE_NAME={self.main_queue_name}")
        print(f"SQS_PUSH_NOTIFICATIONS_DLQ_NAME={self.dlq_name}")

        print("\n📊 Monitoring URLs:")
        print("-" * 50)
        queue_base_url = f"https://console.aws.amazon.com/sqs/v2/home?region={self.credentials.AWS_DEFAULT_REGION}#/queues"
        print(f"Main Queue: {queue_base_url}/{main_queue_arn.split(':')[-1]}")
        print(f"DLQ: {queue_base_url}/{dlq_arn.split(':')[-1]}")

    def run(self):
        """Run the complete setup process"""
        print(f"🚀 Setting up SQS queues for environment: {self.environment}")
        print("-" * 60)

        # Create DLQ first
        dlq_arn = self.create_dead_letter_queue()
        if not dlq_arn:
            print("❌ Failed to create/get DLQ. Aborting.")
            sys.exit(1)

        # Create main queue
        main_queue_arn = self.create_main_queue(dlq_arn)
        if not main_queue_arn:
            print("❌ Failed to create/get main queue. Aborting.")
            sys.exit(1)

        # Setup monitoring
        self.setup_cloudwatch_alarms(main_queue_arn, dlq_arn)

        # Print configuration
        self.print_configuration(main_queue_arn, dlq_arn)


def main():
    parser = argparse.ArgumentParser(
        description="Setup SQS queues for push notifications"
    )
    parser.add_argument(
        "--environment",
        required=True,
        choices=[
            "staging",
            "homolog",
            "production",
            "eco_production",
            "engie_production",
            "engie_staging",
            "ccr_production",
            "ccr_homolog",
        ],
        help="Environment to setup queues for",
    )

    args = parser.parse_args()

    try:
        settings, credentials = setup_django_for_environment(args.environment)
        setup = SQSQueueSetup(args.environment, settings, credentials)
        setup.run()
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
