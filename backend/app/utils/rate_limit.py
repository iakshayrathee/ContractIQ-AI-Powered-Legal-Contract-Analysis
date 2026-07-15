"""Rate limiting configuration using slowapi."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Use client IP as the rate-limit key.
# In production behind a reverse proxy, swap get_remote_address
# for a function that reads X-Forwarded-For.
limiter = Limiter(key_func=get_remote_address)
