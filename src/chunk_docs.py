from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_documents(docs):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " "
        ]
    )

    all_chunks = []

    for doc in docs:

        source = doc["source"]
        content = doc["content"]

        chunks = splitter.split_text(content)

        for chunk in chunks:

            if chunk.strip():

                all_chunks.append({
                    "source": source,
                    "content": chunk
                })

    return all_chunks