import os


class Config:
    EZOP_API_URL = os.getenv("EZOP_API_URL", "https://api.ezop.ai")
    EZOP_API_KEY = os.getenv("EZOP_API_KEY", None)
