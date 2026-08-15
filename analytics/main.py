import json
from pathlib import Path

import polars as pl

_QUESTIONS_PATH = Path(__file__).parent / "questions"


def main():
    questions_ref = _QUESTIONS_PATH / "questions_sql_v1_answers_ref.json"
    reference = json.loads(questions_ref.read_text())
    breakpoint()
    df = pl.DataFrame()
    print("Hello from analytics")


if __name__ == "__main__":
    main()
