my_array = [64, 34, 25, 12, 22, 11, 90, 5]

n = len(my_array)

for i in range( n-1): #time complexity is O(n^2)
    swapped = False
    #note that in the range function when the stop parameter is lesser then the start parameter which by default is  zero, it skips without braking
    for j in range(n - i - 1):#starts from the first element of the list and compares every element as it goes, until it reaches n 
        if my_array[j] > my_array[j+1]:#comparing two elements side by side
            my_array[j],my_array[j+1] = my_array[j+1], my_array[j]
            #python reads the right side first, and stores those values in a tuple meaning it would store
            #j+1 and j and their values in a tuple that is temporary (j+1,j) and then swaps the values
            #same as using a temp variable difference is negligible 
            swapped = True
    if not swapped:
        break
print(f"sorted array: {my_array} ")             