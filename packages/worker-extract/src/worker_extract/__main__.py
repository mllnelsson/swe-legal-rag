import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("worker-extract starting...")


if __name__ == "__main__":
    main()
