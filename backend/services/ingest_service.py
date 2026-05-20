from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from core.config import Config
import os 
import logging

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('app.log'), logging.StreamHandler()])


class IngestService:
    
    def __init__(self):
        """
        Initializes the IngestService with the embedding model, Chroma path, and text splitter.
        core/config.py provides a singleton pattern for the embedding model to ensure it's only loaded once.
        """
        self.embedding_model = Config.get_embedding_model()
        self.chroma_path = Config.CHROMA_PATH
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=Config.CHUNK_SIZE,
            chunk_overlap=Config.CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " "]
        )

    def run_full_pipeline(self):
        """
        Runs the full ingestion pipeline: loads documents, processes them, and saves to the vector database.
        """
        all_chunks = []
        
        for doc_type, folder_path in Config.DATA_SOURCE.items():
            logging.info(f"Starting ingestion pipeline for {folder_path} with doc type '{doc_type}'")
            chunks = self.ingest_directory(folder_path, doc_type)
            all_chunks.extend(chunks)     
        
        if not all_chunks:
            logging.warning("No chunks were created from the ingestion process.")
            return         
        
        success = self.save_to_db(all_chunks)
        return success
            
    def ingest_directory(self, folder_path, doc_type):
        """
        Ingests all PDF documents from a specified directory, processes them, and returns the resulting chunks.
        Args:
            folder_path (str): The path to the directory containing PDF documents.
            doc_type (str): The type of documents being ingested (e.g., 'legal', 'operational') to be added as metadata.
        Returns:
            list: A list of processed document chunks ready to be saved to the vector database.
        """
        chunks_in_dir = []

        # Check if the directory exists
        if not os.path.exists(folder_path):
            print(f"Directory {folder_path} does not exist.")
            return chunks_in_dir

        logging.info(f"Ingesting documents from {folder_path}... [{doc_type}]")

        # Loop through all files in the directory and process PDFs
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(('.pdf')):
                file_path = os.path.join(folder_path, filename)
                print(f"Processing {file_path}...")
                
                try:
                    # load pdf
                    loader = PyPDFLoader(file_path)
                    documents = loader.load()
                    
                    # Add metadata to each document
                    for i, doc in enumerate(documents):
                        doc.metadata.update({
                            "type": doc_type,
                            "source": filename,
                            "page": i+1,
                            "processed_at": Config.get_current_time()
                        })
                 
                    # Process documents (e.g., split, embed, store)
                    chunks = self.splitter.split_documents(documents)
                    chunks_in_dir.extend(chunks)

                    logging.info(f"Finished processing {file_path}. Total chunks: {len(chunks)}")
                except Exception as e:
                    logging.error(f"Error processing {file_path}: {e}")

        return chunks_in_dir

    def save_to_db(self, chunks):
        try:
            logging.info(f"Saving {len(chunks)} chunks to: {Config.CHROMA_PATH}")
            db = Chroma.from_documents(
                documents=chunks,
                embedding=self.embedding_model,
                persist_directory=Config.CHROMA_PATH
            )
            db.persist()
            logging.info("Chunks successfully saved to the vector database.")
            return True
        except Exception as e:
            logging.error(f"Error saving chunks to the vector database: {e}")
            return False