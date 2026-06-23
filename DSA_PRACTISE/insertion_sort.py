my_array = [64, 34, 25, 12, 22, 11, 90, 5]
#
n = len(my_array)

for i in range(1,n):#skipping the first element
    insert_index = i
    current_value = my_array.pop(i)#both the pop and the insert require the shifting of elements so it takes longer although time complexity in the worst case might be the same 
    # we can do the shift manually
    #inner loop only goes over the sorted part of the list, -1 is needed to include the last element from that side, and -1 walks back
    for j in range(i-1, -1, -1):#the last argument in the range function, is the step, it walks backwards
        if my_array[j] > current_value:
            insert_index = j
        my_array.insert(insert_index, current_value)

# a better implementation
for i in range(1,n):
    insert_index = i
    # if the list is 16,5,12,4,3
    # then i is at 1 -> 5
    #and j is at (1-1) -> 16
    #is value is stored in current value -cv
    #we replace the value at j+1 which in this case is i \
    #we then have  16,16,12..
    #but our current replacement index is j->16 and we have it point to current value 5
    # so it becomes 5,16,12\
    #i would point to 12, we know that it j would be i-1 so 16 swap
    #then we have 5,12,16,4,3
    #i -> 4, j-> 16 and then swap, then a second check that happens before as well
    # cv is still 4 but j has moved one step back, so before where it pointed at what is now 4 previously 16
    # it now points at 12 same thing happens, cv still is 4 j moves one step back to look at 5 and then a swap
    #leading to 4,5,12,16
    current_value = my_array[i]
    for j in range(i-1, -1, -1):
        if my_array[j] > current_value:
            my_array[j+1] = my_array[j]#manual shift we essentially move the elment at j to the next index
            insert_index = j
        else:
            break
    my_array[insert_index] = current_value
