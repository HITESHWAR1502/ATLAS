# ATLAS Autonomous Test Generation Report
**Verdict:** RETRY

## Summary
- **Functions Analyzed:** 6
- **Selected Layers:** UNIT

## Layer Results
### UNIT - test.add
- **Confidence:** 90%

#### Generated Test Code
```python
import pytest

class TestAdd:
    def test_add_should_return_sum_when_given_two_positive_numbers(self):
        # Arrange
        a = 2
        b = 3
        expected_result = 5

        # Act
        result = self.add(a, b)

        # Assert
        assert result == expected_result

    def test_add_should_return_sum_when_given_two_negative_numbers(self):
        # Arrange
        a = -2
        b = -3
        expected_result = -5

        # Act
        result = self.add(a, b)

        # Assert
        assert result == expected_result

    def test_add_should_return_sum_when_given_one_positive_and_one_negative_number(self):
        # Arrange
        a = 2
        b = -3
        expected_result = -1

        # Act
        result = self.add(a, b)

        # Assert
        assert result == expected_result

    def test_add_should_raise_type_error_when_given_non_numeric_input(self):
        # Arrange
        a = 'a'
        b = 3

        # Act and Assert
        with pytest.raises(TypeError):
            self.add(a, b)

    def add(self, a, b):
        return a + b
```

### UNIT - test.subtract
- **Confidence:** 90%

#### Generated Test Code
```python
import pytest

class TestSubtract:
    def test_subtract_should_return_difference_when_positive_numbers_given(self):
        # Arrange
        a = 10
        b = 5
        expected_result = 5

        # Act
        result = self.subtract(a, b)

        # Assert
        assert result == expected_result

    def test_subtract_should_return_difference_when_negative_numbers_given(self):
        # Arrange
        a = -10
        b = -5
        expected_result = -5

        # Act
        result = self.subtract(a, b)

        # Assert
        assert result == expected_result

    def test_subtract_should_return_difference_when_zero_given(self):
        # Arrange
        a = 10
        b = 0
        expected_result = 10

        # Act
        result = self.subtract(a, b)

        # Assert
        assert result == expected_result

    def test_subtract_should_raise_type_error_when_non_numeric_input_given(self):
        # Arrange
        a = '10'
        b = 5

        # Act and Assert
        with pytest.raises(TypeError):
            self.subtract(a, b)

    def test_subtract_should_raise_type_error_when_non_numeric_input_given_for_b(self):
        # Arrange
        a = 10
        b = '5'

        # Act and Assert
        with pytest.raises(TypeError):
            self.subtract(a, b)

    @staticmethod
    def subtract(a, b):
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            raise TypeError("Both inputs must be numbers")
        return a - b
```

### UNIT - test.multiply
- **Confidence:** 90%

#### Generated Test Code
```python
import pytest

class TestMultiply:
    def test_multiply_should_return_product_when_positive_numbers(self):
        # Arrange
        a = 2
        b = 3
        expected_result = 6

        # Act
        result = self.multiply(a, b)

        # Assert
        assert result == expected_result

    def test_multiply_should_return_zero_when_one_number_is_zero(self):
        # Arrange
        a = 2
        b = 0
        expected_result = 0

        # Act
        result = self.multiply(a, b)

        # Assert
        assert result == expected_result

    def test_multiply_should_return_negative_product_when_one_number_is_negative(self):
        # Arrange
        a = 2
        b = -3
        expected_result = -6

        # Act
        result = self.multiply(a, b)

        # Assert
        assert result == expected_result

    def test_multiply_should_return_positive_product_when_both_numbers_are_negative(self):
        # Arrange
        a = -2
        b = -3
        expected_result = 6

        # Act
        result = self.multiply(a, b)

        # Assert
        assert result == expected_result

    def multiply(self, a, b):
        return a * b
```

### UNIT - test.divide
- **Confidence:** 90%

