import os
import sys

# The harness never opens a database, but importing app settings requires these.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")

from app.evaluation.adversarial.run import main  # noqa: E402

sys.exit(main())
