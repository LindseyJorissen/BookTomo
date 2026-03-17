import json

import networkx as nx
from pyvis.network import Network


def truncate(text, max_len=30):
    """Shorten text to max_len characters, appending an ellipsis if truncated."""
    if not text:
        return ""
    return text if len(text) <= max_len else text[:27] + "…"


def visualize_book_ego_graph_interactive(graph, focus_book_id):
    """Generate an interactive PyVis ego-graph centered on the given book.

    Uses an ego-graph with radius 4 to show direct and indirect connections.
    Clicking an unread recommendation node sends a postMessage to the React
    parent so the detail panel can display the full explanation.
    Returns the graph as a self-contained HTML string.

    Node colors:
      - Selected book:          dark green  (#8fa6a0)
      - Other read books:       light green (#b7c7c2)
      - Unread recommendations: warm gold   (#e6c79c)
      - Authors and subjects:   beige       (#c4b7a6)
    """
    if focus_book_id not in graph:
        raise ValueError("Book not found in graph")

    net = Network(
        height="670px",
        width="100%",
        bgcolor="#ebe8dd",
        font_color="#4c483c",
        notebook=False,
        cdn_resources="in_line",
    )

    ego = graph.subgraph(nx.ego_graph(graph, focus_book_id, radius=4).nodes)

    # Data sent via postMessage when an unread book node is clicked
    click_node_info = {}
    # Data shown in the floating hover card (all book nodes)
    hover_node_info = {}
    # Nodes that need a tinted colour overlay on their cover image
    image_overlay_nodes = {}

    for node, data in ego.nodes(data=True):
        node_type = data.get("type")

        if node_type == "book":
            full_title = data.get("title", "")
            label = truncate(full_title)
            cover_url = data.get("cover_url")
            rating = data.get("rating")

            if data.get("unread"):
                border_color = "#e6c79c"
                size = 25
                click_node_info[node] = {
                    "title": full_title,
                    "author": data.get("author", ""),
                    "cover_url": cover_url or "",
                    "reason": data.get("reason", ""),
                    "signals": data.get("signals", []),
                    "similarity_score": data.get("similarity_score", 0.65),
                }
            else:
                border_color = "#ebe8dd" if node == focus_book_id else "#b7c7c2"
                size = 35 if node == focus_book_id else 28

            hover_node_info[node] = {
                "title": full_title,
                "author": data.get("author", ""),
                "rating": rating,
                "cover_url": cover_url or "",
                "unread": bool(data.get("unread")),
            }

            if cover_url:
                image_overlay_nodes[node] = {"color": border_color, "size": size}
                net.add_node(
                    node,
                    label=label,
                    title="",
                    shape="image",
                    image=cover_url,
                    color={"border": border_color, "background": border_color},
                    borderWidth=4,
                    size=size,
                )
            else:
                net.add_node(node, label=label, title="", color=border_color, size=size)

        elif node_type == "author":
            label = data.get("name", "")
            net.add_node(node, label=label, title="", color="#c4b7a6", size=26)

        elif node_type == "award":
            label = data.get("name", "")
            net.add_node(
                node,
                label=label,
                title="",
                color={"background": "#d4af7a", "border": "#b8922e"},
                size=24,
                shape="diamond",
            )

        elif node_type == "era":
            label = data.get("name", "")
            net.add_node(
                node,
                label=label,
                title="",
                color={"background": "#a8b8c8", "border": "#6a8ca8"},
                size=24,
                shape="triangle",
            )

        else:
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
            value=data.get("weight", 1.0),
            title=data.get("title"),
            color="rgba(120, 110, 90, 0.35)",
            smooth=True,
        )

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
        "stabilization": { "iterations": 300 }
      },
      "nodes": {
        "font": { "size": 13, "face": "Arial", "color": "#4c483c", "strokeWidth": 0 }
      },
      "edges": {
        "width": 1,
        "smooth": { "type": "continuous" },
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

    click_node_info_json = json.dumps(click_node_info)
    hover_node_info_json = json.dumps(hover_node_info)
    overlay_nodes_json = json.dumps(image_overlay_nodes)

    injected_script = f"""
    <style>
      body {{ background-color: #ebe8dd; margin: 0; padding: 0; }}
      #mynetwork {{ border: none !important; }}
      .card {{ border: none !important; }}
      ::-webkit-scrollbar {{ width: 5px; height: 5px; }}
      ::-webkit-scrollbar-track {{ background: transparent; }}
      ::-webkit-scrollbar-thumb {{ background: #c4b7a6; border-radius: 3px; }}
      ::-webkit-scrollbar-thumb:hover {{ background: #a39988; }}
    </style>
    <!-- Hover card (floating near cursor, book nodes only) -->
    <div id="hover-card" style="
        display: none;
        position: fixed;
        background: #f5f2eb;
        border: 1px solid #c4b7a6;
        border-radius: 10px;
        padding: 10px;
        width: 150px;
        z-index: 1000;
        pointer-events: none;
        box-shadow: 4px 4px 12px rgba(0,0,0,0.15), -2px -2px 6px rgba(255,255,255,0.7);
        font-family: Arial, sans-serif;
        font-size: 12px;
        color: #4c483c;
        line-height: 1.4;
    "></div>

    <script type="text/javascript">
      var clickNodeInfo = {click_node_info_json};
      var hoverNodeInfo = {hover_node_info_json};
      var overlayNodes  = {overlay_nodes_json};
      var hoverCard     = document.getElementById("hover-card");

      // ── Graph load animation ─────────────────────────────────────────────
      var networkDiv = document.getElementById("mynetwork");
      networkDiv.style.opacity = "0";
      networkDiv.style.transition = "opacity 0.6s ease-out";

      setTimeout(function() {{
        // Collapse all nodes to centre so they fan out during stabilisation
        var allIds = network.body.data.nodes.getIds();
        var updates = allIds.map(function(id) {{ return {{ id: id, x: 0, y: 0 }}; }});
        network.body.data.nodes.update(updates);
        network.startSimulation();

        // Fade canvas in
        networkDiv.style.opacity = "1";

        // Focus selected book after physics stabilises so the node is in its final position
        network.once("stabilizationIterationsDone", function() {{
          if (network.body.data.nodes.get("{focus_book_id}")) {{
            network.focus("{focus_book_id}", {{
              scale: 1.2,
              animation: {{ duration: 600, easingFunction: "easeInOutQuad" }}
            }});
          }}
        }});

        // ── Colour overlay on image nodes ──────────────────────────────────
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

        // ── Click: send recommendation data to React parent via postMessage ─
        network.on("click", function(params) {{
          if (params.nodes.length === 0) return;
          var info = clickNodeInfo[params.nodes[0]];
          if (!info) return;
          window.parent.postMessage(
            Object.assign({{ type: "BOOK_CLICK" }}, info),
            "*"
          );
        }});

        // ── Hover card ─────────────────────────────────────────────────────
        network.on("hoverNode", function(params) {{
          var info = hoverNodeInfo[params.node];
          if (!info) {{ hoverCard.style.display = "none"; return; }}

          var stars = "";
          if (info.rating) {{
            for (var i = 0; i < 5; i++) {{
              stars += i < info.rating ? "★" : "☆";
            }}
          }}
          var imgHtml = info.cover_url
            ? "<img src='" + info.cover_url + "' style='width:100%;border-radius:6px;margin-bottom:8px;display:block;'/>"
            : "";

          hoverCard.innerHTML =
            imgHtml +
            "<strong style='font-size:13px;'>" + info.title + "</strong><br>" +
            "<span style='color:#7a7060;font-size:11px;'>" + info.author + "</span>" +
            (stars ? "<br><span style='color:#d4af7a;font-size:13px;margin-top:2px;display:block;'>" + stars + "</span>" : "");

          hoverCard.style.display = "block";
        }});

        network.on("blurNode", function() {{
          hoverCard.style.display = "none";
        }});
      }}, 300);

      // Track mouse position for the hover card
      document.addEventListener("mousemove", function(e) {{
        if (hoverCard.style.display === "none") return;
        var x = e.clientX + 18;
        var y = e.clientY - 20;
        var cardH = hoverCard.offsetHeight || 300;
        if (x + 170 > window.innerWidth)  x = e.clientX - 170;
        if (y + cardH > window.innerHeight) y = e.clientY - cardH;
        hoverCard.style.left = x + "px";
        hoverCard.style.top  = y + "px";
      }});
    </script>
    """

    html = html.replace("</body>", injected_script + "\n</body>")
    return html
