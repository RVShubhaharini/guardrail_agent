import logging
import sys

def setup_logging():
    """Configures structured logs for runtime traceability."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Disable duplicate logs from noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
