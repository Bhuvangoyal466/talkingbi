class TalkingBIError(Exception):
    """Base exception for TalkingBI."""
    pass


class LLMError(TalkingBIError):
    """Raised when LLM inference fails."""
    pass


class SchemaExtractionError(TalkingBIError):
    """Raised when database schema extraction fails."""
    pass


class SQLGenerationError(TalkingBIError):
    """Raised when SQL generation fails after max iterations."""
    pass


class DataPrepError(TalkingBIError):
    """Raised when data preparation pipeline fails."""
    pass


class ChartGenerationError(TalkingBIError):
    """Raised when chart generation fails."""
    pass


class InsightDiscoveryError(TalkingBIError):
    """Raised when insight discovery fails."""
    pass


class FileLoadError(TalkingBIError):
    """Raised when file loading fails."""
    pass


class DatabaseConnectionError(TalkingBIError):
    """Raised when database connection fails."""
    pass
