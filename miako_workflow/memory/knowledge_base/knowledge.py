from llama_index.vector_stores.milvus import MilvusVectorStore
from llama_index.vector_stores.milvus.utils import  BM25BuiltInFunction
from typing import Literal, List
from fastapi import HTTPException, status
from llama_index.core import Document
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.core.schema import NodeWithScore
from llama_index.core import VectorStoreIndex
from miako_workflow.config_files.config import workflow_settings
from llama_index.core.prompts import PromptTemplate
from datetime import datetime, timezone
from miako_workflow.prompts.prompt_library import PromptLibrary
import asyncio


CLIENT_URI=workflow_settings.CLIENT_URI.get_secret_value()
CLIENT_TOKEN=workflow_settings.CLIENT_TOKEN.get_secret_value()
BM25FUNCTION = BM25BuiltInFunction(
    analyzer_params={
        "tokenizer": "icu",
        "filter": [
            "lowercase",
            {"type": "length", "max": 40},
        ],
    },
    enable_match=True,
    input_field_names=["text"],
    output_field_names=["sparse_embeddings"]
)




def vector_store_with_bm25():
    try:
        vector_store = MilvusVectorStore(
            uri=CLIENT_URI,
            token=CLIENT_TOKEN,
            collection_name="hackathon_knowledge_base",
            dim=1536,
            embedding_field='embeddings',
            enable_sparse=True,
            enable_dense=True,
            overwrite=False,
            sparse_embedding_function=BM25FUNCTION, #type: ignore
            sparse_embedding_field="sparse_embeddings",
            search_config={"nprobe": 60},
            similarity_metric="IP",
            consistency_level="Strong",
            hybrid_ranker="RRFRanker",
            hybrid_ranker_params={"k": 60}
        )
        return vector_store
    except Exception as vector_err:
        raise vector_err





data = [
"Organization: Office of the City Health Officer (OCHO) (Government). Sector: Health & Emergency. They provide Primary care; Immunization; Pre-natal; TB DOTS; Animal Bite Center specifically for General public; Pregnant women; Children. To avail of these services, the basic requirements are: Queuing number; Individual Treatment Record (ITR). You can visit them at 2/F New City Hall Building, Malolos. Contact them via: (044) 931-8888 Local 2207.",

"Organization: Bulacan Medical Center (BMC) (Government). Sector: Health & Emergency. They provide Level 3 tertiary hospital; 24/7 ER; Specialized out-patient clinics specifically for General public; Acute trauma patients. To avail of these services, the basic requirements are: Standard hospital admission procedures. You can visit them at 99 Potenciano St., Malolos. Contact them via: (044) 791-0630 / bmc@bulacan.gov.ph.",

"Organization: Malasakit Center (at BMC) (Government). Sector: Health & Emergency. They provide One-stop shop for medical/financial aid (DOH, DSWD, PCSO, PhilHealth) specifically for Indigent and financially incapacitated patients. To avail of these services, the basic requirements are: Medical Abstract; Hospital Bill; Malasakit Unified Form. You can visit them at BMC Compound, Malolos. Contact them via: (044) 791-0630 / inquiry@dswd.gov.ph.",

"Organization: City Disaster Risk Reduction & Mgt Office (CDRRMO) (Government). Sector: Health & Emergency. They provide Malolos Rescue: 24/7 emergency medical dispatch; trauma extraction specifically for Citizens involved in emergencies/accidents. To avail of these services, the basic requirements are: None (Immediate dispatch via call). You can visit them at G/F New City Hall Building, Malolos. Contact them via: Hotline: (044) 760-5160 / cityofmalolos.cdrrmo@gmail.com.",

"Organization: Office of the City Social Welfare and Dev't (CSWD) (Government). Sector: Social Welfare. They provide AICS (Medical/Burial Aid); VAWC protection; PWD/Senior IDs specifically for Indigents; Abused women; At-risk youth; Seniors. To avail of these services, the basic requirements are: Barangay Indigency; Valid ID; Medical Abstract; Social Case Study. You can visit them at G/F New City Hall Building, Malolos. Contact them via: (044) 931-8888 Local 2104.",

"Organization: PGB Tulong Pang-Edukasyon Scholarship (Government). Sector: Education. They provide Financial aid (P3k-P5.5k) & Academic Scholarships (P5k) for HS/College specifically for Registered Bulakenyo youth with no failing grades. To avail of these services, the basic requirements are: Application form; Letter to Governor; Brgy Indigency; Grades. You can visit them at Provincial Capitol Bldg Ground Flr, Malolos. Contact them via: (044) 791-8100 / scholarship@bulacan.gov.ph."
]

