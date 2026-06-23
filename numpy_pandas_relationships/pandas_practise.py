#pandas has two main types
#1. data frame
#2. series - is a 1D labelled Data structure which is a 2D labeled data structure such as full spreadsheet or SQL table
import pandas as pd
#very good at representing 2 Dimensional Datas. ie rows and columns
df = pd.read_csv("orders.csv")#assigns indexes to each row

print(df)#prints the dataframe

#key features are label based indexing 
#columns wise and row-wise operations
#support for mixed data types
#fast vectorized operations, as it is built ontop of numpy which itself is built oin C allowing for vectorized operations and memory aspects

#can convert dictionaries into data frames

# data = {
#     'Name': ['Alic', 'Bob', 'Charlie'],
#     'Age': [25,30,15],
#     'Country': ['USA', 'Canada', 'UK']
# }

# df = pd.DataFrame(data)
# print(df)