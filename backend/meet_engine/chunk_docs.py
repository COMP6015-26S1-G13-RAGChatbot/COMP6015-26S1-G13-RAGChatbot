from langchain_text_splitters import RecursiveCharacterTextSplitter


# =====================================================
# CHUNK DOCUMENTS
# =====================================================

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

    global_chunk_id = 0

    for doc in docs:

        source = doc.get(
            "source",
            "unknown"
        )

        page = doc.get(
            "page",
            -1
        )

        source_type = doc.get(
            "source_type",
            "unknown"
        )

        authority_level = doc.get(
            "authority_level",
            0
        )

        authority_rank = doc.get(
            "authority_rank",
            0
        )

        content = doc.get(
            "content",
            ""
        )

        if not content.strip():
            continue

        # Split one PDF page into smaller chunks
        chunks = splitter.split_text(
            content
        )

        for page_chunk_index, chunk in enumerate(
            chunks
        ):

            if not chunk.strip():
                continue

            all_chunks.append({

                "chunk_id":
                    global_chunk_id,

                "page_chunk_index":
                    page_chunk_index,

                "source":
                    source,

                "page":
                    page,

                "source_type":
                    source_type,

                "authority_level":
                    authority_level,

                "authority_rank":
                    authority_rank,

                "content":
                    chunk.strip()
            })

            global_chunk_id += 1

    print(
        f"\nTotal chunks generated: "
        f"{len(all_chunks)}"
    )

    return all_chunks