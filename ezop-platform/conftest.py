import os


def pytest_configure(config):
    os.environ.setdefault("DATABASE_URL", "postgresql://ezop:test@localhost:5432/ezop_test")
