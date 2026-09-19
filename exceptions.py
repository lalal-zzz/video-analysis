class AnalyzerError(Exception):
    ...


class ScraperError(Exception):
    ...


class TranscriberError(Exception):
    ...


class CacheMissError(KeyError):
    ...


class ConfigError(Exception):
    ...


class RuleEvalError(Exception):
    ...