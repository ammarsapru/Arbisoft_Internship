/* ============================================================
   SAMPLE SCHEMA: 12 Tables
   - 10 "normal" tables, mostly linked by 1:M relationships
   - EmployeeBadges  -> demonstrates 1:1   (with Employees)
   - OrderProducts   -> demonstrates M:M   (junction between Orders and Products)
   ============================================================ */

-- Create the database if it doesn't already exist, then switch to it
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'Relationships')
BEGIN
    CREATE DATABASE Relationships;
END
GO

USE Relationships;
GO

-- Drop tables if they already exist (children first, to respect FK order)
IF OBJECT_ID('dbo.OrderProducts', 'U') IS NOT NULL DROP TABLE dbo.OrderProducts;
IF OBJECT_ID('dbo.EmployeeBadges', 'U') IS NOT NULL DROP TABLE dbo.EmployeeBadges;
IF OBJECT_ID('dbo.Orders', 'U') IS NOT NULL DROP TABLE dbo.Orders;
IF OBJECT_ID('dbo.Products', 'U') IS NOT NULL DROP TABLE dbo.Products;
IF OBJECT_ID('dbo.Employees', 'U') IS NOT NULL DROP TABLE dbo.Employees;
IF OBJECT_ID('dbo.Categories', 'U') IS NOT NULL DROP TABLE dbo.Categories;
IF OBJECT_ID('dbo.Suppliers', 'U') IS NOT NULL DROP TABLE dbo.Suppliers;
IF OBJECT_ID('dbo.Departments', 'U') IS NOT NULL DROP TABLE dbo.Departments;
IF OBJECT_ID('dbo.Customers', 'U') IS NOT NULL DROP TABLE dbo.Customers;
IF OBJECT_ID('dbo.OrderStatus', 'U') IS NOT NULL DROP TABLE dbo.OrderStatus;
IF OBJECT_ID('dbo.ShippingMethods', 'U') IS NOT NULL DROP TABLE dbo.ShippingMethods;
IF OBJECT_ID('dbo.Warehouses', 'U') IS NOT NULL DROP TABLE dbo.Warehouses;
GO

/* ============================================================
   1. Departments  (parent table, no FKs)
   ============================================================ */
CREATE TABLE Departments (
    DepartmentID INT IDENTITY(1,1) PRIMARY KEY,
    DepartmentName VARCHAR(100) NOT NULL
);
GO

/* ============================================================
   2. Employees  (1:M -> Departments: one department has many employees)
   ============================================================ */
CREATE TABLE Employees (
    EmployeeID INT IDENTITY(1,1) PRIMARY KEY,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    HireDate DATE NOT NULL,
    DepartmentID INT NOT NULL,
    CONSTRAINT FK_Employees_Departments FOREIGN KEY (DepartmentID)
        REFERENCES Departments(DepartmentID)
);
GO

/* ============================================================
   3. EmployeeBadges  ***1:1 relationship with Employees***
      Each employee has exactly one badge; each badge belongs to exactly
      one employee. The UNIQUE constraint on EmployeeID is what enforces
      the "1" side instead of allowing many badges per employee.
   ============================================================ */
CREATE TABLE EmployeeBadges (
    BadgeID INT IDENTITY(1,1) PRIMARY KEY,
    EmployeeID INT NOT NULL UNIQUE,        -- UNIQUE = the 1:1 enforcement
    BadgeNumber VARCHAR(20) NOT NULL,
    IssueDate DATE NOT NULL,
    CONSTRAINT FK_EmployeeBadges_Employees FOREIGN KEY (EmployeeID)
        REFERENCES Employees(EmployeeID)
);
GO

/* ============================================================
   4. Customers  (parent table, no FKs)
   ============================================================ */
CREATE TABLE Customers (
    CustomerID INT IDENTITY(1,1) PRIMARY KEY,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    Email VARCHAR(100) NOT NULL,
    Phone VARCHAR(20) NULL
);
GO

/* ============================================================
   5. OrderStatus  (lookup table, no FKs)
   ============================================================ */
CREATE TABLE OrderStatus (
    OrderStatusID INT IDENTITY(1,1) PRIMARY KEY,
    StatusName VARCHAR(30) NOT NULL
);
GO

/* ============================================================
   6. ShippingMethods  (lookup table, no FKs)
   ============================================================ */
CREATE TABLE ShippingMethods (
    ShippingMethodID INT IDENTITY(1,1) PRIMARY KEY,
    MethodName VARCHAR(50) NOT NULL,
    Cost DECIMAL(10,2) NOT NULL
);
GO

