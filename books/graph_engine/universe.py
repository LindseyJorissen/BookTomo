import html as _html
import json
import re

from pyvis.network import Network

# ── Palette ────────────────────────────────────────────────────────────────────
_CLUSTER_COLORS = [
    "#8fa6a0", "#e6c79c", "#b7c7c2", "#c4b7a6",
    "#d4af7a", "#a8b8c8", "#c9a6a6", "#a6c9b7",
]

# Subjects too generic to appear in a cluster label
_GENERIC_SUBJECTS = {
    "fiction", "nonfiction", "non-fiction", "literature", "books",
    "english literature", "american literature", "american fiction",
    "english fiction", "prose literature", "general", "essays",
    "biography", "autobiography", "juvenile fiction", "young adult fiction",
    "children's books", "picture books", "poetry", "drama", "short stories",
    "anthologies", "collections", "history", "novel", "novels",
}


# ── Cluster analysis helpers ────────────────────────────────────────────────────

def _clean_subject(subject: str) -> str:
    """Strip trailing '-- Fiction' / '-- Juvenile fiction' qualifiers and trim."""
    return re.sub(r"\s+--\s+.*$", "", subject).strip()


def _analyze_cluster(book_node_ids: list, graph) -> dict:
    """Extract genres, authors, and titles from a cluster's book nodes.

    Returns a dict with:
      - genres:         List[str] of meaningful subjects sorted by frequency
      - author_counts:  Dict[str, int] mapping author name to book count
      - titles:         List[str] of book titles in the cluster
      - dominant_author: str | None — author present in > 60 % of books
    """
    genre_counts: dict = {}
    author_counts: dict = {}
    titles: list = []

    for node_id in book_node_ids:
        node_data = graph.nodes[node_id]
        author = node_data.get("author", "")
        title = node_data.get("title", "")

        if author:
            author_counts[author] = author_counts.get(author, 0) + 1
        if title:
            titles.append(title)

        # Collect genre/subject nodes connected to this book node
        for nb in graph.neighbors(node_id):
            if graph.nodes[nb].get("type") == "subject":
                raw_name = graph.nodes[nb].get("name", "")
                cleaned = _clean_subject(raw_name)
                if cleaned and cleaned.lower() not in _GENERIC_SUBJECTS and len(cleaned) >= 4:
                    genre_counts[cleaned] = genre_counts.get(cleaned, 0) + 1

    sorted_genres = sorted(genre_counts, key=genre_counts.get, reverse=True)

    # Dominant author: single author with > 60 % share of books in the cluster
    total = len(book_node_ids) or 1
    dominant_author = None
    for author, count in sorted(author_counts.items(), key=lambda x: x[1], reverse=True):
        if count / total > 0.6:
            dominant_author = author
            break

    return {
        "genres": sorted_genres[:6],
        "author_counts": author_counts,
        "titles": titles,
        "dominant_author": dominant_author,
    }


def _generate_cluster_label(analysis: dict, index: int) -> str:
    """Generate a human-readable reading-taste label for a cluster.

    Priority:
      1. "{Author} Universe"     — if one author dominates (> 60 % of books)
      2. "{Genre1} & {Genre2}"   — if two meaningful genres are available
      3. "{Genre1}"              — single meaningful genre
      4. "Reading Cluster {n}"   — fallback
    """
    if analysis["dominant_author"]:
        return f"{analysis['dominant_author']} Universe"

    genres = analysis["genres"]
    if len(genres) >= 2:
        return f"{genres[0]} & {genres[1]}"
    if genres:
        return genres[0]
    return f"Reading Cluster {index + 1}"


def _generate_explanation_signals(analysis: dict) -> list:
    """Build bullet-point reasons explaining why a cluster was formed.

    Returns up to 3 human-readable signal strings.
    """
    signals = []

    genres = analysis["genres"]
    if genres:
        signals.append(f"{genres[0]} genre")
    if len(genres) >= 2:
        signals.append(f"{genres[1]} themes")

    dominant = analysis["dominant_author"]
    if dominant:
        signals.append(f"Strong {dominant} author connections")
    elif analysis["author_counts"]:
        top_author = max(analysis["author_counts"], key=analysis["author_counts"].get)
        if analysis["author_counts"][top_author] >= 2:
            signals.append(f"Multiple {top_author} books")

    return signals[:3]


