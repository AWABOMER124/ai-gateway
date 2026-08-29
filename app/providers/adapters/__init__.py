"""Provider adapters — import all to auto-register with the provider registry."""
from app.providers.adapters import open_meteo  # noqa: F401
from app.providers.adapters import exchangerate  # noqa: F401
from app.providers.adapters import nominatim  # noqa: F401
from app.providers.adapters import local_email  # noqa: F401
from app.providers.adapters import local_phone  # noqa: F401
