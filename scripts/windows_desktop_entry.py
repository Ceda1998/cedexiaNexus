"""Entry point for bundled desktop apps and their verifier subprocess."""

import sys

from nexus_ui.app import main
from nexus_ui.local_model import VERIFY_FLAG
from scripts.verify_model import main as verify_model


if __name__ == "__main__":
    if sys.argv[1:2] == [VERIFY_FLAG]:
        raise SystemExit(verify_model(sys.argv[2:]))
    main(smoke=sys.argv[1:] == ["--smoke-test"])
