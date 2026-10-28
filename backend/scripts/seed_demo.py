"""Create fictional local data; never invokes a model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import Store
from app.demo import seed_demo
from app.service import Services

settings = Settings.from_env()
settings.validate()
store = Store(settings)
try:
    business = seed_demo(Services(store, settings))
    print("Fictional business ID:", business["id"])
finally:
    store.close()
