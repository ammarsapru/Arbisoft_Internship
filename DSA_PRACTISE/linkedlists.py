class Node:#simple linked lists
    def __init__(self,data):
        self.data = data
        self.next = None
    
node1 = Node(3)
node2 = Node(5)
node3 = Node(13)
node4 = Node(2)

node1.next  = node2
node2.next = node3
node3.next = node4

# to make this a circular linked list we would specify
#node4.next = node1
#print the current node data ending with ->
#move to next on the current node
#set a while loop to run until the end of the loop as long as currentnode.data and startnode.data not equal

currentNode = node1
while currentNode:
    print(currentNode.data, end=" -> ")
    currentNode = currentNode.next
print("null")

class doubly_Node:
    def __init__(self,data):
        self.data = data
        self.next = None
        self.prev = None

node11 = doubly_Node(22)
node22 = doubly_Node(33)
node33 = doubly_Node(44)
node44 = doubly_Node(55)

node11.next = node22
node22.prev = node11

node22.next = node33
node33.prev = node22

node33.next = node44
node44.prev = node33

print(f"traversing forward: ")
start_node = node11
while start_node:
    print(f" {start_node.data} ->")
    start_node = start_node.next
print("null")

print("traversing backwards")
end_node = node44
while end_node:
    print(f"  {end_node.data} ", end=" -> ")
    end_node = end_node.prev
print("null")