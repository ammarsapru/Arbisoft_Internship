# Arbisoft Internship

## Overview

This repository contains work completed during an internship at Arbisoft. The internship focuses on building foundational knowledge in Artificial Intelligence and Machine Learning, covering core concepts, algorithms, and practical implementations.

## Internship Scope

The internship covers AI/ML basics, including but not limited to:

- Fundamentals of machine learning
- Data structures and algorithms relevant to AI/ML
- Algorithm complexity and performance analysis
- Graph theory and traversal algorithms
- Sorting and searching algorithms
- Data manipulation and analysis with NumPy and Pandas
- Relational database design and SQL table relationships

## Repository Structure

### DSA_PRACTISE

This folder contains implementations of core data structures and algorithms in Python. These serve as the foundation for understanding how AI/ML algorithms work under the hood.

**Sorting Algorithms**
- Bubble Sort
- Selection Sort
- Insertion Sort
- Merge Sort
- Quick Sort

**Data Structures**
- Linked Lists
- Binary Trees

**Graph Algorithms**
- Undirected graphs using adjacency matrix
- Depth First Search (DFS)
- DFS on directed graphs
- Cyclic detection
- Dijkstra's algorithm (directed and undirected)

**Other**
- Fibonacci sequence implementations

### numpy_pandas_relationships

This folder covers data manipulation with NumPy and Pandas alongside relational database design in SQL.

**NumPy** (`numpy_tutorial.ipynb`)
- Array creation, data types, and memory layout
- Multi-dimensional arrays — shape, ndim, indexing, and slicing
- Element-wise operations, broadcasting, and scalar arithmetic
- Reshaping, flattening, transposing, and concatenation
- Axis-based aggregations (sum, mean, std) across 1D, 2D, and 3D arrays
- Linear algebra — dot product, determinant, inverse, eigenvalues
- Practical examples: image brightness simulation and student score analysis

**Pandas** (`Untitled-1.ipynb`, `pandas_practise.py`)
- DataFrames and Series — loading CSV data with `pd.read_csv`
- DataFrame exploration — `head`, `tail`, `info`, `describe`, `columns`, `index`
- Column selection, `iloc` row access, and boolean filtering

**SQL Relationships** (`relationships.sql`, `many_to_many.sql`)
- 12-table SQL Server schema demonstrating all relationship types
- One-to-One (1:1) — enforced via a `UNIQUE` foreign key
- One-to-Many (1:M) — e.g., Departments → Employees, Customers → Orders
- Many-to-Many (M:M) — Orders ↔ Products via a junction table

**Sample Data** (`orders.csv`)
- 40-row synthetic e-commerce dataset used across the Pandas exercises
