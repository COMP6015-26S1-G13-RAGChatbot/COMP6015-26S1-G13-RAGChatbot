import argparse
import json

from backend.services.evaluation_service import EvaluationService, load_evaluation_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true", help="Run all three modes on the development benchmark")
    parser.add_argument("--dataset", help="Optional .json or .xlsx evaluation dataset")
    parser.add_argument("--summary", action="store_true", help="Print aggregate metrics without per-case output")
    args = parser.parse_args()
    service = EvaluationService()
    rows = load_evaluation_rows(args.dataset) if args.dataset else None
    result = service.compare(rows) if args.compare else service.evaluate(rows)
    payload = result.model_dump()
    if args.summary and not args.compare:
        payload.pop("per_case", None)
    print(json.dumps(payload, indent=2))