def _generate_tooltip_html(label: str, book_count: int, analysis: dict) -> str:
    """Build a safe HTML string for the custom cluster tooltip.

    Dynamic values are HTML-escaped to prevent injection from author names /
    book titles that contain quotes or angle brackets.
    """
    book_word = "book" if book_count == 1 else "books"
    signals = _generate_explanation_signals(analysis)

    e = _html.escape  # shorthand

    reason_html = "".join(f"<div>&bull; {e(s)}</div>" for s in signals)
    example_html = "".join(f"<div>&bull; {e(t)}</div>" for t in analysis["titles"][:3])

    return (
        "<div style=\"font-family:Arial,sans-serif;font-size:13px;"
        "max-width:240px;line-height:1.6;padding:4px\">"
        f"<b style=\"font-size:14px\">{e(label)}</b><br>"
        f"<span style=\"color:#888\">{book_count} {book_word}</span>"
        "<br><br>"
        "<b>Grouped because these books share:</b>"
        f"<div style=\"margin:4px 0 8px\">{reason_html}</div>"
        "<b>Examples:</b>"
        f"<div style=\"margin:4px 0 8px\">{example_html}</div>"
        "<i style=\"color:#999\">Click to explore</i>"
        "</div>"
    )


# ── Community detection ─────────────────────────────────────────────────────────

def detect_communities(graph) -> list:
    """Detect reading-taste communities using greedy modularity maximisation.

    Projects the bipartite book↔subject graph onto a book-book graph first
    (an edge = shared subject, weight = number of shared subjects), then runs
    community detection on that projection so books genuinely cluster by genre.

    Returns a list of cluster dicts sorted by book count (largest first).
    Each dict contains:
      id, name, book_count, book_nodes, representative_book,
      top_genres, explanation_signals, tooltip_html.

    Returns an empty list if the graph is too small or detection fails.
    """
    if graph is None or len(graph) < 4:
        return []

    try:
        import networkx as nx
        from networkx.algorithms import bipartite
        from networkx.algorithms.community import (
            louvain_communities,
            greedy_modularity_communities,
        )

        book_node_set = {n for n, d in graph.nodes(data=True) if d.get("type") == "book"}
        if len(book_node_set) < 4:
            return []

        # Project bipartite book↔subject graph to book-book graph.
        # Edge weight = number of shared subjects between two books.
        projected = bipartite.weighted_projected_graph(graph, book_node_set)

        # Drop isolated books that share no subjects with any other book.
        projected.remove_nodes_from(list(nx.isolates(projected)))
        if len(projected) < 4:
            return []

        # Louvain with resolution > 1 produces more fine-grained clusters.
        # Fall back to greedy if Louvain is unavailable (older NetworkX).
        try:
            raw = list(louvain_communities(projected, weight="weight", resolution=1.5, seed=42))
        except Exception:
            raw = list(greedy_modularity_communities(projected, weight="weight"))
    except Exception:
        return []

    result = []
    for i, comm in enumerate(raw):
        book_nodes = list(comm)
        if not book_nodes:
            continue

        analysis = _analyze_cluster(book_nodes, graph)
        label = _generate_cluster_label(analysis, i)
        signals = _generate_explanation_signals(analysis)
        tooltip_html = _generate_tooltip_html(label, len(book_nodes), analysis)

        # Representative book: most connected in the book-book projected graph
        rep_book = max(book_nodes, key=lambda n: projected.degree(n))

        result.append({
            "id": f"cluster::{i}",
            "name": label,
            "book_count": len(book_nodes),
            "book_nodes": book_nodes,
            "representative_book": rep_book,
            "top_genres": analysis["genres"][:3],
            "explanation_signals": signals,
            "tooltip_html": tooltip_html,
        })

    return sorted(result, key=lambda c: c["book_count"], reverse=True)


# ── Graph rendering ─────────────────────────────────────────────────────────────

_LEGEND_HTML = """
<div style="
  position:fixed;bottom:14px;left:14px;
  font-family:Arial,sans-serif;font-size:11px;color:#888;
  background:rgba(235,232,221,0.92);padding:8px 12px;
  border-radius:8px;line-height:1.7;z-index:100;
  border:1px solid rgba(0,0,0,0.07);
">
  <b style="display:block;margin-bottom:2px;color:#666;font-size:12px">Reading Universe</b>
  &#9679; Node size = books in cluster<br>
  &#9679; Colours = different taste clusters<br>
  &#9679; Click a cluster to explore
</div>
"""


