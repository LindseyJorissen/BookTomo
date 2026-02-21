from pyvis.network import Network
import networkx as nx


def truncate(text, max_len=30):
    """Verkort tekst tot max_len tekens en voegt een beletselteken toe als het langer is."""
    if not text:
        return ""
    return text if len(text) <= max_len else text[:27] + "…"


def visualize_book_ego_graph_interactive(graph, focus_book_id):
    """
    Genereert een interactieve pyvis-graaf rondom het opgegeven boek.
    Gebruikt een ego-graaf met straal 4 om directe en indirecte verbindingen te tonen.
    Geeft de graaf terug als een HTML-string met ingesloten JavaScript.

    Knooppuntkleuren:
      - Geselecteerd boek: donkergroen (#8fa6a0)
      - Overige gelezen boeken: lichtgroen (#b7c7c2)
      - Ongelezen aanbevelingen: warm goud (#e6c79c)
      - Auteurs en onderwerpen: beige (#c4b7a6)
    """
    book_node = focus_book_id

    if book_node not in graph:
        raise ValueError("Book not found in graph")

    net = Network(
        height="600px",
        width="100%",
        bgcolor="#faf9f6",
        font_color="#4c483c",
        notebook=False,
        cdn_resources="in_line"  # JavaScript wordt ingesloten in de HTML (geen CDN nodig)
    )

    # Bouw een ego-graaf: alle knopen binnen straal 4 van het geselecteerde boek
    ego = graph.subgraph(
        nx.ego_graph(graph, book_node, radius=4).nodes
    )

    for node, data in ego.nodes(data=True):
        node_type = data.get("type")
        tooltip = ""

        if node_type == "book":
            full_title = data.get("title", "")
            label = truncate(full_title)
            tooltip = full_title  # Volledige titel zichtbaar bij hover

            if data.get("unread"):
                color = "#e6c79c"  # Warm goud voor ongelezen aanbevelingen
                size = 18
            else:
                # Geselecteerd boek is groter en donkerder dan de rest
                color = "#8fa6a0" if node == book_node else "#b7c7c2"
                size = 28 if node == book_node else 20

        elif node_type == "author":
            label = data.get("name", "")
            tooltip = f"Auteur: {label}"
            color = "#c4b7a6"
            size = 26

        else:
            # Onderwerpknopen (of andere typen)
            label = data.get("name")
            color = {
                "background": "#c4b7a6",
                "border": "#c4b7a6",
                "opacity": 0.6
            }
            size = 26

        net.add_node(
            node,
            label=label,
            title=tooltip,  # Tooltip bij hover
            color=color,
            size=size
        )

    for source, target, data in ego.edges(data=True):
        net.add_edge(
            source,
            target,
            value=data.get("weight", 1.0),  # Dikte van de lijn op basis van gewicht
            title=data.get("title"),         # Tooltip op de kant (indien aanwezig)
            color="rgba(120, 110, 90, 0.35)",
            smooth=True
        )

    # Fysica-instellingen voor de graaf-layout (ForceAtlas2)
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
        "gravitationalConstant": -80,
        "centralGravity": 0.002,
        "springLength": 200,
        "springConstant": 0.02,
        "avoidOverlap": 1
        },
        "stabilization": {
          "iterations": 300
        }
      },
      "nodes": {
        "borderWidth": 0,
        "font": {
          "size": 13,
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

    html = net.generate_html()

    # Voeg een script toe dat de camera na het laden op het geselecteerde boek centreert
    focus_script = f"""
    <script type="text/javascript">
      setTimeout(function() {{
        if (network && network.body && network.body.data.nodes.get("{book_node}")) {{
          network.focus("{book_node}", {{
            scale: 1.2,
            animation: {{
              duration: 600,
              easingFunction: "easeInOutQuad"
            }}
          }});
        }}
      }}, 300);
    </script>
    """

    html = html.replace("</body>", focus_script + "\n</body>")
    return html
