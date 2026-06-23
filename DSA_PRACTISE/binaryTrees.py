class TreeNode: 
    def __init__(self,data):
        self.data = data
        self.left = None
        self.right = None
 
root = TreeNode('R')
nodeA = TreeNode('A')
nodeB = TreeNode('B')
nodeC = TreeNode('C')
nodeD = TreeNode('D')
nodeE = TreeNode('E')
nodeF = TreeNode('F')
nodeG = TreeNode('G')

root.left = nodeA
root.right = nodeB

nodeA.left = nodeC
nodeA.right = nodeD

nodeB.left = nodeE
nodeB.right = nodeF

nodeF.left = nodeG

print("root.right.left.data:", root.right.left.data)
#root.right.left.data: E

def preOrderTraversal(node):
    if node is None:
        return
    print(node.data, end = ",")
    preOrderTraversal(node.left)
    preOrderTraversal(node.right)

preOrderTraversal(root)
#output
# R,A,C,D,B,E,F,G,

def inOrderTraversal(node):
    if node is None:
        return
    inOrderTraversal(node.left)
    print(node.data, end = ", ")
    inOrderTraversal(node.right)