/* ============================================================
   7. Orders  (1:M -> Customers, 1:M -> OrderStatus, 1:M -> ShippingMethods,
               1:M -> Employees: one employee can process many orders)
   ============================================================ */
CREATE TABLE Orders (
    OrderID INT IDENTITY(1,1) PRIMARY KEY,
    CustomerID INT NOT NULL,
    OrderStatusID INT NOT NULL,
    ShippingMethodID INT NOT NULL,
    EmployeeID INT NOT NULL,
    OrderDate DATE NOT NULL,
    CONSTRAINT FK_Orders_Customers FOREIGN KEY (CustomerID)
        REFERENCES Customers(CustomerID),
    CONSTRAINT FK_Orders_OrderStatus FOREIGN KEY (OrderStatusID)
        REFERENCES OrderStatus(OrderStatusID),
    CONSTRAINT FK_Orders_ShippingMethods FOREIGN KEY (ShippingMethodID)
        REFERENCES ShippingMethods(ShippingMethodID),
    CONSTRAINT FK_Orders_Employees FOREIGN KEY (EmployeeID)
        REFERENCES Employees(EmployeeID)
);
GO

/* ============================================================
   8. Suppliers  (parent table, no FKs)
   ============================================================ */
CREATE TABLE Suppliers (
    SupplierID INT IDENTITY(1,1) PRIMARY KEY,
    SupplierName VARCHAR(100) NOT NULL,
    ContactEmail VARCHAR(100) NULL
);
GO

/* ============================================================
   9. Categories  (parent table, no FKs)
   ============================================================ */
CREATE TABLE Categories (
    CategoryID INT IDENTITY(1,1) PRIMARY KEY,
    CategoryName VARCHAR(50) NOT NULL
);
GO

/* ============================================================
   10. Warehouses  (parent table, no FKs)
   ============================================================ */
CREATE TABLE Warehouses (
    WarehouseID INT IDENTITY(1,1) PRIMARY KEY,
    WarehouseName VARCHAR(100) NOT NULL,
    Location VARCHAR(150) NOT NULL
);
GO

/* ============================================================
   11. Products  (1:M -> Suppliers, 1:M -> Categories, 1:M -> Warehouses)
   ============================================================ */
CREATE TABLE Products (
    ProductID INT IDENTITY(1,1) PRIMARY KEY,
    ProductName VARCHAR(100) NOT NULL,
    Price DECIMAL(10,2) NOT NULL,
    SupplierID INT NOT NULL,
    CategoryID INT NOT NULL,
    WarehouseID INT NOT NULL,
    CONSTRAINT FK_Products_Suppliers FOREIGN KEY (SupplierID)
        REFERENCES Suppliers(SupplierID),
    CONSTRAINT FK_Products_Categories FOREIGN KEY (CategoryID)
        REFERENCES Categories(CategoryID),
    CONSTRAINT FK_Products_Warehouses FOREIGN KEY (WarehouseID)
        REFERENCES Warehouses(WarehouseID)
);
GO

/* ============================================================
   12. OrderProducts  ***M:M relationship between Orders and Products***
       An order can contain many products, and a product can appear on
       many orders. The composite primary key (OrderID, ProductID) is
       what makes this a true M:M junction table.
   ============================================================ */
CREATE TABLE OrderProducts (
    OrderID INT NOT NULL,
    ProductID INT NOT NULL,
    Quantity INT NOT NULL,
    UnitPriceAtOrder DECIMAL(10,2) NOT NULL,
    CONSTRAINT PK_OrderProducts PRIMARY KEY (OrderID, ProductID),
    CONSTRAINT FK_OrderProducts_Orders FOREIGN KEY (OrderID)
        REFERENCES Orders(OrderID),
    CONSTRAINT FK_OrderProducts_Products FOREIGN KEY (ProductID)
        REFERENCES Products(ProductID)
);
GO

/* ============================================================
   Summary of relationships created:
   ------------------------------------------------------------
   1:M  Departments      -> Employees
   1:1  Employees        -> EmployeeBadges   (UNIQUE FK enforces 1:1)
   1:M  Customers        -> Orders
   1:M  OrderStatus      -> Orders
   1:M  ShippingMethods  -> Orders
   1:M  Employees        -> Orders
   1:M  Suppliers        -> Products
   1:M  Categories       -> Products
   1:M  Warehouses       -> Products
   M:M  Orders <-> Products  (via OrderProducts junction table)
   ============================================================ */