import os
from redis import Redis
from rq import Queue

# Fetch Redis connection URL from environment configs
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Establish Redis connection
redis_conn = Redis.from_url(REDIS_URL)

# Instantiate the RQ Queue targeted at the 'tax_jobs' queue
queue = Queue("tax_jobs", connection=redis_conn)
