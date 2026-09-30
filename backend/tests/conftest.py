import os

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/stallspan_test_unused.db")
os.environ.setdefault("SEED_ON_EMPTY", "false")
