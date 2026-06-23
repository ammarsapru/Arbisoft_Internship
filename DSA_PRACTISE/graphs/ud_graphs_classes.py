class Graph:
    def __init__(self, size):
        #for a directed graph representation we replace 0 with None
        self.adj_matrix = [[0] * size for _ in range(size)]#multiplies [0] by the size, by the size, so if size is 4 we get
        #[0,0,0,0] first, and then three more times
        #so we get:
        #[0,0,0,0]
        #[0,0,0,0]
        #[0,0,0,0]
        #[0,0,0,0]
        self.size = size
        self.vertex_data = [''] * size #builds the following ['','','',''] if the size is 4

    def add_edge(self, u, v):# we add a weight parameter
        if 0 <= u < self.size and 0 <= v < self.size:
            self.adj_matrix[u][v] = 1 # we replace 1 with the weight
            self.adj_matrix[v][u] = 1# we also remove this line int the adjacency matrix, a edge only goes one way

    def add_vertex_data(self, vertex, data):
        if 0<= vertex < self.size:# the lhs checks if the vertex is non negative or atleast 0 and that vertex is within the bounds of the matrix
            self.vertex_data[vertex] = data
    
    def print_graph(self):
        print("Adjacency matrix:")
        for row in self.adj_matrix:
            print(' '.join(map(str,row)))
        print("\nVertex Data:")
        for vertex, data in enumerate(self.vertex_data):
            print(f"Vertex {vertex}: {data}")

            

g = Graph(4)
g.add_vertex_data(0, 'A')
g.add_vertex_data(1, 'B')
g.add_vertex_data(2, 'C')
g.add_vertex_data(3, 'D')
g.add_edge(0, 1)  # A - B
g.add_edge(0, 2)  # A - C
g.add_edge(0, 3)  # A - D
g.add_edge(1, 2)  # B - C

g.print_graph()