my_array = [64, 34, 25, 12, 22, 11, 90, 5]
#if i is at 34 , j would start at 25 and move ffrom there till the end of the list.
n = len(my_array)

for i in range(0,n-1):#range function goes upto but not including the last element of the list
    min_index = i
    for j in range(i+1, n):#starts one ahead of the i
        if my_array[j] <  my_array[min_index]:#comparing one element against all other elements in the list, except for the element we are comparing against
            min_index = j
    min_value = my_array.pop(min_index)#each pop also requires the function to shift elements to the right, and if no argument or index specified inserts in the end of the list
    my_array.insert(i, min_value)#.insert takes two argument the index to insert if none specifed inserts to start of lise
    #it also pushes all other elements to the right once - O(n)

# time complexity comparison:
# pop+insert outside inner loop: O(n) x (O(n) + O(n) + O(n)) = O(n) x O(n) = O(n^2)
# pop+insert inside inner loop:  O(n) x O(n) x (O(n) + O(n)) = O(n) x O(n) x O(n) = O(n^3)
# constants are dropped in Big O: if outer loop runs n times and inner runs 5 times = 5n = O(n)

print(my_array)
#due to the shifting problem we have a alternate solution where we swap the elements position
my_array_two = [11,2,33,45,6,7,100,50]

n2= len(my_array_two)

for i in range(0, n2 - 1):
    min_index_two = i
    for j in range(i+1,n2):
        if my_array_two[j] < my_array_two[min_index_two]:
            min_index_two = j
    #i is the min index being compared against, we go through the list with j, where we find that the value at min index is greater then j, we set the min index to j
    my_array_two[i], my_array_two[min_index_two] = my_array_two[min_index_two] , my_array_two[i]
    #we then swap the pointer of j with the pointer of i which is the min index

print(my_array_two)

#time complexity of selection sort is also O(n^2)



