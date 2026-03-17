import json

import networkx as nx
from networkx.algorithms import bipartite
from pyvis.network import Network

from books.graph_engine.universe import _CLUSTER_COLORS
from books.graph_engine.visualize_interactive import truncate


def render_full_network(graph, communities=None, cover_map: dict = None) -> str:
    """Render a PyVis graph of all read books and how they connect.

    Uses a book-to-book projected graph where an edge means the two books share
    at least 2 subject tags. Books are coloured by taste cluster so the layout
    visually echoes the Reading Universe. Clicking a book sends a
    READ_BOOK_CLICK postMessage to open its ego-graph in React.
    """
    cover_map = cover_map or {}

    # Map book node id → cluster colour
    node_colors: dict = {}
    if communities:
        for i, cluster in enumerate(communities):
            color = _CLUSTER_COLORS[i % len(_CLUSTER_COLORS)]
            for book_node in cluster["book_nodes"]:
                node_colors[book_node] = color

    book_node_set = {n for n, d in graph.nodes(data=True) if d.get("type") == "book"}

    # Project book↔subject bipartite graph to book-book graph.
    # Edge weight = number of shared subjects between the two books.
    try:
        projected = bipartite.weighted_projected_graph(graph, book_node_set)
    except Exception:
        projected = nx.Graph()

    net = Network(
        height="670px",
        width="100%",
        bgcolor="#ebe8dd",
        font_color="#4c483c",
        notebook=False,
        cdn_resources="in_line",
    )

    hover_node_info: dict = {}
    image_overlay_nodes: dict = {}
    click_node_info: dict = {}

    for node_id in book_node_set:
        data = graph.nodes[node_id]
        full_title = data.get("title", "")
        label = truncate(full_title)
        cover_url = cover_map.get(node_id) or data.get("cover_url")
        rating = data.get("rating")
        color = node_colors.get(node_id, "#c4b7a6")

        # Size by degree in projected graph so well-connected books stand out
        deg = projected.degree(node_id) if projected.has_node(node_id) else 0
        size = min(20 + deg * 2, 42)

        hover_node_info[node_id] = {
            "title": full_title,
            "author": data.get("author", ""),
            "rating": rating,
            "cover_url": cover_url or "",
        }
        click_node_info[node_id] = {"bookId": node_id.replace("book::", "")}

        if cover_url:
            image_overlay_nodes[node_id] = {"color": color, "size": size}
            net.add_node(
                node_id,
                label=label,
                title="",
                shape="image",
                image=cover_url,
                color={"border": color, "background": color},
                borderWidth=4,
                size=size,
            )
        else:
            net.add_node(node_id, label=label, title="", color=color, size=size)

    # Only draw edges with 2+ shared subjects to keep the graph readable
    for u, v, edata in projected.edges(data=True):
        if edata.get("weight", 1) >= 2:
            net.add_edge(u, v, value=edata["weight"], color="rgba(120, 110, 90, 0.25)", smooth=True)

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -120,
          "centralGravity": 0.008,
          "springLength": 200,
          "springConstant": 0.02,
          "avoidOverlap": 1
        },
        "stabilization": { "iterations": 400 }
      },
      "nodes": {
        "font": { "size": 12, "face": "Arial", "color": "#4c483c", "strokeWidth": 0 }
      },
      "edges": {
        "width": 1,
        "smooth": { "type": "continuous" },
        "color": {
          "color": "rgba(120, 110, 90, 0.25)",
          "highlight": "rgba(120, 110, 90, 0.55)",
          "hover": "rgba(120, 110, 90, 0.55)"
        }
      },
      "interaction": { "hover": true, "tooltipDelay": 200, "hideEdgesOnDrag": true }
    }
    """)

    html = net.generate_html()
    click_json = json.dumps(click_node_info)
    hover_json = json.dumps(hover_node_info)
    overlay_json = json.dumps(image_overlay_nodes)

    injected = f"""
    <style>
      body {{ background-color: #ebe8dd; margin: 0; padding: 0; }}
      #mynetwork {{ border: none !important; }}
      .card {{ border: none !important; }}
      ::-webkit-scrollbar {{ width: 5px; height: 5px; }}
      ::-webkit-scrollbar-track {{ background: transparent; }}
      ::-webkit-scrollbar-thumb {{ background: #c4b7a6; border-radius: 3px; }}
      ::-webkit-scrollbar-thumb:hover {{ background: #a39988; }}
    </style>
    <div id="hover-card" style="
        display: none; position: fixed;
        background: #f5f2eb; border: 1px solid #c4b7a6; border-radius: 10px;
        padding: 10px; width: 150px; z-index: 1000; pointer-events: none;
        box-shadow: 4px 4px 12px rgba(0,0,0,0.15), -2px -2px 6px rgba(255,255,255,0.7);
        font-family: Arial, sans-serif; font-size: 12px; color: #4c483c; line-height: 1.4;
    "></div>
    <script type="text/javascript">
      var clickNodeInfo = {click_json};
      var hoverNodeInfo = {hover_json};
      var overlayNodes  = {overlay_json};
      var hoverCard     = document.getElementById("hover-card");
      var networkDiv    = document.getElementById("mynetwork");
      networkDiv.style.opacity = "0";
      networkDiv.style.transition = "opacity 0.8s ease-out";

      setTimeout(function() {{
        var allIds = network.body.data.nodes.getIds();
        var updates = allIds.map(function(id) {{ return {{ id: id, x: 0, y: 0 }}; }});
        network.body.data.nodes.update(updates);
        network.startSimulation();
        networkDiv.style.opacity = "1";

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
          if (params.nodes.length === 0) return;
          var info = clickNodeInfo[params.nodes[0]];
          if (!info) return;
          window.parent.postMessage({{ type: "READ_BOOK_CLICK", bookId: info.bookId }}, "*");
        }});

        network.on("hoverNode", function(params) {{
          var info = hoverNodeInfo[params.node];
          if (!info) {{ hoverCard.style.display = "none"; return; }}
          var stars = "";
          if (info.rating) {{
            for (var i = 0; i < 5; i++) {{ stars += i < info.rating ? "★" : "☆"; }}
          }}
          var imgHtml = info.cover_url
            ? "<img src='" + info.cover_url + "' style='width:100%;border-radius:6px;margin-bottom:8px;display:block;'/>"
            : "";
          hoverCard.innerHTML = imgHtml +
            "<strong style='font-size:13px;'>" + info.title + "</strong><br>" +
            "<span style='color:#7a7060;font-size:11px;'>" + info.author + "</span>" +
            (stars ? "<br><span style='color:#d4af7a;font-size:13px;margin-top:2px;display:block;'>" + stars + "</span>" : "");
          hoverCard.style.display = "block";
        }});

        network.on("blurNode", function() {{ hoverCard.style.display = "none"; }});
      }}, 300);

      document.addEventListener("mousemove", function(e) {{
        if (hoverCard.style.display === "none") return;
        var x = e.clientX + 18, y = e.clientY - 20;
        var cardH = hoverCard.offsetHeight || 300;
        if (x + 170 > window.innerWidth)  x = e.clientX - 170;
        if (y + cardH > window.innerHeight) y = e.clientY - cardH;
        hoverCard.style.left = x + "px";
        hoverCard.style.top  = y + "px";
      }});
    </script>
    """

    html = html.replace("</body>", injected + "\n</body>")
    return html
