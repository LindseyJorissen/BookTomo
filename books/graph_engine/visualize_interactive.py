from pyvis.network import Network
import networkx as nx


def visualize_book_ego_graph_interactive(graph, focus_book_id):
    book_node = focus_book_id

    if book_node not in graph:
        raise ValueError("Book not found in graph")

    net = Network(
        height="600px",
        width="100%",
        bgcolor="#faf9f6",
        font_color="#4c483c",
        notebook=False,
        cdn_resources="in_line"
    )

    ego = graph.subgraph(
        nx.ego_graph(graph, book_node, radius=2).nodes
    )

    for node, data in ego.nodes(data=True):
        node_type = data.get("type")

        if node_type == "book":
            label = data.get("title")
            color = "#8fa6a0" if node == book_node else "#b7c7c2"

            size = 28 if node == book_node else 18

        else:
            label = data.get("name")
            color = "#c4b7a6"
            size = 26

        net.add_node(
            node,
            label=None,
            title=label,
            color=color,
            size=size
        )

    for source, target, data in ego.edges(data=True):
        net.add_edge(
            source,
            target,
            value=data.get("weight", 1.0),
            color="rgba(120, 110, 90, 0.35)",
            smooth=True
        )

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -40,
          "centralGravity": 0.01,
          "springLength": 140,
          "springConstant": 0.04,
          "avoidOverlap": 1
        },
        "stabilization": {
          "iterations": 200
        }
      },
      "nodes": {
        "borderWidth": 0,
        "font": {
          "size": 14,
          "face": "Arial",
          "color": "#4c483c",
          "strokeWidth": 0
        }
      },
      "edges": {
        "width": 1,
        "smooth": {
          "type": "continuous"
        },
        "color": {
          "color": "rgba(120, 110, 90, 0.35)",
          "highlight": "rgba(120, 110, 90, 0.6)",
          "hover": "rgba(120, 110, 90, 0.6)"
        }
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 200,
        "hideEdgesOnDrag": false,
        "hideNodesOnDrag": false
      }
    }
    """)

    return net.generate_html()
