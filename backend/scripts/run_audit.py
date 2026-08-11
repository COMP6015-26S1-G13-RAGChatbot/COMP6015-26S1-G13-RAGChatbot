import argparse
import json

from backend.services.audit_service import AuditService


parser = argparse.ArgumentParser()
parser.add_argument("text")
parser.add_argument("--document-id")
args = parser.parse_args()
print(json.dumps(AuditService().audit(args.text, args.document_id).model_dump(), indent=2, default=str))
