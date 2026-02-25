import json

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

    click_node_info = {}
    image_overlay_nodes = {}  # {nodeId: {color, size}} — used by afterDrawing overlay

    for node, data in ego.nodes(data=True):
        node_type = data.get("type")

        if node_type == "book":
            full_title = data.get("title", "")
            label = truncate(full_title)
            cover_url = data.get("cover_url")

            if data.get("unread"):
                border_color = "#e6c79c"
                size = 25
                click_node_info[node] = {
                    "title": full_title,
                    "author": data.get("author", ""),
                    "reason": data.get("reason", ""),
                    "cover_url": cover_url or "",
                }
            else:
                border_color = "#8fa6a0" if node == book_node else "#b7c7c2"
                size = 35 if node == book_node else 28

            if cover_url:
                image_overlay_nodes[node] = {"color": border_color, "size": size}
                net.add_node(
                    node,
                    label=label,
                    title=full_title,
                    shape="image",
                    image=cover_url,
                    color={"border": border_color, "background": border_color},
                    borderWidth=4,
                    size=size,
                )
            else:
                net.add_node(
                    node,
                    label=label,
                    title=full_title,
                    color=border_color,
                    size=size,
                )

        elif node_type == "author":
            label = data.get("name", "")
            net.add_node(
                node,
                label=label,
                title=f"Author: {label}",
                color="#c4b7a6",
                size=26,
            )

        elif node_type == "award":
            label = data.get("name", "")
            net.add_node(
                node,
                label=label,
                title=f"Award: {label}",
                color={"background": "#d4af7a", "border": "#b8922e"},
                size=24,
                shape="diamond",
            )

        elif node_type == "era":
            label = data.get("name", "")
            net.add_node(
                node,
                label=label,
                title=f"Era: {label}",
                color={"background": "#a8b8c8", "border": "#6a8ca8"},
                size=24,
                shape="triangle",
            )

        else:
            # subject nodes and anything else
            net.add_node(
                node,
                label=data.get("name") or "",
                title="",
                color={"background": "#c4b7a6", "border": "#c4b7a6"},
                size=26,
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

    node_info_json = json.dumps(click_node_info)
    overlay_nodes_json = json.dumps(image_overlay_nodes)

    injected_script = f"""
    <div id="book-tooltip" style="
        display: none;
        position: fixed;
        bottom: 16px;
        left: 16px;
        background: #f5f2eb;
        border: 1px solid #c4b7a6;
        border-radius: 10px;
        padding: 12px 16px;
        max-width: 280px;
        z-index: 999;
        box-shadow: 3px 3px 8px rgba(0,0,0,0.12), -2px -2px 5px rgba(255,255,255,0.7);
        font-family: Arial, sans-serif;
        font-size: 13px;
        color: #4c483c;
        line-height: 1.5;
    "></div>
    <script type="text/javascript">
      var nodeInfo = {node_info_json};
      var overlayNodes = {overlay_nodes_json};

      var tooltip = document.getElementById("book-tooltip");

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

        // Draw a semi-transparent color overlay on image nodes.
        // Skipped for whichever node is currently selected, revealing the full image.
        network.on("afterDrawing", function(ctx) {{
          var selected = network.getSelectedNodes();
          for (var nid in overlayNodes) {{
            if (selected.indexOf(nid) >= 0) continue;
            var n = network.body.nodes[nid];
            if (!n) continue;
            var w = n.width  || overlayNodes[nid].size * 2;
            var h = n.height || overlayNodes[nid].size * 3;
            ctx.save();
            ctx.globalAlpha = 0.45;
            ctx.fillStyle = overlayNodes[nid].color;
            ctx.fillRect(n.x - w / 2, n.y - h / 2, w, h);
            ctx.restore();
          }}
        }});

        network.on("click", function(params) {{
          if (params.nodes.length > 0) {{
            var info = nodeInfo[params.nodes[0]];
            if (info) {{
              var imgHtml = info.cover_url
                ? "<img src='" + info.cover_url + "' style='width:60px; height:auto; border-radius:4px; flex-shrink:0; object-fit:cover;'/>"
                : "";
              tooltip.innerHTML =
                "<span style='font-size:11px; text-transform:uppercase; letter-spacing:0.08em; color:#a39988;'>Why suggested?</span>" +
                "<div style='display:flex; gap:10px; align-items:flex-start; margin-top:6px;'>" +
                  imgHtml +
                  "<div>" +
                    "<strong style='font-size:14px;'>" + info.title + "</strong><br>" +
                    "<span style='color:#7a7060;'>By " + info.author + "</span><br>" +
                    "<span style='display:block; margin-top:4px; font-style:italic;'>" + info.reason + "</span>" +
                  "</div>" +
                "</div>";
              tooltip.style.display = "block";
              return;
            }}
          }}
          tooltip.style.display = "none";
        }});
      }}, 300);
    </script>
    """

    html = html.replace("</body>", injected_script + "\n</body>")
    return html
