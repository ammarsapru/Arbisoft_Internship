def mergesort(arr):#this is a implementation with recursion
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    leftHalf = arr[:mid]
    rightHalf = arr[mid:]

    sortedLeft = mergesort(leftHalf)
    sortedRight = mergesort(rightHalf)

    return merge(sortedLeft, sortedRight)

def mergeSort_w_recur(arr):#if list is [12,3,4,8,9,11]
    step = 1
    length = len(arr)# length becomes 6

    while step < length : #step has to stay below six
        for i in range(0, length, 2*step):#runs from start of list till the end, and step is 2* step, so as step is 1 on the first iteration it goes
            #1,2,4,8 -> with 8 exceeding the length of the list and hence 4 would be the last value of step that is valid
            left = arr[i: i+step]# on the first ieration gets the first element
            right = arr[i+1: i +step*2]#on the first iteration gets starting from the second element and where i is zero plus 2 so it gets the second element

            merged = merge(left,right)
            #then it calls the merge function on those two elements and that sorts them
            for j, val in enumerate(merged):#enumerate gives both the index and the value of the merged list
                arr[i+j] = val #writes the sorted merged values back into the original array at the correct position
        step *= 2 #doubles the step so next iteration merges larger subarrays
    return arr #returns the now fully sorted array

def merge(left, right):
    result = []

    i =  j =0

    while i < len(left) and j < len(right):
        if left[i] < right[j]:
            result.append(left[i])
            i +=1
        else:
            result.append(right[j])
            j+=1
    result.extend(left[i:])
    result.extend(right[j:])

    return result

unsortedArray = [3,7,6,-10,15,23.5,55,-13]
sortedArray = mergesort(unsortedArray)
print(f"Sorted Array: {sortedArray}")
