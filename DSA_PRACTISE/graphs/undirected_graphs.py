vertexData = ['A', 'B', 'C', 'D']

adjacency_matrix = [
    [0,1,1,1],
    [1,0,1,0],
    [1,1,0,0],
    [1,0,0,0]
]

def print_adjacency_matrix(matrix):
    print("\nAdjacency Matrix: ")
    for row in matrix:
        print(row)

print('VertexData: ', vertexData)
print_adjacency_matrix(adjacency_matrix)

def print_connections(matrix, vertices):
    print("\nConnections for each vertex: ")
    for i in range(len(vertices)):
        print(f"{vertices[i]}: ", end = "")
        for j in range(len(vertices)):
            if matrix[i][j]:
                print(vertices[j], end = " ")
        print()#prints a new line

print_connections(adjacency_matrix, vertexData)