from fastapi import Request
import time

# Rate limiting variables
request_timestamps = []
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds
MAX_REQUESTS_PER_WINDOW = 10  # Maximum 10 requests per hour


def check_rate_limit(request: Request) -> bool:
    """Check if the request exceeds rate limits"""
    client_ip = request.client.host
    current_time = time.time()

    # Remove timestamps older than the window
    global request_timestamps
    request_timestamps = [
        (ip, ts)
        for ip, ts in request_timestamps
        if current_time - ts < RATE_LIMIT_WINDOW
    ]

    # Count requests from this IP in the window
    ip_requests = sum(1 for ip, _ in request_timestamps if ip == client_ip)

    # Check if limit exceeded
    if ip_requests >= MAX_REQUESTS_PER_WINDOW:
        return False

    # Add current request to timestamps
    request_timestamps.append((client_ip, current_time))
    return True
