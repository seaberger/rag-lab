import pickle
from llama_index.core.schema import TextNode  # Or relevant node type

nodes_file = "./matrix_chatbot/matrix_nodes.pkl"  # Adjust path
try:
    with open(nodes_file, "rb") as f:
        nodes = pickle.load(f)
    if nodes:
        print(f"Loaded {len(nodes)} nodes.")
        for i, node in enumerate(nodes[:3]):  # Check first 3 nodes
            print(f"\nNode {i}:")
            print(f"  Has embedding attribute? {'embedding' in node.__dict__}")
            if "embedding" in node.__dict__:
                print(f"  Embedding is None? {node.embedding is None}")
                if node.embedding is not None:
                    print(f"  Embedding type: {type(node.embedding)}")
                    print(f"  Embedding length: {len(node.embedding)}")
                    # print(f"  Embedding sample: {node.embedding[:5]}") # Uncomment to see values
            else:
                print("  Node has no .embedding attribute.")
    else:
        print("Node file is empty.")
except Exception as e:
    print(f"Error loading/inspecting pickle: {e}")
