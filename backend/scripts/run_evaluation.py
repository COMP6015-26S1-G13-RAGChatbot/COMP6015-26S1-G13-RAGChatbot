import json

from backend.services.evaluation_service import EvaluationService


if __name__ == "__main__":
    print(json.dumps(EvaluationService().evaluate().model_dump(), indent=2))
