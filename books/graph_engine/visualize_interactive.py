from pyvis.network import Network
import networkx as nx


def visualize_book_ego_graph_interactive(graph, focus_book_id):
    book_node = focus_book_id

    if book_node not in graph:
        raise ValueError("Book not found in graph")

    net = Network(
        height="600px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#333333",
        notebook=False
    )

    ego = graph.subgraph(
        nx.ego_graph(graph, book_node, radius=2).nodes
    )

    for node, data in ego.nodes(data=True):
        node_type = data.get("type")

        if node_type == "book":
            label = data.get("title")
            color = "#2171b5" if node == book_node else "#6baed6"
            rating = data.get("rating")
            size = 18 + (rating * 3 if rating else 0)
            if node == book_node:
                size += 10
        else:
            label = data.get("name")
            color = "#fd8d3c"
            size = 30

        net.add_node(
            node,
            label=None,
            title=label,
            color=color,
            size=size
        )

    for source, target, data in ego.edges(data=True):
        net.add_edge(source, target, value=data.get("weight", 1.0))

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "stabilization": false,
        "forceAtlas2Based": {
          "gravitationalConstant": -120,
          "centralGravity": 0.02,
          "springLength": 100,
          "springConstant": 0.08
        }
      }
    }
    """)

    return net.generate_html()
