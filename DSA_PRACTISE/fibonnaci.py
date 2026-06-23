def fibonnaci_loop(n):
    prev0 = 0
    prev1 = 1

    print(f"the starting numbers, number one {prev0} , {prev1}")
    for fibonnaci in range(n):
        new_num = prev0 + prev1
        print(new_num)
        prev0 = prev1
        prev1 = new_num
        

count = 2
def fibonnaci_recursion_incremental(n):
    def fibo(n, prev1 = 0, prev2=1):
        global count
        if count <= n:
            newFib = prev1 + prev2
            print(newFib)
            prev1 = prev2
            prev2 = newFib
            count += 1
            fibo(n,prev1=prev1, prev2=prev2)
        else:
            return
    fibo(n)

def fibonnaci_decremental_recur(n):#to find the result of the nth number in a fibonnaci sequence
    if n<=1:
        return n
    else:
        return fibonnaci_decremental_recur(n-1) + fibonnaci_decremental_recur(n-2)
    
prompts  =["Enter your choice, 1 for fibonnaci with a loop and 2 for fibonnaci on recursion and 3 for finding the sequnce result for the nth value decrementely: ", "enter amount of times you wish the sequence to repat n: "]
choice = int(input(prompts[0]))
ceiling = int(input(prompts[1]))

if choice == 1:
    fibonnaci_loop(ceiling)
elif choice == 2:
    fibonnaci_recursion_incremental(ceiling)
elif choice == 3:
    print(fibonnaci_decremental_recur(ceiling)) 
else:
    None

