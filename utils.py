import time
from datetime import datetime

def format_time_left(expire_ts):
    remaining = expire_ts - int(time.time())
    if remaining <= 0:
        return "истекла"
    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    minutes = (remaining % 3600) // 60
    return f"{days}д {hours}ч {minutes}м"

def format_datetime(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
