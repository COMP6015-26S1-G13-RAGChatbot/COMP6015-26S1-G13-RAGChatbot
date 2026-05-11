from services.ingest_service import IngestService

def test_ingestion():
    """
    Test the ingestion pipeline end-to-end. 
    This will load documents, process them, and save to the vector database.
    """
    service = IngestService()
    
    success = service.run_full_pipeline()
    
    if success:
        print("\n  [SUCCESS] Ingestion pipeline worked perfectly!")
        print(" Check 'app.log' for detailed logs and 'chroma_db' folder for data.")
    else:
        print("\n  [FAILED] Something went wrong. Check 'app.log' for errors.")

if __name__ == "__main__":
    test_ingestion()