def render_universe_graph(clusters: list, graph) -> str:
    """Render the Reading Universe as a PyVis force-directed graph.

    Each node represents a reading-taste cluster. Node size is proportional
    to book count. Edges connect clusters that share genre (subject) nodes.

    Clicking a cluster sends a postMessage to the parent React app, which
    switches to the ego-graph of the cluster's representative book.
    """
    net = Network(
        height="670px",
        width="100%",
        bgcolor="#ebe8dd",
        font_color="#4c483c",
        notebook=False,
        cdn_resources="in_line",
    )

    cluster_info: dict = {}
    tooltip_html_map: dict = {}  # cid → HTML string, injected via custom JS tooltip

    for i, cluster in enumerate(clusters):
        cid = cluster["id"]
        color = _CLUSTER_COLORS[i % len(_CLUSTER_COLORS)]
        count = cluster["book_count"]
        size = min(28 + count * 5, 90)
        node_label = f"{cluster['name']}\n{count} book{'s' if count != 1 else ''}"

        # No `title` attribute — vis.js renders titles as escaped text, not HTML.
        # The custom tooltip is injected via JavaScript below.
        net.add_node(
            cid,
            label=node_label,
            color={"background": color, "border": color},
            size=size,
            shape="dot",
        )
        cluster_info[cid] = {
            "name": cluster["name"],
            "book_count": count,
            "representative_book": cluster["representative_book"],
            "top_genres": cluster["top_genres"],
            "book_nodes": cluster["book_nodes"],
        }
        tooltip_html_map[cid] = cluster["tooltip_html"]

    # Edges between clusters that share genre (subject) nodes
    genre_to_clusters: dict = {}
    for cluster in clusters:
        for book_node in cluster["book_nodes"]:
            for nb in graph.neighbors(book_node):
                if graph.nodes[nb].get("type") == "subject":
                    genre_to_clusters.setdefault(nb, set()).add(cluster["id"])

    seen_edges: set = set()
    for _, cid_set in genre_to_clusters.items():
        cids = list(cid_set)
        for a in range(len(cids)):
            for b in range(a + 1, len(cids)):
                edge = tuple(sorted([cids[a], cids[b]]))
                if edge not in seen_edges:
                    net.add_edge(cids[a], cids[b], color="rgba(120, 110, 90, 0.2)", smooth=True)
                    seen_edges.add(edge)

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -150,
          "centralGravity": 0.015,
          "springLength": 280,
          "springConstant": 0.02,
          "avoidOverlap": 1
        },
        "stabilization": { "iterations": 200 }
      },
      "nodes": {
        "font": { "size": 13, "face": "Arial", "color": "#4c483c", "multi": true }
      },
      "edges": {
        "smooth": { "type": "continuous" }
      },
      "interaction": { "hover": true }
    }
    """)

    html = net.generate_html()
    cluster_info_json = json.dumps(cluster_info)
    tooltip_html_json = json.dumps(tooltip_html_map)

    injected = f"""
    <style>
      body {{ background-color: #ebe8dd; margin: 0; padding: 0; }}
      #mynetwork {{ border: none !important; }}
      .card {{ border: none !important; }}
      ::-webkit-scrollbar {{ width: 5px; height: 5px; }}
      ::-webkit-scrollbar-track {{ background: transparent; }}
      ::-webkit-scrollbar-thumb {{ background: #c4b7a6; border-radius: 3px; }}
      ::-webkit-scrollbar-thumb:hover {{ background: #a39988; }}
      #cluster-tooltip {{
        display: none;
        position: fixed;
        background: #fff;
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 12px 14px;
        font-family: Arial, sans-serif;
        font-size: 13px;
        max-width: 260px;
        line-height: 1.6;
        z-index: 1000;
        box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        pointer-events: none;
        color: #333;
      }}
    </style>
    <div id="cluster-tooltip"></div>

    <script type="text/javascript">
      var clusterInfo   = {cluster_info_json};
      var tooltipHtml   = {tooltip_html_json};
      var networkDiv    = document.getElementById("mynetwork");
      var tooltipEl     = document.getElementById("cluster-tooltip");

      // ── Custom HTML tooltip ────────────────────────────────────────────────
      document.addEventListener("mousemove", function(e) {{
        if (tooltipEl.style.display === "block") {{
          var x = e.clientX + 14;
          var y = e.clientY - 10;
          // Keep tooltip inside viewport
          if (x + 270 > window.innerWidth)  x = e.clientX - 274;
          if (y + tooltipEl.offsetHeight > window.innerHeight) y = e.clientY - tooltipEl.offsetHeight - 10;
          tooltipEl.style.left = x + "px";
          tooltipEl.style.top  = y + "px";
        }}
      }});

      networkDiv.style.opacity = "0";
      networkDiv.style.transition = "opacity 0.7s ease-out";

      setTimeout(function() {{
        // Place all nodes at centre so they fan out during stabilisation
        var allIds = network.body.data.nodes.getIds();
        var updates = allIds.map(function(id) {{ return {{ id: id, x: 0, y: 0 }}; }});
        network.body.data.nodes.update(updates);
        network.startSimulation();
        networkDiv.style.opacity = "1";

        network.on("hoverNode", function(params) {{
          var html = tooltipHtml[params.node];
          if (!html) return;
          tooltipEl.innerHTML = html;
          tooltipEl.style.display = "block";
        }});

        network.on("blurNode", function() {{
          tooltipEl.style.display = "none";
        }});

        network.on("click", function(params) {{
          tooltipEl.style.display = "none";
          if (params.nodes.length === 0) return;
          var info = clusterInfo[params.nodes[0]];
          if (!info) return;
          window.parent.postMessage({{
            type: "CLUSTER_CLICK",
            representativeBook: info.representative_book,
            clusterName: info.name,
            topGenres: info.top_genres,
            bookNodes: info.book_nodes,
          }}, "*");
        }});
      }}, 300);
    </script>
    {_LEGEND_HTML}
    """

    html = html.replace("</body>", injected + "\n</body>")
    return html


def render_cluster_graph(book_node_ids: list, graph, cover_map: dict = None) -> str:
    """Render a PyVis graph of books within a single taste cluster.

    Shows books connected via shared subject nodes (subjects linked to 2+ books
    in the cluster). Clicking a book sends a READ_BOOK_CLICK postMessage to the
    React parent so it can switch to that book's ego-graph.
    """
    from pyvis.network import Network
    from books.graph_engine.visualize_interactive import truncate

    cover_map = cover_map or {}

    # Subjects shared by 2+ cluster books — used as connector nodes
    subject_to_book_count: dict = {}
    for node_id in book_node_ids:
        if node_id not in graph:
            continue
        for nb in graph.neighbors(node_id):
            if graph.nodes[nb].get("type") == "subject":
                subject_to_book_count[nb] = subject_to_book_count.get(nb, 0) + 1

    shared_subjects = {s for s, c in subject_to_book_count.items() if c >= 2}
    if not shared_subjects:
        shared_subjects = set(subject_to_book_count.keys())

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

    valid_book_nodes = [n for n in book_node_ids if n in graph]
    for node_id in valid_book_nodes:
        data = graph.nodes[node_id]
        full_title = data.get("title", "")
        label = truncate(full_title)
        cover_url = cover_map.get(node_id) or data.get("cover_url")
        rating = data.get("rating")
        color = "#b7c7c2"
        size = 30

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

    for subject_id in shared_subjects:
        if subject_id not in graph:
            continue
        name = graph.nodes[subject_id].get("name", subject_id.replace("subject::", ""))
        net.add_node(
            subject_id,
            label=name,
            title="",
            color={"background": "#c4b7a6", "border": "#c4b7a6"},
            size=14,
        )

    valid_set = set(valid_book_nodes)
    for node_id in valid_set:
        for nb in graph.neighbors(node_id):
            if nb in shared_subjects:
                net.add_edge(node_id, nb, color="rgba(120, 110, 90, 0.35)", smooth=True)

    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -60,
          "centralGravity": 0.01,
          "springLength": 150,
          "springConstant": 0.04,
          "avoidOverlap": 1
        },
        "stabilization": { "iterations": 300 }
      },
      "nodes": {
        "font": { "size": 12, "face": "Arial", "color": "#4c483c", "strokeWidth": 0 }
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
      "interaction": { "hover": true, "tooltipDelay": 200 }
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
      networkDiv.style.transition = "opacity 0.6s ease-out";

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
