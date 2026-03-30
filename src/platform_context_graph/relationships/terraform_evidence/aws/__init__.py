"""AWS Terraform evidence extractors.

Importing this module registers all AWS resource extractors with the
global registry.
"""

from . import compute  # noqa: F401
from . import networking  # noqa: F401
from . import data  # noqa: F401
from . import messaging  # noqa: F401
from . import storage  # noqa: F401
from . import cicd  # noqa: F401
