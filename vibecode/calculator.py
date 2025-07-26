#!/usr/bin/env python3
"""Simple calculator with basic operations and command-line interface."""


class Calculator:
    """A simple calculator class with basic arithmetic operations."""
    
    def add(self, a, b):
        """Add two numbers."""
        return a + b
    
    def subtract(self, a, b):
        """Subtract b from a."""
        return a - b
    
    def multiply(self, a, b):
        """Multiply two numbers."""
        return a * b
    
    def divide(self, a, b):
        """Divide a by b with zero division validation."""
        if b == 0:
            raise ValueError("Cannot divide by zero!")
        return a / b
    
    def power(self, a, b):
        """Raise a to the power of b."""
        return a ** b


def main():
    """Simple command-line interface for the calculator."""
    calc = Calculator()
    
    print("Welcome to Simple Calculator!")
    print("Available operations: add, subtract, multiply, divide, power, quit")
    
    while True:
        print("\n" + "="*40)
        operation = input("Enter operation (or 'quit' to exit): ").strip().lower()
        
        if operation == 'quit':
            print("Thank you for using the calculator!")
            break
        
        if operation not in ['add', 'subtract', 'multiply', 'divide', 'power']:
            print("Invalid operation. Please choose from: add, subtract, multiply, divide, power")
            continue
        
        try:
            # Get numbers from user
            num1 = float(input("Enter first number: "))
            num2 = float(input("Enter second number: "))
            
            # Perform the operation
            if operation == 'add':
                result = calc.add(num1, num2)
                print(f"{num1} + {num2} = {result}")
            elif operation == 'subtract':
                result = calc.subtract(num1, num2)
                print(f"{num1} - {num2} = {result}")
            elif operation == 'multiply':
                result = calc.multiply(num1, num2)
                print(f"{num1} * {num2} = {result}")
            elif operation == 'divide':
                result = calc.divide(num1, num2)
                print(f"{num1} / {num2} = {result}")
            elif operation == 'power':
                result = calc.power(num1, num2)
                print(f"{num1} ^ {num2} = {result}")
                
        except ValueError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()