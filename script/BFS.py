# import numpy as np
# from scipy.sparse.csgraph import dijkstra, shortest_path
# import heapq
#
# def precompute_distance_matrix(path_or_text):
#     from pathlib import Path
#     from scipy.sparse import dok_matrix
#     raw_text = (
#         Path(path_or_text).read_text()
#         if Path(str(path_or_text)).exists()
#         else str(path_or_text)
#     ).strip()
#     lines = [ln.rstrip() for ln in raw_text.splitlines()]
#
#     height = int(next(ln.split()[1] for ln in lines[:4] if ln.startswith("height")))
#     width = int(next(ln.split()[1] for ln in lines[:4] if ln.startswith("width")))
#     grid = np.array([list(ln) for ln in lines[4: 4 + height]], dtype="U1")
#
#     total_cells = height * width
#     to_node = lambda r, c: r * width + c
#     cardinal = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # N, S, W, E
#
#     graph = dok_matrix((total_cells, total_cells), dtype=np.uint8)
#
#     for row in range(height):
#         for col in range(width):
#             if grid[row, col] == "@":
#                 continue
#             node = to_node(row, col)
#             for dr, dc in cardinal:
#                 nr, nc = row + dr, col + dc
#                 if (
#                         0 <= nr < height
#                         and 0 <= nc < width
#                         and grid[nr, nc] != "@"
#                 ):
#                     graph[node, to_node(nr, nc)] = 1  # undirected edge
#     return graph.tocsr()
#
# matrix = precompute_distance_matrix(r"C:\Users\steph\PycharmProjects\PlanViz\example\warehouse_small.map")
#
#
# def choose_landmarks(graph, num_landmarks=8):
#     from scipy.sparse.csgraph import dijkstra
#     import numpy as np
#
#     num_nodes = graph.shape[0]
#     landmarks = []
#     dist_matrix = np.empty((num_landmarks, num_nodes), dtype=np.float32)
#
#     # Start from the first walkable node
#     for i in range(num_nodes):
#         if graph.getrow(i).nnz > 0:
#             current = i
#             break
#     else:
#         raise ValueError("No walkable node found.")
#
#     for i in range(num_landmarks):
#         dist = dijkstra(graph, directed=False, indices=current)
#         dist[np.isinf(dist)] = 0
#         dist_matrix[i] = dist
#         landmarks.append(current)
#
#         # Sort nodes by distance descending and skip already used landmarks
#         sorted_nodes = np.argsort(-dist)
#         for next_candidate in sorted_nodes:
#             if next_candidate not in landmarks and dist[next_candidate] > 0:
#                 current = next_candidate
#                 break
#         else:
#             print(f"⚠️ Could not find a new distant node at landmark {i+1}")
#             return landmarks, dist_matrix[:i+1]
#
#     return landmarks, dist_matrix
#
# def estimated_distance_ALT(loc, goal, width, landmark_dists):
#     to_id = lambda rc: rc[0] * width + rc[1]
#     u, v = to_id(loc), to_id(goal)
#     return max(
#         abs(landmark_dists[i, u] - landmark_dists[i, v])
#         for i in range(landmark_dists.shape[0])
#     )
#
# true_dist_matrix = shortest_path(
#             matrix,
#             directed=False,
#             unweighted=True
#         )
# print(true_dist_matrix)
#
# def shortest_path_distance(loc, goal, width):
#     to_id = lambda rc: rc[0] * width + rc[1]
#     return true_dist_matrix[to_id(loc), to_id(goal)]
#
#
#
# estimated_distance = (choose_landmarks(matrix))
# lower = estimated_distance_ALT(
#     loc=(22, 40),
#     goal=(6, 10),
#     width=57,
#     landmark_dists=estimated_distance[1]
# )
#
# true = shortest_path_distance(
#     loc=(22, 40),
#     goal=(6, 10),
#     width=57)
#
#
# print(lower)
# print(true)

vertex_ids = [0, 1023, 930, 95, 496, 544, 18, 631, 1009, 744, 230, 314, 1011, 543, 735, 608, 489, 596, 194, 241]
true_coords = []
for id in vertex_ids:
    row = id//32
    col = id%32
    true_coords.append((row, col))
print(true_coords)