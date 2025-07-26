#!/usr/bin/env python3
"""Test script for the calculator module."""

from calculator import Calculator


def test_calculator():
    calc = Calculator()
    
    print("Testing Calculator Functions:")
    print("="*40)
    
    # Test addition
    print("Testing addition: 5 + 3 =", calc.add(5, 3))
    assert calc.add(5, 3) == 8
    
    # Test subtraction
    print("Testing subtraction: 10 - 4 =", calc.subtract(10, 4))
    assert calc.subtract(10, 4) == 6
    
    # Test multiplication
    print("Testing multiplication: 6 * 7 =", calc.multiply(6, 7))
    assert calc.multiply(6, 7) == 42
    
    # Test division
    print("Testing division: 20 / 4 =", calc.divide(20, 4))
    assert calc.divide(20, 4) == 5
    
    # Test power function
    print("Testing power: 2 ^ 3 =", calc.power(2, 3))
    assert calc.power(2, 3) == 8
    print("Testing power: 5 ^ 2 =", calc.power(5, 2))
    assert calc.power(5, 2) == 25
    
    # Test division by zero protection
    print("\nTesting division by zero:")
    try:
        calc.divide(10, 0)
        print("ERROR: Division by zero should have raised an exception!")
    except ValueError as e:
        print(f"✓ Successfully caught division by zero: {e}")
    
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    test_calculator()