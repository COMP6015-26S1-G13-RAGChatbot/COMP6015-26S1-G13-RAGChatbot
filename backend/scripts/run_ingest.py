from backend.services.ingest_service import IngestService


if __name__ == "__main__":
    chunks = IngestService().build()
    print(f"Indexed {len(chunks)} approved production sections/pages.")