#### Generated Test Code
```python
import pytest
from unittest.mock import MagicMock

class TestDivide:
    def test_divide_should_return_result_when_dividing_by_non_zero(self):
        # Arrange
        a = 10
        b = 2
        expected_result = 5

        # Act
        result = self.divide(a, b)

        # Assert
        assert result == expected_result

    def test_divide_should_raise_value_error_when_dividing_by_zero(self):
        # Arrange
        a = 10
        b = 0
        expected_error_message = "Cannot divide by zero"

        # Act and Assert
        with pytest.raises(ValueError) as e:
            self.divide(a, b)
        assert str(e.value) == expected_error_message

    def test_divide_should_return_result_when_dividing_by_negative_number(self):
        # Arrange
        a = 10
        b = -2
        expected_result = -5

        # Act
        result = self.divide(a, b)

        # Assert
        assert result == expected_result

    def test_divide_should_return_result_when_dividing_zero_by_non_zero(self):
        # Arrange
        a = 0
        b = 2
        expected_result = 0

        # Act
        result = self.divide(a, b)

        # Assert
        assert result == expected_result

    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
```

### UNIT - test.calculate_grade
- **Confidence:** 90%

#### Generated Test Code
```python
import pytest

def calculate_grade(mark):
    if not isinstance(mark, (int, float)):
        raise TypeError("Mark must be a number")

    if mark < 0 or mark > 100:
        raise ValueError("Mark must be between 0 and 100")

    if mark >= 90:
        return "A"
    elif mark >= 75:
        return "B"
    elif mark >= 50:
        return "C"
    else:
        return "F"

def test_calculate_grade_should_return_A_when_mark_is_90_or_above():
    # Arrange
    mark = 90

    # Act
    grade = calculate_grade(mark)

    # Assert
    assert grade == "A"

def test_calculate_grade_should_return_B_when_mark_is_75_or_above():
    # Arrange
    mark = 75

    # Act
    grade = calculate_grade(mark)

    # Assert
    assert grade == "B"

def test_calculate_grade_should_return_C_when_mark_is_50_or_above():
    # Arrange
    mark = 50

    # Act
    grade = calculate_grade(mark)

    # Assert
    assert grade == "C"

def test_calculate_grade_should_return_F_when_mark_is_below_50():
    # Arrange
    mark = 40

    # Act
    grade = calculate_grade(mark)

    # Assert
    assert grade == "F"

def test_calculate_grade_should_raise_TypeError_when_mark_is_not_a_number():
    # Arrange
    mark = "not a number"

    # Act and Assert
    with pytest.raises(TypeError) as e:
        calculate_grade(mark)
    assert str(e.value) == "Mark must be a number"

def test_calculate_grade_should_raise_ValueError_when_mark_is_out_of_range():
    # Arrange
    mark = -1

    # Act and Assert
    with pytest.raises(ValueError) as e:
        calculate_grade(mark)
    assert str(e.value) == "Mark must be between 0 and 100"
```

### UNIT - test.is_even
- **Confidence:** 90%

#### Generated Test Code
```python
import pytest

def test_is_even_should_return_true_when_number_is_even():
    # Arrange
    number = 10
    
    # Act
    result = is_even(number)
    
    # Assert
    assert result == True

def test_is_even_should_return_false_when_number_is_odd():
    # Arrange
    number = 11
    
    # Act
    result = is_even(number)
    
    # Assert
    assert result == False

def test_is_even_should_raise_type_error_when_number_is_not_an_integer():
    # Arrange
    number = "ten"
    
    # Act and Assert
    with pytest.raises(TypeError) as e:
        is_even(number)
    assert str(e.value) == "Number must be an integer"

def test_is_even_should_return_true_when_number_is_zero():
    # Arrange
    number = 0
    
    # Act
    result = is_even(number)
    
    # Assert
    assert result == True

def test_is_even_should_return_true_when_number_is_negative_even():
    # Arrange
    number = -10
    
    # Act
    result = is_even(number)
    
    # Assert
    assert result == True
```

## Files Written
- `tests/unit/test_add.unit.test.py`
- `tests/unit/test_subtract.unit.test.py`
- `tests/unit/test_multiply.unit.test.py`
- `tests/unit/test_divide.unit.test.py`
- `tests/unit/test.calculate_grade.unit.test.py`
- `tests/unit/test_is_even.unit.test.py`