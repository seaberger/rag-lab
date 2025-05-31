import pickle

# Load the nodes from the pickle file
with open('./enhanced_laser_nodes.pkl', 'rb') as f:
    nodes = pickle.load(f)

# Find and display the node with the specified ID
node_id_to_inspect = '689e8cb7-3767-4d08-beff-e995c7e792e1'

for node in nodes:
    if node.metadata.get('id') == node_id_to_inspect:
        print("Node found:")
        print(f"ID: {node.metadata.get('id')}")
        print(f"File Name: {node.metadata.get('file_name')}")
        print(f"Text Length: {len(node.text)}")
        print("Sample Content:")
        print(node.text[:500] + '...')
        print("Metadata:")
        print(node.metadata)
        break
else:
    print("Node with the specified ID not found.")
