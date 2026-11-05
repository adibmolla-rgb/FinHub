import os

# Tests must not start the real OpenBB worker.
os.environ["FINHUB_SKIP_WARMUP"] = "1"
