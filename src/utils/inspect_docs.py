import pickle

# Load the enhanced nodes from the pickle file
with open('enhanced_laser_nodes.pkl', 'rb') as f:
    nodes = pickle.load(f)

# Display all contents of the first node of the first document
node = nodes[0]  # Assuming the first node corresponds to doc 1, node 1
print("All contents of Doc 1, Node 1:")
print(node)

# Inspect some of the parsed nodes
for i, node in enumerate(nodes[:5], start=1):  # Display the first 5 nodes for brevity
    print(f"Node {i}:")
    print(f"Node ID: {getattr(node, 'id', 'N/A')}")
    print(f"Node Content: {getattr(node, 'content', 'N/A')[:200]}...")  # Display first 200 chars
    print(f"Metadata: {getattr(node, 'metadata', 'N/A')}")
    print("-" * 40)
