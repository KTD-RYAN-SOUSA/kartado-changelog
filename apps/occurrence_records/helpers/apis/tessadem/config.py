from RoadLabsAPI.settings.credentials import TESSADEM_API_KEY

PARM_LOCATION = "&locations="

TESSADEM_BASE_URL = (
    f"https://tessadem.com/api/elevation?key={TESSADEM_API_KEY}{PARM_LOCATION}"
)
