from enum import IntEnum, auto


SEARCH_MAX_NUM_RESULTS = 1000

POLLING_INTERVAL_SECONDS = 1

# Matching the `QueryJobType` class in `job_orchestration.query_scheduler.constants`.
class QueryJobType(IntEnum):
    SEARCH_OR_AGGREGATION = 0
    EXTRACT_IR = auto()
    EXTRACT_JSON = auto()

# Matching the `QueryJobStatus` class in `job_orchestration.query_scheduler.constants`.
class QueryJobStatus(IntEnum):
    PENDING = 0
    RUNNING = auto()
    SUCCEEDED = auto()
    FAILED = auto()
    CANCELLING = auto()
    CANCELLED = auto()
    KILLED = auto()

