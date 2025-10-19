"""Utility functions for CLP MCP server."""

from datetime import datetime, timezone


def convert_epoch_to_date_string(epoch_ts: int) -> str:
    """
    :param epoch_ts: Unix epoch timestamp in milliseconds
    :return: ISO 8601 formatted date string with millisecond precision (YYYY-MM-DDTHH:mm:ss.fffZ)
    :raise TypeError: If epoch_ts is None or not an integer
    :raise ValueError: If epoch_ts is out of valid range
    :raise OSError: If the timestamp cannot be converted (platform-specific limits)
    """
    if epoch_ts is None:
        err_msg = "Timestamp cannot be None"
        raise TypeError(err_msg)

    if not isinstance(epoch_ts, int):
        err_msg = f"Timestamp must be int, got {type(epoch_ts).__name__}"
        raise TypeError(err_msg)

    try:
        epoch_seconds = epoch_ts / 1000.0
        dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except (ValueError, OSError, OverflowError) as e:
        raise ValueError(f"Invalid timestamp {epoch_ts}: {e}") from e


def convert_date_string_to_epoch(date_string: str) -> int:
    """
    :param date_string: ISO 8601 formatted date string (YYYY-MM-DDTHH:mm:ss.fffZ or similar)
    :return: Unix epoch timestamp in milliseconds
    :raise TypeError: If date_string is None or not a string
    :raise ValueError: If date_string cannot be parsed or is invalid
    """
    if date_string is None:
        err_msg = "Date string cannot be None"
        raise TypeError(err_msg)

    if not isinstance(date_string, str):
        err_msg = f"Date string must be str, got {type(date_string).__name__}"
        raise TypeError(err_msg)

    try:
        # Remove 'Z' suffix if present and parse
        cleaned_string = date_string.rstrip('Z')

        # Try parsing ISO format with fractional seconds
        if '.' in cleaned_string:
            dt = datetime.fromisoformat(cleaned_string)
        else:
            # Handle ISO format without fractional seconds
            dt = datetime.fromisoformat(cleaned_string)

        # Ensure timezone aware (assume UTC if naive)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Convert to milliseconds
        epoch_seconds = dt.timestamp()
        return int(epoch_seconds * 1000)

    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid date string '{date_string}': {e}") from e


def clean_query_result(results: list[dict]) -> list[str]:
    """
    Clean query results by keeping only timestamp and message fields.

    :param results: List of result dictionaries from the database
    :return: List of formatted strings with only timestamp and message
    :raise TypeError: If timestamp is invalid type
    :raise ValueError: If timestamp is out of valid range
    """
    cleaned = []
    for obj in results:
        try:
            timestamp_str = convert_epoch_to_date_string(obj.get("timestamp"))
            message = obj.get("message", "")
            cleaned.append(f"timestamp: {timestamp_str}, message: {message}")
        except (TypeError, ValueError) as e:
            # Re-raise with context about which entry failed
            logging.error(f"Failed to clean result entry: {e}, obj: {obj}")
            cleaned.append(f"timestamp: N/A, message: {obj.get('message', '')}")

    return cleaned

