"""Phase modules. Importing this package registers every phase into the global registry
(side-effect imports). Add new phases here as they are built.
"""
from pipeline3.phases import p100_validation  # noqa: F401
from pipeline3.phases import p200_fillout  # noqa: F401
from pipeline3.phases import p300_staging  # noqa: F401
from pipeline3.phases import p400_interfaces  # noqa: F401
from pipeline3.phases import p500_signals  # noqa: F401
