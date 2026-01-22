import matplotlib.pyplot as plt
import networkx as nx


def visualize_book_ego_graph(graph, book_id, output_path="book_graph.png"):
    book_node = f"book::{book_id}"

    if book_node not in graph:
        raise ValueError("Book not found in graph")

    ego = nx.ego_graph(graph, book_node, radius=2)

    pos = nx.spring_layout(ego, seed=42)

    book_nodes = [
        n for n in ego.nodes
        if ego.nodes[n]["type"] == "book"
    ]
    author_nodes = [
        n for n in ego.nodes
        if ego.nodes[n]["type"] == "author"
    ]

    nx.draw_networkx_nodes(
        ego, pos,
        nodelist=book_nodes,
        node_color="#6baed6",
        node_size=800,
        label="Books"
    )

    nx.draw_networkx_nodes(
        ego, pos,
        nodelist=author_nodes,
        node_color="#fd8d3c",
        node_size=1200,
        label="Authors"
    )

    nx.draw_networkx_nodes(
        ego, pos,
        nodelist=[book_node],
        node_color="#2171b5",
        node_size=1600
    )

    nx.draw_networkx_edges(ego, pos, alpha=0.6)

    labels = {
        n: ego.nodes[n].get("title")
        for n in book_nodes
    }
    nx.draw_networkx_labels(ego, pos, labels, font_size=8)

    plt.legend(scatterpoints=1)
    plt.title("Book Recommendation Graph")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
