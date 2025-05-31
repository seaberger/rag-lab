import pickle

def load_nodes(file_path):
    with open(file_path, 'rb') as f:
        return pickle.load(f)

def check_pairs(nodes):
    print("Found pairs:")
    print("-" * 50)
    
    for node in nodes:
        if "pairs" in node.metadata:
            print(f"\nNode text sample: {node.text[:200]}...")
            print("\nPairs found:")
            for pair in node.metadata["pairs"]:
                print(f"  Part number: {pair['part_number']}")
                print(f"  Product name: {pair['product_name']}")
                print("-" * 30)

if __name__ == "__main__":
    nodes = load_nodes("./enhanced_laser_nodes.pkl")
    check_pairs(nodes)
