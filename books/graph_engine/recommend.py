def recommend_books_by_author(graph, book_id, top_n=5):
    book_node = f"book::{book_id}"

    if book_node not in graph:
        return []

    recommendations = []

    for neighbor in graph.neighbors(book_node):
        if graph.nodes[neighbor]["type"] != "author":
            continue

        for other in graph.neighbors(neighbor):
            if other == book_node:
                continue

            edge_data = graph.get_edge_data(neighbor, other)
            weight = edge_data.get("weight", 1.0)

            recommendations.append({
                "book_node": other,
                "weight": weight,
                "title": graph.nodes[other]["title"]
            })

    recommendations.sort(key=lambda x: x["weight"], reverse=True)

    return recommendations[:top_n]
