from datetime import timedelta

DEFAULT_INTERVAL = timedelta(0)
DEFAULT_LABEL = "IMMEDIATE"

NOTIFICATION_INTERVALS = [
    (DEFAULT_INTERVAL, DEFAULT_LABEL),
    (timedelta(minutes=10), "TENMIN"),
    (timedelta(minutes=30), "HALFHOUR"),
    (timedelta(hours=1), "HOUR"),
    (timedelta(days=1), "DAY"),
    (timedelta(weeks=1), "WEEK"),
    (timedelta(weeks=4), "MONTH"),
]
