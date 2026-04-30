"""
AWS Lambda Handler for Zappa with Docker Images

This file serves as a bridge between AWS Lambda and Zappa when using Docker images.
It imports the lambda_handler from zappa.handler and re-exports it so that Lambda
can find it at the expected location (/var/task/handler.py).

When deploying with Docker images (PackageType: Image), AWS Lambda looks for the
handler module at /var/task/handler.py, but Zappa is installed in site-packages.
This file resolves that by importing and re-exporting the handler.
"""

# Import the Zappa lambda handler
from zappa.handler import lambda_handler  # noqa: F401

# The lambda_handler is now available at this module level
# AWS Lambda will call handler.lambda_handler when the function is invoked