LIB = PromptLibrary()

PRESENTATION_NODE = PromptTemplate(LIB.get_prompt("template.for_node"))
PRESENTATION_MESSAGE = PromptTemplate(LIB.get_prompt("template.for_message"))

EMBED_TYPE = Literal["document", "query"]
SPLITTER = SentenceSplitter(chunk_size=1000, chunk_overlap=200)


class HackathonRetrievalKnowledge:

    @property
    def milvus_store(self) -> MilvusVectorStore:
        return vector_store_with_bm25()

    @staticmethod
    def embed_model_document():
        _embed_model_document = CohereEmbedding(
            model_name="embed-v4.0",
            api_key=workflow_settings.COHERE_API_KEY.get_secret_value(),
            input_type="search_document"
        )
        return _embed_model_document

    @staticmethod
    def embed_model_query():
        _embed_model_query = CohereEmbedding(
            model_name="embed-v4.0",
            api_key=workflow_settings.COHERE_API_KEY.get_secret_value(),
            input_type="search_query"
        )
        return _embed_model_query

    async def _get_index(self, embed_type: EMBED_TYPE):
        if embed_type not in ("document", "query"):
            raise MemoryStoreException(detail="Error in parameter type")
        try:
            if embed_type == "document":
                embed_model = HackathonRetrievalKnowledge.embed_model_document()
            else:
                embed_model = HackathonRetrievalKnowledge.embed_model_query()

            _index = VectorStoreIndex.from_vector_store(
                vector_store=self.milvus_store, embed_model=embed_model, use_async=True
            )
            return _index
        except Exception as e:
            raise MemoryStoreException(detail=str(e))

    async def _get_retriever(self) -> BaseRetriever:
        index = await self._get_index(embed_type="query")

        retriever = index.as_retriever(
            vector_store_query_mode="hybrid", similarity_top_k=5
        )
        return retriever

    async def _show_result_with_retriever(self, query: str) -> str:

        retriever = await self._get_retriever()
        node_with_score = await retriever.aretrieve(query)

        output = ""

        for node in node_with_score:
            text = node.text
            md = getattr(node, "metadata", {}) or {}
            presentation = PRESENTATION_NODE.format(
                text=text,
                source=md.get("source","unknown"),
                turn_index=md.get("turn_index",-1),
                score=getattr(node, "score", 0),
            )
            output += presentation

        return output

    async def ingest_knowledge_base(self, data_list: list[str]) -> None:
        """
        Ingests the list of static data paragraphs into the vector store.
        """
        _docs = []

        # --- ITERATION START ---
        # We loop through your 'data' list here, Master!
        for text_content in data_list:
            # We create a Document for each paragraph
            # We don't need 'user_message' metadata here, just a simple type label
            new_doc = Document(
                text=text_content,
                metadata={
                    "type": "static_knowledge",
                    "source": "manual_ingestion",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            _docs.append(new_doc)
        # --- ITERATION END ---

        # Now we process them all at once (Batch processing is faster!)
        if _docs:
            index = await self._get_index(embed_type="document")

            # Split the documents into nodes (though our paragraphs are already small)
            nodes = await SPLITTER.aget_nodes_from_documents(_docs)

            # Insert all nodes into the vector database
            await index.ainsert_nodes(nodes=nodes)

            print(f"S-Successfully ingested {len(nodes)} nodes, Master!")




    async def add_knowledge(
            self,
            knowledge_dataset: list[str]
    ):
        try:
            await self.ingest_knowledge_base(data_list=knowledge_dataset)
            return True

        except MemoryStoreException:
            raise

        except Exception as e:
            raise MemoryStoreException(detail=str(e))



    async def show_knowledge(self, query: str):
        try:
            output = await self._show_result_with_retriever(query)
            return output

        except MemoryStoreException:
            raise

        except Exception as e:
            raise MemoryStoreException(detail=str(e))

    async def _retrieve_raw_nodes(self, query: str) -> List[NodeWithScore]:
        """
        Retrieves the raw Node objects without converting them to a string immediately.
        This allows us to access metadata and text separately later.
        """
        try:
            retriever = await self._get_retriever()
            # This returns the list of nodes with their similarity scores
            nodes = await retriever.aretrieve(query)
            return nodes
        except Exception as e:
            # I-I will make sure we catch errors properly...
            raise MemoryStoreException(detail=str(e))

    @staticmethod
    def format_for_llm(nodes: List[NodeWithScore]) -> str:
        """
        Takes raw nodes and formats them into a clean string context for the LLM.
        Master, we can customize this format however you like!
        """
        context_string = ""
        for i, node_with_score in enumerate(nodes, 1):
            node = node_with_score.node
            meta = node.metadata or {}

            # Here we extract specific metadata to help the LLM understand the source
            org = meta.get('type', 'General Knowledge')  # Or extract 'Organization' if you parse it
            score = node_with_score.score

            # We build a block of text for the LLM
            # We don't include XML tags unless the LLM specifically needs them.
            # Usually, a clean labeled format is best.
            context_string += (
                f"--- Source {i} (Relevance: {score:.2f}) ---\n"
                f"Content: {node.get_content()}\n"
                f"Metadata: {meta}\n\n"
            )

        return context_string

    async def retrieve_nodes(self, query: str):
        try:
            raw_nodes = await self._retrieve_raw_nodes(query)
            optimized_nodes = HackathonRetrievalKnowledge.format_for_llm(raw_nodes)
            return optimized_nodes
        except Exception as e:
            raise MemoryStoreException(detail=str(e))



class MemoryStoreException(HTTPException):
    def __init__(self, detail: str = "Error occurred during conversation memory."):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


# async def run_test_scenario():
#     print("M-Master, I am initializing the memory store now...")
#
#     # 1. Instantiate your store
#     memory_store = ConversationMemoryStore()
#
#     # 2. Ingest the static data provided in your 'data' list
#     # We check if it returns True as expected
#     print("Ingesting knowledge base... p-please wait...")
#     try:
#         await memory_store.add_(knowledge_dataset=data)
#         print("Ingestion complete! The data is now inside Milvus.")
#     except Exception as e:
#         print(f"Oh no! I failed to ingest the data: {e}")
#         return
#
#     # 3. Test Retrieval
#     # Let's ask a question relevant to the data, like the Animal Bite Center
#     test_query = "What are the requirements for the Animal Bite Center?"
#
#     print(f"\nTesting retrieval with query: '{test_query}'")
#     try:
#         result = await memory_store.show_(query=test_query)
#
#         print("\n" + "=" * 30)
#         print("RETRIEVAL RESULT")
#         print("=" * 30)
#         print(result)
#         print("=" * 30)
#
#     except Exception as e:
#         print(f"I-I am sorry Master, I encountered an error during retrieval: {e}")


# In your main execution block:

async def run_test_scenario():
    memory_store = HackathonRetrievalKnowledge()
    is_exist = True
    # ... (Ingestion code from before) ...
    # ... inside your run_test_scenario ...

    # 2. Ingest
    print("Ingesting knowledge base... p-please wait...")
    if not is_exist:
        await memory_store.add_knowledge(knowledge_dataset=data)
        print("Ingestion complete!")
    else:
        print("Nothing to do!")

    # --- ADD THIS BLOCK, MASTER! ---
    print("Waiting for the database to index the new data...")
    await asyncio.sleep(5)  # A 5-second nap should be enough for a small dataset!
    # -------------------------------

    # 3. Test Retrieval
    # ...

    test_query = "What are the requirements for the Animal Bite Center?"

    print(f"\nQuerying: '{test_query}'")


    # 1. Get the Raw Nodes
    raw_nodes = await memory_store._retrieve_raw_nodes(query=test_query)

    print(f"\nI found {len(raw_nodes)} relevant chunks, Master!\n")

    # 2. Inspect specific metadata programmatically (Use this logic for your code)
    for node_obj in raw_nodes:
        # Accessing the internal node
        real_node = node_obj.node
        print(f"[Score: {node_obj.score:.4f}]")
        print(f"   - Text Preview: {real_node.text[:50]}...")
        print(f"   - Full Metadata: {real_node.metadata}")
        # You can now access real_node.metadata['source'] directly!

    # 3. Convert to LLM Context String
    print("\n" + "=" * 30)
    print("FORMATTED CONTEXT FOR LLM")
    print("=" * 30)
    llm_context = HackathonRetrievalKnowledge.format_for_llm(raw_nodes)
    print(llm_context)

# if __name__ == "__main__":
#     # This starts the async event loop
#     asyncio.run(run_test_scenario())